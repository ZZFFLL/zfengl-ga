import json
import subprocess

from browser_actions import BrowserActionLayer, SUPPORTED_ACTIONS, build_browser_action_script


NODE_ACTION_RUNTIME = r"""
global.Event = function Event(type, options = {}) {
  this.type = type;
  this.options = options;
};
global.KeyboardEvent = function KeyboardEvent(type, options = {}) {
  this.type = type;
  this.key = options.key;
  this.options = options;
};
global.setTimeout = (fn, _ms) => fn();
let now = 0;
Date.now = () => {
  now += 200;
  return now;
};
global.document = {
  body: null,
  activeElement: null,
  contains: (el) => Boolean(el && el.attached !== false),
  querySelector: (_selector) => null,
  querySelectorAll: (_selector) => [],
};
global.window = {
  __GA_BROWSER_ACTION_STATE__: null,
  getComputedStyle: (el) => el._style || { display: "block", visibility: "visible", opacity: "1" },
};
document.defaultView = window;
function makeElement(options = {}) {
  const attrs = options.attrs || {};
  const element = {
    tagName: String(options.tag || "div").toUpperCase(),
    innerText: options.text || "",
    textContent: options.text || "",
    disabled: Boolean(options.disabled),
    readOnly: Boolean(options.readOnly),
    isContentEditable: Boolean(options.contentEditable),
    attached: options.attached !== false,
    _style: options.visible === false
      ? { display: "block", visibility: "hidden", opacity: "1" }
      : { display: "block", visibility: "visible", opacity: "1" },
    getAttribute(name) {
      if (name === "role" && options.role) return options.role;
      if (name === "contenteditable" && options.contentEditable) return "true";
      if (name === "type" && options.type) return options.type;
      if (name === "aria-label" && options.ariaLabel) return options.ariaLabel;
      if (name === "placeholder" && options.placeholder) return options.placeholder;
      if (name === "title" && options.title) return options.title;
      return attrs[name] ?? null;
    },
    getBoundingClientRect() {
      return { x: 0, y: 0, width: 10, height: 10 };
    },
    scrollIntoView() {
      this.scrolled = true;
    },
    dispatchEvent(event) {
      this.dispatched = this.dispatched || [];
      this.dispatched.push(event.type);
      return true;
    },
    focus() {
      document.activeElement = this;
      this.focused = true;
    },
    click() {
      this.clicked = true;
    },
    select() {
      this.selected = true;
    },
  };
  element.ownerDocument = options.ownerDocument || document;
  if (Object.prototype.hasOwnProperty.call(options, "value")) {
    element.value = options.value;
  }
  return element;
}
document.body = makeElement({ tag: "body" });
document.activeElement = document.body;
"""


def run_browser_action_script(script, setup_js):
    node_code = "\n".join(
        [
            f"const script = {json.dumps(script)};",
            NODE_ACTION_RUNTIME,
            setup_js,
            """
(async () => {
  const result = await eval(script);
  if (typeof __GA_TEST_PROBE__ === "function") {
    console.log(JSON.stringify({ result, probe: __GA_TEST_PROBE__() }));
  } else {
    console.log(JSON.stringify(result));
  }
})().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
""",
        ]
    )
    completed = subprocess.run(
        ["node", "-"],
        input=node_code,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return json.loads(completed.stdout)


def run_browser_action_scripts(scripts, setup_js):
    node_code = "\n".join(
        [
            f"const scripts = {json.dumps(scripts)};",
            NODE_ACTION_RUNTIME,
            setup_js,
            """
(async () => {
  const results = [];
  for (const script of scripts) {
    results.push(await eval(script));
  }
  if (typeof __GA_TEST_PROBE__ === "function") {
    console.log(JSON.stringify({ results, probe: __GA_TEST_PROBE__() }));
  } else {
    console.log(JSON.stringify({ results }));
  }
})().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
""",
        ]
    )
    completed = subprocess.run(
        ["node", "-"],
        input=node_code,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return json.loads(completed.stdout)


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

    assert result["status"] == "failed"
    assert result["action"] == "click"
    assert result["index"] == 1
    assert result["stage"] == "state_missing"
    assert result["error"] == "Run browser_state before browser_action click."
    assert result["recovery"]["code"] == "refresh_state"


def test_run_action_keys_with_stale_index_suggests_active_element_retry():
    layer = BrowserActionLayer()
    driver = FakeDriver()

    result = layer.run_action(driver, action="keys", index=52, text="Enter")

    assert result["status"] == "failed"
    assert result["stage"] == "state_missing"
    assert result["action"] == "keys"
    assert result["index"] == 52
    assert "without index" in result["hint"]
    assert "focused element" in result["hint"]
    assert result["suggested_args"] == {"action": "keys", "text": "Enter"}
    assert driver.calls == []


def test_run_action_rejects_unknown_action():
    layer = BrowserActionLayer()
    driver = FakeDriver()

    result = layer.run_action(driver, action="drag", index=1)

    assert result["status"] == "failed"
    assert result["stage"] == "invalid_args"
    assert "Unsupported browser action" in result["error"]


def test_run_action_rejects_invalid_verify_type():
    layer = BrowserActionLayer()
    driver = FakeDriver()

    result = layer.run_action(driver, action="click", index=1, verify="url")

    assert result["status"] == "failed"
    assert result["stage"] == "invalid_args"
    assert result["error"] == "Unsupported verification type: url"
    assert result["index"] == 1
    assert driver.calls == []


def test_run_action_requires_expected_text_for_text_verification():
    layer = BrowserActionLayer()
    driver = FakeDriver()

    result = layer.run_action(driver, action="click", index=1, verify="text")

    assert result["status"] == "failed"
    assert result["stage"] == "invalid_args"
    assert "verify_text is required" in result["error"]
    assert result["index"] == 1
    assert driver.calls == []


def test_run_action_requires_expected_text_for_element_text_verification():
    layer = BrowserActionLayer()
    driver = FakeDriver()

    result = layer.run_action(driver, action="click", index=1, verify="element_text", verify_text="  ")

    assert result["status"] == "failed"
    assert result["stage"] == "invalid_args"
    assert "verify_text is required" in result["error"]
    assert result["index"] == 1
    assert driver.calls == []


def test_run_action_requires_expected_selector_for_selector_verification():
    layer = BrowserActionLayer()
    driver = FakeDriver()

    result = layer.run_action(driver, action="click", index=1, verify="selector")

    assert result["status"] == "failed"
    assert result["stage"] == "invalid_args"
    assert "verify_selector is required" in result["error"]
    assert result["index"] == 1
    assert driver.calls == []


def test_run_action_rejects_verify_on_wait_actions():
    cases = [
        ("wait_index", {"index": 1}),
        ("wait_text", {"text": "Ready"}),
        ("wait_selector", {"selector": ".ready"}),
        ("wait_dom_stable", {}),
        ("wait_not_busy", {}),
        ("wait_enabled", {"index": 1}),
        ("wait_route", {"value": "/ready"}),
    ]

    for action, kwargs in cases:
        layer = BrowserActionLayer()
        driver = FakeDriver()

        result = layer.run_action(driver, action=action, verify="text", verify_text="Ready", **kwargs)

        assert result["status"] == "failed"
        assert result["stage"] == "invalid_args"
        assert "verify is not supported" in result["error"]
        assert driver.calls == []


def test_run_action_field_value_verification_requires_non_empty_expected_value():
    layer = BrowserActionLayer()
    driver = FakeDriver()

    from_blank_text = layer.run_action(driver, action="input", index=1, text="", verify="field_value")
    from_blank_value = layer.run_action(driver, action="select", index=1, value="  ", verify="field_value")
    from_blank_verify_value = layer.run_action(
        driver,
        action="input",
        index=1,
        text="openai",
        verify="field_value",
        verify_value="  ",
    )

    for result in [from_blank_text, from_blank_value, from_blank_verify_value]:
        assert result["status"] == "failed"
        assert result["stage"] == "invalid_args"
        assert "field_value verification requires" in result["error"]
    assert driver.calls == []


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


def test_run_action_verify_failed_invalidates_state():
    layer = BrowserActionLayer()
    layer._last_state = {"tab_id": "7", "state_token": "tok-1"}
    driver = FakeDriver(
        [
            {
                "data": {
                    "status": "failed",
                    "action": "input",
                    "index": 1,
                    "stage": "verify_failed",
                    "error": "Verification failed.",
                }
            }
        ]
    )

    result = layer.run_action(driver, action="input", index=1, text="openai", verify="field_value")

    assert result["status"] == "failed"
    assert result["stage"] == "verify_failed"
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


def test_run_action_rejects_indexed_action_after_state_from_different_tab():
    layer = BrowserActionLayer()
    driver = FakeDriver(
        [
            {
                "data": {
                    "status": "success",
                    "state_token": "tok-8",
                    "elements": [{"index": 1, "tag": "button", "text": "Go"}],
                }
            },
            {"data": {"status": "success", "action": "click", "index": 1, "result": "clicked"}},
        ]
    )

    state = layer.get_state(driver, switch_tab_id="8")
    result = layer.run_action(driver, action="click", index=1, switch_tab_id="7")

    assert state["status"] == "success"
    assert state["tab_id"] == "8"
    assert result["status"] == "failed"
    assert result["stage"] == "stale_index"
    assert "current tab" in result["error"]
    assert result["tab_id"] == "7"
    assert len(driver.calls) == 1
    assert len(driver.responses) == 1


def test_run_action_allows_wait_text_without_cached_state():
    layer = BrowserActionLayer()
    driver = FakeDriver([{"data": {"status": "success", "action": "wait_text", "result": "text_found"}}])

    result = layer.run_action(driver, action="wait_text", text="Ready", timeout=2)

    assert result["status"] == "success"
    assert result["tab_id"] == "7"
    assert '"text": "Ready"' in driver.calls[0]["script"]


def test_run_action_wait_text_ignores_incidental_index_without_cached_state():
    layer = BrowserActionLayer()
    driver = FakeDriver([{"data": {"status": "success", "action": "wait_text", "result": "text_found"}}])

    result = layer.run_action(driver, action="wait_text", index=1, text="Ready", timeout=2)

    assert result["status"] == "success"
    assert result["tab_id"] == "7"
    assert len(driver.calls) == 1
    assert '"index": null' in driver.calls[0]["script"]


def test_run_action_wait_selector_ignores_incidental_index_without_cached_state():
    layer = BrowserActionLayer()
    driver = FakeDriver([{"data": {"status": "success", "action": "wait_selector", "result": "selector_found"}}])

    result = layer.run_action(driver, action="wait_selector", index=1, selector=".ready", timeout=2)

    assert result["status"] == "success"
    assert result["tab_id"] == "7"
    assert len(driver.calls) == 1
    assert '"index": null' in driver.calls[0]["script"]


def test_browser_action_script_wait_text_searches_same_origin_frames():
    script = build_browser_action_script(
        action="wait_text",
        index=None,
        text="Frame Ready",
        value=None,
        timeout=1,
        state_token=None,
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
const iframe = makeElement({ tag: "iframe" });
const frameWindow = { ...window, frameElement: iframe, parent: window };
const frameDocument = {
  defaultView: frameWindow,
  body: { innerText: "Frame Ready", textContent: "Frame Ready" },
  querySelectorAll: (_selector) => [],
};
iframe.contentDocument = frameDocument;
document.body.innerText = "Top Only";
document.body.textContent = "Top Only";
document.querySelectorAll = (selector) => selector === "iframe, frame" ? [iframe] : [];
""",
    )

    assert result["status"] == "success"
    assert result["result"] == "text_found"


def test_browser_action_script_wait_selector_searches_same_origin_frames():
    script = build_browser_action_script(
        action="wait_selector",
        index=None,
        text=None,
        value=None,
        timeout=1,
        state_token=None,
        selector=".inside-frame",
    )

    result = run_browser_action_script(
        script,
        """
const iframe = makeElement({ tag: "iframe" });
const frameWindow = { ...window, frameElement: iframe, parent: window };
const frameDocument = {
  defaultView: frameWindow,
  body: { innerText: "", textContent: "" },
  querySelector: (selector) => selector === ".inside-frame" ? makeElement({ tag: "button", text: "Inside" }) : null,
  querySelectorAll: (_selector) => [],
};
iframe.contentDocument = frameDocument;
document.querySelector = (_selector) => null;
document.querySelectorAll = (selector) => selector === "iframe, frame" ? [iframe] : [];
""",
    )

    assert result["status"] == "success"
    assert result["result"] == "selector_found"


def test_browser_action_script_verify_selector_searches_same_origin_frames():
    script = build_browser_action_script(
        action="click",
        index=1,
        text=None,
        value=None,
        timeout=1,
        state_token="tok-2",
        selector=None,
        verify="selector",
        verify_selector=".post-click",
    )

    result = run_browser_action_script(
        script,
        """
const button = makeElement({ tag: "button", text: "Open" });
const iframe = makeElement({ tag: "iframe" });
const frameWindow = { ...window, frameElement: iframe, parent: window };
const frameDocument = {
  defaultView: frameWindow,
  body: { innerText: "", textContent: "" },
  querySelector: (selector) => selector === ".post-click" ? makeElement({ tag: "div", text: "Ready" }) : null,
  querySelectorAll: (_selector) => [],
};
iframe.contentDocument = frameDocument;
document.querySelector = (_selector) => null;
document.querySelectorAll = (selector) => selector === "iframe, frame" ? [iframe] : [];
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [button] };
""",
    )

    assert result["status"] == "success"
    assert result["verification"] == {
        "type": "selector",
        "observed": ".post-click",
        "expected": ".post-click",
        "passed": True,
    }


def test_browser_action_script_wait_text_skips_hidden_same_origin_frames():
    script = build_browser_action_script(
        action="wait_text",
        index=None,
        text="Hidden Frame Ready",
        value=None,
        timeout=1,
        state_token=None,
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
const iframe = makeElement({ tag: "iframe", visible: false });
const frameWindow = { ...window, frameElement: iframe, parent: window };
const frameDocument = {
  defaultView: frameWindow,
  body: { innerText: "Hidden Frame Ready", textContent: "Hidden Frame Ready" },
  querySelectorAll: (_selector) => [],
};
iframe.contentDocument = frameDocument;
document.body.innerText = "Top Only";
document.body.textContent = "Top Only";
document.querySelectorAll = (selector) => selector === "iframe, frame" ? [iframe] : [];
""",
    )

    assert result["status"] == "failed"
    assert result["stage"] == "timeout"


def test_browser_action_script_wait_selector_skips_hidden_same_origin_frames():
    script = build_browser_action_script(
        action="wait_selector",
        index=None,
        text=None,
        value=None,
        timeout=1,
        state_token=None,
        selector=".inside-hidden-frame",
    )

    result = run_browser_action_script(
        script,
        """
const iframe = makeElement({ tag: "iframe", visible: false });
const frameWindow = { ...window, frameElement: iframe, parent: window };
const frameDocument = {
  defaultView: frameWindow,
  body: { innerText: "", textContent: "" },
  querySelector: (selector) => selector === ".inside-hidden-frame" ? makeElement({ tag: "button", text: "Inside" }) : null,
  querySelectorAll: (_selector) => [],
};
iframe.contentDocument = frameDocument;
document.querySelector = (_selector) => null;
document.querySelectorAll = (selector) => selector === "iframe, frame" ? [iframe] : [];
""",
    )

    assert result["status"] == "failed"
    assert result["stage"] == "timeout"


def test_supported_actions_includes_spa_waits():
    assert {"wait_dom_stable", "wait_not_busy", "wait_enabled", "wait_route"} <= SUPPORTED_ACTIONS


def test_run_action_allows_wait_dom_stable_without_cached_state():
    layer = BrowserActionLayer()
    driver = FakeDriver([{"data": {"status": "success", "action": "wait_dom_stable", "result": "dom_stable"}}])

    result = layer.run_action(driver, action="wait_dom_stable", timeout=2)

    assert result["status"] == "success"
    assert result["tab_id"] == "7"
    assert '"action": "wait_dom_stable"' in driver.calls[0]["script"]


def test_run_action_wait_dom_stable_ignores_incidental_index_without_cached_state():
    layer = BrowserActionLayer()
    driver = FakeDriver([{"data": {"status": "success", "action": "wait_dom_stable", "result": "dom_stable"}}])

    result = layer.run_action(driver, action="wait_dom_stable", index=1, timeout=2)

    assert result["status"] == "success"
    assert result["tab_id"] == "7"
    assert len(driver.calls) == 1
    assert '"index": null' in driver.calls[0]["script"]


def test_run_action_allows_wait_not_busy_without_cached_state():
    layer = BrowserActionLayer()
    driver = FakeDriver([{"data": {"status": "success", "action": "wait_not_busy", "result": "not_busy"}}])

    result = layer.run_action(driver, action="wait_not_busy", selector=".busy", timeout=2)

    assert result["status"] == "success"
    assert result["tab_id"] == "7"
    assert '"selector": ".busy"' in driver.calls[0]["script"]


def test_run_action_wait_not_busy_ignores_incidental_index_without_cached_state():
    layer = BrowserActionLayer()
    driver = FakeDriver([{"data": {"status": "success", "action": "wait_not_busy", "result": "not_busy"}}])

    result = layer.run_action(driver, action="wait_not_busy", index=1, timeout=2)

    assert result["status"] == "success"
    assert result["tab_id"] == "7"
    assert len(driver.calls) == 1
    assert '"index": null' in driver.calls[0]["script"]


def test_run_action_wait_route_without_cached_state_requires_text_or_value():
    layer = BrowserActionLayer()
    driver = FakeDriver([{"data": {"status": "success", "action": "wait_route", "result": "route_matched"}}])

    missing = layer.run_action(driver, action="wait_route", timeout=2)
    result = layer.run_action(driver, action="wait_route", value="/dashboard", timeout=2)

    assert missing["status"] == "failed"
    assert missing["stage"] == "invalid_args"
    assert "text or value is required" in missing["error"]
    assert result["status"] == "success"
    assert result["tab_id"] == "7"
    assert '"value": "/dashboard"' in driver.calls[0]["script"]


def test_run_action_wait_route_ignores_incidental_index_without_cached_state():
    layer = BrowserActionLayer()
    driver = FakeDriver([{"data": {"status": "success", "action": "wait_route", "result": "route_matched"}}])

    result = layer.run_action(driver, action="wait_route", index=1, text="/dashboard", timeout=2)

    assert result["status"] == "success"
    assert result["tab_id"] == "7"
    assert len(driver.calls) == 1
    assert '"index": null' in driver.calls[0]["script"]


def test_run_action_wait_enabled_requires_state_when_indexed():
    layer = BrowserActionLayer()
    driver = FakeDriver()

    result = layer.run_action(driver, action="wait_enabled", index=1, timeout=2)

    assert result["status"] == "failed"
    assert result["stage"] == "state_missing"
    assert result["error"] == "Run browser_state before browser_action wait_enabled."
    assert driver.calls == []


def test_run_action_wait_index_uses_cached_selector_hint():
    layer = BrowserActionLayer()
    driver = FakeDriver(
        [
            {
                "data": {
                    "status": "success",
                    "state_token": "tok-1",
                    "elements": [
                        {"index": 1, "tag": "button", "text": "Go", "selector_hint": 'button[name="go"]'}
                    ],
                }
            },
            {"data": {"status": "success", "action": "wait_index", "index": 1, "result": "element_visible"}},
        ]
    )

    layer.get_state(driver)
    result = layer.run_action(driver, action="wait_index", index=1)

    assert result["status"] == "success"
    assert '"selector": "button[name=\\"go\\"]"' in driver.calls[1]["script"]


def test_run_action_wait_index_passes_cached_selector_identity():
    layer = BrowserActionLayer()
    driver = FakeDriver(
        [
            {
                "data": {
                    "status": "success",
                    "state_token": "tok-1",
                    "elements": [
                        {
                            "index": 1,
                            "tag": "button",
                            "role": "button",
                            "text": "Go",
                            "selector_hint": 'button[name="go"]',
                        }
                    ],
                }
            },
            {"data": {"status": "success", "action": "wait_index", "index": 1, "result": "element_visible"}},
        ]
    )

    layer.get_state(driver)
    result = layer.run_action(driver, action="wait_index", index=1)

    assert result["status"] == "success"
    script = driver.calls[1]["script"]
    assert '"selector_tag": "button"' in script
    assert '"selector_role": "button"' in script
    assert '"selector_text": "Go"' in script


def test_run_action_passes_cached_frame_path_from_latest_state():
    layer = BrowserActionLayer()
    driver = FakeDriver(
        [
            {
                "data": {
                    "status": "success",
                    "state_token": "tok-1",
                    "elements": [
                        {
                            "index": 1,
                            "tag": "button",
                            "text": "Go",
                            "selector_hint": 'button[name="go"]',
                            "frame_path": [0],
                        }
                    ],
                }
            },
            {"data": {"status": "success", "action": "wait_index", "index": 1, "result": "element_visible"}},
        ]
    )

    layer.get_state(driver)
    result = layer.run_action(driver, action="wait_index", index=1)

    assert result["status"] == "success"
    assert '"frame_path": [0]' in driver.calls[1]["script"]


def test_run_action_wait_index_user_selector_still_passes_cached_identity():
    layer = BrowserActionLayer()
    driver = FakeDriver(
        [
            {
                "data": {
                    "status": "success",
                    "state_token": "tok-1",
                    "elements": [
                        {
                            "index": 1,
                            "tag": "button",
                            "role": "button",
                            "text": "Go",
                            "selector_hint": "button",
                        }
                    ],
                }
            },
            {"data": {"status": "success", "action": "wait_index", "index": 1, "result": "element_visible"}},
        ]
    )

    layer.get_state(driver)
    result = layer.run_action(driver, action="wait_index", index=1, selector="#other")

    assert result["status"] == "success"
    script = driver.calls[1]["script"]
    assert '"selector": "#other"' in script
    assert '"selector_tag": "button"' in script
    assert '"selector_role": "button"' in script
    assert '"selector_text": "Go"' in script


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


def test_build_browser_action_script_contains_spa_wait_branches():
    script = build_browser_action_script(
        action="wait_dom_stable",
        index=None,
        text="/dashboard",
        value=None,
        timeout=4,
        state_token=None,
        selector=None,
    )

    assert "dom_unstable" in script
    assert "busySelector" in script
    assert "[aria-busy='true'], [data-loading='true'], .loading, .spinner, .ant-spin-spinning, .ant-spin-dot, .el-loading-mask" in script
    assert "location.href" in script
    assert "location.pathname" in script
    assert 'request.action === "wait_enabled"' in script


def test_browser_action_script_wait_dom_stable_runtime_succeeds_after_stable_ticks():
    script = build_browser_action_script(
        action="wait_dom_stable",
        index=None,
        text=None,
        value=None,
        timeout=1,
        state_token=None,
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
let queryCalls = 0;
document.body.innerText = "Ready";
document.body.textContent = "Ready";
document.querySelectorAll = (selector) => {
  queryCalls += 1;
  if (selector === "*") return [document.body];
  return [];
};
global.__GA_TEST_PROBE__ = () => ({ queryCalls });
""",
    )

    probe = result["probe"]
    result = result["result"]
    assert result["status"] == "success"
    assert result["result"] == "dom_stable"
    assert probe["queryCalls"] >= 4


def test_browser_action_script_wait_not_busy_runtime_waits_until_spinner_disappears():
    script = build_browser_action_script(
        action="wait_not_busy",
        index=None,
        text=None,
        value=None,
        timeout=1,
        state_token=None,
        selector=".spinner",
    )

    result = run_browser_action_script(
        script,
        """
const spinner = makeElement({ tag: "div" });
let queryCalls = 0;
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame") return [];
  if (selector === ".spinner") {
    queryCalls += 1;
    return queryCalls === 1 ? [spinner] : [];
  }
  return [];
};
global.__GA_TEST_PROBE__ = () => ({ queryCalls });
""",
    )

    probe = result["probe"]
    result = result["result"]
    assert result["status"] == "success"
    assert result["result"] == "not_busy"
    assert probe["queryCalls"] == 2


def test_browser_action_script_wait_not_busy_searches_same_origin_frames():
    script = build_browser_action_script(
        action="wait_not_busy",
        index=None,
        text=None,
        value=None,
        timeout=1,
        state_token=None,
        selector=".spinner",
    )

    result = run_browser_action_script(
        script,
        """
const iframe = makeElement({ tag: "iframe" });
const frameWindow = { ...window, frameElement: iframe, parent: window };
const spinner = makeElement({ tag: "div" });
let frameQueryCalls = 0;
const frameDocument = {
  defaultView: frameWindow,
  body: { innerText: "", textContent: "" },
  querySelectorAll: (selector) => {
    if (selector === "iframe, frame") return [];
    if (selector === ".spinner") {
      frameQueryCalls += 1;
      return frameQueryCalls === 1 ? [spinner] : [];
    }
    return [];
  },
};
iframe.contentDocument = frameDocument;
document.querySelectorAll = (selector) => selector === "iframe, frame" ? [iframe] : [];
global.__GA_TEST_PROBE__ = () => ({ frameQueryCalls });
""",
    )

    probe = result["probe"]
    result = result["result"]
    assert result["status"] == "success"
    assert result["result"] == "not_busy"
    assert probe["frameQueryCalls"] == 2


def test_browser_action_script_wait_enabled_runtime_waits_for_enabled_cached_element():
    script = build_browser_action_script(
        action="wait_enabled",
        index=1,
        text=None,
        value=None,
        timeout=1,
        state_token="tok-2",
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
const input = makeElement({ tag: "input", type: "text", value: "" });
let disabledChecks = 0;
Object.defineProperty(input, "disabled", {
  get() {
    disabledChecks += 1;
    return disabledChecks === 1;
  }
});
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [input] };
global.__GA_TEST_PROBE__ = () => ({ disabledChecks });
""",
    )

    probe = result["probe"]
    result = result["result"]
    assert result["status"] == "success"
    assert result["result"] == "element_enabled"
    assert probe["disabledChecks"] == 2


def test_browser_action_script_wait_route_runtime_matches_pathname():
    script = build_browser_action_script(
        action="wait_route",
        index=None,
        text=None,
        value="/dashboard",
        timeout=1,
        state_token=None,
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
global.location = { href: "https://example.test/app/dashboard?tab=1", pathname: "/app/dashboard" };
""",
    )

    assert result["status"] == "success"
    assert result["result"] == "route_matched"


def test_browser_action_script_wait_route_ignores_component_text_without_url_change():
    script = build_browser_action_script(
        action="wait_route",
        index=None,
        text="details",
        value=None,
        timeout=1,
        state_token=None,
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
global.location = { href: "https://example.test/app/home", pathname: "/app/home" };
document.body.innerText = "details component mounted";
document.body.textContent = "details component mounted";
""",
    )

    assert result["status"] == "failed"
    assert result["stage"] == "timeout"


def test_build_browser_action_script_rejects_unsupported_keys():
    script = build_browser_action_script(
        action="keys",
        index=None,
        text="hello",
        value=None,
        timeout=4,
        state_token=None,
        selector=None,
    )

    assert 'const allowedKeys = ["Enter", "Escape", "Tab", "Control+A", "Backspace"];' in script
    assert 'if (!allowedKeys.includes(key)) return fail("invalid_args", "Unsupported key action.");' in script


def test_build_browser_action_script_rejects_disabled_and_readonly_controls():
    script = build_browser_action_script(
        action="input",
        index=3,
        text="hello",
        value=None,
        timeout=4,
        state_token="tok-2",
        selector=None,
    )

    assert "function blockedForAction(el, action)" in script
    assert 'return "Element is disabled.";' in script
    assert 'return "Element is read-only.";' in script


def test_build_browser_action_script_keys_checks_active_target_readonly_state():
    script = build_browser_action_script(
        action="keys",
        index=None,
        text="Backspace",
        value=None,
        timeout=4,
        state_token=None,
        selector=None,
    )

    assert 'const blocked = blockedForAction(target, request.action);' in script
    assert 'if (blocked) return fail("visibility", blocked);' in script


def test_browser_action_script_keys_uses_same_origin_frame_active_element():
    script = build_browser_action_script(
        action="keys",
        index=None,
        text="Enter",
        value=None,
        timeout=1,
        state_token=None,
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
const iframe = makeElement({ tag: "iframe" });
const frameInput = makeElement({ tag: "input", type: "text", value: "" });
const frameDocument = {
  defaultView: window,
  activeElement: frameInput,
  body: makeElement({ tag: "body" }),
  contains: (el) => Boolean(el && el.attached !== false && el.ownerDocument === frameDocument),
  querySelectorAll: (_selector) => [],
};
frameInput.ownerDocument = frameDocument;
iframe.contentDocument = frameDocument;
document.activeElement = iframe;
global.__GA_TEST_PROBE__ = () => ({
  frameEvents: frameInput.dispatched || [],
  iframeEvents: iframe.dispatched || [],
});
""",
    )

    probe = result["probe"]
    result = result["result"]
    assert result["status"] == "success"
    assert result["result"] == "Enter"
    assert probe["frameEvents"] == ["keydown", "keyup"]
    assert probe["iframeEvents"] == []


def test_build_browser_action_script_wait_index_uses_selector_hint_when_available():
    script = build_browser_action_script(
        action="wait_index",
        index=1,
        text=None,
        value=None,
        timeout=4,
        state_token="tok-2",
        selector='button[data-testid="login"]',
    )

    assert 'if (request.selector) {' in script
    assert 'const target = queryDocument.querySelector(request.selector);' in script
    assert 'if (!visible(target)) return null;' in script
    assert 'replaceCachedElement(request.index, target, request.state_token);' in script


def test_build_browser_action_script_contains_frame_document_helpers():
    script = build_browser_action_script(
        action="wait_index",
        index=1,
        text=None,
        value=None,
        timeout=4,
        state_token="tok-2",
        selector='button[data-testid="login"]',
        frame_path=[0],
    )

    assert '"frame_path": [0]' in script
    assert "function ownerWindowOf(el)" in script
    assert "function ownerDocumentContains(el)" in script
    assert "el.ownerDocument.contains(el)" in script
    assert "function frameStepIndex(step)" in script
    assert "function documentForFramePath(framePath)" in script
    assert "frame_unavailable" in script


def test_build_browser_action_script_wait_index_prefers_cached_node_and_checks_selector_identity():
    script = build_browser_action_script(
        action="wait_index",
        index=1,
        text=None,
        value=None,
        timeout=4,
        state_token="tok-2",
        selector='button[data-testid="login"]',
    )

    assert "function matchesSelectorIdentity(target)" in script
    assert "if (ownerDocumentContains(el)) return visible(el) ? el : null;" in script
    assert "el = null;" in script
    assert "if (!matchesSelectorIdentity(target)) return null;" in script


def test_build_browser_action_script_input_rejects_non_editable_targets():
    script = build_browser_action_script(
        action="input",
        index=3,
        text="hello",
        value=None,
        timeout=4,
        state_token="tok-2",
        selector=None,
    )

    assert "function editableForInput(el)" in script
    assert 'return fail("invalid_args", "input action requires an editable text element.");' in script
    assert "const isContentEditable = isContentEditableTarget(el);" in script


def test_build_browser_action_script_keys_requires_editable_target_for_editing_keys():
    script = build_browser_action_script(
        action="keys",
        index=None,
        text="Backspace",
        value=None,
        timeout=4,
        state_token=None,
        selector=None,
    )

    assert "function requiresEditableKey(key)" in script
    assert 'return fail("invalid_args", "Focused element is not editable.");' in script


def test_browser_action_script_wait_index_does_not_fallback_when_cached_node_is_hidden():
    script = build_browser_action_script(
        action="wait_index",
        index=1,
        text=None,
        value=None,
        timeout=1,
        state_token="tok-2",
        selector='button[name="go"]',
        selector_tag="button",
        selector_role="button",
        selector_text="Go",
    )

    result = run_browser_action_script(
        script,
        """
const cached = makeElement({ tag: "button", role: "button", text: "Go", visible: false });
const replacement = makeElement({ tag: "button", role: "button", text: "Go", visible: true });
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [cached] };
document.querySelector = (_selector) => replacement;
""",
    )

    assert result["status"] == "failed"
    assert result["stage"] == "timeout"


def test_browser_action_script_wait_index_fallback_succeeds_when_cached_node_detached():
    script = build_browser_action_script(
        action="wait_index",
        index=1,
        text=None,
        value=None,
        timeout=1,
        state_token="tok-2",
        selector='button[name="go"]',
        selector_tag="button",
        selector_role="button",
        selector_text="Go",
    )

    result = run_browser_action_script(
        script,
        """
const cached = makeElement({ tag: "button", role: "button", text: "Go", attached: false });
const replacement = makeElement({ tag: "button", role: "button", text: "Go", visible: true });
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [cached] };
document.querySelector = (_selector) => replacement;
""",
    )

    assert result["status"] == "success"
    assert result["result"] == "element_visible"


def test_browser_action_script_wait_index_fallback_refreshes_cached_node_for_next_action():
    wait_script = build_browser_action_script(
        action="wait_index",
        index=1,
        text=None,
        value=None,
        timeout=1,
        state_token="tok-2",
        selector='button[name="go"]',
        selector_tag="button",
        selector_role="button",
        selector_text="Go",
    )
    click_script = build_browser_action_script(
        action="click",
        index=1,
        text=None,
        value=None,
        timeout=1,
        state_token="tok-2",
        selector=None,
    )

    result = run_browser_action_scripts(
        [wait_script, click_script],
        """
const cached = makeElement({ tag: "button", role: "button", text: "Go", attached: false });
const replacement = makeElement({ tag: "button", role: "button", text: "Go", visible: true });
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [cached] };
document.querySelector = (_selector) => replacement;
global.__GA_TEST_PROBE__ = () => ({
  cachedClicked: Boolean(cached.clicked),
  replacementClicked: Boolean(replacement.clicked),
  cachePointsToReplacement: window.__GA_BROWSER_ACTION_STATE__.elements[0] === replacement,
});
""",
    )

    wait_result, click_result = result["results"]
    assert wait_result["status"] == "success"
    assert wait_result["result"] == "element_visible"
    assert click_result["status"] == "success"
    assert click_result["result"] == "clicked"
    assert result["probe"] == {
        "cachedClicked": False,
        "replacementClicked": True,
        "cachePointsToReplacement": True,
    }


def test_browser_action_script_wait_index_fallback_rejects_cache_token_change():
    script = build_browser_action_script(
        action="wait_index",
        index=1,
        text=None,
        value=None,
        timeout=1,
        state_token="tok-2",
        selector='button[name="go"]',
        selector_tag="button",
        selector_role="button",
        selector_text="Go",
    )

    result = run_browser_action_script(
        script,
        """
const cached = makeElement({ tag: "button", role: "button", text: "Go", attached: false });
const replacement = makeElement({ tag: "button", role: "button", text: "Go", visible: true });
const other = makeElement({ tag: "button", role: "button", text: "Other" });
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [cached] };
document.querySelector = (_selector) => {
  window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-new", elements: [other] };
  return replacement;
};
global.__GA_TEST_PROBE__ = () => ({
  token: window.__GA_BROWSER_ACTION_STATE__.token,
  cachePointsToReplacement: window.__GA_BROWSER_ACTION_STATE__.elements[0] === replacement,
  cachePointsToOther: window.__GA_BROWSER_ACTION_STATE__.elements[0] === other,
});
""",
    )

    probe = result["probe"]
    result = result["result"]
    assert result["status"] == "failed"
    assert result["stage"] == "stale_index"
    assert probe == {
        "token": "tok-new",
        "cachePointsToReplacement": False,
        "cachePointsToOther": True,
    }


def test_browser_action_script_wait_index_fallback_rejects_cache_index_shrink():
    script = build_browser_action_script(
        action="wait_index",
        index=1,
        text=None,
        value=None,
        timeout=1,
        state_token="tok-2",
        selector='button[name="go"]',
        selector_tag="button",
        selector_role="button",
        selector_text="Go",
    )

    result = run_browser_action_script(
        script,
        """
const cached = makeElement({ tag: "button", role: "button", text: "Go", attached: false });
const replacement = makeElement({ tag: "button", role: "button", text: "Go", visible: true });
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [cached] };
document.querySelector = (_selector) => {
  window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [] };
  return replacement;
};
global.__GA_TEST_PROBE__ = () => ({
  cacheLength: window.__GA_BROWSER_ACTION_STATE__.elements.length,
});
""",
    )

    probe = result["probe"]
    result = result["result"]
    assert result["status"] == "failed"
    assert result["stage"] == "stale_index"
    assert probe == {"cacheLength": 0}


def test_browser_action_script_wait_enabled_missing_cached_node_returns_stale_index():
    script = build_browser_action_script(
        action="wait_enabled",
        index=1,
        text=None,
        value=None,
        timeout=1,
        state_token="tok-2",
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [null] };
""",
    )

    assert result["status"] == "failed"
    assert result["stage"] == "stale_index"


def test_browser_action_script_wait_enabled_detached_cached_node_returns_stale_index():
    script = build_browser_action_script(
        action="wait_enabled",
        index=1,
        text=None,
        value=None,
        timeout=1,
        state_token="tok-2",
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
const input = makeElement({ tag: "input", type: "text", attached: false });
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [input] };
""",
    )

    assert result["status"] == "failed"
    assert result["stage"] == "stale_index"


def test_browser_action_script_wait_index_fallback_succeeds_with_tag_only_hint():
    script = build_browser_action_script(
        action="wait_index",
        index=1,
        text=None,
        value=None,
        timeout=1,
        state_token="tok-2",
        selector="button",
        selector_tag="button",
        selector_role="button",
        selector_text="Go",
    )

    result = run_browser_action_script(
        script,
        """
const cached = makeElement({ tag: "button", role: "button", text: "Go", attached: false });
const replacement = makeElement({ tag: "button", role: "button", text: "Go", visible: true });
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [cached] };
document.querySelector = (_selector) => replacement;
""",
    )

    assert result["status"] == "success"
    assert result["result"] == "element_visible"


def test_browser_action_script_wait_index_selector_fallback_requires_identity():
    script = build_browser_action_script(
        action="wait_index",
        index=1,
        text=None,
        value=None,
        timeout=1,
        state_token="tok-2",
        selector="#other",
    )

    result = run_browser_action_script(
        script,
        """
const cached = makeElement({ tag: "button", role: "button", text: "Go", attached: false });
const unrelated = makeElement({ tag: "button", role: "button", text: "Delete", visible: true });
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [cached] };
document.querySelector = (_selector) => unrelated;
""",
    )

    assert result["status"] == "failed"
    assert result["stage"] == "timeout"


def test_browser_action_script_wait_index_fallback_queries_frame_document():
    script = build_browser_action_script(
        action="wait_index",
        index=1,
        text=None,
        value=None,
        timeout=1,
        state_token="tok-2",
        selector='button[name="go"]',
        selector_tag="button",
        selector_role="button",
        selector_text="Go",
        frame_path=[0],
    )

    result = run_browser_action_script(
        script,
        """
const frameDocument = {
  defaultView: window,
  contains: (el) => Boolean(el && el.attached !== false && el.ownerDocument === frameDocument),
  querySelector: (_selector) => makeElement({
    tag: "button",
    role: "button",
    text: "Go",
    visible: true,
    ownerDocument: frameDocument
  }),
  querySelectorAll: (_selector) => [],
};
const iframe = { contentDocument: frameDocument };
const cached = makeElement({ tag: "button", role: "button", text: "Go", attached: false, ownerDocument: frameDocument });
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [cached] };
document.querySelector = (_selector) => null;
document.querySelectorAll = (selector) => selector === "iframe, frame" ? [iframe] : [];
""",
    )

    assert result["status"] == "success"
    assert result["result"] == "element_visible"


def test_browser_action_script_rejects_cached_target_in_detached_iframe():
    for action, target_js, action_kwargs in [
        (
            "click",
            'makeElement({ tag: "button", role: "button", text: "Go", ownerDocument: frameDocument })',
            {"text": None, "value": None},
        ),
        (
            "input",
            'makeElement({ tag: "input", type: "text", value: "", ownerDocument: frameDocument })',
            {"text": "openai", "value": None},
        ),
    ]:
        script = build_browser_action_script(
            action=action,
            index=1,
            timeout=1,
            state_token="tok-2",
            selector=None,
            **action_kwargs,
        )

        result = run_browser_action_script(
            script,
            f"""
const detachedIframe = {{ attached: false, ownerDocument: document }};
const frameWindow = {{ ...window, frameElement: detachedIframe, parent: window }};
const frameDocument = {{
  defaultView: frameWindow,
  contains: (el) => Boolean(el && el.attached !== false && el.ownerDocument === frameDocument),
  querySelector: (_selector) => null,
  querySelectorAll: (_selector) => [],
}};
window.__GA_BROWSER_ACTION_STATE__ = {{ token: "tok-2", elements: [{target_js}] }};
""",
        )

        assert result["status"] == "failed"
        assert result["stage"] == "stale_index"


def test_browser_action_script_rejects_cached_target_with_null_owner_window():
    for action, target_js, action_kwargs in [
        (
            "click",
            'makeElement({ tag: "button", role: "button", text: "Go", ownerDocument: frameDocument })',
            {"text": None, "value": None},
        ),
        (
            "input",
            'makeElement({ tag: "input", type: "text", value: "", ownerDocument: frameDocument })',
            {"text": "openai", "value": None},
        ),
    ]:
        script = build_browser_action_script(
            action=action,
            index=1,
            timeout=1,
            state_token="tok-2",
            selector=None,
            **action_kwargs,
        )

        result = run_browser_action_script(
            script,
            f"""
const frameDocument = {{
  defaultView: null,
  contains: (el) => Boolean(el && el.attached !== false && el.ownerDocument === frameDocument),
  querySelector: (_selector) => null,
  querySelectorAll: (_selector) => [],
}};
window.__GA_BROWSER_ACTION_STATE__ = {{ token: "tok-2", elements: [{target_js}] }};
""",
        )

        assert result["status"] == "failed"
        assert result["stage"] == "stale_index"


def test_browser_action_script_wait_index_rejects_replaced_iframe_path():
    script = build_browser_action_script(
        action="wait_index",
        index=1,
        text=None,
        value=None,
        timeout=1,
        state_token="tok-2",
        selector='button[name="go"]',
        selector_tag="button",
        selector_role="button",
        selector_text="Go",
        frame_path=[0],
    )

    result = run_browser_action_script(
        script,
        """
const originalIframe = { attached: false, ownerDocument: document };
const originalFrameWindow = { ...window, frameElement: originalIframe, parent: window };
const originalFrameDocument = {
  defaultView: originalFrameWindow,
  contains: (el) => Boolean(el && el.attached !== false && el.ownerDocument === originalFrameDocument),
  querySelector: (_selector) => null,
  querySelectorAll: (_selector) => [],
};
const replacementFrameDocument = {
  defaultView: window,
  contains: (el) => Boolean(el && el.attached !== false && el.ownerDocument === replacementFrameDocument),
  querySelector: (_selector) => makeElement({
    tag: "button",
    role: "button",
    text: "Go",
    visible: true,
    ownerDocument: replacementFrameDocument
  }),
  querySelectorAll: (_selector) => [],
};
const replacementIframe = { attached: true, ownerDocument: document, contentDocument: replacementFrameDocument };
const cached = makeElement({
  tag: "button",
  role: "button",
  text: "Go",
  ownerDocument: originalFrameDocument
});
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [cached] };
document.querySelectorAll = (selector) => selector === "iframe, frame" ? [replacementIframe] : [];
""",
    )

    assert result["status"] == "failed"
    assert result["stage"] in {"stale_index", "frame_unavailable"}


def test_browser_action_script_wait_index_rejects_attached_iframe_replaced_document():
    script = build_browser_action_script(
        action="wait_index",
        index=1,
        text=None,
        value=None,
        timeout=1,
        state_token="tok-2",
        selector='button[name="go"]',
        selector_tag="button",
        selector_role="button",
        selector_text="Go",
        frame_path=[0],
    )

    result = run_browser_action_script(
        script,
        """
const iframe = makeElement({ tag: "iframe", ownerDocument: document });
const originalFrameWindow = { ...window, frameElement: iframe, parent: window };
const originalFrameDocument = {
  defaultView: originalFrameWindow,
  contains: (_el) => false,
  querySelector: (_selector) => null,
  querySelectorAll: (_selector) => [],
};
const replacementFrameDocument = {
  defaultView: window,
  contains: (el) => Boolean(el && el.attached !== false && el.ownerDocument === replacementFrameDocument),
  querySelector: (_selector) => makeElement({
    tag: "button",
    role: "button",
    text: "Go",
    visible: true,
    ownerDocument: replacementFrameDocument
  }),
  querySelectorAll: (_selector) => [],
};
iframe.contentDocument = replacementFrameDocument;
const cached = makeElement({
  tag: "button",
  role: "button",
  text: "Go",
  ownerDocument: originalFrameDocument
});
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [cached] };
document.querySelectorAll = (selector) => selector === "iframe, frame" ? [iframe] : [];
""",
    )

    assert result["status"] == "failed"
    assert result["stage"] == "stale_index"


def test_browser_action_script_rejects_nested_target_with_null_ancestor_window():
    script = build_browser_action_script(
        action="click",
        index=1,
        text=None,
        value=None,
        timeout=1,
        state_token="tok-2",
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
const parentFrameDocument = {
  defaultView: null,
  contains: (el) => Boolean(el && el.attached !== false && el.ownerDocument === parentFrameDocument),
  querySelector: (_selector) => null,
  querySelectorAll: (_selector) => [],
};
const childFrameElement = { attached: true, ownerDocument: parentFrameDocument };
const childFrameWindow = { ...window, frameElement: childFrameElement, parent: null };
const childFrameDocument = {
  defaultView: childFrameWindow,
  contains: (el) => Boolean(el && el.attached !== false && el.ownerDocument === childFrameDocument),
  querySelector: (_selector) => null,
  querySelectorAll: (_selector) => [],
};
const cached = makeElement({
  tag: "button",
  role: "button",
  text: "Go",
  ownerDocument: childFrameDocument
});
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [cached] };
""",
    )

    assert result["status"] == "failed"
    assert result["stage"] == "stale_index"


def test_browser_action_script_rejects_target_inside_hidden_parent_iframe():
    script = build_browser_action_script(
        action="click",
        index=1,
        text=None,
        value=None,
        timeout=1,
        state_token="tok-2",
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
const parentIframe = makeElement({ tag: "iframe", visible: false });
const parentFrameWindow = { ...window, frameElement: parentIframe, parent: window };
const parentFrameDocument = {
  defaultView: parentFrameWindow,
  contains: (el) => Boolean(el && el.attached !== false && el.ownerDocument === parentFrameDocument),
  querySelector: (_selector) => null,
  querySelectorAll: (_selector) => [],
};
const childIframe = makeElement({ tag: "iframe", ownerDocument: parentFrameDocument });
const childFrameWindow = { ...window, frameElement: childIframe, parent: parentFrameWindow };
const childFrameDocument = {
  defaultView: childFrameWindow,
  contains: (el) => Boolean(el && el.attached !== false && el.ownerDocument === childFrameDocument),
  querySelector: (_selector) => null,
  querySelectorAll: (_selector) => [],
};
const cached = makeElement({
  tag: "button",
  role: "button",
  text: "Go",
  ownerDocument: childFrameDocument
});
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [cached] };
""",
    )

    assert result["status"] == "failed"
    assert result["stage"] == "visibility"


def test_browser_action_script_rejects_target_inside_iframe_hidden_by_ancestor_container():
    script = build_browser_action_script(
        action="click",
        index=1,
        text=None,
        value=None,
        timeout=1,
        state_token="tok-2",
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
const hiddenContainer = makeElement({ tag: "div" });
hiddenContainer._style = { display: "none", visibility: "visible", opacity: "1" };
const iframe = makeElement({ tag: "iframe" });
iframe.parentElement = hiddenContainer;
const frameWindow = { ...window, frameElement: iframe, parent: window };
const frameDocument = {
  defaultView: frameWindow,
  contains: (el) => Boolean(el && el.attached !== false && el.ownerDocument === frameDocument),
  querySelector: (_selector) => null,
  querySelectorAll: (_selector) => [],
};
const cached = makeElement({
  tag: "button",
  role: "button",
  text: "Go",
  ownerDocument: frameDocument
});
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [cached] };
""",
    )

    assert result["status"] == "failed"
    assert result["stage"] == "visibility"


def test_browser_action_script_keys_without_index_rejects_hidden_frame_focus():
    script = build_browser_action_script(
        action="keys",
        index=None,
        text="Enter",
        value=None,
        timeout=1,
        state_token=None,
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
const hiddenIframe = makeElement({ tag: "iframe", visible: false });
const frameWindow = { ...window, frameElement: hiddenIframe, parent: window };
const frameInput = makeElement({ tag: "input", type: "text", value: "" });
const frameDocument = {
  defaultView: frameWindow,
  activeElement: frameInput,
  body: null,
  contains: (el) => Boolean(el && el.attached !== false && el.ownerDocument === frameDocument),
  querySelector: (_selector) => null,
  querySelectorAll: (_selector) => [],
};
frameDocument.body = makeElement({ tag: "body", ownerDocument: frameDocument });
frameInput.ownerDocument = frameDocument;
hiddenIframe.contentDocument = frameDocument;
document.activeElement = hiddenIframe;
global.__GA_TEST_PROBE__ = () => ({ frameEvents: frameInput.dispatched || [] });
""",
    )

    probe = result["probe"]
    result = result["result"]
    assert result["status"] == "failed"
    assert result["stage"] == "visibility"
    assert probe["frameEvents"] == []


def test_browser_action_script_keys_without_index_rejects_hidden_ancestor_frame_focus():
    script = build_browser_action_script(
        action="keys",
        index=None,
        text="Enter",
        value=None,
        timeout=1,
        state_token=None,
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
const hiddenOuterIframe = makeElement({ tag: "iframe", visible: false });
const outerWindow = { ...window, frameElement: hiddenOuterIframe, parent: window };
const innerIframe = makeElement({ tag: "iframe" });
const outerDocument = {
  defaultView: outerWindow,
  activeElement: innerIframe,
  body: null,
  contains: (el) => Boolean(el && el.attached !== false && el.ownerDocument === outerDocument),
  querySelector: (_selector) => null,
  querySelectorAll: (_selector) => [],
};
outerDocument.body = makeElement({ tag: "body", ownerDocument: outerDocument });
innerIframe.ownerDocument = outerDocument;

const innerWindow = { ...window, frameElement: innerIframe, parent: outerWindow };
const frameInput = makeElement({ tag: "input", type: "text", value: "" });
const innerDocument = {
  defaultView: innerWindow,
  activeElement: frameInput,
  body: null,
  contains: (el) => Boolean(el && el.attached !== false && el.ownerDocument === innerDocument),
  querySelector: (_selector) => null,
  querySelectorAll: (_selector) => [],
};
innerDocument.body = makeElement({ tag: "body", ownerDocument: innerDocument });
frameInput.ownerDocument = innerDocument;
hiddenOuterIframe.contentDocument = outerDocument;
innerIframe.contentDocument = innerDocument;
document.activeElement = hiddenOuterIframe;
global.__GA_TEST_PROBE__ = () => ({ frameEvents: frameInput.dispatched || [] });
""",
    )

    probe = result["probe"]
    result = result["result"]
    assert result["status"] == "failed"
    assert result["stage"] == "visibility"
    assert probe["frameEvents"] == []


def test_browser_action_script_keys_rejects_contenteditable_editing_key():
    script = build_browser_action_script(
        action="keys",
        index=None,
        text="Backspace",
        value=None,
        timeout=1,
        state_token=None,
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
const editor = makeElement({ tag: "div", text: "abc", contentEditable: true });
document.activeElement = editor;
""",
    )

    assert result["status"] == "failed"
    assert result["stage"] == "invalid_args"
    assert result["error"] == "Focused element is not editable."


def test_browser_action_script_keys_rejects_contenteditable_control_a():
    script = build_browser_action_script(
        action="keys",
        index=None,
        text="Control+A",
        value=None,
        timeout=1,
        state_token=None,
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
const editor = makeElement({ tag: "div", text: "abc", contentEditable: true });
document.activeElement = editor;
""",
    )

    assert result["status"] == "failed"
    assert result["stage"] == "invalid_args"
    assert result["error"] == "Focused element is not editable."


def test_browser_action_script_input_rejects_non_editable_button():
    script = build_browser_action_script(
        action="input",
        index=1,
        text="hello",
        value=None,
        timeout=1,
        state_token="tok-2",
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
const button = makeElement({ tag: "button", role: "button", text: "Submit" });
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [button] };
""",
    )

    assert result["status"] == "failed"
    assert result["stage"] == "invalid_args"


def test_browser_action_script_input_success_suggests_keys_without_index():
    script = build_browser_action_script(
        action="input",
        index=1,
        text="openai",
        value=None,
        timeout=1,
        state_token="tok-2",
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
const input = makeElement({ tag: "input", type: "text", value: "" });
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [input] };
""",
    )

    assert result["status"] == "success"
    assert result["result"] == "input_set"
    assert "without index" in result["next_action_hint"]
    assert "focused element" in result["next_action_hint"]
    assert result["suggested_next_action"] == {"action": "keys", "text": "Enter"}


def test_browser_action_script_input_detects_framework_rejected_value_setter():
    script = build_browser_action_script(
        action="input",
        index=1,
        text="1.00",
        value=None,
        timeout=1,
        state_token="tok-2",
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
const input = makeElement({ tag: "input", type: "text" });
let storedValue = "";
let attemptedValue = "";
Object.defineProperty(input, "value", {
  get() {
    return storedValue;
  },
  set(nextValue) {
    attemptedValue = nextValue;
  },
  configurable: true,
});
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [input] };
global.__GA_TEST_PROBE__ = () => ({ storedValue, attemptedValue });
""",
    )

    probe = result["probe"]
    result = result["result"]
    assert result["status"] == "failed"
    assert result["stage"] == "dom_event"
    assert result["error"] == "Input value was not accepted."
    assert probe == {"storedValue": "", "attemptedValue": "1.00"}


def test_browser_action_script_native_select_still_selects_option():
    script = build_browser_action_script(
        action="select",
        index=1,
        text=None,
        value="us",
        timeout=1,
        state_token="tok-2",
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
const select = makeElement({ tag: "select", value: "" });
select.options = [
  { value: "ca", text: "Canada" },
  { value: "us", text: "United States" },
];
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [select] };
""",
    )

    assert result["status"] == "success"
    assert result["result"] == "us"


def test_browser_action_script_select_rejects_disabled_native_option():
    script = build_browser_action_script(
        action="select",
        index=1,
        text=None,
        value="us",
        timeout=1,
        state_token="tok-2",
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
const select = makeElement({ tag: "select", value: "" });
select.options = [
  { value: "ca", text: "Canada", disabled: false },
  { value: "us", text: "United States", disabled: true },
];
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [select] };
""",
    )

    assert result["status"] == "failed"
    assert result["stage"] == "visibility"
    assert "option is disabled" in result["error"]


def test_browser_action_script_select_rejects_disabled_optgroup_option():
    script = build_browser_action_script(
        action="select",
        index=1,
        text=None,
        value="us",
        timeout=1,
        state_token="tok-2",
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
const select = makeElement({ tag: "select", value: "" });
const group = makeElement({ tag: "optgroup", disabled: true });
select.options = [
  { value: "us", text: "United States", disabled: false, parentElement: group },
];
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [select] };
""",
    )

    assert result["status"] == "failed"
    assert result["stage"] == "visibility"
    assert "optgroup is disabled" in result["error"]


def test_browser_action_script_select_rejects_custom_combobox_with_click_hint():
    script = build_browser_action_script(
        action="select",
        index=3,
        text=None,
        value="Admin",
        timeout=1,
        state_token="tok-2",
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
const combo = makeElement({
  tag: "div",
  role: "combobox",
  attrs: { "aria-haspopup": "listbox" },
});
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [null, null, combo] };
""",
    )

    assert result["status"] == "failed"
    assert result["stage"] == "control_unsupported"
    assert result["retryable"] is True
    assert "custom" in result["hint"]
    assert result["suggested_next_action"] == {"action": "click", "index": 3}


def test_browser_action_script_select_rejects_custom_option_with_click_hint():
    script = build_browser_action_script(
        action="select",
        index=1,
        text=None,
        value="Admin",
        timeout=1,
        state_token="tok-2",
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
const option = makeElement({ tag: "div", role: "option" });
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [option] };
""",
    )

    assert result["status"] == "failed"
    assert result["stage"] == "control_unsupported"
    assert result["retryable"] is True
    assert "custom option" in result["hint"]
    assert result["suggested_next_action"] == {"action": "click", "index": 1}


def test_browser_action_script_select_rejects_custom_listbox_without_clicking_container():
    script = build_browser_action_script(
        action="select",
        index=1,
        text=None,
        value="Admin",
        timeout=1,
        state_token="tok-2",
        selector=None,
    )

    result = run_browser_action_script(
        script,
        """
const listbox = makeElement({ tag: "div", role: "listbox" });
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [listbox] };
""",
    )

    assert result["status"] == "failed"
    assert result["stage"] == "control_unsupported"
    assert result["retryable"] is True
    assert "visible child option" in result["hint"]
    assert "suggested_next_action" not in result
    assert "visible child option" in result["suggested_next_step"]


def test_browser_action_script_input_verify_field_value_success():
    script = build_browser_action_script(
        action="input",
        index=1,
        text="openai",
        value=None,
        timeout=1,
        state_token="tok-2",
        selector=None,
        verify="field_value",
    )

    result = run_browser_action_script(
        script,
        """
const input = makeElement({ tag: "input", type: "text", value: "" });
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [input] };
""",
    )

    assert result["status"] == "success"
    assert result["verification"] == {
        "type": "field_value",
        "observed": "openai",
        "expected": "openai",
        "passed": True,
    }
    assert result["verify_hint"] == "Use verify='field_value' with verify_value to require the field value after input."


def test_browser_action_script_input_contenteditable_verify_field_value_success():
    script = build_browser_action_script(
        action="input",
        index=1,
        text="rich text update",
        value=None,
        timeout=1,
        state_token="tok-2",
        selector=None,
        verify="field_value",
    )

    result = run_browser_action_script(
        script,
        """
global.InputEvent = function InputEvent(type, options = {}) {
  this.type = type;
  this.inputType = options.inputType || "";
  this.data = options.data || null;
  this.options = options;
};
const editor = makeElement({ tag: "div", text: "seed", contentEditable: true });
const events = [];
editor.dispatchEvent = (event) => {
  events.push({
    type: event.type,
    inputType: event.inputType || "",
    data: event.data || null,
    bubbles: Boolean(event.options && event.options.bubbles),
    cancelable: Boolean(event.options && event.options.cancelable),
  });
  return true;
};
global.__GA_TEST_PROBE__ = () => ({ events, innerText: editor.innerText, textContent: editor.textContent });
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [editor] };
""",
    )

    probe = result["probe"]
    result = result["result"]
    assert result["status"] == "success"
    assert result["verification"] == {
        "type": "field_value",
        "observed": "rich text update",
        "expected": "rich text update",
        "passed": True,
    }
    assert probe["innerText"] == "rich text update"
    assert probe["textContent"] == "rich text update"
    assert [event["type"] for event in probe["events"]] == ["beforeinput", "input", "change"]
    assert probe["events"][0] == {
        "type": "beforeinput",
        "inputType": "insertText",
        "data": "rich text update",
        "bubbles": True,
        "cancelable": True,
    }
    assert probe["events"][1] == {
        "type": "input",
        "inputType": "insertText",
        "data": "rich text update",
        "bubbles": True,
        "cancelable": False,
    }


def test_browser_action_script_input_designmode_iframe_body_verify_field_value_success():
    script = build_browser_action_script(
        action="input",
        index=1,
        text="design mode update",
        value=None,
        timeout=1,
        state_token="tok-2",
        selector=None,
        verify="field_value",
    )

    result = run_browser_action_script(
        script,
        """
global.InputEvent = function InputEvent(type, options = {}) {
  this.type = type;
  this.inputType = options.inputType || "";
  this.data = options.data || null;
  this.options = options;
};
const iframe = makeElement({ tag: "iframe" });
const frameWindow = { ...window, frameElement: iframe, parent: window };
const frameDocument = {
  defaultView: frameWindow,
  designMode: "on",
  contains: (el) => Boolean(el && el.attached !== false && el.ownerDocument === frameDocument),
  querySelector: (_selector) => null,
  querySelectorAll: (_selector) => [],
};
const editorBody = makeElement({ tag: "body", text: "seed", ownerDocument: frameDocument });
frameDocument.body = editorBody;
const events = [];
editorBody.dispatchEvent = (event) => {
  events.push(event.type);
  return true;
};
global.__GA_TEST_PROBE__ = () => ({
  events,
  innerText: editorBody.innerText,
  textContent: editorBody.textContent,
});
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [editorBody] };
""",
    )

    probe = result["probe"]
    result = result["result"]
    assert result["status"] == "success"
    assert result["verification"] == {
        "type": "field_value",
        "observed": "design mode update",
        "expected": "design mode update",
        "passed": True,
    }
    assert probe == {
        "events": ["beforeinput", "input", "change"],
        "innerText": "design mode update",
        "textContent": "design mode update",
    }


def test_browser_action_script_input_contenteditable_fails_when_beforeinput_canceled():
    script = build_browser_action_script(
        action="input",
        index=1,
        text="rich text update",
        value=None,
        timeout=1,
        state_token="tok-2",
        selector=None,
        verify="field_value",
    )

    result = run_browser_action_script(
        script,
        """
global.InputEvent = function InputEvent(type, options = {}) {
  this.type = type;
  this.inputType = options.inputType || "";
  this.data = options.data || null;
  this.options = options;
};
const editor = makeElement({ tag: "div", text: "seed", contentEditable: true });
const events = [];
editor.dispatchEvent = (event) => {
  events.push(event.type);
  return event.type !== "beforeinput";
};
global.__GA_TEST_PROBE__ = () => ({ events, innerText: editor.innerText, textContent: editor.textContent });
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [editor] };
""",
    )

    probe = result["probe"]
    result = result["result"]
    assert result["status"] == "failed"
    assert result["stage"] == "dom_event"
    assert "rejected synthetic DOM input" in result["error"]
    assert "lower-level CDP" in result["hint"]
    assert probe == {
        "events": ["beforeinput"],
        "innerText": "seed",
        "textContent": "seed",
    }


def test_browser_action_script_input_verify_field_value_failure():
    script = build_browser_action_script(
        action="input",
        index=1,
        text="openai",
        value=None,
        timeout=1,
        state_token="tok-2",
        selector=None,
        verify="field_value",
        verify_value="expected",
    )

    result = run_browser_action_script(
        script,
        """
const input = makeElement({ tag: "input", type: "text", value: "" });
window.__GA_BROWSER_ACTION_STATE__ = { token: "tok-2", elements: [input] };
""",
    )

    assert result["status"] == "failed"
    assert result["stage"] == "verify_failed"
    assert result["observed"] == "openai"
    assert result["expected"] == "expected"
    assert result["retryable"] is True
    assert result["verification"] == {
        "type": "field_value",
        "observed": "openai",
        "expected": "expected",
        "passed": False,
    }


def test_build_browser_action_script_input_uses_native_setter_and_verifies_value():
    script = build_browser_action_script(
        action="input",
        index=3,
        text="hello",
        value=None,
        timeout=4,
        state_token="tok-2",
        selector=None,
    )

    assert 'Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), "value")?.set' in script
    assert "valueSetter.call(el, nextValue)" in script
    assert 'if ("value" in el && el.value !== nextValue)' in script
    assert 'return fail("dom_event", "Input value was not accepted.")' in script


def test_run_action_state_missing_includes_structured_recovery():
    layer = BrowserActionLayer()
    driver = FakeDriver([])

    result = layer.run_action(driver, action="click", index=3)

    assert result["stage"] == "state_missing"
    assert result["recovery"]["code"] == "refresh_state"
    assert result["recovery"]["next_tool"] == "browser_state"


def test_run_action_stale_tab_includes_find_recovery():
    layer = BrowserActionLayer()
    layer._last_state = {"tab_id": "old-tab", "state_token": "tok", "elements_by_index": {1: {"index": 1}}}
    driver = FakeDriver([])
    driver.default_session_id = "new-tab"

    result = layer.run_action(driver, action="click", index=1)

    assert result["stage"] == "stale_index"
    assert result["recovery"]["code"] == "refresh_state_then_find"
    assert result["recovery"]["next_tool"] == "browser_find"


def test_run_action_blocks_third_repeated_failure():
    layer = BrowserActionLayer()
    driver = FakeDriver([])

    first = layer.run_action(driver, action="click", index=9)
    second = layer.run_action(driver, action="click", index=9)
    third = layer.run_action(driver, action="click", index=9)

    assert first["stage"] == "state_missing"
    assert second["recovery"]["stop_retry"] is True
    assert third["stage"] == "repeat_blocked"
    assert third["recovery"]["code"] == "stop_repeating"


def test_run_action_blocks_repeated_failure_even_after_state_refresh():
    layer = BrowserActionLayer()
    state_payload = {
        "status": "success",
        "state_token": "tok-1",
        "url": "https://example.test/form",
        "elements": [
            {"index": 1, "text": "Save", "labels": [], "visible": True, "disabled": False, "stable_key": "button#save", "selector_hint": "button#save"}
        ],
    }
    driver = FakeDriver(
        [
            state_payload,
            {"data": {"status": "failed", "stage": "dom_event", "error": "boom"}},
            state_payload,
            {"data": {"status": "failed", "stage": "dom_event", "error": "boom"}},
            state_payload,
        ]
    )

    layer.get_state(driver)
    first = layer.run_action(driver, action="click", index=1)
    layer.get_state(driver)
    second = layer.run_action(driver, action="click", index=1)
    layer.get_state(driver)
    third = layer.run_action(driver, action="click", index=1)

    assert first["stage"] == "dom_event"
    assert second["recovery"]["stop_retry"] is True
    assert third["stage"] == "repeat_blocked"
    assert len(driver.calls) == 5


def test_run_action_preflight_blocks_third_repeated_js_failure_before_execute():
    layer = BrowserActionLayer()
    layer._last_state = {
        "tab_id": "7",
        "state_token": "tok-1",
        "elements_by_index": {
            1: {"index": 1, "stable_key": "button#save", "selector_hint": "button#save", "text": "Save"}
        },
    }
    driver = FakeDriver(
        [
            {"data": {"status": "failed", "stage": "dom_event", "error": "boom"}},
            {"data": {"status": "failed", "stage": "dom_event", "error": "boom"}},
        ]
    )

    first = layer.run_action(driver, action="click", index=1)
    second = layer.run_action(driver, action="click", index=1)
    third = layer.run_action(driver, action="click", index=1)

    assert first["stage"] == "dom_event"
    assert second["recovery"]["stop_retry"] is True
    assert third["stage"] == "repeat_blocked"
    assert len(driver.calls) == 2


def test_run_action_repeat_blocked_verify_failure_page_change_invalidates_state():
    layer = BrowserActionLayer()
    cached_state = {
        "tab_id": "7",
        "state_token": "tok-1",
        "elements_by_index": {
            1: {"index": 1, "stable_key": "button#save", "selector_hint": "button#save", "text": "Save"},
            2: {"index": 2, "stable_key": "button#cancel", "selector_hint": "button#cancel", "text": "Cancel"},
        },
    }
    driver = FakeDriver(
        [
            {
                "data": {
                    "status": "failed",
                    "stage": "verify_failed",
                    "page_changed": True,
                    "error": "not verified",
                }
            },
            {
                "data": {
                    "status": "failed",
                    "stage": "verify_failed",
                    "page_changed": True,
                    "error": "not verified",
                }
            },
            {
                "data": {
                    "status": "failed",
                    "stage": "verify_failed",
                    "page_changed": True,
                    "error": "not verified",
                }
            },
        ]
    )

    layer._last_state = dict(cached_state)
    first = layer.run_action(driver, action="click", index=1)
    layer._last_state = dict(cached_state)
    second = layer.run_action(driver, action="click", index=1)
    layer._last_state = dict(cached_state)
    third = layer.run_action(driver, action="click", index=1)

    assert first["stage"] == "verify_failed"
    assert second["recovery"]["stop_retry"] is True
    assert third["stage"] == "repeat_blocked"
    assert layer.last_state_token is None


def test_run_action_success_resets_fuse_for_js_failures():
    layer = BrowserActionLayer()
    layer._last_state = {
        "tab_id": "7",
        "state_token": "tok-1",
        "elements_by_index": {
            1: {"index": 1, "stable_key": "button#save", "selector_hint": "button#save", "text": "Save"}
        },
    }
    driver = FakeDriver(
        [
            {"data": {"status": "failed", "stage": "dom_event", "error": "boom"}},
            {"data": {"status": "failed", "stage": "dom_event", "error": "boom"}},
            {"data": {"status": "success", "action": "wait_index", "index": 1, "result": "element_visible"}},
            {"data": {"status": "failed", "stage": "dom_event", "error": "boom"}},
        ]
    )

    first = layer.run_action(driver, action="wait_index", index=1)
    second = layer.run_action(driver, action="wait_index", index=1)
    success = layer.run_action(driver, action="wait_index", index=2)
    after_success = layer.run_action(driver, action="wait_index", index=1)

    assert first["recovery"]["stop_retry"] is False
    assert second["recovery"]["stop_retry"] is True
    assert success["status"] == "success"
    assert after_success["stage"] == "dom_event"
    assert after_success["recovery"]["stop_retry"] is False
