# GA Browser Action Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add browser-use style `state -> indexed element -> action` browser tools to GenericAgent while keeping GA's existing real-user Chrome bridge and login-state behavior.

**Architecture:** Add a small Browser Action Layer above `TMWebDriver + assets/tmwd_cdp_bridge`. `browser_indexer.py` builds a current-tab interactive element snapshot, `browser_actions.py` executes bounded indexed actions against that snapshot, and `ga.py` exposes the layer as new tools without changing `web_scan` or `web_execute_js`.

**Tech Stack:** Python, pytest, existing GenericAgent tool handler model, existing `TMWebDriver.execute_js(...)` browser bridge, existing WebUI execution-log parser tests.

---

## Scope And Success Criteria

- Add new tools only: `browser_state` and `browser_action`.
- Do not replace or change `web_scan`.
- Do not replace or change `web_execute_js`.
- Do not modify `E:\zfengl-ai-project\browser-use`.
- Do not require Chrome remote debugging or a browser-use managed Chromium.
- Reuse the user's already-open Chrome session through the existing GA extension bridge.
- Return structured failures for unavailable browser, missing state, stale index, invalid arguments, DOM action failure, and timeout.
- Keep P0 bounded to `click`, `input`, `select`, `keys`, `wait_index`, `wait_text`, and `wait_selector`.

---

## File Map

- Create: `browser_indexer.py`
  - Owns JavaScript generation for current-tab indexed element state.
  - Owns Python-side normalization of state output.

- Create: `browser_actions.py`
  - Owns `BrowserActionLayer`.
  - Owns state cache, argument checks, driver availability checks, and action JavaScript generation.

- Create: `tests/test_browser_indexer.py`
  - Tests state script characteristics and normalization.

- Create: `tests/test_browser_actions.py`
  - Tests driver-unavailable errors, state caching, stale-state behavior, action script dispatch, and wait actions with a fake driver.

- Create: `tests/test_browser_tool_handlers.py`
  - Tests `ga.py` handler behavior without launching a real browser.

- Create: `tests/test_browser_tool_schemas.py`
  - Tests both English and Chinese tool schema files expose the new tools with bounded enums.

- Modify: `ga.py`
  - Import `BrowserActionLayer`.
  - Add module-level `browser_action_layer`.
  - Add `browser_state(...)` and `browser_action(...)` helper functions.
  - Add `GenericAgentHandler.do_browser_state(...)`.
  - Add `GenericAgentHandler.do_browser_action(...)`.

- Modify: `assets/tools_schema.json`
  - Add `browser_state`.
  - Add `browser_action`.

- Modify: `assets/tools_schema_cn.json`
  - Add Chinese descriptions for `browser_state`.
  - Add Chinese descriptions for `browser_action`.

- Modify: `tests/test_webui_server.py`
  - Add execution-display contract tests for `browser_state` and `browser_action`.

---

### Task 1: Browser State Indexer

**Files:**
- Create: `browser_indexer.py`
- Create: `tests/test_browser_indexer.py`

- [ ] **Step 1: Write failing tests for the indexer module**

Create `tests/test_browser_indexer.py` with:

```python
import pytest

from browser_indexer import build_browser_state_script, normalize_state_result


def test_build_browser_state_script_contains_index_state_and_limit():
    script = build_browser_state_script(include_invisible=False, max_elements=3)

    assert "window.__GA_BROWSER_ACTION_STATE__" in script
    assert "const maxElements = 3;" in script
    assert "const includeInvisible = false;" in script
    assert "a[href]" in script
    assert "[contenteditable=\"true\"]" in script


def test_build_browser_state_script_clamps_max_elements():
    low = build_browser_state_script(max_elements=0)
    high = build_browser_state_script(max_elements=9999)

    assert "const maxElements = 1;" in low
    assert "const maxElements = 500;" in high


def test_normalize_state_result_adds_indices_and_defaults():
    raw = {
        "status": "success",
        "backend": "tmwd_user_chrome",
        "tab_id": "11",
        "url": "https://example.test",
        "title": "Example",
        "state_token": "abc",
        "viewport": {"width": 1280, "height": 720},
        "elements": [
            {"tag": "button", "text": "Submit", "bbox": {"x": 1, "y": 2, "width": 3, "height": 4}},
            {"index": 7, "tag": "input", "value": "secret", "type": "password"},
        ],
    }

    state = normalize_state_result(raw)

    assert state["status"] == "success"
    assert state["backend"] == "tmwd_user_chrome"
    assert state["tab_id"] == "11"
    assert state["state_token"] == "abc"
    assert state["elements"][0]["index"] == 1
    assert state["elements"][0]["visible"] is True
    assert state["elements"][0]["disabled"] is False
    assert state["elements"][1]["index"] == 7
    assert state["elements"][1]["value"] == "[REDACTED]"


def test_normalize_state_result_rejects_non_dict():
    state = normalize_state_result("not a dict")

    assert state == {
        "status": "failed",
        "stage": "dom_event",
        "error": "browser_state returned a non-object result",
    }


def test_normalize_state_result_preserves_failed_result():
    state = normalize_state_result({
        "status": "failed",
        "stage": "browser_unavailable",
        "error": "no tab",
    })

    assert state == {
        "status": "failed",
        "stage": "browser_unavailable",
        "error": "no tab",
    }
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_browser_indexer.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'browser_indexer'
```

- [ ] **Step 3: Implement the minimal indexer module**

Create `browser_indexer.py` with:

```python
from __future__ import annotations

import json
from typing import Any


DEFAULT_MAX_ELEMENTS = 120
MIN_MAX_ELEMENTS = 1
MAX_MAX_ELEMENTS = 500

INTERACTIVE_SELECTOR = ",".join(
    [
        "a[href]",
        "button",
        "input",
        "textarea",
        "select",
        "[role=\"button\"]",
        "[role=\"link\"]",
        "[contenteditable=\"true\"]",
        "[onclick]",
    ]
)


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def build_browser_state_script(
    include_invisible: bool = False,
    max_elements: int = DEFAULT_MAX_ELEMENTS,
) -> str:
    limit = _clamp_int(max_elements, DEFAULT_MAX_ELEMENTS, MIN_MAX_ELEMENTS, MAX_MAX_ELEMENTS)
    include = "true" if include_invisible else "false"
    selector = json.dumps(INTERACTIVE_SELECTOR)

    return f"""
(() => {{
  const includeInvisible = {include};
  const maxElements = {limit};
  const interactiveSelector = {selector};
  const stateToken = String(Date.now()) + "-" + Math.random().toString(36).slice(2);
  const elements = [];

  function textOf(el) {{
    const raw = [
      el.getAttribute("aria-label"),
      el.getAttribute("placeholder"),
      el.getAttribute("title"),
      el.innerText,
      el.textContent,
      el.value
    ].filter(Boolean).join(" ").replace(/\\s+/g, " ").trim();
    return raw.slice(0, 240);
  }}

  function visibleOf(el) {{
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    if (style.display === "none" || style.visibility === "hidden") return false;
    if (Number(style.opacity || "1") === 0) return false;
    if (rect.width <= 0 || rect.height <= 0) return false;
    const vw = window.innerWidth || document.documentElement.clientWidth || 0;
    const vh = window.innerHeight || document.documentElement.clientHeight || 0;
    const intersectsViewport = rect.bottom >= 0 && rect.right >= 0 && rect.top <= vh && rect.left <= vw;
    return intersectsViewport || el.scrollIntoView !== undefined;
  }}

  function selectorHint(el) {{
    if (el.id) return "#" + CSS.escape(el.id);
    const dataTest = el.getAttribute("data-testid") || el.getAttribute("data-test");
    if (dataTest) return el.tagName.toLowerCase() + "[data-testid=\\"" + dataTest.replace(/"/g, "\\\\\\"") + "\\"]";
    const name = el.getAttribute("name");
    if (name) return el.tagName.toLowerCase() + "[name=\\"" + name.replace(/"/g, "\\\\\\"") + "\\"]";
    const cls = String(el.className || "").split(/\\s+/).filter(Boolean).slice(0, 2).map(CSS.escape).join(".");
    return cls ? el.tagName.toLowerCase() + "." + cls : el.tagName.toLowerCase();
  }}

  function roleOf(el) {{
    return el.getAttribute("role") || (
      el.tagName === "A" ? "link" :
      el.tagName === "BUTTON" ? "button" :
      el.tagName === "SELECT" ? "combobox" :
      el.tagName === "TEXTAREA" ? "textbox" :
      el.tagName === "INPUT" ? "textbox" : ""
    );
  }}

  const nodes = Array.from(document.querySelectorAll(interactiveSelector));
  for (const el of nodes) {{
    if (elements.length >= maxElements) break;
    const visible = visibleOf(el);
    if (!includeInvisible && !visible) continue;
    const rect = el.getBoundingClientRect();
    const type = (el.getAttribute("type") || "").toLowerCase();
    elements.push(el);
  }}

  window.__GA_BROWSER_ACTION_STATE__ = {{ token: stateToken, elements }};

  return {{
    status: "success",
    backend: "tmwd_user_chrome",
    tab_id: null,
    url: location.href,
    title: document.title,
    state_token: stateToken,
    viewport: {{
      width: window.innerWidth,
      height: window.innerHeight,
      scroll_x: window.scrollX,
      scroll_y: window.scrollY
    }},
    elements: elements.map((el, i) => {{
      const rect = el.getBoundingClientRect();
      const type = (el.getAttribute("type") || "").toLowerCase();
      return {{
        index: i + 1,
        tag: el.tagName.toLowerCase(),
        type,
        role: roleOf(el),
        text: textOf(el),
        value: type === "password" ? "[REDACTED]" : String(el.value || "").slice(0, 240),
        visible: visibleOf(el),
        disabled: Boolean(el.disabled || el.getAttribute("aria-disabled") === "true"),
        bbox: {{
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          width: Math.round(rect.width),
          height: Math.round(rect.height)
        }},
        selector_hint: selectorHint(el)
      }};
    }})
  }};
}})();
""".strip()


def normalize_state_result(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {
            "status": "failed",
            "stage": "dom_event",
            "error": "browser_state returned a non-object result",
        }

    if raw.get("status") == "failed":
        return {
            "status": "failed",
            "stage": str(raw.get("stage") or "dom_event"),
            "error": str(raw.get("error") or "browser_state failed"),
        }

    elements = []
    for position, item in enumerate(raw.get("elements") or [], start=1):
        if not isinstance(item, dict):
            continue
        element = {
            "index": item.get("index") or position,
            "tag": str(item.get("tag") or ""),
            "type": str(item.get("type") or ""),
            "role": str(item.get("role") or ""),
            "text": str(item.get("text") or ""),
            "value": "[REDACTED]" if item.get("type") == "password" else str(item.get("value") or ""),
            "visible": bool(item.get("visible", True)),
            "disabled": bool(item.get("disabled", False)),
            "bbox": item.get("bbox") if isinstance(item.get("bbox"), dict) else {},
            "selector_hint": str(item.get("selector_hint") or ""),
        }
        elements.append(element)

    return {
        "status": "success",
        "backend": str(raw.get("backend") or "tmwd_user_chrome"),
        "tab_id": raw.get("tab_id"),
        "url": str(raw.get("url") or ""),
        "title": str(raw.get("title") or ""),
        "state_token": str(raw.get("state_token") or ""),
        "viewport": raw.get("viewport") if isinstance(raw.get("viewport"), dict) else {},
        "elements": elements,
    }
```

- [ ] **Step 4: Run indexer tests and confirm pass**

Run:

```powershell
python -m pytest tests/test_browser_indexer.py -q
```

Expected:

```text
5 passed
```

- [ ] **Step 5: Commit task 1**

Run:

```powershell
git add browser_indexer.py tests/test_browser_indexer.py
git commit -m "feat: add browser state indexer"
```

Expected:

```text
[ga-browser-use ...] feat: add browser state indexer
```

---

### Task 2: Browser Action Layer

**Files:**
- Create: `browser_actions.py`
- Create: `tests/test_browser_actions.py`

- [ ] **Step 1: Write failing tests for action orchestration**

Create `tests/test_browser_actions.py` with:

```python
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


def test_get_state_returns_browser_unavailable_when_no_sessions():
    layer = BrowserActionLayer()
    driver = FakeDriver(sessions=[])

    result = layer.get_state(driver)

    assert result["status"] == "failed"
    assert result["stage"] == "browser_unavailable"
    assert "没有可用的浏览器标签页" in result["error"]


def test_get_state_executes_indexer_and_caches_state_token():
    layer = BrowserActionLayer()
    driver = FakeDriver([
        {
            "data": {
                "status": "success",
                "state_token": "tok-1",
                "elements": [{"index": 1, "tag": "button", "text": "Go"}],
            }
        }
    ])

    result = layer.get_state(driver, max_elements=5)

    assert result["status"] == "success"
    assert result["tab_id"] == "7"
    assert layer.last_state_token == "tok-1"
    assert "const maxElements = 5;" in driver.calls[0]["script"]


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
    driver = FakeDriver([
        {"data": {"status": "success", "action": "click", "index": 2, "result": "clicked"}}
    ])

    result = layer.run_action(driver, action="click", index=2)

    assert result["status"] == "success"
    assert result["tab_id"] == "7"
    assert '"state_token": "tok-1"' in driver.calls[0]["script"]
    assert '"action": "click"' in driver.calls[0]["script"]
    assert layer.last_state_token is None


def test_run_action_allows_wait_text_without_cached_state():
    layer = BrowserActionLayer()
    driver = FakeDriver([
        {"data": {"status": "success", "action": "wait_text", "result": "text_found"}}
    ])

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
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_browser_actions.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'browser_actions'
```

- [ ] **Step 3: Implement action layer and action script builder**

Create `browser_actions.py` with:

```python
from __future__ import annotations

import json
from typing import Any

from browser_indexer import build_browser_state_script, normalize_state_result


SUPPORTED_ACTIONS = {
    "click",
    "input",
    "select",
    "keys",
    "wait_index",
    "wait_text",
    "wait_selector",
}

INDEX_REQUIRED_ACTIONS = {"click", "input", "select", "wait_index"}
STATE_MUTATING_ACTIONS = {"click", "input", "select", "keys"}


def failed_result(action: str | None, stage: str, error: str, index: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "failed", "stage": stage, "error": error}
    if action:
        result["action"] = action
    if index is not None:
        result["index"] = index
    return result


def _response_payload(response: Any) -> Any:
    if isinstance(response, dict):
        if "data" in response:
            return response["data"]
        if "result" in response:
            return response["result"]
    return response


def _safe_timeout(value: Any) -> int:
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        timeout = 10
    return max(1, min(60, timeout))


def _safe_index(value: Any) -> int | None:
    try:
        index = int(value)
    except (TypeError, ValueError):
        return None
    return index if index > 0 else None


def build_browser_action_script(
    *,
    action: str,
    index: int | None,
    text: str | None,
    value: str | None,
    timeout: int,
    state_token: str | None,
    selector: str | None,
) -> str:
    request = {
        "action": action,
        "index": index,
        "text": text,
        "value": value,
        "timeout": timeout,
        "state_token": state_token,
        "selector": selector,
    }
    request_json = json.dumps(request, ensure_ascii=False)

    return f"""
(async () => {{
  const request = {request_json};
  const deadline = Date.now() + Math.max(1, Number(request.timeout || 10)) * 1000;
  const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

  function fail(stage, error) {{
    return {{ status: "failed", action: request.action, index: request.index, stage, error }};
  }}

  function visible(el) {{
    if (!el || !document.contains(el)) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== "none" &&
      style.visibility !== "hidden" &&
      Number(style.opacity || "1") !== 0 &&
      rect.width > 0 &&
      rect.height > 0;
  }}

  function cachedElement() {{
    const state = window.__GA_BROWSER_ACTION_STATE__;
    if (!state || !state.token) return {{ error: fail("state_missing", "Run browser_state before indexed browser_action.") }};
    if (state.token !== request.state_token) return {{ error: fail("stale_index", "Element index is stale. Run browser_state again.") }};
    const el = state.elements && state.elements[Number(request.index) - 1];
    if (!el || !document.contains(el)) return {{ error: fail("stale_index", "Element index is stale. Run browser_state again.") }};
    return {{ el }};
  }}

  async function waitFor(predicate, stage, message) {{
    while (Date.now() <= deadline) {{
      const value = predicate();
      if (value) return value;
      await sleep(100);
    }}
    return {{ error: fail(stage, message) }};
  }}

  function dispatchInputEvents(el) {{
    el.dispatchEvent(new Event("input", {{ bubbles: true }}));
    el.dispatchEvent(new Event("change", {{ bubbles: true }}));
  }}

  function keyboardEvent(target, type, key) {{
    target.dispatchEvent(new KeyboardEvent(type, {{ key, bubbles: true, cancelable: true }}));
  }}

  try {{
    if (request.action === "wait_text") {{
      if (!request.text) return fail("invalid_args", "text is required for wait_text.");
      const waited = await waitFor(
        () => document.body && document.body.innerText.includes(request.text),
        "timeout",
        "Timed out waiting for text."
      );
      if (waited && waited.error) return waited.error;
      return {{ status: "success", action: "wait_text", result: "text_found" }};
    }}

    if (request.action === "wait_selector") {{
      if (!request.selector) return fail("invalid_args", "selector is required for wait_selector.");
      const waited = await waitFor(
        () => document.querySelector(request.selector),
        "timeout",
        "Timed out waiting for selector."
      );
      if (waited && waited.error) return waited.error;
      return {{ status: "success", action: "wait_selector", result: "selector_found" }};
    }}

    const located = cachedElement();
    if (located.error) return located.error;
    const el = located.el;

    if (request.action === "wait_index") {{
      const waited = await waitFor(
        () => visible(el),
        "timeout",
        "Timed out waiting for element index."
      );
      if (waited && waited.error) return waited.error;
      return {{ status: "success", action: "wait_index", index: request.index, result: "element_visible" }};
    }}

    el.scrollIntoView({{ block: "center", inline: "center", behavior: "instant" }});
    await sleep(50);
    if (!visible(el)) return fail("visibility", "Element is not visible.");

    if (request.action === "click") {{
      el.focus({{ preventScroll: true }});
      el.click();
      return {{ status: "success", action: "click", index: request.index, result: "clicked", page_changed: true }};
    }}

    if (request.action === "input") {{
      if (request.text === null && request.value === null) return fail("invalid_args", "text or value is required for input.");
      const nextValue = String(request.text !== null ? request.text : request.value);
      el.focus({{ preventScroll: true }});
      if ("value" in el) {{
        el.value = nextValue;
      }} else {{
        el.textContent = nextValue;
      }}
      dispatchInputEvents(el);
      const inputType = String(el.getAttribute("type") || "").toLowerCase();
      return {{
        status: "success",
        action: "input",
        index: request.index,
        result: inputType === "password" ? "[REDACTED]" : "input_set",
        page_changed: true
      }};
    }}

    if (request.action === "select") {{
      const wanted = String(request.value !== null ? request.value : request.text || "");
      if (!wanted) return fail("invalid_args", "value or text is required for select.");
      if (el.tagName !== "SELECT") return fail("invalid_args", "select action requires a select element.");
      const option = Array.from(el.options).find(opt => opt.value === wanted || opt.text.trim() === wanted);
      if (!option) return fail("locate", "No matching option found.");
      el.value = option.value;
      dispatchInputEvents(el);
      return {{ status: "success", action: "select", index: request.index, result: option.value, page_changed: true }};
    }}

    if (request.action === "keys") {{
      const key = String(request.text || request.value || "");
      if (!key) return fail("invalid_args", "text or value is required for keys.");
      const target = el || document.activeElement || document.body;
      target.focus && target.focus({{ preventScroll: true }});
      if (key === "Control+A" && target.select) {{
        target.select();
      }} else if (key === "Backspace" && "value" in target) {{
        target.value = String(target.value || "").slice(0, -1);
        dispatchInputEvents(target);
      }} else {{
        keyboardEvent(target, "keydown", key);
        keyboardEvent(target, "keyup", key);
      }}
      return {{ status: "success", action: "keys", index: request.index, result: key, page_changed: true }};
    }}

    return fail("invalid_args", "Unsupported browser action.");
  }} catch (e) {{
    return fail("dom_event", e && e.message ? e.message : String(e));
  }}
}})();
""".strip()


class BrowserActionLayer:
    def __init__(self) -> None:
        self._last_state: dict[str, Any] | None = None

    @property
    def last_state_token(self) -> str | None:
        if not self._last_state:
            return None
        return self._last_state.get("state_token")

    def _ensure_driver(self, driver: Any) -> dict[str, Any] | None:
        if driver is None:
            return failed_result(None, "browser_unavailable", "没有可用的浏览器标签页，查L3记忆分析原因。")
        try:
            sessions = driver.get_all_sessions()
        except Exception as exc:
            return failed_result(None, "browser_unavailable", str(exc))
        if len(sessions) == 0:
            return failed_result(None, "browser_unavailable", "没有可用的浏览器标签页，查L3记忆分析原因。")
        return None

    def get_state(
        self,
        driver: Any,
        *,
        switch_tab_id: str | None = None,
        include_invisible: bool = False,
        max_elements: int = 120,
    ) -> dict[str, Any]:
        unavailable = self._ensure_driver(driver)
        if unavailable:
            return unavailable
        if switch_tab_id:
            driver.default_session_id = str(switch_tab_id)

        script = build_browser_state_script(include_invisible=include_invisible, max_elements=max_elements)
        try:
            raw = _response_payload(driver.execute_js(script, timeout=10))
        except Exception as exc:
            return failed_result(None, "dom_event", str(exc))

        state = normalize_state_result(raw)
        if state.get("status") == "success":
            state["tab_id"] = state.get("tab_id") or driver.default_session_id
            self._last_state = {"tab_id": state["tab_id"], "state_token": state.get("state_token")}
        return state

    def run_action(
        self,
        driver: Any,
        *,
        action: str,
        index: int | None = None,
        text: str | None = None,
        value: str | None = None,
        selector: str | None = None,
        timeout: int = 10,
        switch_tab_id: str | None = None,
    ) -> dict[str, Any]:
        action = str(action or "").strip()
        safe_index = _safe_index(index)
        safe_timeout = _safe_timeout(timeout)

        if action not in SUPPORTED_ACTIONS:
            return failed_result(action or None, "invalid_args", f"Unsupported browser action: {action}", safe_index)
        if action in INDEX_REQUIRED_ACTIONS and safe_index is None:
            return failed_result(action, "invalid_args", f"index is required for {action}.")
        if action == "wait_selector" and not selector:
            return failed_result(action, "invalid_args", "selector is required for wait_selector.")
        if action == "wait_text" and not text:
            return failed_result(action, "invalid_args", "text is required for wait_text.")

        unavailable = self._ensure_driver(driver)
        if unavailable:
            unavailable["action"] = action
            if safe_index is not None:
                unavailable["index"] = safe_index
            return unavailable
        if switch_tab_id:
            driver.default_session_id = str(switch_tab_id)

        state_token = None
        if action in INDEX_REQUIRED_ACTIONS or safe_index is not None:
            if not self._last_state:
                return failed_result(action, "state_missing", f"Run browser_state before browser_action {action}.", safe_index)
            state_token = self._last_state.get("state_token")

        script = build_browser_action_script(
            action=action,
            index=safe_index,
            text=text,
            value=value,
            timeout=safe_timeout,
            state_token=state_token,
            selector=selector,
        )

        try:
            raw = _response_payload(driver.execute_js(script, timeout=safe_timeout + 3))
        except Exception as exc:
            return failed_result(action, "dom_event", str(exc), safe_index)

        if isinstance(raw, dict):
            result = dict(raw)
        else:
            result = {"status": "success", "action": action, "result": raw}
        result.setdefault("tab_id", driver.default_session_id)

        if action in STATE_MUTATING_ACTIONS and result.get("status") == "success":
            self._last_state = None
        return result
```

- [ ] **Step 4: Run action layer tests and confirm pass**

Run:

```powershell
python -m pytest tests/test_browser_actions.py -q
```

Expected:

```text
7 passed
```

- [ ] **Step 5: Commit task 2**

Run:

```powershell
git add browser_actions.py tests/test_browser_actions.py
git commit -m "feat: add browser action layer"
```

Expected:

```text
[ga-browser-use ...] feat: add browser action layer
```

---

### Task 3: Wire New Tools Into GA Handler

**Files:**
- Modify: `ga.py`
- Create: `tests/test_browser_tool_handlers.py`

- [ ] **Step 1: Write failing handler tests**

Create `tests/test_browser_tool_handlers.py` with:

```python
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
    data = json.loads(outcome.result)
    assert data["status"] == "success"
    assert data["elements"][0]["text"] == "Login"


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
    data = json.loads(outcome.result)
    assert data == {"status": "success", "action": "click", "index": 1, "result": "clicked"}
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_browser_tool_handlers.py -q
```

Expected:

```text
AttributeError: module 'ga' has no attribute 'browser_state'
```

- [ ] **Step 3: Add imports and module-level action layer to `ga.py`**

In `ga.py`, near the existing imports at the top, add:

```python
from browser_actions import BrowserActionLayer
```

Near the existing global driver setup:

```python
import simphtml
driver = None
browser_action_layer = BrowserActionLayer()
```

- [ ] **Step 4: Add helper functions next to existing browser helpers**

In `ga.py`, after `web_execute_js(...)`, add:

```python
def browser_state(switch_tab_id=None, include_invisible=False, max_elements=120):
    """Return indexed interactive elements from the current real Chrome tab."""
    global driver
    try:
        if driver is None:
            first_init_driver()
        return browser_action_layer.get_state(
            driver,
            switch_tab_id=switch_tab_id,
            include_invisible=include_invisible,
            max_elements=max_elements,
        )
    except Exception as e:
        return {"status": "failed", "stage": "browser_unavailable", "error": format_error(e)}


def browser_action(
    action,
    index=None,
    text=None,
    value=None,
    selector=None,
    timeout=10,
    switch_tab_id=None,
):
    """Run a bounded browser action against the latest browser_state snapshot."""
    global driver
    try:
        if driver is None:
            first_init_driver()
        return browser_action_layer.run_action(
            driver,
            action=action,
            index=index,
            text=text,
            value=value,
            selector=selector,
            timeout=timeout,
            switch_tab_id=switch_tab_id,
        )
    except Exception as e:
        return {"status": "failed", "action": action, "stage": "dom_event", "error": format_error(e)}
```

- [ ] **Step 5: Add handler methods inside `GenericAgentHandler` after `do_web_execute_js(...)`**

In `ga.py`, add:

```python
    def do_browser_state(self, args, response):
        """获取当前真实 Chrome 标签页的可操作元素索引。"""
        switch_tab_id = args.get("switch_tab_id") or args.get("tab_id")
        include_invisible = args.get("include_invisible", False)
        max_elements = args.get("max_elements", 120)
        result = browser_state(
            switch_tab_id=switch_tab_id,
            include_invisible=include_invisible,
            max_elements=max_elements,
        )
        maxlen = 12000 // args.get("_tool_num", 1)
        formatted = json.dumps(result, ensure_ascii=False, indent=2, default=json_default)
        yield f"Browser state:\n{smart_format(formatted, max_str_len=1000)}\n"
        return StepOutcome(smart_format(json.dumps(result, ensure_ascii=False, default=json_default), max_str_len=maxlen), next_prompt="\n")

    def do_browser_action(self, args, response):
        """基于 browser_state 的 index 执行浏览器动作。"""
        action = args.get("action", "")
        index = args.get("index")
        text = args.get("text")
        value = args.get("value")
        selector = args.get("selector")
        timeout = args.get("timeout", 10)
        switch_tab_id = args.get("switch_tab_id") or args.get("tab_id")
        result = browser_action(
            action=action,
            index=index,
            text=text,
            value=value,
            selector=selector,
            timeout=timeout,
            switch_tab_id=switch_tab_id,
        )
        formatted = json.dumps(result, ensure_ascii=False, indent=2, default=json_default)
        yield f"Browser action result:\n{smart_format(formatted, max_str_len=1000)}\n"
        maxlen = 8000 // args.get("_tool_num", 1)
        next_prompt = self._get_anchor_prompt(skip=args.get("_index", 0) > 0)
        return StepOutcome(smart_format(json.dumps(result, ensure_ascii=False, default=json_default), max_str_len=maxlen), next_prompt=next_prompt)
```

- [ ] **Step 6: Run handler tests and confirm pass**

Run:

```powershell
python -m pytest tests/test_browser_tool_handlers.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 7: Run browser unit tests together**

Run:

```powershell
python -m pytest tests/test_browser_indexer.py tests/test_browser_actions.py tests/test_browser_tool_handlers.py -q
```

Expected:

```text
15 passed
```

- [ ] **Step 8: Commit task 3**

Run:

```powershell
git add ga.py tests/test_browser_tool_handlers.py
git commit -m "feat: expose browser action tools in GA"
```

Expected:

```text
[ga-browser-use ...] feat: expose browser action tools in GA
```

---

### Task 4: Add Tool Schemas

**Files:**
- Modify: `assets/tools_schema.json`
- Modify: `assets/tools_schema_cn.json`
- Create: `tests/test_browser_tool_schemas.py`

- [ ] **Step 1: Write failing schema tests**

Create `tests/test_browser_tool_schemas.py` with:

```python
import json
from pathlib import Path


def load_tools(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def tool_by_name(tools, name):
    for item in tools:
        function = item.get("function", {})
        if function.get("name") == name:
            return function
    raise AssertionError(f"tool not found: {name}")


def test_english_schema_exposes_browser_tools():
    tools = load_tools("assets/tools_schema.json")

    state = tool_by_name(tools, "browser_state")
    action = tool_by_name(tools, "browser_action")

    assert "indexed" in state["description"].lower()
    assert state["parameters"]["properties"]["max_elements"]["default"] == 120
    assert action["parameters"]["properties"]["action"]["enum"] == [
        "click",
        "input",
        "select",
        "keys",
        "wait_index",
        "wait_text",
        "wait_selector",
    ]


def test_chinese_schema_exposes_browser_tools():
    tools = load_tools("assets/tools_schema_cn.json")

    state = tool_by_name(tools, "browser_state")
    action = tool_by_name(tools, "browser_action")

    assert "索引" in state["description"]
    assert "真实 Chrome" in state["description"]
    assert "index" in action["parameters"]["properties"]
    assert "selector" in action["parameters"]["properties"]
```

- [ ] **Step 2: Run schema tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_browser_tool_schemas.py -q
```

Expected:

```text
AssertionError: tool not found: browser_state
```

- [ ] **Step 3: Insert English tool schemas after `web_execute_js`**

In `assets/tools_schema.json`, add these two tool entries immediately after the existing `web_execute_js` entry:

```json
  {"type": "function", "function": {
    "name": "browser_state",
    "description": "Get indexed interactive elements from the current real Chrome tab. Use before browser_action. Returns element index, tag, role, text, value, bbox, disabled, visible, selector_hint, url, title, viewport, and tab_id.",
    "parameters": {"type": "object", "properties": {
      "switch_tab_id": {"type": "string", "description": "[Optional] Tab ID to switch to before scanning"},
      "include_invisible": {"type": "boolean", "description": "Include hidden or currently invisible elements", "default": false},
      "max_elements": {"type": "integer", "description": "Maximum indexed elements to return", "default": 120}}}
  }},
  {"type": "function", "function": {
    "name": "browser_action",
    "description": "Run a bounded browser action against the latest browser_state index in the user's real Chrome tab. Call browser_state again when an index is stale.",
    "parameters": {"type": "object", "properties": {
      "action": {"type": "string", "enum": ["click", "input", "select", "keys", "wait_index", "wait_text", "wait_selector"], "description": "Action to run"},
      "index": {"type": "integer", "description": "Element index from browser_state. Required for click, input, select, wait_index; optional for keys"},
      "text": {"type": "string", "description": "Text for input, keys, wait_text, or visible option text for select"},
      "value": {"type": "string", "description": "Value for input, keys, or select option value"},
      "selector": {"type": "string", "description": "CSS selector for wait_selector"},
      "timeout": {"type": "integer", "description": "Timeout in seconds for wait actions and DOM execution", "default": 10},
      "switch_tab_id": {"type": "string", "description": "[Optional] Tab ID to switch to before acting"}}}
  }},
```

- [ ] **Step 4: Insert Chinese tool schemas after `web_execute_js`**

In `assets/tools_schema_cn.json`, add these two tool entries immediately after the existing `web_execute_js` entry:

```json
  {"type": "function", "function": {
    "name": "browser_state",
    "description": "获取用户真实 Chrome 当前标签页的可操作元素索引。应在 browser_action 前调用。返回 index、tag、role、text、value、bbox、disabled、visible、selector_hint、url、title、viewport、tab_id。",
    "parameters": {"type": "object", "properties": {
      "switch_tab_id": {"type": "string", "description": "可选的标签页 ID，扫描前切换到该标签页"},
      "include_invisible": {"type": "boolean", "description": "是否包含隐藏或当前不可见元素", "default": false},
      "max_elements": {"type": "integer", "description": "最多返回多少个索引元素", "default": 120}}}
  }},
  {"type": "function", "function": {
    "name": "browser_action",
    "description": "基于最近一次 browser_state 的 index 在用户真实 Chrome 标签页执行有边界的浏览器动作。index 过期时重新调用 browser_state。",
    "parameters": {"type": "object", "properties": {
      "action": {"type": "string", "enum": ["click", "input", "select", "keys", "wait_index", "wait_text", "wait_selector"], "description": "要执行的动作"},
      "index": {"type": "integer", "description": "browser_state 返回的元素索引。click、input、select、wait_index 必填；keys 可选"},
      "text": {"type": "string", "description": "input、keys、wait_text 的文本，或 select 的可见选项文本"},
      "value": {"type": "string", "description": "input、keys 的值，或 select 的 option value"},
      "selector": {"type": "string", "description": "wait_selector 使用的 CSS selector"},
      "timeout": {"type": "integer", "description": "等待动作和 DOM 执行的超时时间，单位秒", "default": 10},
      "switch_tab_id": {"type": "string", "description": "可选的标签页 ID，执行前切换到该标签页"}}}
  }},
```

- [ ] **Step 5: Run schema tests and JSON parse checks**

Run:

```powershell
python -m pytest tests/test_browser_tool_schemas.py -q
python -c "import json; json.load(open('assets/tools_schema.json', encoding='utf-8')); json.load(open('assets/tools_schema_cn.json', encoding='utf-8')); print('schema json ok')"
```

Expected:

```text
2 passed
schema json ok
```

- [ ] **Step 6: Commit task 4**

Run:

```powershell
git add assets/tools_schema.json assets/tools_schema_cn.json tests/test_browser_tool_schemas.py
git commit -m "feat: add browser action tool schemas"
```

Expected:

```text
[ga-browser-use ...] feat: add browser action tool schemas
```

---

### Task 5: Execution Display Contract Tests

**Files:**
- Modify: `tests/test_webui_server.py`

- [ ] **Step 1: Add display contract tests after existing browser tool tests**

In `tests/test_webui_server.py`, after `test_tool_contract_web_execute_js_result_stays_in_execution_panel`, add:

```python
    def test_tool_contract_browser_state_result_stays_in_execution_panel(self):
        text = (
            "**LLM Running (Turn 1) ...**\n"
            "<summary>\n索引当前浏览器页面\n</summary>\n"
            "🛠️ Tool: `browser_state`  📥 args:\n"
            "````text\n"
            "{\n"
            '  "max_elements": 20\n'
            "}\n"
            "````\n"
            "`````\n"
            "Browser state:\n"
            "{\n"
            '  "status": "success",\n'
            '  "elements": [{"index": 1, "text": "登录"}]\n'
            "}\n"
            "`````\n\n"
            "已定位登录按钮。"
        )

        visible = extract_visible_reply_text(text)
        turns = parse_execution_log(text)

        self.assertEqual(visible, "已定位登录按钮。")
        self.assertEqual(turns[0]["tool_calls"][0]["tool"], "browser_state")
        self.assertIn('"text": "登录"', turns[0]["tool_calls"][0]["result"])
        self.assertNotIn("Browser state", visible)
        self.assertNotIn("elements", visible)

    def test_tool_contract_browser_action_result_stays_in_execution_panel(self):
        text = (
            "**LLM Running (Turn 1) ...**\n"
            "<summary>\n点击浏览器元素\n</summary>\n"
            "🛠️ Tool: `browser_action`  📥 args:\n"
            "````text\n"
            "{\n"
            '  "action": "click",\n'
            '  "index": 1\n'
            "}\n"
            "````\n"
            "`````\n"
            "Browser action result:\n"
            "{\n"
            '  "status": "success",\n'
            '  "action": "click",\n'
            '  "result": "clicked"\n'
            "}\n"
            "`````\n\n"
            "点击完成。"
        )

        visible = extract_visible_reply_text(text)
        turns = parse_execution_log(text)

        self.assertEqual(visible, "点击完成。")
        self.assertEqual(turns[0]["tool_calls"][0]["tool"], "browser_action")
        self.assertIn('"result": "clicked"', turns[0]["tool_calls"][0]["result"])
        self.assertNotIn("Browser action result", visible)
        self.assertNotIn("clicked", visible)
```

- [ ] **Step 2: Run focused WebUI parser tests**

Run:

```powershell
python -m pytest tests/test_webui_server.py -q
```

Expected:

```text
passed
```

The exact count depends on current tests in `tests/test_webui_server.py`; the command must finish with no failures.

- [ ] **Step 3: Commit task 5**

Run:

```powershell
git add tests/test_webui_server.py
git commit -m "test: cover browser action execution display"
```

Expected:

```text
[ga-browser-use ...] test: cover browser action execution display
```

---

### Task 6: Final Verification And Real-Browser Smoke

**Files:**
- No new source files.
- No browser-use repo edits.

- [ ] **Step 1: Run focused Python test suite**

Run:

```powershell
python -m pytest tests/test_browser_indexer.py tests/test_browser_actions.py tests/test_browser_tool_handlers.py tests/test_browser_tool_schemas.py tests/test_webui_server.py -q
```

Expected:

```text
passed
```

The output may show a count higher than the browser-specific tests because `tests/test_webui_server.py` contains existing coverage. There must be zero failures.

- [ ] **Step 2: Run frontend execution-state tests if Node dependencies are installed**

Run:

```powershell
node tests/execution_panel_state.test.mjs
node tests/webui_inline_execution.test.mjs
```

Expected:

```text
ok
ok
```

If Node dependencies are missing, record the exact error in the final implementation note and keep the Python parser tests as the blocking verification.

- [ ] **Step 3: Run repository-wide Python tests when practical**

Run:

```powershell
python -m pytest tests -q
```

Expected:

```text
passed
```

If unrelated pre-existing tests fail, capture the failing test names and error messages before deciding whether they are in scope.

- [ ] **Step 4: Run whitespace and diff checks**

Run:

```powershell
git diff --check
git status --short
```

Expected:

```text
```

`git diff --check` must print no whitespace errors. `git status --short` should show no uncommitted files after the task commits.

- [ ] **Step 5: Manual real-browser smoke with existing GA bridge**

Prerequisites:

- User has opened Chrome normally.
- `assets/tmwd_cdp_bridge` is installed and connected as it is for existing `web_scan` / `web_execute_js`.
- Do not start Chrome with remote debugging for this smoke; this validates the intended no-manual-CDP path.

Smoke sequence in GA:

```text
1. Call web_scan with tabs_only=true to confirm GA sees the user's Chrome tabs.
2. Open or focus a simple page with one input and one button.
3. Call browser_state with max_elements=20.
4. Confirm the returned elements include the input and button indices.
5. Call browser_action input with the input index and text="ga-smoke".
6. Call browser_action click with the button index.
7. Call browser_state again and confirm the visible page state changed.
```

Expected:

```json
{"status": "success"}
```

Each `browser_state` and `browser_action` call should return `status: "success"` in normal pages. If an index is stale after navigation or DOM replacement, the expected result is a structured failure with `stage: "state_missing"` or `stage: "stale_index"`, followed by a new `browser_state` call.

- [ ] **Step 6: Final implementation commit if verification fixes touched planned files**

Run only if Task 6 required small test or doc corrections:

```powershell
git add browser_indexer.py browser_actions.py ga.py assets/tools_schema.json assets/tools_schema_cn.json tests/test_browser_indexer.py tests/test_browser_actions.py tests/test_browser_tool_handlers.py tests/test_browser_tool_schemas.py tests/test_webui_server.py
git commit -m "test: verify browser action layer"
```

Expected:

```text
[ga-browser-use ...] test: verify browser action layer
```

---

## Implementation Notes

- `browser_state` is action-oriented, not a replacement for `web_scan` page reading.
- P0 intentionally uses DOM actions through the existing user-Chrome bridge. It does not embed browser-use runtime.
- `keys` is bounded to DOM-dispatched key behavior in P0. Native CDP key and mouse event upgrades are separate work after P0 proves value.
- State cache is invalidated after successful mutating actions because navigation or DOM updates can make element handles stale.
- Password input values are redacted in `browser_state` output and `input` result output.
- Browser internal pages such as `chrome://` remain governed by the existing extension bridge scriptability constraints.

---

## Self-Review Checklist

- Spec coverage:
  - `browser_state`: Task 1, Task 3, Task 4, Task 5.
  - `browser_action`: Task 2, Task 3, Task 4, Task 5.
  - Real user Chrome bridge: Task 2 uses `driver.execute_js`, Task 6 smoke forbids manual CDP.
  - Existing tools unchanged: File map and scope exclude `web_scan` / `web_execute_js` behavior changes.
  - Structured failures: Task 2 tests and `failed_result(...)`.
  - No browser-use source edits: Scope and Task 6.

- Placeholder scan:
  - No banned placeholder markers.
  - No unspecified file paths in commands.
  - No unbounded "add error handling" step.
  - Every code-writing step includes concrete code.

- Type consistency:
  - Tool names are `browser_state` and `browser_action` in tests, schemas, and handlers.
  - Action enum is identical in Python and both schema files.
  - Returned failure stages match design names: `browser_unavailable`, `state_missing`, `stale_index`, `locate`, `visibility`, `dom_event`, `timeout`, `invalid_args`.

---

## Execution Handoff

Plan complete at `docs/superpowers/plans/2026-05-16-ga-browser-action-layer.md`.

Recommended execution mode: `superpowers:subagent-driven-development`, one fresh worker per task with review after each task. Inline execution with `superpowers:executing-plans` is also valid if the branch should stay in one session.
