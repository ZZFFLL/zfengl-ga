import json
import subprocess

from browser_actions import BrowserActionLayer, build_browser_action_script


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
  console.log(JSON.stringify(result));
})().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
""",
        ]
    )
    completed = subprocess.run(
        ["node", "-e", node_code],
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

    assert result == {
        "status": "failed",
        "action": "click",
        "index": 1,
        "stage": "state_missing",
        "error": "Run browser_state before browser_action click.",
    }


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
    assert 'return visible(target) ? target : null;' in script


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
    assert "else if (isContentEditableTarget(el))" in script


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
