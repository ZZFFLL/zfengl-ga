DEFAULT_MAX_ELEMENTS = 120
MIN_MAX_ELEMENTS = 1
MAX_MAX_ELEMENTS = 500

INTERACTIVE_SELECTOR = (
    'a[href], button, input, textarea, select, [role="button"], [role="link"], '
    '[role="textbox"], [role="checkbox"], [role="radio"], [role="combobox"], '
    '[role="menuitem"], [onclick], [tabindex], [contenteditable="true"]'
)


def _clamp_int(value, default, minimum, maximum):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default

    return max(minimum, min(maximum, parsed))


def build_browser_state_script(include_invisible=False, max_elements=DEFAULT_MAX_ELEMENTS):
    max_elements = _clamp_int(max_elements, DEFAULT_MAX_ELEMENTS, MIN_MAX_ELEMENTS, MAX_MAX_ELEMENTS)
    include_invisible_value = "true" if include_invisible else "false"

    return f"""
(() => {{
  const maxElements = {max_elements};
  const includeInvisible = {include_invisible_value};
  const selector = `{INTERACTIVE_SELECTOR}`;

  const cssEscape = (value) => {{
    if (window.CSS && window.CSS.escape) {{
      return window.CSS.escape(value);
    }}
    return String(value).replace(/["\\\\]/g, "\\\\$&");
  }};

  const textOf = (element) => {{
    const aria = element.getAttribute("aria-label") || "";
    const title = element.getAttribute("title") || "";
    const text = element.innerText || element.textContent || "";
    return (aria || title || text).trim().replace(/\\s+/g, " ");
  }};

  const boundedText = (value) => {{
    return String(value || "").slice(0, 240);
  }};

  const selectorHint = (element) => {{
    const tag = element.tagName.toLowerCase();
    const id = element.getAttribute("id");
    const name = element.getAttribute("name");
    if (id) {{
      return `${{tag}}#${{cssEscape(id)}}`;
    }}
    if (name) {{
      return `${{tag}}[name="${{cssEscape(name)}}"]`;
    }}
    return tag;
  }};

  const isVisible = (element, rect) => {{
    const style = window.getComputedStyle(element);
    return Boolean(
      rect.width &&
      rect.height &&
      style.visibility !== "hidden" &&
      style.display !== "none" &&
      Number(style.opacity || "1") > 0
    );
  }};

  const nativeRoleOf = (element, tag, type) => {{
    if (tag === "a" && element.hasAttribute("href")) {{
      return "link";
    }}
    if (tag === "button") {{
      return "button";
    }}
    if (tag === "select") {{
      return "combobox";
    }}
    if (tag === "textarea") {{
      return "textbox";
    }}
    if (tag === "input") {{
      const inputType = type.toLowerCase();
      if (inputType === "checkbox") {{
        return "checkbox";
      }}
      if (inputType === "radio") {{
        return "radio";
      }}
      if (["button", "submit", "reset"].includes(inputType)) {{
        return "button";
      }}
      return "textbox";
    }}
    return "";
  }};

  const elements = [];
  for (const element of document.querySelectorAll(selector)) {{
    if (elements.length >= maxElements) {{
      break;
    }}

    const rect = element.getBoundingClientRect();
    const visible = isVisible(element, rect);
    if (!includeInvisible && !visible) {{
      continue;
    }}

    elements.push(element);
  }}

  const snapshots = elements.map((element, index) => {{
    const rect = element.getBoundingClientRect();
    const tag = element.tagName.toLowerCase();
    const type = element.getAttribute("type") || "";
    const rawValue = "value" in element ? element.value : "";
    const value = type.toLowerCase() === "password" && rawValue ? "[REDACTED]" : rawValue;

    return {{
      index: index + 1,
      tag,
      role: element.getAttribute("role") || nativeRoleOf(element, tag, type),
      type,
      text: boundedText(textOf(element)),
      value: boundedText(value),
      visible: isVisible(element, rect),
      disabled: Boolean(element.disabled || element.getAttribute("aria-disabled") === "true"),
      bbox: {{
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height,
      }},
      selector_hint: selectorHint(element),
    }};
  }});

  window.__GA_BROWSER_STATE_COUNTER__ = (window.__GA_BROWSER_STATE_COUNTER__ || 0) + 1;
  const randomPart = Math.random().toString(36).slice(2);
  const stateToken = `${{Date.now()}}:${{window.__GA_BROWSER_STATE_COUNTER__}}:${{randomPart}}:${{elements.length}}`;
  window.__GA_BROWSER_ACTION_STATE__ = {{ token: stateToken, elements }};
  return {{
    state_token: stateToken,
    elements: snapshots,
  }};
}})();
""".strip()


def normalize_state_result(result):
    if not isinstance(result, dict):
        return {
            "status": "failed",
            "stage": "dom_event",
            "error": "browser_state returned a non-object result",
        }

    if result.get("status") == "failed":
        failed = dict(result)
        failed.setdefault("stage", "dom_event")
        failed.setdefault("error", "browser_state failed")
        return failed

    state = dict(result)
    state.setdefault("status", "success")
    state.setdefault("backend", "")
    state.setdefault("tab_id", "")
    state.setdefault("url", "")
    state.setdefault("title", "")
    state.setdefault("state_token", "")
    state.setdefault("viewport", {})
    elements = result.get("elements")
    if not isinstance(elements, list):
        elements = []

    normalized_elements = []
    for position, element in enumerate(elements, start=1):
        if not isinstance(element, dict):
            continue

        normalized = dict(element)
        normalized.setdefault("index", position)
        normalized.setdefault("tag", "")
        normalized.setdefault("type", "")
        normalized.setdefault("role", "")
        normalized.setdefault("text", "")
        normalized.setdefault("value", "")
        normalized.setdefault("visible", True)
        normalized.setdefault("disabled", False)
        normalized.setdefault("bbox", {})
        normalized.setdefault("selector_hint", "")

        if str(normalized.get("type", "")).lower() == "password" and normalized.get("value"):
            normalized["value"] = "[REDACTED]"

        normalized_elements.append(normalized)

    state["elements"] = normalized_elements
    return state
