DEFAULT_MAX_ELEMENTS = 120
MIN_MAX_ELEMENTS = 1
MAX_MAX_ELEMENTS = 500

INTERACTIVE_SELECTOR = (
    'a[href], button, input, textarea, select, [role="button"], [role="link"], '
    '[role="textbox"], [role="checkbox"], [role="radio"], [role="combobox"], '
    '[role="listbox"], [role="option"], [aria-haspopup="listbox"], [role="menuitem"], [onclick], '
    '[tabindex], [contenteditable="true"], .ant-select-selector, .ant-picker, '
    '.ui-browser-item, .ui-browser [role="treeitem"], .ui-browser [role="menuitem"]'
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
    const placeholder = element.getAttribute("placeholder") || "";
    const title = element.getAttribute("title") || "";
    const text = element.innerText || element.textContent || "";
    return [aria, placeholder, title, text].filter(Boolean).join(" ").trim().replace(/\\s+/g, " ");
  }};

  const boundedText = (value) => {{
    return String(value || "").slice(0, 240);
  }};

  const isDecorativeIconOnly = (element) => {{
    const className = String(element.getAttribute("class") || "");
    if (!/\\b(ui-icon|anticon|iconfont)\\b/.test(className)) return false;
    const tag = element.tagName.toLowerCase();
    const tabindex = element.getAttribute("tabindex");
    const hasTabAction = tabindex !== null && Number(tabindex) >= 0;
    const hasNativeAction = tag === "button" || tag === "input" || tag === "textarea" || tag === "select" || (tag === "a" && element.hasAttribute("href"));
    const hasActionSignal = hasNativeAction || element.getAttribute("role") || hasTabAction || element.getAttribute("onclick");
    return !hasActionSignal;
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

  const elementTreeVisible = (element, elementWindow) => {{
    if (!element) {{
      return false;
    }}
    if (typeof element.checkVisibility === "function") {{
      try {{
        if (!element.checkVisibility({{ checkOpacity: true, checkVisibilityCSS: true }})) {{
          return false;
        }}
      }} catch (error) {{
        try {{
          if (!element.checkVisibility()) {{
            return false;
          }}
        }} catch (ignored) {{
          // Fall back to computed style checks below.
        }}
      }}
    }}
    let current = element;
    while (current && current.nodeType !== 9) {{
      const currentWindow = (current.ownerDocument && current.ownerDocument.defaultView) || elementWindow || window;
      const style = currentWindow.getComputedStyle(current);
      if (
        current.hidden ||
        style.visibility === "hidden" ||
        style.visibility === "collapse" ||
        style.display === "none" ||
        style.contentVisibility === "hidden" ||
        Number(style.opacity || "1") <= 0
      ) {{
        return false;
      }}
      current = current.parentElement;
    }}
    return true;
  }};

  const isVisible = (element, rect, elementWindow) => {{
    return Boolean(
      rect.width &&
      rect.height &&
      elementTreeVisible(element, elementWindow)
    );
  }};

  const frameChainVisible = (elementWindow) => {{
    try {{
      let currentWindow = elementWindow;
      while (currentWindow && currentWindow.frameElement) {{
        const frame = currentWindow.frameElement;
        if (!frame.ownerDocument || !frame.ownerDocument.contains || !frame.ownerDocument.contains(frame)) {{
          return false;
        }}
        const parentWindow = frame.ownerDocument.defaultView || window;
        if (!isVisible(frame, frame.getBoundingClientRect(), parentWindow)) {{
          return false;
        }}
        currentWindow = parentWindow;
      }}
      return true;
    }} catch (error) {{
      return false;
    }}
  }};

  const isVisibleInFrameChain = (element, rect, elementWindow) => {{
    return isVisible(element, rect, elementWindow) && frameChainVisible(elementWindow);
  }};

  const isContentEditableTarget = (element) => {{
    const isDesignModeBody = Boolean(
      element &&
      element.ownerDocument &&
      element.ownerDocument.body === element &&
      String(element.ownerDocument.designMode || "").toLowerCase() === "on"
    );
    return Boolean(element && (
      element.isContentEditable ||
      element.getAttribute("contenteditable") === "true" ||
      isDesignModeBody
    ));
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

  const compactUnique = (values) => {{
    const seen = new Set();
    const result = [];
    for (const value of values) {{
      const text = String(value || "").trim().replace(/\\s+/g, " ");
      if (text && !seen.has(text)) {{
        seen.add(text);
        result.push(boundedText(text));
      }}
    }}
    return result;
  }};

  const labelsOf = (element) => {{
    const values = [];
    const doc = element.ownerDocument || document;
    values.push(element.getAttribute("aria-label"));
    const labelledBy = String(element.getAttribute("aria-labelledby") || "").split(/\\s+/).filter(Boolean);
    for (const id of labelledBy) {{
      const labelElement = doc.getElementById && doc.getElementById(id);
      if (labelElement) {{
        values.push(labelElement.innerText || labelElement.textContent || "");
      }}
    }}
    const id = element.getAttribute("id");
    if (id) {{
      try {{
        for (const label of doc.querySelectorAll(`label[for="${{cssEscape(id)}}"]`)) {{
          values.push(label.innerText || label.textContent || "");
        }}
      }} catch (error) {{
        // Ignore invalid selector edge cases from unusual ids.
      }}
    }}
    const parentLabel = element.closest && element.closest("label");
    if (parentLabel) {{
      values.push(parentLabel.innerText || parentLabel.textContent || "");
    }}
    values.push(element.getAttribute("placeholder"));
    return compactUnique(values);
  }};

  const attributesOf = (element) => {{
    const attr = (name) => element.getAttribute(name) || "";
    return {{
      id: attr("id"),
      name: attr("name"),
      class: attr("class"),
      role: attr("role"),
      aria_expanded: attr("aria-expanded"),
      aria_controls: attr("aria-controls"),
      aria_invalid: attr("aria-invalid"),
      data_testid: attr("data-testid") || attr("data-test"),
      autocomplete: attr("autocomplete"),
    }};
  }};

  const validationOf = (element) => {{
    const maxLength = element.getAttribute("maxlength");
    return {{
      required: Boolean(element.required || element.getAttribute("aria-required") === "true"),
      invalid: Boolean(element.getAttribute("aria-invalid") === "true" || (element.validity && element.validity.valid === false)),
      read_only: Boolean(element.readOnly || element.getAttribute("aria-readonly") === "true"),
      max_length: maxLength === null ? "" : maxLength,
      pattern: element.getAttribute("pattern") || "",
    }};
  }};

  const stableKeyOf = (element, tag, role) => {{
    const attrs = attributesOf(element);
    if (attrs.id) return `${{tag}}#${{attrs.id}}`;
    if (attrs.name) return `${{tag}}[name="${{attrs.name}}"]`;
    if (attrs.data_testid) return `${{tag}}[data-testid="${{attrs.data_testid}}"]`;
    const label = labelsOf(element)[0] || "";
    if (label) return `${{tag}}:${{role}}:${{label}}`;
    return `${{tag}}:${{role}}:${{boundedText(textOf(element))}}`;
  }};

  const textFromNode = (node) => boundedText(node ? (node.innerText || node.textContent || "") : "");

  const previousCellTextOf = (element) => {{
    const cell = element.closest && element.closest("td, th, [role='cell'], [role='gridcell'], [role='columnheader'], [role='rowheader']");
    const row = element.closest && element.closest("tr, [role='row']");
    if (!cell || !row) return "";
    const children = Array.from(row.children || []);
    const columnIndex = children.indexOf(cell);
    if (columnIndex <= 0) return "";
    for (let index = columnIndex - 1; index >= 0; index -= 1) {{
      const text = textFromNode(children[index]);
      if (text) return text;
    }}
    return "";
  }};

  const fieldAttrFrom = (element, attrName) => {{
    let current = element;
    while (current) {{
      const value = current.getAttribute && current.getAttribute(attrName);
      if (value && /field\\d+(?:_\\d+)?/i.test(String(value))) return String(value);
      current = current.parentElement;
    }}
    const own = element && element.getAttribute && element.getAttribute(attrName);
    return own ? String(own) : "";
  }};

  const fieldContainerHintOf = (element) => {{
    const cell = element.closest && element.closest("td, th, [role='cell'], [role='gridcell']");
    if (cell) {{
      return String(cell.tagName || (cell.getAttribute && cell.getAttribute("role")) || "").toLowerCase();
    }}
    const container = element.closest && element.closest(".wea-field, .wea-browser, .wea-select, .ant-select, .ant-picker");
    if (!container) return "";
    const className = String(container.getAttribute && container.getAttribute("class") || "");
    if (className.includes("wea-field")) return "wea-field";
    if (className.includes("wea-browser")) return "wea-browser";
    if (className.includes("wea-select")) return "wea-select";
    if (className.includes("ant-select")) return "ant-select";
    if (className.includes("ant-picker")) return "ant-picker";
    return String(container.tagName || "").toLowerCase();
  }};

  const fieldContextOf = (element) => {{
    const form = element.closest && element.closest("form");
    const fieldset = element.closest && element.closest("fieldset");
    const legend = fieldset && fieldset.querySelector("legend");
    const previousCellText = previousCellTextOf(element);
    return {{
      labels: labelsOf(element),
      placeholder: element.getAttribute("placeholder") || "",
      form_id: form ? (form.getAttribute("id") || "") : "",
      form_name: form ? (form.getAttribute("name") || "") : "",
      fieldset_legend: legend ? boundedText(legend.innerText || legend.textContent || "") : "",
      nearby_text: previousCellText,
      row_label: previousCellText,
      previous_cell_text: previousCellText,
      next_cell_text: "",
      field_id: fieldAttrFrom(element, "id"),
      field_name: fieldAttrFrom(element, "name"),
      field_container_hint: fieldContainerHintOf(element),
    }};
  }};

  const tableContextOf = (element) => {{
    const cell = element.closest && element.closest("td, th, [role='cell'], [role='gridcell'], [role='columnheader'], [role='rowheader']");
    const row = element.closest && element.closest("tr, [role='row']");
    const table = element.closest && element.closest("table, [role='table'], [role='grid']");
    if (!cell && !row && !table) {{
      return {{}};
    }}
    const rowChildren = row ? Array.from(row.children || []) : [];
    const tableRows = table ? Array.from(table.querySelectorAll("tr, [role='row']")) : [];
    const rowIndex = row && tableRows.length ? tableRows.indexOf(row) + 1 : 0;
    const columnIndex = cell && rowChildren.length ? rowChildren.indexOf(cell) + 1 : 0;
    const textFrom = (node) => boundedText(node ? (node.innerText || node.textContent || "") : "");
    const textFromChildren = (children) => boundedText(children.map(child => textFrom(child)).filter(Boolean).join(" "));
    const rowText = row ? (textFrom(row) || textFromChildren(rowChildren)) : "";
    const sameColumnCell = (candidateRow) => {{
      const children = Array.from((candidateRow && candidateRow.children) || []);
      return columnIndex > 0 ? children[columnIndex - 1] : null;
    }};
    const roleOf = (node) => String((node && node.getAttribute && node.getAttribute("role")) || "").toLowerCase();
    const tagOf = (node) => String((node && node.tagName) || "").toLowerCase();
    const isColumnHeader = (node) => {{
      const role = roleOf(node);
      const tag = tagOf(node);
      return tag === "th" || role === "columnheader";
    }};
    const firstRow = tableRows.length ? tableRows[0] : null;
    const firstRowColumn = sameColumnCell(firstRow);
    const explicitHeader = tableRows
      .map(candidateRow => sameColumnCell(candidateRow))
      .find(candidateCell => candidateCell && isColumnHeader(candidateCell));
    const rowHeaderCell = rowChildren.find(candidateCell => {{
      const role = roleOf(candidateCell);
      const tag = tagOf(candidateCell);
      return candidateCell !== cell && (tag === "th" || role === "rowheader");
    }}) || (columnIndex > 1 ? rowChildren[0] : null);
    return {{
      table_role: table ? (table.getAttribute("role") || table.tagName.toLowerCase()) : "",
      table_label: table ? (table.getAttribute("aria-label") || labelsOf(table)[0] || "") : "",
      row_index: rowIndex,
      column_index: columnIndex,
      cell_role: cell ? (cell.getAttribute("role") || cell.tagName.toLowerCase()) : "",
      cell_text: cell ? boundedText(cell.innerText || cell.textContent || "") : "",
      row_text: rowText,
      row_header: rowHeaderCell ? textFrom(rowHeaderCell) : "",
      column_header: explicitHeader ? textFrom(explicitHeader) : (firstRowColumn && firstRow !== row ? textFrom(firstRowColumn) : ""),
      column_text: explicitHeader ? textFrom(explicitHeader) : (firstRowColumn && firstRow !== row ? textFrom(firstRowColumn) : ""),
      header_text: explicitHeader ? textFrom(explicitHeader) : (firstRowColumn && firstRow !== row ? textFrom(firstRowColumn) : ""),
    }};
  }};

  const layerContextOf = (element) => {{
    const overlaySelector = [
      ".ant-modal",
      ".ant-drawer",
      ".ant-select-dropdown",
      ".ant-dropdown",
      "[role='dialog']",
      "[aria-modal='true']",
      "[role='menu']",
      "[role='listbox']",
      "[data-popover]",
      ".modal",
      ".drawer",
      ".dropdown",
      ".popover",
    ].join(", ");
    const root = element.closest && element.closest(overlaySelector);
    if (!root) {{
      return {{ layer: "main", layer_root_hint: "", modal_rank: 0 }};
    }}
    const className = String(root.getAttribute("class") || "");
    let layer = "overlay";
    if (root.matches(".ant-modal, [role='dialog'], [aria-modal='true'], .modal")) layer = "modal";
    else if (root.matches(".ant-drawer, .drawer")) layer = "drawer";
    else if (root.matches(".ant-select-dropdown, .ant-dropdown, .dropdown")) layer = "dropdown";
    else if (root.matches("[data-popover], .popover")) layer = "popover";
    const visibleOverlays = Array.from((root.ownerDocument || document).querySelectorAll(overlaySelector))
      .filter(node => isVisible(node, node.getBoundingClientRect(), node.ownerDocument.defaultView || window));
    return {{
      layer,
      layer_root_hint: selectorHint(root),
      modal_rank: visibleOverlays.indexOf(root) + 1,
      layer_class: className,
    }};
  }};

  const controlKindOf = (element, tag, role, type) => {{
    const normalizedType = String(type || "").toLowerCase();
    const normalizedRole = String(role || "").toLowerCase();
    const hasListboxPopup = String(element.getAttribute("aria-haspopup") || "").toLowerCase() === "listbox";
    if (tag === "select") return "native_select";
    if (normalizedRole === "combobox" || hasListboxPopup) return "custom_select";
    if (normalizedRole === "option" || tag === "option") return "option";
    if (tag === "textarea") return "textarea";
    if (isContentEditableTarget(element)) return "contenteditable";
    if (tag === "input" && ["date", "datetime-local", "month", "time", "week"].includes(normalizedType)) return "date_input";
    if (tag === "input") return "native_input";
    if (tag === "button" || normalizedRole === "button") return "button";
    if ((tag === "a" && element.hasAttribute("href")) || normalizedRole === "link") return "link";
    return normalizedRole || tag;
  }};

  const actionHintsOf = (element, tag, role, controlKind) => {{
    if (controlKind === "custom_select") return ["click_to_open", "state_after_open", "select_option_by_click"];
    if (controlKind === "native_select") return ["select_by_value_or_text"];
    if (controlKind === "option") return ["click_to_select"];
    if (controlKind === "contenteditable") return ["input", "verify_field_value"];
    if (["native_input", "textarea", "date_input"].includes(controlKind)) return ["input", "verify_field_value", "keys_after_input"];
    if (["button", "link"].includes(controlKind)) return ["click"];
    return [];
  }};

  const elements = [];
  const seenElements = new WeakSet();
  const addElement = (element, framePath, frameWindow) => {{
    if (!element || seenElements.has(element) || elements.length >= maxElements) {{
      return;
    }}
    if (!frameChainVisible(frameWindow)) {{
      return;
    }}
    if (isDecorativeIconOnly(element)) {{
      return;
    }}

    const rect = element.getBoundingClientRect();
    const visible = isVisible(element, rect, frameWindow);
    if (!includeInvisible && !visible) {{
      return;
    }}

    seenElements.add(element);
    elements.push({{ element, framePath, frameWindow }});
  }};

  const collectDocument = (doc, framePath, frameWindow) => {{
    for (const element of doc.querySelectorAll(selector)) {{
      if (elements.length >= maxElements) {{
        break;
      }}

      addElement(element, framePath, frameWindow);
    }}

    if (elements.length >= maxElements) {{
      return;
    }}

    const frames = doc.querySelectorAll("iframe, frame");
    for (let frameIndex = 0; frameIndex < frames.length; frameIndex += 1) {{
      if (elements.length >= maxElements) {{
        break;
      }}

      const frame = frames[frameIndex];
      try {{
        const frameDocument = frame.contentDocument;
        const childWindow = frame.contentWindow;
        if (!frameDocument || !childWindow) {{
          continue;
        }}
        const editorBodyCandidate = frameDocument.body;
        if (
          editorBodyCandidate &&
          (isContentEditableTarget(frameDocument.body) || String(frameDocument.designMode || "").toLowerCase() === "on")
        ) {{
          addElement(editorBodyCandidate, framePath.concat(frameIndex), childWindow);
        }}
        collectDocument(frameDocument, framePath.concat(frameIndex), childWindow);
      }} catch (error) {{
        continue;
      }}
    }}
  }};

  collectDocument(document, [], window);

  const snapshots = elements.map((entry, index) => {{
    const element = entry.element;
    const frameWindow = entry.frameWindow || window;
    const framePath = entry.framePath || [];
    const rect = element.getBoundingClientRect();
    const tag = element.tagName.toLowerCase();
    const type = element.getAttribute("type") || "";
    const role = element.getAttribute("role") || nativeRoleOf(element, tag, type);
    const controlKind = controlKindOf(element, tag, role, type);
    const layerContext = layerContextOf(element);
    const rawValue = "value" in element ? element.value : "";
    const value = type.toLowerCase() === "password" && rawValue ? "[REDACTED]" : rawValue;

    return {{
      index: index + 1,
      tag,
      role,
      type,
      text: boundedText(textOf(element)),
      value: boundedText(value),
      visible: isVisibleInFrameChain(element, rect, frameWindow),
      disabled: Boolean(element.disabled || element.getAttribute("aria-disabled") === "true"),
      bbox: {{
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height,
      }},
      selector_hint: selectorHint(element),
      frame_path: framePath,
      frame_depth: framePath.length,
      frame_url: frameWindow.location.href,
      frame_title: element.ownerDocument.title,
      labels: labelsOf(element),
      attributes: attributesOf(element),
      validation: validationOf(element),
      stable_key: stableKeyOf(element, tag, role),
      field_context: fieldContextOf(element),
      table_context: tableContextOf(element),
      layer: layerContext.layer,
      layer_root_hint: layerContext.layer_root_hint,
      modal_rank: layerContext.modal_rank,
      control_kind: controlKind,
      action_hints: actionHintsOf(element, tag, role, controlKind),
    }};
  }});

  window.__GA_BROWSER_STATE_COUNTER__ = (window.__GA_BROWSER_STATE_COUNTER__ || 0) + 1;
  const randomPart = Math.random().toString(36).slice(2);
  const stateToken = `${{Date.now()}}:${{window.__GA_BROWSER_STATE_COUNTER__}}:${{randomPart}}:${{elements.length}}`;
  const actionElements = elements.map(entry => entry.element);
  window.__GA_BROWSER_ACTION_STATE__ = {{ token: stateToken, elements: actionElements }};
  return {{
    status: "success",
    backend: "tmwd_user_chrome",
    url: location.href,
    title: document.title,
    viewport: {{
      width: window.innerWidth,
      height: window.innerHeight,
      scroll_x: window.scrollX,
      scroll_y: window.scrollY,
    }},
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
        normalized.setdefault("frame_path", [])
        normalized.setdefault("frame_depth", 0)
        normalized.setdefault("frame_url", "")
        normalized.setdefault("frame_title", "")
        normalized.setdefault("labels", [])
        normalized.setdefault("attributes", {})
        normalized.setdefault("validation", {})
        normalized.setdefault("stable_key", "")
        normalized.setdefault("field_context", {})
        normalized.setdefault("table_context", {})
        normalized.setdefault("layer", "main")
        normalized.setdefault("layer_root_hint", "")
        normalized.setdefault("modal_rank", 0)
        normalized.setdefault("control_kind", "")
        normalized.setdefault("action_hints", [])

        if str(normalized.get("type", "")).lower() == "password" and normalized.get("value"):
            normalized["value"] = "[REDACTED]"

        field_context = normalized.get("field_context")
        if isinstance(field_context, dict) and field_context:
            field_context.setdefault("nearby_text", "")
            field_context.setdefault("row_label", "")
            field_context.setdefault("previous_cell_text", "")
            field_context.setdefault("next_cell_text", "")
            field_context.setdefault("field_id", "")
            field_context.setdefault("field_name", "")
            field_context.setdefault("field_container_hint", "")

        normalized_elements.append(normalized)

    state["elements"] = normalized_elements
    return state
