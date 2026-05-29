import json

import pytest

from agent_loop import BaseHandler


def test_tool_schemas_expose_exactly_one_provider_neutral_search_tool():
    schema_paths = ["assets/tools_schema.json", "assets/tools_schema_cn.json"]
    for path in schema_paths:
        tools = json.load(open(path, "r", encoding="utf-8"))
        names = [tool["function"]["name"] for tool in tools]
        search_names = [name for name in names if "search" in name]
        assert search_names == ["web_search"], (path, search_names)

        web_search = next(tool for tool in tools if tool["function"]["name"] == "web_search")
        properties = web_search["function"]["parameters"]["properties"]
        assert set(properties) == {"keyword"}


class FakeParent:
    task_dir = None


def test_web_search_dispatch_forwards_structured_success(monkeypatch):
    import ga

    def fake_search(keyword):
        assert keyword == "GenericAgent"
        return {
            "status": "success",
            "provider": "fake",
            "query": keyword,
            "results": [{"title": "GA", "url": "https://example.com"}],
        }

    monkeypatch.setattr(ga.searchserver, "search", fake_search)
    handler = ga.GenericAgentHandler(FakeParent())

    gen = BaseHandler.dispatch(handler, "web_search", {"keyword": "GenericAgent"}, "")
    chunks = []
    try:
        while True:
            chunks.append(next(gen))
    except StopIteration as stop:
        outcome = stop.value

    assert any("fake" in chunk for chunk in chunks)
    assert outcome.data["status"] == "success"
    assert outcome.data["provider"] == "fake"
    assert outcome.data["query"] == "GenericAgent"


def test_web_search_dispatch_accepts_query_alias(monkeypatch):
    import ga

    monkeypatch.setattr(
        ga.searchserver,
        "search",
        lambda keyword: {"status": "success", "provider": "fake", "query": keyword, "results": []},
    )
    handler = ga.GenericAgentHandler(FakeParent())

    gen = BaseHandler.dispatch(handler, "web_search", {"query": "alias"}, "")
    try:
        while True:
            next(gen)
    except StopIteration as stop:
        outcome = stop.value

    assert outcome.data["query"] == "alias"


def test_web_search_dispatch_returns_all_failed_payload(monkeypatch):
    import ga

    error_payload = {
        "status": "error",
        "msg": "无法搜索: all providers failed",
        "query": "GenericAgent",
        "provider_errors": [{"provider": "tavily", "error": "bad key"}],
    }
    monkeypatch.setattr(ga.searchserver, "search", lambda keyword: error_payload)
    handler = ga.GenericAgentHandler(FakeParent())

    gen = BaseHandler.dispatch(handler, "web_search", {"keyword": "GenericAgent"}, "")
    try:
        while True:
            next(gen)
    except StopIteration as stop:
        outcome = stop.value

    assert outcome.data == error_payload


def test_web_search_requires_keyword_or_query():
    import ga

    handler = ga.GenericAgentHandler(FakeParent())
    gen = BaseHandler.dispatch(handler, "web_search", {}, "")

    try:
        while True:
            next(gen)
    except StopIteration as stop:
        outcome = stop.value

    assert outcome.data["status"] == "error"
    assert "keyword" in outcome.data["msg"]


def test_web_search_coerces_non_string_keyword(monkeypatch):
    import ga

    monkeypatch.setattr(
        ga.searchserver,
        "search",
        lambda keyword: {"status": "success", "provider": "fake", "query": keyword, "results": []},
    )
    handler = ga.GenericAgentHandler(FakeParent())
    gen = BaseHandler.dispatch(handler, "web_search", {"keyword": 123}, "")

    try:
        while True:
            next(gen)
    except StopIteration as stop:
        outcome = stop.value

    assert outcome.data["status"] == "success"
    assert outcome.data["query"] == "123"
