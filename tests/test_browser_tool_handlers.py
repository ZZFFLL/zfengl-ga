import json
from types import SimpleNamespace

import ga
from ga import GenericAgentHandler


def run_generator(gen):
    chunks = []
    while True:
        try:
            chunks.append(next(gen))
        except StopIteration as stop:
            return chunks, stop.value


def make_handler():
    return GenericAgentHandler(SimpleNamespace(verbose=False, task_dir=None), [], "./temp")


def test_browser_state_wrapper_initializes_driver(monkeypatch):
    calls = []
    fake_driver = SimpleNamespace(default_session_id="9", get_all_sessions=lambda: [{"id": "9"}])

    def fake_init():
        calls.append("init")
        ga.driver = fake_driver

    class FakeLayer:
        def get_state(self, driver, **kwargs):
            return {"status": "success", "tab_id": driver.default_session_id, "elements": []}

    monkeypatch.setattr(ga, "driver", None)
    monkeypatch.setattr(ga, "first_init_driver", fake_init)
    monkeypatch.setattr(ga, "browser_action_layer", FakeLayer())

    result = ga.browser_state(max_elements=2)

    assert calls == ["init"]
    assert result == {"status": "success", "tab_id": "9", "elements": []}


def test_do_browser_state_formats_execution_output(monkeypatch):
    monkeypatch.setattr(
        ga,
        "browser_state",
        lambda **kwargs: {
            "status": "success",
            "tab_id": "7",
            "elements": [{"index": 1, "tag": "button", "text": "Login"}],
        },
    )
    handler = make_handler()

    chunks, outcome = run_generator(handler.do_browser_state({"max_elements": 10}, SimpleNamespace(content="")))

    assert "Browser state:" in "".join(chunks)
    data = json.loads(outcome.data)
    assert data["status"] == "success"
    assert data["elements"][0]["text"] == "Login"


def test_do_browser_state_forwards_tab_id_alias(monkeypatch):
    calls = []

    def fake_browser_state(**kwargs):
        calls.append(kwargs)
        return {"status": "success", "tab_id": kwargs["switch_tab_id"], "elements": []}

    monkeypatch.setattr(ga, "browser_state", fake_browser_state)
    handler = make_handler()

    chunks, outcome = run_generator(handler.do_browser_state({"tab_id": "tab-3"}, SimpleNamespace(content="")))

    assert "Browser state:" in "".join(chunks)
    assert calls[0]["switch_tab_id"] == "tab-3"
    assert json.loads(outcome.data)["tab_id"] == "tab-3"


def test_do_browser_state_truncates_large_output(monkeypatch):
    large_result = {
        "status": "success",
        "tab_id": "7",
        "elements": [{"index": i, "tag": "button", "text": "Login " + ("x" * 80)} for i in range(200)],
    }
    raw_json = json.dumps(large_result, ensure_ascii=False, default=ga.json_default)
    monkeypatch.setattr(ga, "browser_state", lambda **kwargs: large_result)
    handler = make_handler()

    chunks, outcome = run_generator(
        handler.do_browser_state({"max_elements": 200, "_tool_num": 2}, SimpleNamespace(content=""))
    )

    assert "Browser state:" in "".join(chunks)
    assert " ... " in outcome.data
    assert len(outcome.data) < len(raw_json)


def test_do_browser_action_formats_execution_output(monkeypatch):
    monkeypatch.setattr(
        ga,
        "browser_action",
        lambda **kwargs: {
            "status": "success",
            "action": kwargs["action"],
            "index": kwargs["index"],
            "result": "clicked",
        },
    )
    handler = make_handler()

    chunks, outcome = run_generator(
        handler.do_browser_action({"action": "click", "index": 1}, SimpleNamespace(content=""))
    )

    assert "Browser action result:" in "".join(chunks)
    data = json.loads(outcome.data)
    assert data == {"status": "success", "action": "click", "index": 1, "result": "clicked"}


def test_do_browser_action_forwards_tab_id_alias(monkeypatch):
    calls = []

    def fake_browser_action(**kwargs):
        calls.append(kwargs)
        return {"status": "success", "action": kwargs["action"], "tab_id": kwargs["switch_tab_id"]}

    monkeypatch.setattr(ga, "browser_action", fake_browser_action)
    handler = make_handler()

    chunks, outcome = run_generator(
        handler.do_browser_action({"action": "wait_text", "text": "Ready", "tab_id": "tab-3"}, SimpleNamespace(content=""))
    )

    assert "Browser action result:" in "".join(chunks)
    assert calls[0]["switch_tab_id"] == "tab-3"
    assert json.loads(outcome.data)["tab_id"] == "tab-3"


def test_browser_action_init_failure_reports_browser_unavailable(monkeypatch):
    def fail_init():
        raise RuntimeError("Chrome unavailable")

    monkeypatch.setattr(ga, "driver", None)
    monkeypatch.setattr(ga, "first_init_driver", fail_init)

    result = ga.browser_action(action="click", index=1)

    assert result["status"] == "failed"
    assert result["action"] == "click"
    assert result["stage"] == "browser_unavailable"
    assert "Chrome unavailable" in result["error"]
