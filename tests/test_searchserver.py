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
    _, _, config, tavily = import_searchserver()
    module = types.SimpleNamespace(
        tavily_search_keys=["tvly-one", "tvly-two"],
        tavily_search_url="https://api.tavily.com/search",
    )

    providers = config.load_provider_configs(module, provider_classes={"tavily": tavily.TavilyProvider})

    assert providers["tavily"].keys == ["tvly-one", "tvly-two"]
    assert providers["tavily"].url == "https://api.tavily.com/search"
    assert providers["tavily"].type == "国外数据全能"


def test_search_falls_back_to_next_provider_after_failure():
    searchserver, base, _, _ = import_searchserver()

    class FailingProvider(base.SearchProvider):
        name = "failing"

        type = "国内数据全能"

        def search(self, query, result_count):
            raise base.ProviderError("temporary failure")

    class WorkingProvider(base.SearchProvider):
        name = "working"
        type = "国外数据全能"

        def search(self, query, result_count):
            assert result_count == 7
            return base.success_payload("working", query, [{"title": "ok", "url": "https://example.com"}])

    result = searchserver.search("generic agent", 7, providers=[FailingProvider(), WorkingProvider()])

    assert result["status"] == "success"
    assert result["provider"] == "working"
    assert result["query"] == "generic agent"
    assert result["results"][0]["title"] == "ok"


def test_search_reports_all_provider_errors_when_all_fail():
    searchserver, base, _, _ = import_searchserver()

    class FirstProvider(base.SearchProvider):
        name = "first"
        type = "国内新闻"

        def search(self, query, result_count):
            raise base.ProviderError("bad key")

    class SecondProvider(base.SearchProvider):
        name = "second"
        type = "国外新闻"

        def search(self, query, result_count):
            raise RuntimeError("rate limited")

    result = searchserver.search("generic agent", 5, providers=[FirstProvider(), SecondProvider()])

    assert result["status"] == "error"
    assert result["query"] == "generic agent"
    assert result["msg"] == "first: bad key\nsecond: rate limited"
    assert result["provider_errors"] == [
        {"provider": "first", "error": "bad key"},
        {"provider": "second", "error": "rate limited"},
    ]


def test_search_prioritizes_provider_type_for_news_queries():
    searchserver, base, _, _ = import_searchserver()

    class GeneralProvider(base.SearchProvider):
        name = "general"
        type = "国外数据全能"

        def search(self, query, result_count):
            return base.success_payload("general", query, [{"title": "general", "url": "https://example.com"}])

    class NewsProvider(base.SearchProvider):
        name = "news"
        type = "国外新闻"

        def search(self, query, result_count):
            return base.success_payload("news", query, [{"title": "news", "url": "https://example.com"}])

    result = searchserver.search("latest AI news", 5, providers=[GeneralProvider(), NewsProvider()])

    assert result["provider"] == "news"


def test_search_reports_discovery_errors_as_all_failed_payload(monkeypatch):
    searchserver, _, _, _ = import_searchserver()

    def broken_discovery(provider_names=None, provider_types=None):
        raise RuntimeError("bad provider import")

    monkeypatch.setattr(searchserver.registry, "build_providers", broken_discovery)

    result = searchserver.search("generic agent", 5)

    assert result["status"] == "error"
    assert result["query"] == "generic agent"
    assert result["msg"] == "searchserver: bad provider import"
    assert result["provider_errors"] == [{"provider": "searchserver", "error": "bad provider import"}]


def test_registry_build_providers_supports_default_and_explicit_selection(monkeypatch):
    searchserver, base, _, tavily = import_searchserver()

    class FakeProvider(base.SearchProvider):
        name = "fake"
        type = "国内数据全能"

        def __init__(self, config):
            self.config = config

        def search(self, query, result_count):
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

    providers, unavailable = searchserver.registry.build_providers(provider_types=["国外数据全能"], configs=configs)
    assert [provider.name for provider in providers] == ["tavily"]
    assert unavailable == []


def test_tavily_strategy_configs_reuse_tavily_key_variables():
    _, _, config, tavily = import_searchserver()
    module = types.SimpleNamespace(
        tavily_search_keys=["tvly-one"],
        tavily_search_url="https://api.tavily.com/search",
    )
    provider_classes = {
        "tavily": tavily.TavilyProvider,
        "tavily_deep": tavily.TavilyDeepProvider,
        "tavily_news": tavily.TavilyNewsProvider,
        "tavily_finance": tavily.TavilyFinanceProvider,
    }

    providers = config.load_provider_configs(module, provider_classes=provider_classes)

    assert set(providers) == {"tavily", "tavily_deep", "tavily_news", "tavily_finance"}
    assert {cfg.url for cfg in providers.values()} == {"https://api.tavily.com/search"}
    assert {tuple(cfg.keys) for cfg in providers.values()} == {("tvly-one",)}
    assert providers["tavily_deep"].type == "国外深度数据"
    assert providers["tavily_news"].type == "国外新闻"
    assert providers["tavily_finance"].type == "国外金融"


def test_registry_rejects_provider_without_type(monkeypatch):
    searchserver, base, _, _ = import_searchserver()

    class UntypedProvider(base.SearchProvider):
        name = "untyped"

        def __init__(self, config):
            self.config = config

        def search(self, query, result_count):
            return base.success_payload("untyped", query, [])

    monkeypatch.setattr(searchserver.registry, "discover_provider_classes", lambda: {"untyped": UntypedProvider})
    configs = {"untyped": base.ProviderConfig(name="untyped", keys=["k"], url="https://example.com/search")}

    providers, unavailable = searchserver.registry.build_providers(configs=configs)
    assert providers == []
    assert unavailable == [{"provider": "untyped", "error": "missing provider type"}]


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

    result = provider.search("latest AI search", 80)

    assert [call[2]["Authorization"] for call in calls] == ["Bearer tvly-bad", "Bearer tvly-good"]
    assert [call[1]["max_results"] for call in calls] == [20, 20]
    assert result["status"] == "success"
    assert result["provider"] == "tavily"
    assert result["query"] == "latest AI search"
    assert result["results"] == [
        {"title": "Result", "url": "https://example.com", "content": "Snippet", "score": 0.9}
    ]


def test_tavily_strategy_providers_set_advanced_news_and_finance_parameters():
    _, base, _, tavily = import_searchserver()
    payloads = []

    def fake_post(url, payload, headers, timeout):
        payloads.append(payload)
        return {"results": [{"title": payload["query"], "url": "https://example.com"}]}

    config = base.ProviderConfig(name="tavily", keys=["tvly-good"], url="https://api.tavily.com/search")
    providers = [
        tavily.TavilyDeepProvider(config, http_post=fake_post),
        tavily.TavilyNewsProvider(config, http_post=fake_post),
        tavily.TavilyFinanceProvider(config, http_post=fake_post),
    ]

    for provider in providers:
        provider.search("latest AI search", 3)

    assert payloads == [
        {"query": "latest AI search", "search_depth": "advanced", "max_results": 3, "chunks_per_source": 3},
        {"query": "latest AI search", "search_depth": "basic", "max_results": 3, "topic": "news"},
        {"query": "latest AI search", "search_depth": "basic", "max_results": 3, "topic": "finance"},
    ]


def test_tavily_post_json_uses_api_error_detail(monkeypatch):
    _, base, _, tavily = import_searchserver()

    class FakeResponse:
        def raise_for_status(self):
            raise tavily.requests.HTTPError("400 Bad Request")

        def json(self):
            return {"detail": {"error": "Invalid topic. Must be 'general' or 'news'."}}

    monkeypatch.setattr(tavily.requests, "post", lambda *args, **kwargs: FakeResponse())

    with pytest.raises(base.ProviderError) as exc:
        tavily._post_json("https://api.tavily.com/search", {}, {}, 15)

    assert str(exc.value) == "Invalid topic. Must be 'general' or 'news'."


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
        provider.search("generic agent", 5)

    assert "tvly-one" not in str(exc.value)
    assert "tvly-two" not in str(exc.value)
    assert "key 1" in str(exc.value)
    assert "key 2" in str(exc.value)
