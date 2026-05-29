import pytest


def test_tavily_real_provider_smoke_when_configured():
    try:
        from tools.searchserver import config, search
    except ModuleNotFoundError as exc:
        pytest.fail(f"searchserver package missing: {exc}")

    providers = config.load_provider_configs()
    tavily = providers.get("tavily")
    if not tavily or not tavily.keys or not tavily.url:
        pytest.skip("Tavily smoke skipped: tavily_search_keys and tavily_search_url are not configured")

    result = search("GenericAgent autonomous agent framework", 5, provider_names=["tavily"])

    assert result["status"] == "success"
    assert result["provider"] == "tavily"
    assert result["query"] == "GenericAgent autonomous agent framework"
    assert isinstance(result["results"], list)
