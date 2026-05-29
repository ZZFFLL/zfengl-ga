import types

import pytest


def import_searchserver():
    try:
        import tools.searchserver as searchserver
        from tools.searchserver import base, config
        from tools.searchserver.providers import tavily
    except ModuleNotFoundError as exc:
        pytest.fail(f"searchserver package missing: {exc}")
    return searchserver, base, config, tavily


def test_config_reads_tavily_keys_and_endpoint_without_llm_config_names():
    _, _, config, _ = import_searchserver()
    module = types.SimpleNamespace(
        tavily_search_keys=["tvly-one", "tvly-two"],
        tavily_search_url="https://api.tavily.com/search",
    )

    providers = config.load_provider_configs(module)

    assert providers["tavily"].keys == ["tvly-one", "tvly-two"]
    assert providers["tavily"].url == "https://api.tavily.com/search"


def test_search_falls_back_to_next_provider_after_failure():
    searchserver, base, _, _ = import_searchserver()

    class FailingProvider(base.SearchProvider):
        name = "failing"

        def search(self, query):
            raise base.ProviderError("temporary failure")

    class WorkingProvider(base.SearchProvider):
        name = "working"

        def search(self, query):
            return base.success_payload("working", query, [{"title": "ok", "url": "https://example.com"}])

    result = searchserver.search("generic agent", providers=[FailingProvider(), WorkingProvider()])

    assert result["status"] == "success"
    assert result["provider"] == "working"
    assert result["query"] == "generic agent"
    assert result["results"][0]["title"] == "ok"


def test_search_reports_all_provider_errors_when_all_fail():
    searchserver, base, _, _ = import_searchserver()

    class FirstProvider(base.SearchProvider):
        name = "first"

        def search(self, query):
            raise base.ProviderError("bad key")

    class SecondProvider(base.SearchProvider):
        name = "second"

        def search(self, query):
            raise RuntimeError("rate limited")

    result = searchserver.search("generic agent", providers=[FirstProvider(), SecondProvider()])

    assert result["status"] == "error"
    assert result["query"] == "generic agent"
    assert "无法搜索" in result["msg"]
    assert result["provider_errors"] == [
        {"provider": "first", "error": "bad key"},
        {"provider": "second", "error": "rate limited"},
    ]


def test_search_reports_discovery_errors_as_all_failed_payload(monkeypatch):
    searchserver, _, _, _ = import_searchserver()

    def broken_discovery(provider_names=None):
        raise RuntimeError("bad provider import")

    monkeypatch.setattr(searchserver.registry, "build_providers", broken_discovery)

    result = searchserver.search("generic agent")

    assert result["status"] == "error"
    assert result["query"] == "generic agent"
    assert "无法搜索" in result["msg"]
    assert result["provider_errors"] == [{"provider": "searchserver", "error": "bad provider import"}]


def test_registry_build_providers_supports_default_and_explicit_selection(monkeypatch):
    searchserver, base, _, tavily = import_searchserver()

    class FakeProvider(base.SearchProvider):
        name = "fake"

        def __init__(self, config):
            self.config = config

        def search(self, query):
            return base.success_payload("fake", query, [{"title": "fake", "url": "https://fake.example"}])

    monkeypatch.setattr(
        searchserver.registry,
        "discover_provider_classes",
        lambda: {"fake": FakeProvider, "tavily": tavily.TavilyProvider},
    )
    configs = {
        "fake": base.ProviderConfig(name="fake", keys=["fake-key"], url="https://fake.example/search"),
        "tavily": base.ProviderConfig(name="tavily", keys=["tvly-one"], url="https://api.tavily.com/search"),
    }

    providers, unavailable = searchserver.registry.build_providers(configs=configs)
    assert [provider.name for provider in providers] == ["fake", "tavily"]
    assert unavailable == []

    providers, unavailable = searchserver.registry.build_providers(provider_names=["tavily"], configs=configs)
    assert [provider.name for provider in providers] == ["tavily"]
    assert unavailable == []


def test_tavily_provider_rotates_keys_and_normalizes_results():
    _, base, _, tavily = import_searchserver()
    calls = []

    def fake_post(url, payload, headers, timeout):
        calls.append((url, payload, headers, timeout))
        if headers["Authorization"] == "Bearer tvly-bad":
            raise base.ProviderError("unauthorized")
        return {
            "query": payload["query"],
            "results": [
                {"title": "Result", "url": "https://example.com", "content": "Snippet", "score": 0.9}
            ],
        }

    provider = tavily.TavilyProvider(
        base.ProviderConfig(
            name="tavily",
            keys=["tvly-bad", "tvly-good"],
            url="https://api.tavily.com/search",
        ),
        http_post=fake_post,
    )

    result = provider.search("latest AI search")

    assert [call[2]["Authorization"] for call in calls] == ["Bearer tvly-bad", "Bearer tvly-good"]
    assert result["status"] == "success"
    assert result["provider"] == "tavily"
    assert result["query"] == "latest AI search"
    assert result["results"] == [
        {"title": "Result", "url": "https://example.com", "content": "Snippet", "score": 0.9}
    ]


def test_tavily_provider_reports_key_failures_when_every_key_fails():
    _, base, _, tavily = import_searchserver()

    def fake_post(url, payload, headers, timeout):
        raise base.ProviderError(f"failed {headers['Authorization']}")

    provider = tavily.TavilyProvider(
        base.ProviderConfig(
            name="tavily",
            keys=["tvly-one", "tvly-two"],
            url="https://api.tavily.com/search",
        ),
        http_post=fake_post,
    )

    with pytest.raises(base.ProviderError) as exc:
        provider.search("generic agent")

    assert "tvly-one" not in str(exc.value)
    assert "tvly-two" not in str(exc.value)
    assert "key 1" in str(exc.value)
    assert "key 2" in str(exc.value)
