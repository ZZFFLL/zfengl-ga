from browser_actions import BrowserActionLayer, build_browser_action_script


class FakeDriver:
    def __init__(self, responses=None, sessions=None):
        self.responses = list(responses or [])
        self.sessions = sessions if sessions is not None else [{"id": "7", "url": "https://example.test"}]
        self.default_session_id = "7"
        self.calls = []

    def get_all_sessions(self):
        return list(self.sessions)

    def execute_js(self, script, timeout=15, session_id=None):
        self.calls.append({"script": script, "timeout": timeout, "session_id": session_id})
        return self.responses.pop(0)


class RaisingDriver(FakeDriver):
    def execute_js(self, script, timeout=15, session_id=None):
        self.calls.append({"script": script, "timeout": timeout, "session_id": session_id})
        raise RuntimeError("bridge failed")


def test_get_state_returns_browser_unavailable_when_no_sessions():
    layer = BrowserActionLayer()
    driver = FakeDriver(sessions=[])

    result = layer.get_state(driver)

    assert result["status"] == "failed"
    assert result["stage"] == "browser_unavailable"
    assert "没有可用的浏览器标签页" in result["error"]


def test_get_state_unavailable_clears_cached_state():
    layer = BrowserActionLayer()
    layer._last_state = {"tab_id": "7", "state_token": "old"}
    driver = FakeDriver(sessions=[])

    result = layer.get_state(driver)

    assert result["status"] == "failed"
    assert layer.last_state_token is None


def test_get_state_executes_indexer_and_caches_state_token():
    layer = BrowserActionLayer()
    driver = FakeDriver(
        [
            {
                "data": {
                    "status": "success",
                    "state_token": "tok-1",
                    "elements": [{"index": 1, "tag": "button", "text": "Go"}],
                }
            }
        ]
    )

    result = layer.get_state(driver, max_elements=5)

    assert result["status"] == "success"
    assert result["tab_id"] == "7"
    assert layer.last_state_token == "tok-1"
    assert "const maxElements = 5;" in driver.calls[0]["script"]


def test_get_state_failed_payload_clears_cached_state_and_blocks_stale_action():
    layer = BrowserActionLayer()
    layer._last_state = {"tab_id": "7", "state_token": "old-token"}
    driver = FakeDriver([{"data": {"status": "failed", "stage": "dom_event", "error": "scan failed"}}])

    state = layer.get_state(driver)
    action = layer.run_action(driver, action="click", index=1)

    assert state["status"] == "failed"
    assert layer.last_state_token is None
    assert action["status"] == "failed"
    assert action["stage"] == "state_missing"
    assert len(driver.calls) == 1


def test_get_state_exception_clears_cached_state_and_blocks_stale_action():
    layer = BrowserActionLayer()
    layer._last_state = {"tab_id": "7", "state_token": "old-token"}
    driver = RaisingDriver()

    state = layer.get_state(driver)
    action = layer.run_action(driver, action="click", index=1)

    assert state["status"] == "failed"
    assert layer.last_state_token is None
    assert action["status"] == "failed"
    assert action["stage"] == "state_missing"
    assert len(driver.calls) == 1


def test_run_action_requires_state_for_index_action():
    layer = BrowserActionLayer()
    driver = FakeDriver()

    result = layer.run_action(driver, action="click", index=1)

    assert result == {
        "status": "failed",
        "action": "click",
        "index": 1,
        "stage": "state_missing",
        "error": "Run browser_state before browser_action click.",
    }


def test_run_action_rejects_unknown_action():
    layer = BrowserActionLayer()
    driver = FakeDriver()

    result = layer.run_action(driver, action="drag", index=1)

    assert result["status"] == "failed"
    assert result["stage"] == "invalid_args"
    assert "Unsupported browser action" in result["error"]


def test_run_action_executes_click_with_cached_token_and_invalidates_state():
    layer = BrowserActionLayer()
    layer._last_state = {"tab_id": "7", "state_token": "tok-1"}
    driver = FakeDriver([{"data": {"status": "success", "action": "click", "index": 2, "result": "clicked"}}])

    result = layer.run_action(driver, action="click", index=2)

    assert result["status"] == "success"
    assert result["tab_id"] == "7"
    assert '"state_token": "tok-1"' in driver.calls[0]["script"]
    assert '"action": "click"' in driver.calls[0]["script"]
    assert layer.last_state_token is None


def test_run_action_execute_js_exception_includes_tab_id():
    layer = BrowserActionLayer()
    layer._last_state = {"tab_id": "7", "state_token": "tok-1"}
    driver = RaisingDriver()

    result = layer.run_action(driver, action="click", index=1)

    assert result["status"] == "failed"
    assert result["stage"] == "dom_event"
    assert result["tab_id"] == "7"


def test_run_action_non_object_result_fails_with_tab_id():
    layer = BrowserActionLayer()
    layer._last_state = {"tab_id": "7", "state_token": "tok-1"}
    driver = FakeDriver([{"data": None}])

    result = layer.run_action(driver, action="click", index=1)

    assert result["status"] == "failed"
    assert result["action"] == "click"
    assert result["index"] == 1
    assert result["stage"] == "dom_event"
    assert result["error"] == "browser_action returned a non-object result"
    assert result["tab_id"] == "7"


def test_run_action_rejects_indexed_action_when_cached_tab_mismatches_switch():
    layer = BrowserActionLayer()
    layer._last_state = {"tab_id": "7", "state_token": "tok-1"}
    driver = FakeDriver([{"data": {"status": "success"}}])

    result = layer.run_action(driver, action="click", index=1, switch_tab_id="8")

    assert result["status"] == "failed"
    assert result["stage"] in {"state_missing", "stale_index"}
    assert "Run browser_state" in result["error"]
    assert result["tab_id"] == "8"
    assert driver.calls == []
    assert len(driver.responses) == 1


def test_run_action_allows_wait_text_without_cached_state():
    layer = BrowserActionLayer()
    driver = FakeDriver([{"data": {"status": "success", "action": "wait_text", "result": "text_found"}}])

    result = layer.run_action(driver, action="wait_text", text="Ready", timeout=2)

    assert result["status"] == "success"
    assert result["tab_id"] == "7"
    assert '"text": "Ready"' in driver.calls[0]["script"]


def test_build_browser_action_script_contains_stale_index_check():
    script = build_browser_action_script(
        action="input",
        index=3,
        text="hello",
        value=None,
        timeout=4,
        state_token="tok-2",
        selector=None,
    )

    assert "state_missing" in script
    assert "stale_index" in script
    assert "dom_event" in script
    assert '"action": "input"' in script
