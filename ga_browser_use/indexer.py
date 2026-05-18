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


def _non_negative_int(value, default=0):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default

    return max(0, parsed)


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
    let current = element;
    for (let depth = 0; current && depth < 8; depth += 1) {{
      const role = String((current.getAttribute && current.getAttribute("role")) || "").toLowerCase();
      const popup = String((current.getAttribute && current.getAttribute("aria-haspopup")) || "").toLowerCase();
      const className = String((current.getAttribute && current.getAttribute("class")) || "").toLowerCase();
      const tokens = className.split(/[^a-z0-9]+/).filter(Boolean);
      const hasToken = (name) => tokens.some(token => token.includes(name));
      if (role === "combobox") return "combobox";
      if (popup === "listbox" || hasToken("select")) return "select";
      if (hasToken("browser")) return "browser";
      if (hasToken("picker")) return "picker";
      if (hasToken("field")) return "field";
      current = current.parentElement;
    }}
    return "";
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

  const isOverlayCandidate = (element) => {{
    const root = element && element.closest && element.closest(overlaySelector);
    return Boolean(root && root.matches && root.matches(overlaySelector));
  }};

  const countNonOverlayTail = (elements, startIndex) => {{
    let count = 0;
    for (let index = startIndex; index < elements.length; index += 1) {{
      if (!isOverlayCandidate(elements[index])) {{
        count += 1;
      }}
    }}
    return count;
  }};

  const countOverlayCandidates = (doc) => {{
    const candidates = new Set();
    const roots = doc.querySelectorAll(overlaySelector);
    for (let rootIndex = 0; rootIndex < roots.length; rootIndex += 1) {{
      const root = roots[rootIndex];
      if (root.matches && root.matches(selector)) {{
        candidates.add(root);
      }}
      for (const element of root.querySelectorAll(selector)) {{
        candidates.add(element);
      }}
    }}
    return candidates.size;
  }};

  const countDocumentCandidates = (doc) => {{
    const interactiveElements = doc.querySelectorAll(selector);
    return countNonOverlayTail(interactiveElements, 0) + countOverlayCandidates(doc);
  }};

  const countEditorBodyCandidate = (doc) => {{
    const editorBodyCandidate = doc.body;
    return (
      editorBodyCandidate &&
      (isContentEditableTarget(editorBodyCandidate) || String(doc.designMode || "").toLowerCase() === "on")
    ) ? 1 : 0;
  }};

  const layerContextOf = (element) => {{
    const root = element.closest && element.closest(overlaySelector);
    if (!root || !(root.matches && root.matches(overlaySelector))) {{
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

  const loadingSelector = [
    "[aria-busy='true']",
    "[role='progressbar']",
    "[data-loading='true']",
    ".loading",
    ".spinner",
    ".ant-spin-spinning",
    ".ant-skeleton",
  ].join(", ");

  const visibleNodes = (doc, candidateSelector) => {{
    return Array.from(doc.querySelectorAll(candidateSelector)).filter(node => {{
      if (node.matches) {{
        try {{
          if (!node.matches(candidateSelector)) return false;
        }} catch (error) {{
          return false;
        }}
      }}
      const nodeWindow = (node.ownerDocument && node.ownerDocument.defaultView) || window;
      return isVisible(node, node.getBoundingClientRect(), nodeWindow);
    }});
  }};

  const pageSignalsOf = () => {{
    const visibleLoading = visibleNodes(document, loadingSelector);
    const visibleOverlays = visibleNodes(document, overlaySelector);
    const focused = document.activeElement || null;
    return {{
      ready_state: document.readyState || "",
      busy: Boolean(visibleLoading.length > 0 || (document.body && document.body.getAttribute("aria-busy") === "true")),
      loading_count: visibleLoading.length,
      overlay_count: visibleOverlays.length,
      focused_selector_hint: focused && focused.tagName ? selectorHint(focused) : "",
    }};
  }};

  const frameInfoOf = (frame, framePath, sameOriginAccessible, childWindow, frameDocument, error) => {{
    let frameUrl = "";
    let frameTitle = "";
    try {{
      frameUrl = childWindow && childWindow.location ? String(childWindow.location.href || "") : "";
    }} catch (ignored) {{
      frameUrl = "";
    }}
    if (!frameUrl) {{
      frameUrl = frame.getAttribute("src") || "";
    }}
    if (frameDocument) {{
      frameTitle = frameDocument.title || "";
    }}
    if (!frameTitle) {{
      frameTitle = frame.getAttribute("title") || frame.getAttribute("name") || "";
    }}
    return {{
      frame_path: framePath,
      frame_depth: framePath.length,
      selector_hint: selectorHint(frame),
      visible: isVisibleInFrameChain(frame, frame.getBoundingClientRect(), frame.ownerDocument.defaultView || window),
      same_origin_accessible: Boolean(sameOriginAccessible),
      url: boundedText(frameUrl),
      title: boundedText(frameTitle),
      error: sameOriginAccessible ? "" : boundedText(error || "inaccessible"),
    }};
  }};

  const scanAnchorOf = (fieldContext, tableContext, layerContext, framePath) => {{
    return {{
      near_text: fieldContext.nearby_text || fieldContext.previous_cell_text || "",
      field_label: fieldContext.row_label || (fieldContext.labels && fieldContext.labels[0]) || "",
      row_text: tableContext.row_text || tableContext.row_header || "",
      column_text: tableContext.column_text || tableContext.column_header || tableContext.header_text || "",
      layer: layerContext.layer || "main",
      frame_path: framePath,
    }};
  }};

  const mainReserved = Math.max(1, Math.floor(maxElements * 0.6));
  const frameReserved = Math.max(1, maxElements - mainReserved);
  const overlayReserved = Math.max(1, Math.floor(maxElements * 0.2));
  const mainCapacity = Math.max(mainReserved, maxElements);
  const frameCapacity = Math.max(frameReserved, maxElements);
  const overlayCapacity = Math.max(overlayReserved, maxElements);
  const selectedMain = [];
  const selectedFrame = [];
  const selectedOverlay = [];
  const extraMain = [];
  const extraFrame = [];
  const extraOverlay = [];
  const frameSummaries = [];
  let sequence = 0;
  let omittedCount = 0;
  let iframeOmittedCount = 0;
  const seenElements = new WeakSet();
  const bucketStoredCount = (isFrame) => {{
    return isFrame ? selectedFrame.length + extraFrame.length : selectedMain.length + extraMain.length;
  }};
  const bucketCapacity = (isFrame) => isFrame ? frameCapacity : mainCapacity;
  const hasBucketCapacity = (isFrame) => bucketStoredCount(isFrame) < bucketCapacity(isFrame);
  const overlayStoredCount = () => selectedOverlay.length + extraOverlay.length;
  const hasOverlayCapacity = () => overlayStoredCount() < overlayCapacity;
  const recordOmitted = (count, isFrame) => {{
    const safeCount = Math.max(0, Number(count) || 0);
    omittedCount += safeCount;
    if (isFrame) {{
      iframeOmittedCount += safeCount;
    }}
  }};
  const addElement = (element, framePath, frameWindow, priority = "normal") => {{
    if (!element || seenElements.has(element)) {{
      return;
    }}
    const isFrameElement = Boolean(framePath.length);
    if (priority === "overlay") {{
      if (!hasOverlayCapacity()) {{
        recordOmitted(1, isFrameElement);
        return;
      }}
    }} else
    if (!hasBucketCapacity(isFrameElement)) {{
      recordOmitted(1, isFrameElement);
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
    const entry = {{ element, framePath, frameWindow, sequence: sequence++ }};
    if (priority === "overlay") {{
      if (selectedOverlay.length < overlayReserved) selectedOverlay.push(entry);
      else extraOverlay.push(entry);
    }} else if (isFrameElement) {{
      if (selectedFrame.length < frameReserved) selectedFrame.push(entry);
      else extraFrame.push(entry);
    }} else {{
      if (selectedMain.length < mainReserved) selectedMain.push(entry);
      else extraMain.push(entry);
    }}
  }};

  const collectOverlayCandidates = (doc, framePath, frameWindow) => {{
    const roots = doc.querySelectorAll(overlaySelector);
    for (let rootIndex = 0; rootIndex < roots.length; rootIndex += 1) {{
      if (!hasOverlayCapacity()) {{
        recordOmitted(roots.length - rootIndex, Boolean(framePath.length));
        break;
      }}
      const root = roots[rootIndex];
      if (!includeInvisible && !isVisible(root, root.getBoundingClientRect(), frameWindow)) {{
        continue;
      }}
      if (root.matches && root.matches(selector)) {{
        addElement(root, framePath, frameWindow, "overlay");
      }}
      const overlayElements = root.querySelectorAll(selector);
      for (let index = 0; index < overlayElements.length; index += 1) {{
        if (!hasOverlayCapacity()) {{
          recordOmitted(overlayElements.length - index, Boolean(framePath.length));
          break;
        }}
        addElement(overlayElements[index], framePath, frameWindow, "overlay");
      }}
    }}
  }};

  const collectDocument = (doc, framePath, frameWindow) => {{
    const isFrameDocument = Boolean(framePath.length);
    const interactiveElements = doc.querySelectorAll(selector);
    let frameBucketExhausted = false;
    for (let index = 0; index < interactiveElements.length; index += 1) {{
      const element = interactiveElements[index];
      if (isOverlayCandidate(element)) {{
        continue;
      }}
      if (!hasBucketCapacity(isFrameDocument)) {{
        recordOmitted(countNonOverlayTail(interactiveElements, index), isFrameDocument);
        frameBucketExhausted = isFrameDocument;
        break;
      }}
      addElement(element, framePath, frameWindow);
    }}

    if (frameBucketExhausted) {{
      collectOverlayCandidates(doc, framePath, frameWindow);
      return;
    }}

    collectOverlayCandidates(doc, framePath, frameWindow);

    const frames = doc.querySelectorAll("iframe, frame");
    for (let frameIndex = 0; frameIndex < frames.length; frameIndex += 1) {{
      const frame = frames[frameIndex];
      const childFramePath = framePath.concat(frameIndex);
      try {{
        const frameDocument = frame.contentDocument;
        const childWindow = frame.contentWindow;
        if (!frameDocument || !childWindow) {{
          frameSummaries.push(frameInfoOf(frame, childFramePath, false, childWindow, frameDocument, "missing frame document"));
          continue;
        }}
        frameSummaries.push(frameInfoOf(frame, childFramePath, true, childWindow, frameDocument, ""));
        const editorBodyCandidate = frameDocument.body;
        if (countEditorBodyCandidate(frameDocument)) {{
          addElement(editorBodyCandidate, childFramePath, childWindow);
        }}
        if (hasBucketCapacity(true)) {{
          collectDocument(frameDocument, childFramePath, childWindow);
        }} else {{
          recordOmitted(countDocumentCandidates(frameDocument), true);
        }}
      }} catch (error) {{
        const message = error && error.message ? error.message : "inaccessible frame";
        frameSummaries.push(frameInfoOf(frame, childFramePath, false, null, null, message));
        continue;
      }}
    }}
  }};

  collectDocument(document, [], window);

  const chooseLimitedElements = () => {{
    const selected = [];
    const addSelected = (entry) => {{
      if (entry && selected.length < maxElements && !selected.includes(entry)) {{
        selected.push(entry);
      }}
    }};

    const primaryEntries = selectedMain.concat(selectedFrame, selectedOverlay).sort((left, right) => left.sequence - right.sequence);
    if (maxElements === 1) {{
      addSelected(primaryEntries[0]);
    }} else {{
      addSelected(selectedMain[0]);
      addSelected(selectedFrame[0]);
      addSelected(selectedOverlay[0]);
    }}

    if (selected.length < maxElements) {{
      for (const entry of primaryEntries) {{
        addSelected(entry);
        if (selected.length >= maxElements) break;
      }}
    }}

    const extraEntries = extraOverlay.concat(extraMain, extraFrame).sort((left, right) => left.sequence - right.sequence);
    for (const entry of extraEntries) {{
      addSelected(entry);
      if (selected.length >= maxElements) break;
    }}

    const storedEntries = primaryEntries.concat(extraEntries);
    const droppedEntries = storedEntries.filter(entry => !selected.includes(entry));
    const droppedIframeCount = droppedEntries.filter(entry => entry.framePath.length).length;
    return {{
      elements: selected,
      truncation: {{
        omitted_count: omittedCount + droppedEntries.length,
        iframe_omitted_count: iframeOmittedCount + droppedIframeCount,
        total_limit: maxElements,
        main_reserved: mainReserved,
        frame_reserved: frameReserved,
      }},
    }};
  }};

  const limited = chooseLimitedElements();
  const elements = limited.elements;
  const truncation = limited.truncation;

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
    const fieldContext = fieldContextOf(element);
    const tableContext = tableContextOf(element);
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
      field_context: fieldContext,
      table_context: tableContext,
      scan_anchor: scanAnchorOf(fieldContext, tableContext, layerContext, framePath),
      layer: layerContext.layer,
      layer_root_hint: layerContext.layer_root_hint,
      modal_rank: layerContext.modal_rank,
      control_kind: controlKind,
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
    page_signals: pageSignalsOf(),
    frames: frameSummaries,
    truncated: truncation.omitted_count > 0,
    truncation,
    elements: snapshots,
  }};
}})();
""".strip()


def normalize_state_result(result):
    if not isinstance(result, dict):
        return {
            "status": "failed",
            "stage": "dom_event",
            "error": "browser_use_index returned a non-object result",
        }

    if result.get("status") == "failed":
        failed = dict(result)
        failed.setdefault("stage", "dom_event")
        failed.setdefault("error", "browser_use_index failed")
        return failed

    state = dict(result)
    state.setdefault("status", "success")
    state.setdefault("backend", "")
    state.setdefault("tab_id", "")
    state.setdefault("url", "")
    state.setdefault("title", "")
    state.setdefault("state_token", "")
    state.setdefault("viewport", {})
    page_signals = state.get("page_signals")
    if not isinstance(page_signals, dict):
        page_signals = {}
    page_signals = dict(page_signals)
    page_signals.setdefault("ready_state", "")
    page_signals["busy"] = bool(page_signals.get("busy", False))
    page_signals["loading_count"] = _non_negative_int(page_signals.get("loading_count"), 0)
    page_signals["overlay_count"] = _non_negative_int(page_signals.get("overlay_count"), 0)
    page_signals.setdefault("focused_selector_hint", "")
    state["page_signals"] = page_signals

    frames = state.get("frames")
    if not isinstance(frames, list):
        frames = []
    normalized_frames = []
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        normalized_frame = dict(frame)
        normalized_frame.setdefault("frame_path", [])
        normalized_frame.setdefault("frame_depth", len(normalized_frame.get("frame_path") or []))
        normalized_frame.setdefault("selector_hint", "")
        normalized_frame["visible"] = bool(normalized_frame.get("visible", False))
        normalized_frame["same_origin_accessible"] = bool(normalized_frame.get("same_origin_accessible", False))
        normalized_frame.setdefault("url", "")
        normalized_frame.setdefault("title", "")
        normalized_frame.setdefault("error", "")
        normalized_frames.append(normalized_frame)
    state["frames"] = normalized_frames

    elements = result.get("elements")
    if not isinstance(elements, list):
        elements = []

    truncation = state.get("truncation")
    if not isinstance(truncation, dict):
        truncation = {}
    truncation = dict(truncation)
    truncation["omitted_count"] = _non_negative_int(truncation.get("omitted_count"), 0)
    truncation["iframe_omitted_count"] = _non_negative_int(truncation.get("iframe_omitted_count"), 0)
    truncation["total_limit"] = _non_negative_int(truncation.get("total_limit"), len(elements))
    truncation["main_reserved"] = _non_negative_int(truncation.get("main_reserved"), 0)
    truncation["frame_reserved"] = _non_negative_int(truncation.get("frame_reserved"), 0)
    state["truncation"] = truncation
    if not isinstance(state.get("truncated"), bool):
        state["truncated"] = bool(truncation.get("omitted_count", 0))

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
        normalized.setdefault("scan_anchor", {})
        normalized.setdefault("layer", "main")
        normalized.setdefault("layer_root_hint", "")
        normalized.setdefault("modal_rank", 0)
        normalized.setdefault("control_kind", "")
        normalized.pop("recipe_hint", None)
        normalized.pop("action_hints", None)

        if str(normalized.get("type", "")).lower() == "password" and normalized.get("value"):
            normalized["value"] = "[REDACTED]"

        field_context = normalized.get("field_context")
        if isinstance(field_context, dict) and field_context:
            field_context = dict(field_context)
            normalized["field_context"] = field_context
            field_context.setdefault("nearby_text", "")
            field_context.setdefault("row_label", "")
            field_context.setdefault("previous_cell_text", "")
            field_context.setdefault("next_cell_text", "")
            field_context.setdefault("field_id", "")
            field_context.setdefault("field_name", "")
            field_context.setdefault("field_container_hint", "")

        scan_anchor = normalized.get("scan_anchor")
        if isinstance(scan_anchor, dict) and scan_anchor:
            scan_anchor = dict(scan_anchor)
            normalized["scan_anchor"] = scan_anchor
            scan_anchor.setdefault("near_text", "")
            scan_anchor.setdefault("field_label", "")
            scan_anchor.setdefault("row_text", "")
            scan_anchor.setdefault("column_text", "")
            scan_anchor.setdefault("layer", normalized.get("layer", "main"))
            scan_anchor.setdefault("frame_path", normalized.get("frame_path", []))

        normalized_elements.append(normalized)

    state["elements"] = normalized_elements
    return state
