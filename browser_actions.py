from __future__ import annotations

import json
from typing import Any

from browser_indexer import build_browser_state_script, normalize_state_result


SUPPORTED_ACTIONS = {"click", "input", "select", "keys", "wait_index", "wait_text", "wait_selector"}
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

    let el = null;
    if (request.index !== null && request.index !== undefined) {{
      const located = cachedElement();
      if (located.error) return located.error;
      el = located.el;
    }}

    if (request.action === "wait_index") {{
      const waited = await waitFor(
        () => visible(el),
        "timeout",
        "Timed out waiting for element index."
      );
      if (waited && waited.error) return waited.error;
      return {{ status: "success", action: "wait_index", index: request.index, result: "element_visible" }};
    }}

    if (el) {{
      el.scrollIntoView({{ block: "center", inline: "center", behavior: "instant" }});
      await sleep(50);
      if (!visible(el)) return fail("visibility", "Element is not visible.");
    }}

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
      if (!target) return fail("locate", "No keyboard target found.");
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
            return failed_result(None, "browser_unavailable", "没有可用的浏览器标签页。")
        try:
            sessions = driver.get_all_sessions()
        except Exception as exc:
            return failed_result(None, "browser_unavailable", str(exc))
        if not sessions:
            return failed_result(None, "browser_unavailable", "没有可用的浏览器标签页。")
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
            if str(self._last_state.get("tab_id") or "") != str(driver.default_session_id):
                result = failed_result(
                    action,
                    "stale_index",
                    "Run browser_state before browser_action for the current tab.",
                    safe_index,
                )
                result["tab_id"] = driver.default_session_id
                return result
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
            result = failed_result(action, "dom_event", str(exc), safe_index)
            result["tab_id"] = driver.default_session_id
            return result

        if isinstance(raw, dict):
            result = dict(raw)
        else:
            result = {"status": "success", "action": action, "result": raw}
        result.setdefault("tab_id", driver.default_session_id)

        if action in STATE_MUTATING_ACTIONS and result.get("status") == "success":
            self._last_state = None
        return result
