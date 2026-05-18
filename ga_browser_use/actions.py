from __future__ import annotations

import json
import time
from typing import Any

from ga_browser_use.finder import find_in_state, safe_max_results
from ga_browser_use.indexer import build_browser_state_script, normalize_state_result
from ga_browser_use.results import FailureFuse, add_recovery, failed_result as structured_failed_result
from ga_browser_use.runtime_log import log_event


SUPPORTED_ACTIONS = {
    "click",
    "input",
    "select",
    "keys",
    "wait_index",
    "wait_text",
    "wait_selector",
    "wait_dom_stable",
    "wait_not_busy",
    "wait_enabled",
    "wait_route",
}
INDEX_REQUIRED_ACTIONS = {"click", "input", "select", "wait_index", "wait_enabled"}
STATE_MUTATING_ACTIONS = {"click", "input", "select", "keys"}
WAIT_ACTIONS = {
    "wait_index",
    "wait_text",
    "wait_selector",
    "wait_dom_stable",
    "wait_not_busy",
    "wait_enabled",
    "wait_route",
}
KEYS_AFTER_INPUT_HINT = (
    "For keys after a successful input, retry browser_action without index to use the focused element."
)


def failed_result(action: str | None, stage: str, error: str, index: int | None = None) -> dict[str, Any]:
    return structured_failed_result(action, stage, error, index)


def keys_without_index_retry_result(action: str, index: int, text: str | None, value: str | None) -> dict[str, Any]:
    result = failed_result(action, "state_missing", f"Run browser_state before browser_action {action}.", index)
    result["hint"] = KEYS_AFTER_INPUT_HINT
    key = text if text is not None else value
    if key:
        result["suggested_args"] = {"action": "keys", "text": str(key)}
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


def _elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


def _recovery_code(result: dict[str, Any]) -> str | None:
    recovery = result.get("recovery")
    if isinstance(recovery, dict):
        code = recovery.get("code")
        return str(code) if code else None
    return None


def _log_result(tool: str, started_at: float, result: dict[str, Any], fields: dict[str, Any] | None = None) -> dict[str, Any]:
    summary = dict(result)
    summary.update(fields or {})
    summary["status"] = result.get("status")
    summary["stage"] = result.get("stage")
    summary["duration_ms"] = _elapsed_ms(started_at)
    recovery_code = _recovery_code(result)
    if recovery_code:
        summary["recovery_code"] = recovery_code
    if result.get("tab_id"):
        summary["tab_id"] = result.get("tab_id")
    if result.get("page_changed") is not None:
        summary["page_changed"] = result.get("page_changed")
    log_event(tool, "end", fields=summary)
    return result


def build_browser_action_script(
    *,
    action: str,
    index: int | None,
    text: str | None,
    value: str | None,
    timeout: int,
    state_token: str | None,
    selector: str | None,
    verify: str | None = None,
    verify_text: str | None = None,
    verify_value: str | None = None,
    verify_selector: str | None = None,
    selector_tag: str | None = None,
    selector_role: str | None = None,
    selector_text: str | None = None,
    frame_path: list[Any] | None = None,
) -> str:
    request = {
        "action": action,
        "index": index,
        "text": text,
        "value": value,
        "timeout": timeout,
        "state_token": state_token,
        "selector": selector,
        "verify": verify,
        "verify_text": verify_text,
        "verify_value": verify_value,
        "verify_selector": verify_selector,
        "selector_tag": selector_tag,
        "selector_role": selector_role,
        "selector_text": selector_text,
        "frame_path": frame_path or [],
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

  function ownerWindowOf(el) {{
    return (el && el.ownerDocument && el.ownerDocument.defaultView) || window;
  }}

  function ownerFrameChainAttached(el) {{
    try {{
      let currentWindow = el && el.ownerDocument && el.ownerDocument.defaultView;
      if (!currentWindow) return false;
      while (currentWindow && currentWindow.frameElement) {{
        const frame = currentWindow.frameElement;
        if (!frame.ownerDocument || !frame.ownerDocument.contains || !frame.ownerDocument.contains(frame)) {{
          return false;
        }}
        currentWindow = frame.ownerDocument.defaultView;
        if (!currentWindow) return false;
      }}
      return true;
    }} catch (e) {{
      return false;
    }}
  }}

  function elementTreeVisible(el, elementWindow, requireBox) {{
    if (!el) return false;
    if (typeof el.checkVisibility === "function") {{
      try {{
        if (!el.checkVisibility({{ checkOpacity: true, checkVisibilityCSS: true }})) return false;
      }} catch (e) {{
        try {{
          if (!el.checkVisibility()) return false;
        }} catch (ignored) {{
          // Fall back to computed style checks below.
        }}
      }}
    }}
    let current = el;
    while (current && current.nodeType !== 9) {{
      const currentWindow = (current.ownerDocument && current.ownerDocument.defaultView) || elementWindow || window;
      const style = currentWindow.getComputedStyle(current);
      if (
        current.hidden ||
        style.display === "none" ||
        style.visibility === "hidden" ||
        style.visibility === "collapse" ||
        style.contentVisibility === "hidden" ||
        Number(style.opacity || "1") <= 0
      ) {{
        return false;
      }}
      current = current.parentElement;
    }}
    if (!requireBox) return true;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }}

  function frameElementVisible(frame) {{
    const parentWindow = (frame && frame.ownerDocument && frame.ownerDocument.defaultView) || window;
    return elementTreeVisible(frame, parentWindow, true);
  }}

  function ownerFrameChainVisible(el) {{
    try {{
      let currentWindow = el && el.ownerDocument && el.ownerDocument.defaultView;
      if (!currentWindow) return false;
      while (currentWindow && currentWindow.frameElement) {{
        const frame = currentWindow.frameElement;
        if (!frame.ownerDocument || !frame.ownerDocument.contains || !frame.ownerDocument.contains(frame)) {{
          return false;
        }}
        if (!frameElementVisible(frame)) return false;
        currentWindow = frame.ownerDocument.defaultView;
        if (!currentWindow) return false;
      }}
      return true;
    }} catch (e) {{
      return false;
    }}
  }}

  function elementDocumentContains(el) {{
    return Boolean(
      el &&
      el.ownerDocument &&
      el.ownerDocument.contains &&
      el.ownerDocument.contains(el)
    );
  }}

  function ownerDocumentContains(el) {{
    return elementDocumentContains(el) && ownerFrameChainAttached(el);
  }}

  function frameStepIndex(step) {{
    if (typeof step === "number") return Number.isInteger(step) && step >= 0 ? step : null;
    if (step && typeof step === "object" && typeof step.index === "number") {{
      return Number.isInteger(step.index) && step.index >= 0 ? step.index : null;
    }}
    return null;
  }}

  function documentForFramePath(framePath) {{
    let currentDocument = document;
    for (const step of framePath || []) {{
      const index = frameStepIndex(step);
      if (index === null) return {{ error: fail("frame_unavailable", "Frame path is invalid.") }};
      const frame = currentDocument.querySelectorAll("iframe, frame")[index];
      if (!frame) return {{ error: fail("frame_unavailable", "Frame path is unavailable.") }};
      let nextDocument = null;
      try {{
        nextDocument = frame.contentDocument;
      }} catch (e) {{
        return {{ error: fail("frame_unavailable", "Frame document is unavailable.") }};
      }}
      if (!nextDocument) return {{ error: fail("frame_unavailable", "Frame document is unavailable.") }};
      currentDocument = nextDocument;
    }}
    return {{ document: currentDocument }};
  }}

  function visible(el) {{
    if (!ownerDocumentContains(el)) return false;
    if (!ownerFrameChainVisible(el)) return false;
    return elementTreeVisible(el, ownerWindowOf(el), true);
  }}

  function cachedElement(allowDetached) {{
    const state = window.__GA_BROWSER_ACTION_STATE__;
    if (!state || !state.token) return {{ error: fail("state_missing", "Run browser_state before indexed browser_action.") }};
    if (state.token !== request.state_token) return {{ error: fail("stale_index", "Element index is stale. Run browser_state again.") }};
    const el = state.elements && state.elements[Number(request.index) - 1];
    if (!el) {{
      return {{ error: fail("stale_index", "Element index is stale. Run browser_state again.") }};
    }}
    if (!ownerFrameChainAttached(el)) {{
      return {{ error: fail("stale_index", "Element index is stale. Run browser_state again.") }};
    }}
    if (!elementDocumentContains(el)) {{
      if (allowDetached === "keep") return {{ el }};
      if (allowDetached) return {{ el: null, cachedDocument: el.ownerDocument || null }};
      return {{ error: fail("stale_index", "Element index is stale. Run browser_state again.") }};
    }}
    return {{ el, cachedDocument: el.ownerDocument || null }};
  }}

  function replaceCachedElement(index, target, expectedToken) {{
    const state = window.__GA_BROWSER_ACTION_STATE__;
    if (!state || state.token !== expectedToken || !Array.isArray(state.elements) || !target) {{
      return {{ error: fail("stale_index", "Element index is stale. Run browser_state again.") }};
    }}
    const safeIndex = Number(index) - 1;
    if (!Number.isInteger(safeIndex) || safeIndex < 0 || safeIndex >= state.elements.length) {{
      return {{ error: fail("stale_index", "Element index is stale. Run browser_state again.") }};
    }}
    state.elements[safeIndex] = target;
    return {{ ok: true }};
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

  function inputEventConstructorFor(el) {{
    const ownerWindow = ownerWindowOf(el);
    if (ownerWindow && typeof ownerWindow.InputEvent === "function") return ownerWindow.InputEvent;
    if (typeof InputEvent === "function") return InputEvent;
    return null;
  }}

  function contentEditableRejectedInputResult() {{
    const result = fail("dom_event", "Contenteditable editor rejected synthetic DOM input.");
    result.hint = "The editor rejected synthetic DOM input; it may require lower-level CDP or component-specific handling.";
    result.retryable = true;
    return result;
  }}

  function dispatchContentEditableBeforeInput(el, nextValue) {{
    const InputEventConstructor = inputEventConstructorFor(el);
    if (!InputEventConstructor) return null;

    const beforeInputEvent = new InputEventConstructor("beforeinput", {{
      inputType: "insertText",
      data: nextValue,
      bubbles: true,
      cancelable: true,
    }});
    if (el.dispatchEvent(beforeInputEvent) === false) {{
      return contentEditableRejectedInputResult();
    }}
    return null;
  }}

  function dispatchContentEditableInputEvents(el, nextValue) {{
    const InputEventConstructor = inputEventConstructorFor(el);
    if (InputEventConstructor) {{
      el.dispatchEvent(new InputEventConstructor("input", {{
        inputType: "insertText",
        data: nextValue,
        bubbles: true,
      }}));
    }} else {{
      el.dispatchEvent(new Event("input", {{ bubbles: true }}));
    }}
    el.dispatchEvent(new Event("change", {{ bubbles: true }}));
  }}

  function tagOf(el) {{
    return el && el.tagName ? el.tagName.toLowerCase() : "";
  }}

  function textOf(element) {{
    const aria = element.getAttribute("aria-label") || "";
    const placeholder = element.getAttribute("placeholder") || "";
    const title = element.getAttribute("title") || "";
    const text = element.innerText || element.textContent || "";
    return [aria, placeholder, title, text].filter(Boolean).join(" ").trim().replace(/\\s+/g, " ");
  }}

  function readableDocuments(rootDocument) {{
    const docs = [];
    const seen = new Set();
    function visit(doc) {{
      if (!doc || seen.has(doc)) return;
      seen.add(doc);
      docs.push(doc);
      let frames = [];
      try {{
        frames = Array.from(doc.querySelectorAll("iframe, frame"));
      }} catch (e) {{
        frames = [];
      }}
      for (const frame of frames) {{
        try {{
          if (frameElementVisible(frame) && frame.contentDocument) visit(frame.contentDocument);
        }} catch (e) {{
          // Cross-origin frames are intentionally skipped.
        }}
      }}
    }}
    visit(rootDocument || document);
    return docs;
  }}

  function focusedElementInDocument(rootDocument) {{
    function descend(doc) {{
      if (!doc) return null;
      let active = null;
      try {{
        active = doc.activeElement;
      }} catch (e) {{
        return null;
      }}
      if (!active) return null;
      const tag = tagOf(active);
      if (tag === "iframe" || tag === "frame") {{
        try {{
          const child = descend(active.contentDocument);
          return child || active;
        }} catch (e) {{
          return active;
        }}
      }}
      return active;
    }}
    return descend(rootDocument || document);
  }}

  function documentReadableText(doc) {{
    try {{
      return (doc.body && (doc.body.innerText || doc.body.textContent || "")) || "";
    }} catch (e) {{
      return "";
    }}
  }}

  function readElementValue(el) {{
    if (!el) return "";
    if ("value" in el) {{
      const inputType = String(el.getAttribute("type") || "").toLowerCase();
      if (inputType === "password") return "[REDACTED]";
      return String(el.value ?? "");
    }}
    if (isContentEditableTarget(el)) {{
      return String(el.innerText || el.textContent || "");
    }}
    return String(el.innerText || el.textContent || "");
  }}

  function expectedFieldValue() {{
    return String(request.verify_value !== null && request.verify_value !== undefined
      ? request.verify_value
      : (request.value !== null && request.value !== undefined ? request.value : (request.text || "")));
  }}

  function verifySuccess(type, observed, expected) {{
    return {{ type, observed, expected, passed: true }};
  }}

  function verifyFailure(type, observed, expected) {{
    return {{
      status: "failed",
      action: request.action,
      index: request.index,
      stage: "verify_failed",
      error: "Verification failed.",
      verification: {{ type, observed, expected, passed: false }},
      observed,
      expected,
      retryable: true
    }};
  }}

  function verifyAction(el) {{
    const type = request.verify;
    if (!type) return null;

    if (type === "field_value") {{
      const expected = expectedFieldValue();
      const observed = readElementValue(el);
      return observed === expected
        ? verifySuccess(type, observed, expected)
        : verifyFailure(type, observed, expected);
    }}

    if (type === "element_text") {{
      const expected = String(request.verify_text !== null && request.verify_text !== undefined
        ? request.verify_text
        : (request.text || ""));
      const observed = readElementValue(el);
      return observed.includes(expected)
        ? verifySuccess(type, observed, expected)
        : verifyFailure(type, observed, expected);
    }}

    if (type === "text") {{
      const expected = String(request.verify_text !== null && request.verify_text !== undefined
        ? request.verify_text
        : (request.text || ""));
      const observed = readableDocuments(document).map(documentReadableText).join("\\n");
      return observed.includes(expected)
        ? verifySuccess(type, observed, expected)
        : verifyFailure(type, observed, expected);
    }}

    if (type === "selector") {{
      const expected = String(request.verify_selector || request.selector || "");
      let found = false;
      for (const doc of readableDocuments(document)) {{
        try {{
          if (expected && doc.querySelector(expected)) {{
            found = true;
            break;
          }}
        }} catch (e) {{
          found = false;
        }}
      }}
      const observed = found ? expected : null;
      return found
        ? verifySuccess(type, observed, expected)
        : verifyFailure(type, observed, expected);
    }}

    return verifyFailure(type, "", "");
  }}

  function verifyHintFor(action) {{
    if (action === "input") return "Use verify='field_value' with verify_value to require the field value after input.";
    if (action === "select") return "Use verify='field_value' with verify_value to require the selected value.";
    if (action === "click") return "Use verify='text' or verify='selector' to require the expected post-click page state.";
    if (action === "keys") return "Use verify='text', verify='selector', or verify='field_value' to require the expected post-key state.";
    return "";
  }}

  function finalizeMutatingAction(result, target) {{
    result.verify_hint = verifyHintFor(request.action);
    if (request.verify) {{
      const verification = verifyAction(target);
      if (verification && verification.status === "failed") return verification;
      if (verification) result.verification = verification;
    }}
    return result;
  }}

  function nativeRoleOf(element, tag, type) {{
    if (tag === "a" && element.hasAttribute("href")) return "link";
    if (tag === "button") return "button";
    if (tag === "select") return "combobox";
    if (tag === "textarea") return "textbox";
    if (tag === "input") {{
      const inputType = type.toLowerCase();
      if (inputType === "checkbox") return "checkbox";
      if (inputType === "radio") return "radio";
      if (["button", "submit", "reset"].includes(inputType)) return "button";
      return "textbox";
    }}
    return "";
  }}

  function roleOf(element) {{
    const tag = tagOf(element);
    return (element.getAttribute("role") || nativeRoleOf(element, tag, element.getAttribute("type") || "")).toLowerCase();
  }}

  function isContentEditableTarget(el) {{
    const isDesignModeBody = Boolean(
      el &&
      el.ownerDocument &&
      el.ownerDocument.body === el &&
      String(el.ownerDocument.designMode || "").toLowerCase() === "on"
    );
    return Boolean(el && (el.isContentEditable || el.getAttribute("contenteditable") === "true" || isDesignModeBody));
  }}

  function editableForInput(el) {{
    const tag = tagOf(el);
    if (tag === "textarea" || isContentEditableTarget(el)) return true;
    if (tag !== "input") return false;
    const type = String(el.getAttribute("type") || "text").toLowerCase();
    return !["button", "submit", "reset", "checkbox", "radio", "file", "image", "range", "color", "hidden"].includes(type);
  }}

  function requiresEditableKey(key) {{
    return ["Control+A", "Backspace"].includes(key);
  }}

  function editableForEditingKey(el) {{
    const tag = tagOf(el);
    if (tag === "textarea") return true;
    if (tag !== "input") return false;
    const type = String(el.getAttribute("type") || "text").toLowerCase();
    return !["button", "submit", "reset", "checkbox", "radio", "file", "image", "range", "color", "hidden"].includes(type);
  }}

  function matchesSelectorIdentity(target) {{
    if (!target) return false;
    if (!request.selector_tag && !request.selector_role && !request.selector_text) return false;
    if (request.selector_tag && tagOf(target) !== String(request.selector_tag).toLowerCase()) return false;
    if (request.selector_role && roleOf(target) !== String(request.selector_role).toLowerCase()) return false;
    if (request.selector_text) {{
      const expected = String(request.selector_text).trim().replace(/\\s+/g, " ");
      const actual = textOf(target);
      if (expected && !actual) return false;
      if (expected && !actual.includes(expected) && !expected.includes(actual)) return false;
    }}
    return true;
  }}

  function keyboardEvent(target, type, key) {{
    return target.dispatchEvent(new KeyboardEvent(type, {{ key, bubbles: true, cancelable: true }}));
  }}

  function shouldSubmitFormOnEnter(target, key) {{
    if (key !== "Enter" || tagOf(target) !== "input" || !target.form) return false;
    const type = String(target.getAttribute("type") || "text").toLowerCase();
    return !["button", "submit", "reset", "checkbox", "radio", "file", "image", "range", "color", "hidden"].includes(type);
  }}

  function submitFormOnEnter(target) {{
    const form = target && target.form;
    if (!form) return false;
    if (typeof form.requestSubmit === "function") {{
      form.requestSubmit();
      return true;
    }}
    if (typeof form.submit === "function") {{
      form.submit();
      return true;
    }}
    return false;
  }}

  function blockedForAction(el, action) {{
    if (!el) return "";
    if (el.disabled || el.getAttribute("aria-disabled") === "true") {{
      return "Element is disabled.";
    }}
    if (["input", "select", "keys"].includes(action) &&
        (el.readOnly || el.getAttribute("aria-readonly") === "true")) {{
      return "Element is read-only.";
    }}
    return "";
  }}

  function optionDisabled(option) {{
    return Boolean(option && (
      option.disabled ||
      (option.getAttribute && option.getAttribute("disabled") !== null)
    ));
  }}

  function optionOptgroupDisabled(option) {{
    const parent = option && option.parentElement;
    return Boolean(parent && tagOf(parent) === "optgroup" && (
      parent.disabled ||
      (parent.getAttribute && parent.getAttribute("disabled") !== null)
    ));
  }}

  function boundedDomSignature() {{
    const parts = [];
    for (const doc of readableDocuments(document)) {{
      let elements = [];
      try {{
        elements = Array.from(doc.querySelectorAll("*")).slice(0, 300);
      }} catch (e) {{
        elements = [];
      }}
      const bodyText = documentReadableText(doc).trim().replace(/\\s+/g, " ").slice(0, 500);
      parts.push(`body:${{bodyText.length}}:${{bodyText}}`);
      parts.push(`count:${{elements.length}}`);
      for (const element of elements) {{
        const id = element.id || "";
        const className = typeof element.className === "string" ? element.className : "";
        const text = (element.innerText || element.textContent || "").trim().replace(/\\s+/g, " ").slice(0, 40);
        parts.push(`${{tagOf(element)}}#${{id}}.${{className}}:${{text}}`);
      }}
    }}
    return parts.join("|").slice(0, 20000);
  }}

  function visibleBusyElements(selector) {{
    const matches = [];
    for (const doc of readableDocuments(document)) {{
      let elements = [];
      try {{
        elements = Array.from(doc.querySelectorAll(selector));
      }} catch (e) {{
        return {{ error: fail("invalid_args", "Busy selector is invalid.") }};
      }}
      for (const element of elements) {{
        if (visible(element)) matches.push(element);
      }}
    }}
    return {{ elements: matches }};
  }}

  try {{
    const waitActions = new Set(["wait_index", "wait_text", "wait_selector", "wait_dom_stable", "wait_not_busy", "wait_enabled", "wait_route"]);
    if (request.verify && waitActions.has(request.action)) {{
      return fail("invalid_args", "verify is not supported for wait actions.");
    }}
    if (request.verify === "field_value" && !expectedFieldValue().trim()) {{
      return fail("invalid_args", "field_value verification requires a non-empty expected value.");
    }}

    if (request.action === "wait_text") {{
      if (!request.text) return fail("invalid_args", "text is required for wait_text.");
      const waited = await waitFor(
        () => readableDocuments(document).some(doc => documentReadableText(doc).includes(request.text)),
        "timeout",
        "Timed out waiting for text."
      );
      if (waited && waited.error) return waited.error;
      return {{ status: "success", action: "wait_text", result: "text_found" }};
    }}

    if (request.action === "wait_selector") {{
      if (!request.selector) return fail("invalid_args", "selector is required for wait_selector.");
      const waited = await waitFor(
        () => {{
          for (const doc of readableDocuments(document)) {{
            try {{
              if (doc.querySelector(request.selector)) return true;
            }} catch (e) {{
              return {{ error: fail("invalid_args", "selector is invalid.") }};
            }}
          }}
          return false;
        }},
        "timeout",
        "Timed out waiting for selector."
      );
      if (waited && waited.error) return waited.error;
      return {{ status: "success", action: "wait_selector", result: "selector_found" }};
    }}

    if (request.action === "wait_dom_stable") {{
      let lastSignature = null;
      let stableTicks = 0;
      const waited = await waitFor(
        () => {{
          const signature = boundedDomSignature();
          if (signature === lastSignature) {{
            stableTicks += 1;
          }} else {{
            lastSignature = signature;
            stableTicks = 0;
          }}
          return stableTicks >= 3 ? true : null;
        }},
        "dom_unstable",
        "Timed out waiting for DOM to become stable."
      );
      if (waited && waited.error) return waited.error;
      return {{ status: "success", action: "wait_dom_stable", result: "dom_stable" }};
    }}

    if (request.action === "wait_not_busy") {{
      const busySelector = request.selector || "[aria-busy='true'], [data-loading='true'], .loading, .spinner, .ant-spin-spinning, .ant-spin-dot, .el-loading-mask";
      const waited = await waitFor(
        () => {{
          const visibleBusy = visibleBusyElements(busySelector);
          if (visibleBusy.error) return visibleBusy;
          return visibleBusy.elements.length === 0 ? true : null;
        }},
        "timeout",
        "Timed out waiting for loading indicators to disappear."
      );
      if (waited && waited.error) return waited.error;
      return {{ status: "success", action: "wait_not_busy", result: "not_busy" }};
    }}

    if (request.action === "wait_route") {{
      const expected = String(request.text || request.value || "");
      if (!expected) return fail("invalid_args", "text or value is required for wait_route.");
      const waited = await waitFor(
        () => location.href.includes(expected) || location.pathname.includes(expected),
        "timeout",
        "Timed out waiting for route."
      );
      if (waited && waited.error) return waited.error;
      return {{ status: "success", action: "wait_route", result: "route_matched" }};
    }}

    let el = null;
    let cachedDocument = null;
    if (request.index !== null && request.index !== undefined) {{
      const located = cachedElement(request.action === "wait_index" && Boolean(request.selector));
      if (located.error) return located.error;
      el = located.el;
      cachedDocument = located.cachedDocument || (el && el.ownerDocument) || null;
    }}

    if (request.action === "wait_index") {{
      function waitIndexTarget() {{
        if (el !== null) {{
          if (ownerDocumentContains(el)) return visible(el) ? el : null;
          el = null;
        }}
        if (request.selector) {{
          const resolvedDocument = documentForFramePath(request.frame_path || []);
          if (resolvedDocument.error) return resolvedDocument;
          const queryDocument = resolvedDocument.document;
          if (cachedDocument && queryDocument !== cachedDocument) {{
            return {{ error: fail("stale_index", "Element index is stale. Run browser_state again.") }};
          }}
          const target = queryDocument.querySelector(request.selector);
          if (!matchesSelectorIdentity(target)) return null;
          if (!visible(target)) return null;
          if (el !== target) {{
            const replaced = replaceCachedElement(request.index, target, request.state_token);
            if (replaced && replaced.error) return replaced;
            el = target;
          }}
          return target;
        }}
        return null;
      }}
      const waited = await waitFor(
        () => waitIndexTarget(),
        "timeout",
        "Timed out waiting for element index."
      );
      if (waited && waited.error && waited.error.stage === "frame_unavailable") return waited.error;
      if (waited && waited.error) return waited.error;
      return {{ status: "success", action: "wait_index", index: request.index, result: "element_visible" }};
    }}

    if (request.action === "wait_enabled") {{
      const waited = await waitFor(
        () => ownerDocumentContains(el) && visible(el) && !blockedForAction(el, "input") ? el : null,
        "timeout",
        "Timed out waiting for element to become enabled."
      );
      if (waited && waited.error) return waited.error;
      return {{ status: "success", action: "wait_enabled", index: request.index, result: "element_enabled" }};
    }}

    if (el) {{
      el.scrollIntoView({{ block: "center", inline: "center", behavior: "instant" }});
      await sleep(50);
      if (!visible(el)) return fail("visibility", "Element is not visible.");
      const blocked = blockedForAction(el, request.action);
      if (blocked) return fail("visibility", blocked);
    }}

    if (request.action === "click") {{
      el.focus({{ preventScroll: true }});
      el.click();
      return finalizeMutatingAction({{ status: "success", action: "click", index: request.index, result: "clicked", page_changed: true }}, el);
    }}

    if (request.action === "input") {{
      if (request.text === null && request.value === null) return fail("invalid_args", "text or value is required for input.");
      if (!editableForInput(el)) return fail("invalid_args", "input action requires an editable text element.");
      const nextValue = String(request.text !== null ? request.text : request.value);
      el.focus({{ preventScroll: true }});
      const isContentEditable = isContentEditableTarget(el);
      if ("value" in el) {{
        const valueSetter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), "value")?.set;
        if (valueSetter) {{
          valueSetter.call(el, nextValue);
        }} else {{
          el.value = nextValue;
        }}
        dispatchInputEvents(el);
      }} else if (isContentEditable) {{
        const beforeInputFailure = dispatchContentEditableBeforeInput(el, nextValue);
        if (beforeInputFailure) return beforeInputFailure;
        el.textContent = nextValue;
        if ("innerText" in el) el.innerText = nextValue;
        dispatchContentEditableInputEvents(el, nextValue);
      }} else {{
        return fail("invalid_args", "input action requires an editable text element.");
      }}
      if ("value" in el && el.value !== nextValue) {{
        return fail("dom_event", "Input value was not accepted.");
      }}
      const inputType = String(el.getAttribute("type") || "").toLowerCase();
      return finalizeMutatingAction({{
        status: "success",
        action: "input",
        index: request.index,
        result: inputType === "password" ? "[REDACTED]" : "input_set",
        next_action_hint: "To submit/search after input, call browser_action with action='keys', text='Enter' and without index; this uses the focused element.",
        suggested_next_action: {{ action: "keys", text: "Enter" }},
        page_changed: true
      }}, el);
    }}

    if (request.action === "select") {{
      const wanted = String(request.value !== null ? request.value : request.text || "");
      if (!wanted) return fail("invalid_args", "value or text is required for select.");
      if (el.tagName !== "SELECT") {{
        const role = roleOf(el);
        const hasListboxPopup = String(el.getAttribute("aria-haspopup") || "").toLowerCase() === "listbox";
        if (role === "option") {{
          return {{
            status: "failed",
            action: request.action,
            index: request.index,
            stage: "control_unsupported",
            error: "select action only supports native select elements.",
            hint: "This is a custom option, not a native select. Click this option instead.",
            suggested_next_action: {{ action: "click", index: request.index }},
            retryable: true
          }};
        }}
        if (role === "listbox") {{
          return {{
            status: "failed",
            action: request.action,
            index: request.index,
            stage: "control_unsupported",
            error: "select action only supports native select elements.",
            hint: "This is an open custom listbox. Use browser_state to choose a visible child option, then click that option.",
            suggested_next_step: "Run browser_state and click the visible child option matching the desired value.",
            retryable: true
          }};
        }}
        if (role === "combobox" || hasListboxPopup) {{
          return {{
            status: "failed",
            action: request.action,
            index: request.index,
            stage: "control_unsupported",
            error: "select action only supports native select elements.",
            hint: "This appears to be a custom select/combobox. Click it, run browser_state again, then click the desired option.",
            suggested_next_action: {{ action: "click", index: request.index }},
            retryable: true
          }};
        }}
        return fail("invalid_args", "select action requires a select element.");
      }}
      const option = Array.from(el.options).find(opt => opt.value === wanted || opt.text.trim() === wanted);
      if (!option) return fail("locate", "No matching option found.");
      if (optionDisabled(option)) return fail("visibility", "Selected option is disabled.");
      if (optionOptgroupDisabled(option)) return fail("visibility", "Selected option's optgroup is disabled.");
      el.value = option.value;
      dispatchInputEvents(el);
      return finalizeMutatingAction({{ status: "success", action: "select", index: request.index, result: option.value, page_changed: true }}, el);
    }}

    if (request.action === "keys") {{
      const key = String(request.text || request.value || "");
      if (!key) return fail("invalid_args", "text or value is required for keys.");
      const allowedKeys = ["Enter", "Escape", "Tab", "Control+A", "Backspace"];
      if (!allowedKeys.includes(key)) return fail("invalid_args", "Unsupported key action.");
      const target = el || focusedElementInDocument(document) || document.body;
      if (!target) return fail("locate", "No keyboard target found.");
      if (target !== document.body && !visible(target)) return fail("visibility", "Keyboard target is not visible.");
      const blocked = blockedForAction(target, request.action);
      if (blocked) return fail("visibility", blocked);
      if (requiresEditableKey(key) && !editableForEditingKey(target)) {{
        return fail("invalid_args", "Focused element is not editable.");
      }}
      target.focus && target.focus({{ preventScroll: true }});
      if (key === "Control+A" && target.select) {{
        target.select();
      }} else if (key === "Backspace" && "value" in target) {{
        target.value = String(target.value || "").slice(0, -1);
        dispatchInputEvents(target);
      }} else {{
        const keydownAccepted = keyboardEvent(target, "keydown", key);
        keyboardEvent(target, "keyup", key);
        if (keydownAccepted !== false && shouldSubmitFormOnEnter(target, key)) {{
          submitFormOnEnter(target);
        }}
      }}
      return finalizeMutatingAction({{ status: "success", action: "keys", index: request.index, result: key, page_changed: true }}, target);
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
        self._failure_fuse = FailureFuse()
        self._failure_fuse_meta: dict[tuple[str, ...], dict[str, Any]] = {}

    @property
    def last_state_token(self) -> str | None:
        if not self._last_state:
            return None
        return self._last_state.get("state_token")

    @staticmethod
    def _cached_state_options(last_state: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(last_state, dict):
            return {}
        options = last_state.get("state_options")
        return options if isinstance(options, dict) else {}

    def _cached_state_supports(self, *, include_invisible: bool, max_elements: int) -> bool:
        options = self._cached_state_options(self._last_state)
        cached_include_invisible = bool(options.get("include_invisible"))
        cached_max_elements = options.get("max_elements")
        try:
            cached_max_elements_int = int(cached_max_elements)
        except (TypeError, ValueError):
            cached_max_elements_int = 120
        if cached_include_invisible != include_invisible:
            return False
        return cached_max_elements_int >= max_elements

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

    def _record_failure(
        self,
        result: dict[str, Any],
        *,
        driver: Any,
        target: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tab_id = str(getattr(driver, "default_session_id", "") or result.get("tab_id") or "")
        url = ""
        if self._last_state:
            url = str(self._last_state.get("url") or "")
        signature = self._failure_fuse._signature(result, tab_id=tab_id, url=url, target=target)
        if result.get("page_changed") is True or result.get("stage") == "verify_failed":
            self._failure_fuse_meta[signature] = {
                "original_stage": result.get("stage"),
                "page_changed": result.get("page_changed"),
            }
        recorded = self._failure_fuse.record(result, tab_id=tab_id, url=url, target=target)
        recorded.setdefault("tab_id", tab_id)
        if recorded.get("stage") == "repeat_blocked":
            meta = self._failure_fuse_meta.get(signature, {})
            if meta.get("original_stage") and "original_stage" not in recorded:
                recorded["original_stage"] = meta["original_stage"]
            if meta.get("page_changed") is True:
                recorded["page_changed"] = True
        return self._augment_truncated_refresh_recovery(recorded)

    def _preflight_repeated_failure(
        self,
        *,
        action: str,
        index: int | None,
        driver: Any,
        target: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not isinstance(target, dict):
            return None
        tab_id = str(getattr(driver, "default_session_id", "") or "")
        url = str((self._last_state or {}).get("url") or "")
        target = target or {}
        expected = (
            str(tab_id or ""),
            str(url or ""),
            str(action or ""),
            str(index or ""),
            str(target.get("stable_key") or ""),
            str(target.get("selector_hint") or ""),
            str(target.get("text") or target.get("value") or "")[:120],
        )
        for signature, count in self._failure_fuse._counts.items():
            if count < self._failure_fuse.threshold - 1:
                continue
            comparable = signature[:4] + signature[5:]
            if comparable != expected:
                continue
            result = failed_result(
                action,
                "repeat_blocked",
                "The same browser action failed repeatedly against the same target.",
                index,
            )
            result["tab_id"] = tab_id
            meta = self._failure_fuse_meta.get(signature, {})
            if meta.get("original_stage"):
                result["original_stage"] = meta["original_stage"]
            if meta.get("page_changed") is True:
                result["page_changed"] = True
            return result
        return None

    def _reset_failure_fuse(self) -> None:
        self._failure_fuse.reset()
        self._failure_fuse_meta.clear()

    def _should_clear_state_after_action(self, action: str, result: dict[str, Any]) -> bool:
        return action in STATE_MUTATING_ACTIONS and (
            result.get("status") == "success"
            or result.get("stage") == "verify_failed"
            or result.get("original_stage") == "verify_failed"
            or result.get("page_changed") is True
        )

    def _field_query_for_target(self, target: dict[str, Any] | None) -> str:
        if not isinstance(target, dict):
            return ""
        field_context = target.get("field_context") or {}
        if isinstance(field_context, dict):
            for key in ("row_label", "nearby_text", "previous_cell_text"):
                value = str(field_context.get(key) or "").strip()
                if value:
                    return value
        for key in ("text", "value"):
            value = str(target.get(key) or "").strip()
            if value:
                return value
        labels = target.get("labels") or []
        if isinstance(labels, list) and labels:
            return str(labels[0] or "").strip()
        return ""

    def _recipe_target_for_cached_element(self, index: int | None, target: dict[str, Any] | None) -> dict[str, Any]:
        query = self._field_query_for_target(target)
        if query:
            return {"query": query}
        if index is not None:
            return {"index": index}
        return {}

    def _visibility_recovery_control_kind(self, target: dict[str, Any] | None) -> str:
        control_kind = str((target or {}).get("control_kind") or "")
        return control_kind if control_kind in {"button", "custom_select"} else ""

    @staticmethod
    def _safe_truncation_total_limit(truncation: dict[str, Any]) -> int:
        try:
            return int(truncation.get("total_limit") or 120)
        except (TypeError, ValueError):
            return 120

    def _augment_truncated_refresh_recovery(self, result: dict[str, Any]) -> dict[str, Any]:
        recovery = result.get("recovery")
        if not isinstance(recovery, dict) or recovery.get("code") != "refresh_state":
            return result
        state = (self._last_state or {}).get("state") if isinstance(self._last_state, dict) else {}
        if not isinstance(state, dict) or not state.get("truncated"):
            return result
        truncation = state.get("truncation") if isinstance(state.get("truncation"), dict) else {}
        updated = dict(result)
        updated_recovery = dict(recovery)
        next_args = dict(updated_recovery.get("next_args") or {})
        next_args["max_elements"] = max(150, self._safe_truncation_total_limit(truncation) + 30)
        updated_recovery["next_args"] = next_args
        base_message = str(updated_recovery.get("message") or "").strip()
        truncation_message = (
            "The previous browser_state snapshot was truncated; use a larger max_elements value before choosing a fresh index."
        )
        updated_recovery["message"] = f"{base_message} {truncation_message}".strip()
        updated["recovery"] = updated_recovery
        return updated

    def _augment_action_recovery(
        self,
        result: dict[str, Any],
        *,
        action: str,
        index: int | None,
        target: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if result.get("status") != "failed":
            return result
        updated = dict(result)
        recovery = dict(updated.get("recovery") or {})
        query = self._field_query_for_target(target)
        control_kind = str((target or {}).get("control_kind") or "")
        if action == "click" and updated.get("stage") == "visibility" and query:
            next_args: dict[str, Any] = {"query": query, "refresh": True, "max_results": 5}
            recovery_control_kind = self._visibility_recovery_control_kind(target)
            if recovery_control_kind:
                next_args["control_kind"] = recovery_control_kind
            recovery.update(
                {
                    "code": "find_clickable_in_same_field",
                    "message": "The indexed wrapper is not clickable. Find a visible clickable control in the same field.",
                    "stop_retry": False,
                    "next_tool": "browser_find",
                    "next_args": next_args,
                }
            )
        elif updated.get("stage") == "repeat_blocked":
            alternatives = []
            if query:
                alternatives.append({"tool": "browser_find", "args": {"query": query, "refresh": True, "max_results": 5}})
            if control_kind == "custom_select" and query:
                alternatives.append({"tool": "browser_recipe", "args": {"recipe": "custom_select", "target": {"query": query}}})
            alternatives.append(
                {"tool": "web_execute_js", "reason": "Use low-level probing if structured metadata is insufficient."}
            )
            recovery["alternatives"] = alternatives
        updated["recovery"] = recovery
        return self._augment_truncated_refresh_recovery(updated)

    def get_state(
        self,
        driver: Any,
        *,
        switch_tab_id: str | None = None,
        include_invisible: bool = False,
        max_elements: int = 120,
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        log_event(
            "browser_state",
            "start",
            fields={
                "include_invisible": include_invisible,
                "max_elements": max_elements,
                "switch_tab_id": switch_tab_id,
            },
        )
        unavailable = self._ensure_driver(driver)
        if unavailable:
            self._last_state = None
            return _log_result("browser_state", started_at, unavailable)
        if switch_tab_id:
            if str(getattr(driver, "default_session_id", "") or "") != str(switch_tab_id):
                self._reset_failure_fuse()
            driver.default_session_id = str(switch_tab_id)

        script = build_browser_state_script(include_invisible=include_invisible, max_elements=max_elements)
        try:
            raw = _response_payload(driver.execute_js(script, timeout=10))
        except Exception as exc:
            self._last_state = None
            return _log_result("browser_state", started_at, failed_result(None, "dom_event", str(exc)))

        state = normalize_state_result(raw)
        if state.get("status") == "success":
            self._reset_failure_fuse()
            state["tab_id"] = state.get("tab_id") or driver.default_session_id
            elements_by_index = {}
            for element in state.get("elements", []):
                if not isinstance(element, dict):
                    continue
                element_index = _safe_index(element.get("index"))
                if element_index is not None:
                    elements_by_index[element_index] = element
            self._last_state = {
                "tab_id": state["tab_id"],
                "state_token": state.get("state_token"),
                "elements_by_index": elements_by_index,
                "state": state,
                "url": state.get("url", ""),
                "state_options": {
                    "include_invisible": include_invisible,
                    "max_elements": max_elements,
                },
            }
        else:
            self._last_state = None
        return _log_result(
            "browser_state",
            started_at,
            state,
            fields={
                "element_count": len(state.get("elements") or []) if isinstance(state.get("elements"), list) else 0,
                "elements": state.get("elements") if isinstance(state.get("elements"), list) else [],
                "url": state.get("url"),
            },
        )

    def find(
        self,
        driver: Any,
        *,
        query: str | None = None,
        role: str | None = None,
        control_kind: str | None = None,
        layer: str | None = None,
        frame_path: list[Any] | None = None,
        table: dict[str, Any] | None = None,
        max_results: int = 5,
        refresh: bool = False,
        include_invisible: bool = False,
        switch_tab_id: str | None = None,
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        limit = safe_max_results(max_results)
        log_event(
            "browser_find",
            "start",
            fields={
                "role": role,
                "control_kind": control_kind,
                "layer": layer,
                "frame_path": frame_path,
                "max_results": limit,
                "refresh": refresh,
                "include_invisible": include_invisible,
                "switch_tab_id": switch_tab_id,
            },
            sensitive={"query": query, "table": table},
        )

        def finish(result: dict[str, Any]) -> dict[str, Any]:
            fields: dict[str, Any] = {}
            matches = result.get("matches")
            if isinstance(matches, list):
                fields["match_count"] = len(matches)
            if result.get("ambiguous") is not None:
                fields["ambiguous"] = result.get("ambiguous")
            return _log_result("browser_find", started_at, result, fields=fields)

        has_locator = (
            str(query or "").strip()
            or (isinstance(table, dict) and any(table.get(key) for key in ("row_text", "column_text", "header_text")))
        )
        if not has_locator:
            return finish(
                find_in_state(
                    {"status": "success", "elements": []},
                    query=query,
                    role=role,
                    control_kind=control_kind,
                    layer=layer,
                    frame_path=frame_path,
                    table=table,
                    max_results=limit,
                )
            )
        requested_tab_id = str(switch_tab_id or getattr(driver, "default_session_id", "") or "")
        cached_tab_id = str((self._last_state or {}).get("tab_id") or "")
        if switch_tab_id:
            if str(getattr(driver, "default_session_id", "") or "") != str(switch_tab_id):
                self._reset_failure_fuse()
            driver.default_session_id = str(switch_tab_id)
        requested_max_elements = max(120, limit)
        should_refresh = refresh or not self._last_state or (requested_tab_id and cached_tab_id != requested_tab_id)
        if not should_refresh and not self._cached_state_supports(
            include_invisible=include_invisible,
            max_elements=requested_max_elements,
        ):
            should_refresh = True
        if should_refresh:
            state = self.get_state(
                driver,
                switch_tab_id=switch_tab_id,
                include_invisible=include_invisible,
                max_elements=requested_max_elements,
            )
        else:
            state = self._last_state.get("state") or {}
        result = find_in_state(
            state,
            query=query,
            role=role,
            control_kind=control_kind,
            layer=layer,
            frame_path=frame_path,
            table=table,
            max_results=limit,
        )
        recovery = result.get("recovery")
        if result.get("status") == "failed" and isinstance(recovery, dict):
            if refresh and result.get("stage") == "target_not_found":
                recovery = dict(recovery)
                recovery["code"] = "narrow_locator"
                recovery["message"] = "The refreshed browser state still did not contain this target. Stop repeating the same find call and provide a narrower query, table, layer, frame, or control constraint."
                recovery["stop_retry"] = True
                recovery.pop("next_tool", None)
                recovery.pop("next_args", None)
                recovery.pop("follow_up", None)
                result = dict(result)
                result["recovery"] = recovery
                return finish(result)
            next_args = dict(recovery.get("next_args") or {})
            if switch_tab_id:
                next_args["switch_tab_id"] = switch_tab_id
            if include_invisible:
                next_args["include_invisible"] = True
            if next_args:
                recovery = dict(recovery)
                recovery["next_args"] = next_args
                result = dict(result)
                result["recovery"] = recovery
        return finish(result)

    def run_action(
        self,
        driver: Any,
        *,
        action: str,
        index: int | None = None,
        text: str | None = None,
        value: str | None = None,
        selector: str | None = None,
        verify: str | None = None,
        verify_text: str | None = None,
        verify_value: str | None = None,
        verify_selector: str | None = None,
        timeout: int = 10,
        switch_tab_id: str | None = None,
    ) -> dict[str, Any]:
        action = str(action or "").strip()
        safe_index = _safe_index(index)
        safe_timeout = _safe_timeout(timeout)
        valid_verify = {"field_value", "text", "selector", "element_text"}
        verify = str(verify or "").strip() or None
        started_at = time.perf_counter()
        log_event(
            "browser_action",
            "start",
            fields={
                "action": action,
                "index": safe_index,
                "selector": selector,
                "verify": verify,
                "timeout": safe_timeout,
                "switch_tab_id": switch_tab_id,
                "has_text": text is not None,
                "has_value": value is not None,
            },
            sensitive={
                "text": text,
                "value": value,
                "verify_text": verify_text,
                "verify_value": verify_value,
            },
        )

        def finish(result: dict[str, Any]) -> dict[str, Any]:
            return _log_result(
                "browser_action",
                started_at,
                result,
                fields={
                    "action": result.get("action") or action,
                    "index": result.get("index") if result.get("index") is not None else safe_index,
                    "timeout": safe_timeout,
                    "verify": verify,
                },
            )

        if action not in SUPPORTED_ACTIONS:
            return finish(failed_result(action or None, "invalid_args", f"Unsupported browser action: {action}", safe_index))
        if verify and verify not in valid_verify:
            return finish(failed_result(action or None, "invalid_args", f"Unsupported verification type: {verify}", safe_index))
        if verify and action in WAIT_ACTIONS:
            return finish(failed_result(action, "invalid_args", "verify is not supported for wait actions.", safe_index))
        if verify == "field_value":
            expected = verify_value if verify_value is not None else value if value is not None else text
            if not str(expected or "").strip():
                return finish(
                    failed_result(
                        action,
                        "invalid_args",
                        "field_value verification requires a non-empty expected value.",
                        safe_index,
                    )
                )
        if verify in {"text", "element_text"} and not str(verify_text or "").strip():
            return finish(failed_result(action or None, "invalid_args", f"verify_text is required for {verify} verification.", safe_index))
        if verify == "selector" and not str(verify_selector or "").strip():
            return finish(failed_result(action or None, "invalid_args", "verify_selector is required for selector verification.", safe_index))
        if action in {"wait_text", "wait_selector", "wait_dom_stable", "wait_not_busy", "wait_route"}:
            safe_index = None
        if action in INDEX_REQUIRED_ACTIONS and safe_index is None:
            return finish(failed_result(action, "invalid_args", f"index is required for {action}."))
        if action == "wait_selector" and not selector:
            return finish(failed_result(action, "invalid_args", "selector is required for wait_selector."))
        if action == "wait_text" and not text:
            return finish(failed_result(action, "invalid_args", "text is required for wait_text."))
        if action == "wait_route" and not (text or value):
            return finish(failed_result(action, "invalid_args", "text or value is required for wait_route."))

        unavailable = self._ensure_driver(driver)
        if unavailable:
            unavailable["action"] = action
            if safe_index is not None:
                unavailable["index"] = safe_index
            return finish(unavailable)
        if switch_tab_id:
            if str(getattr(driver, "default_session_id", "") or "") != str(switch_tab_id):
                self._reset_failure_fuse()
            driver.default_session_id = str(switch_tab_id)

        state_token = None
        if action in INDEX_REQUIRED_ACTIONS or safe_index is not None:
            if not self._last_state:
                if action == "keys" and safe_index is not None:
                    result = keys_without_index_retry_result(action, safe_index, text, value)
                    return finish(self._record_failure(result, driver=driver))
                result = failed_result(action, "state_missing", f"Run browser_state before browser_action {action}.", safe_index)
                return finish(self._record_failure(result, driver=driver))
            if str(self._last_state.get("tab_id") or "") != str(driver.default_session_id):
                result = failed_result(
                    action,
                    "stale_index",
                    "Run browser_state before browser_action for the current tab.",
                    safe_index,
                )
                result["tab_id"] = driver.default_session_id
                target = (self._last_state.get("elements_by_index") or {}).get(safe_index)
                return finish(self._record_failure(result, driver=driver, target=target if isinstance(target, dict) else None))
            state_token = self._last_state.get("state_token")

        effective_selector = selector
        selector_tag = None
        selector_role = None
        selector_text = None
        frame_path: list[Any] = []
        cached_element = None
        if safe_index is not None and self._last_state:
            cached_element = (self._last_state.get("elements_by_index") or {}).get(safe_index)
            if isinstance(cached_element, dict):
                cached_frame_path = cached_element.get("frame_path")
                if isinstance(cached_frame_path, list):
                    frame_path = cached_frame_path
        if action == "wait_index" and safe_index is not None and self._last_state:
            if isinstance(cached_element, dict):
                hint = str(cached_element.get("selector_hint") or "").strip()
                tag = str(cached_element.get("tag") or "").strip()
                if not effective_selector and hint:
                    effective_selector = hint
                selector_tag = tag or None
                selector_role = str(cached_element.get("role") or "").strip() or None
                selector_text = str(cached_element.get("text") or "").strip() or None

        preflight_blocked = self._preflight_repeated_failure(
            action=action,
            index=safe_index,
            driver=driver,
            target=cached_element if isinstance(cached_element, dict) else None,
        )
        if preflight_blocked:
            preflight_blocked = self._augment_action_recovery(
                preflight_blocked,
                action=action,
                index=safe_index,
                target=cached_element if isinstance(cached_element, dict) else None,
            )
            if self._should_clear_state_after_action(action, preflight_blocked):
                self._last_state = None
            return finish(preflight_blocked)

        script = build_browser_action_script(
            action=action,
            index=safe_index,
            text=text,
            value=value,
            timeout=safe_timeout,
            state_token=state_token,
            selector=effective_selector,
            verify=verify,
            verify_text=verify_text,
            verify_value=verify_value,
            verify_selector=verify_selector,
            selector_tag=selector_tag,
            selector_role=selector_role,
            selector_text=selector_text,
            frame_path=frame_path,
        )

        try:
            raw = _response_payload(driver.execute_js(script, timeout=safe_timeout + 3))
        except Exception as exc:
            result = failed_result(action, "dom_event", str(exc), safe_index)
            result["tab_id"] = driver.default_session_id
            return finish(
                self._record_failure(
                    result,
                    driver=driver,
                    target=cached_element if isinstance(cached_element, dict) else None,
                )
            )

        if not isinstance(raw, dict):
            result = failed_result(action, "dom_event", "browser_action returned a non-object result", safe_index)
            result["tab_id"] = driver.default_session_id
            return finish(
                self._record_failure(
                    result,
                    driver=driver,
                    target=cached_element if isinstance(cached_element, dict) else None,
                )
            )

        result = dict(raw)
        result.setdefault("tab_id", driver.default_session_id)
        raw_result = dict(result)
        if result.get("status") == "success":
            if action == "click" and isinstance(cached_element, dict) and cached_element.get("control_kind") == "custom_select":
                recipe_target = self._recipe_target_for_cached_element(safe_index, cached_element)
                if recipe_target:
                    result = dict(result)
                    result["next_action_hint"] = {
                        "message": "Custom select may have opened an overlay. Refresh browser_state or run browser_recipe custom_select with option_text.",
                        "next_tools": ["browser_state", "browser_recipe"],
                        "recipe": {"recipe": "custom_select", "target": recipe_target},
                    }
            if action in STATE_MUTATING_ACTIONS:
                self._reset_failure_fuse()
        else:
            if action == "select" and result.get("stage") == "control_unsupported" and safe_index is not None:
                option_text = str(value if value is not None else text or "").strip()
                recipe_target = self._recipe_target_for_cached_element(safe_index, cached_element)
                if option_text and recipe_target:
                    result["suggested_args"] = {"target": recipe_target, "option_text": option_text}
            result = add_recovery(result, action=action, index=safe_index)
            result = self._augment_action_recovery(
                result,
                action=action,
                index=safe_index,
                target=cached_element if isinstance(cached_element, dict) else None,
            )
            result = self._record_failure(
                result,
                driver=driver,
                target=cached_element if isinstance(cached_element, dict) else None,
            )
            result = self._augment_action_recovery(
                result,
                action=action,
                index=safe_index,
                target=cached_element if isinstance(cached_element, dict) else None,
            )

        if self._should_clear_state_after_action(action, raw_result) or self._should_clear_state_after_action(action, result):
            self._last_state = None
        return finish(result)
