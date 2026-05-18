import json
import subprocess

from browser_indexer import build_browser_state_script, normalize_state_result


def run_browser_state_script(script, setup_js):
    node_code = "\n".join(
        [
            f"const script = {json.dumps(script)};",
            """
function makeElement(options = {}) {
  const attrs = options.attrs || {};
  const element = {
    tagName: String(options.tag || "div").toUpperCase(),
    innerText: options.text || "",
    textContent: options.text || "",
    disabled: Boolean(options.disabled),
    readOnly: Boolean(options.readOnly),
    required: Boolean(options.required),
    validity: options.validity || { valid: true },
    isContentEditable: Boolean(options.contentEditable),
    _style: options.visible === false
      ? { display: "block", visibility: "hidden", opacity: "1" }
      : { display: "block", visibility: "visible", opacity: "1" },
    getAttribute(name) {
      if (name === "role" && options.role) return options.role;
      if (name === "type" && options.type) return options.type;
      if (name === "id" && options.id) return options.id;
      if (name === "name" && options.name) return options.name;
      if (name === "contenteditable" && options.contentEditable) return "true";
      return attrs[name] ?? null;
    },
    hasAttribute(name) {
      return this.getAttribute(name) !== null;
    },
    getBoundingClientRect() {
      return {
        x: 0,
        y: 0,
        width: options.width === undefined ? 10 : options.width,
        height: options.height === undefined ? 10 : options.height,
      };
    },
    closest() {
      return null;
    },
    matches() {
      return false;
    },
    querySelectorAll() {
      return [];
    },
  };
  if (Object.prototype.hasOwnProperty.call(options, "value")) {
    element.value = options.value;
  }
  element.ownerDocument = options.ownerDocument || document;
  return element;
}
global.window = {
  CSS: { escape: (value) => String(value) },
  innerWidth: 1280,
  innerHeight: 720,
  scrollX: 0,
  scrollY: 0,
  location: { href: "https://example.test/" },
  getComputedStyle: (el) => el._style || { display: "block", visibility: "visible", opacity: "1" },
};
global.location = window.location;
global.document = {
  title: "Top",
  defaultView: window,
  body: null,
  getElementById: (_id) => null,
  querySelectorAll: (_selector) => [],
};
document.body = makeElement({ tag: "body" });
""",
            setup_js,
            """
const result = eval(script);
const finalResult = typeof global.__afterBrowserState === "function" ? global.__afterBrowserState(result) : result;
console.log(JSON.stringify(finalResult));
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


def test_build_browser_state_script_contains_index_state_and_limit():
    script = build_browser_state_script(include_invisible=False, max_elements=3)

    assert "window.__GA_BROWSER_ACTION_STATE__" in script
    assert "const maxElements = 3;" in script
    assert "const includeInvisible = false;" in script
    assert "a[href]" in script
    assert "[onclick]" in script
    assert "[contenteditable=\"true\"]" in script
    assert "const isContentEditableTarget = (element) =>" in script
    assert "contenteditable" in script
    assert '"input"' in script
    assert "scan_anchor" in script


def test_build_browser_state_script_indexes_same_origin_editor_frame_body():
    script = build_browser_state_script()

    assert "editorBodyCandidate" in script
    assert "designMode" in script
    assert "isContentEditableTarget(editorBodyCandidate)" in script


def test_build_browser_state_script_includes_custom_select_roles():
    script = build_browser_state_script()

    assert "[role=\"option\"]" in script
    assert "[role=\"listbox\"]" in script


def test_build_browser_state_script_includes_aria_haspopup_listbox_trigger():
    script = build_browser_state_script()

    assert '[aria-haspopup="listbox"]' in script


def test_build_browser_state_script_includes_antd_picker_and_ui_browser_patterns():
    script = build_browser_state_script()

    assert ".ant-picker" in script
    assert ".ant-select-selector" in script
    assert ".ui-browser" in script


def test_browser_state_script_indexes_ui_browser_actionable_item_but_not_naked_icon():
    script = build_browser_state_script(max_elements=20)

    result = run_browser_state_script(
        script,
        """
const decorativeIcon = makeElement({
  tag: "span",
  text: "decorative",
  attrs: { class: "ui-icon" },
});
const targetNode = makeElement({
  tag: "div",
  text: "目标节点",
  attrs: { class: "ui-browser-item", tabindex: "0" },
});
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
  const matches = [];
  if (selector.includes(".ui-icon")) matches.push(decorativeIcon);
  if (selector.includes(".ui-browser-item")) matches.push(targetNode);
  return matches;
};
""",
    )

    texts = [element["text"] for element in result["elements"]]
    assert "目标节点" in texts
    assert "decorative" not in texts


def test_browser_state_script_filters_decorative_icon_candidate_with_tabindex_minus_one():
    script = build_browser_state_script(max_elements=20, include_invisible=True)

    result = run_browser_state_script(
        script,
        """
const decorativeIcon = makeElement({
  tag: "span",
  text: "decorative",
  attrs: { class: "ui-icon", tabindex: "-1" },
});
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
  if (selector.includes("[tabindex]")) return [decorativeIcon];
  return [];
};
""",
    )

    assert [element["text"] for element in result["elements"]] == []


def test_browser_state_script_keeps_native_icon_button_and_link_controls():
    script = build_browser_state_script(max_elements=20)

    result = run_browser_state_script(
        script,
        """
const refreshButton = makeElement({
  tag: "button",
  attrs: { class: "anticon", "aria-label": "刷新" },
});
const openLink = makeElement({
  tag: "a",
  attrs: { class: "ui-icon", href: "/open", "aria-label": "打开" },
});
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
  const matches = [];
  if (selector.includes("button")) matches.push(refreshButton);
  if (selector.includes("a[href]")) matches.push(openLink);
  return matches;
};
""",
    )

    texts = [element["text"] for element in result["elements"]]
    assert "刷新" in texts
    assert "打开" in texts


def test_build_browser_state_script_defaults_to_visible_elements_only():
    script = build_browser_state_script()

    assert "const includeInvisible = false;" in script


def test_build_browser_state_script_clamps_max_elements():
    low = build_browser_state_script(max_elements=0)
    high = build_browser_state_script(max_elements=9999)

    assert "const maxElements = 1;" in low
    assert "const maxElements = 500;" in high


def test_build_browser_state_script_infers_native_roles():
    script = build_browser_state_script()

    assert "const nativeRoleOf = (element, tag, type) =>" in script
    assert 'if (tag === "a" && element.hasAttribute("href")) {' in script
    assert 'if (tag === "button") {' in script
    assert 'if (tag === "select") {' in script
    assert 'if (tag === "textarea") {' in script
    assert 'if (tag === "input") {' in script
    assert 'const role = element.getAttribute("role") || nativeRoleOf(element, tag, type);' in script
    assert "role," in script


def test_build_browser_state_script_includes_placeholder_text():
    script = build_browser_state_script()

    assert 'element.getAttribute("placeholder") || ""' in script


def test_build_browser_state_script_includes_metadata_helpers():
    script = build_browser_state_script()

    for helper in [
        "labelsOf",
        "attributesOf",
        "validationOf",
        "stableKeyOf",
        "fieldContextOf",
        "tableContextOf",
        "layerContextOf",
        "controlKindOf",
        "pageSignalsOf",
        "frameInfoOf",
        "scanAnchorOf",
    ]:
        assert f"const {helper} = " in script

    for field in [
        "labels: labelsOf(element),",
        "attributes: attributesOf(element),",
        "validation: validationOf(element),",
        "stable_key: stableKeyOf(element, tag, role),",
        "field_context: fieldContext,",
        "table_context: tableContext,",
        "scan_anchor: scanAnchorOf(fieldContext, tableContext, layerContext, framePath),",
        "layer: layerContext.layer,",
        "layer_root_hint: layerContext.layer_root_hint,",
        "modal_rank: layerContext.modal_rank,",
        "control_kind: controlKind,",
    ]:
        assert field in script


def test_build_browser_state_script_includes_overlay_patterns_and_control_kinds():
    script = build_browser_state_script()

    assert ".ant-modal" in script
    assert ".ant-drawer" in script
    assert ".ant-select-dropdown" in script
    assert ".ant-dropdown" in script
    assert "custom_select" in script
    assert "native_select" in script


def test_build_browser_state_script_separates_cached_nodes_from_snapshots():
    script = build_browser_state_script()

    assert "const snapshots = elements.map((entry, index) =>" in script
    assert "const actionElements = elements.map(entry => entry.element);" in script
    assert "const stateToken =" in script
    assert "window.__GA_BROWSER_ACTION_STATE__ = { token: stateToken, elements: actionElements };" in script
    assert 'status: "success",' in script
    assert 'backend: "tmwd_user_chrome",' in script
    assert "url: location.href," in script
    assert "title: document.title," in script
    assert "viewport: {" in script
    assert "width: window.innerWidth," in script
    assert "height: window.innerHeight," in script
    assert "scroll_x: window.scrollX," in script
    assert "scroll_y: window.scrollY," in script
    assert "state_token: stateToken," in script
    assert "elements: snapshots," in script


def test_build_browser_state_script_traverses_same_origin_frames():
    script = build_browser_state_script()

    assert "collectDocument(document, [], window)" in script
    assert 'querySelectorAll("iframe, frame")' in script
    assert "frame.contentDocument" in script
    assert "frame_path" in script
    assert "frame_depth" in script
    assert "frame_url" in script
    assert "frame_title" in script


def test_browser_state_script_indexes_same_origin_design_mode_frame_body():
    script = build_browser_state_script(include_invisible=False, max_elements=10)

    state = run_browser_state_script(
        script,
        """
const editorIframe = makeElement({ tag: "iframe", ownerDocument: document });
const frameWindow = {
  ...window,
  frameElement: editorIframe,
  parent: window,
  location: { href: "https://example.test/editor" },
};
const frameDocument = {
  title: "Editor Frame",
  defaultView: frameWindow,
  designMode: "on",
  body: null,
  getElementById: (_id) => null,
  querySelectorAll: (_selector) => [],
};
frameDocument.body = makeElement({
  tag: "body",
  text: "Editable frame body",
  ownerDocument: frameDocument,
});
editorIframe.contentDocument = frameDocument;
editorIframe.contentWindow = frameWindow;
document.contains = (element) => element === editorIframe || element === document.body;
document.querySelectorAll = (selector) => selector === "iframe, frame" ? [editorIframe] : [];
""",
    )

    assert state["status"] == "success"
    assert len(state["elements"]) == 1
    element = state["elements"][0]
    assert element["tag"] == "body"
    assert element["text"] == "Editable frame body"
    assert element["visible"] is True
    assert element["frame_path"] == [0]
    assert element["frame_depth"] == 1
    assert element["frame_url"] == "https://example.test/editor"
    assert element["frame_title"] == "Editor Frame"
    assert element["control_kind"] == "contenteditable"
    assert element["scan_anchor"]["frame_path"] == [0]


def test_browser_state_script_keeps_keys_after_input_for_textarea_and_date_input():
    script = build_browser_state_script(include_invisible=False, max_elements=10)

    state = run_browser_state_script(
        script,
        """
const notes = makeElement({ tag: "textarea", text: "", value: "" });
const dueDate = makeElement({ tag: "input", type: "date", value: "2026-05-17" });
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
  return [notes, dueDate];
};
""",
    )

    assert state["status"] == "success"
    by_kind = {element["control_kind"]: element for element in state["elements"]}
    assert "action_hints" not in by_kind["textarea"]
    assert "action_hints" not in by_kind["date_input"]


def test_browser_state_script_marks_ant_select_trigger_and_overlay_option():
    script = build_browser_state_script(include_invisible=False, max_elements=10)

    state = run_browser_state_script(
        script,
        """
const trigger = makeElement({
  tag: "div",
  id: "leave-select",
  text: "Select leave",
  role: "combobox",
  attrs: { "aria-haspopup": "listbox" },
});
const dropdownRoot = makeElement({
  tag: "div",
  attrs: { class: "ant-select-dropdown" },
});
dropdownRoot.matches = (selector) => selector.includes(".ant-select-dropdown");
const option = makeElement({
  tag: "div",
  text: "Yes",
  role: "option",
});
dropdownRoot.querySelectorAll = (selector) => selector.includes("[role=\\"option\\"]") ? [option] : [];
option.closest = (selector) => {
  if (selector.includes(".ant-select-dropdown") || selector.includes("[role='listbox']")) return dropdownRoot;
  return null;
};
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
  if (selector.includes(".ant-select-dropdown") && selector.includes("[role='listbox']")) return [dropdownRoot];
  return [trigger, option];
};
""",
    )

    assert state["status"] == "success"
    by_text = {element["text"]: element for element in state["elements"]}
    assert by_text["Select leave"]["control_kind"] == "custom_select"
    assert "action_hints" not in by_text["Select leave"]
    assert by_text["Yes"]["control_kind"] == "option"
    assert "action_hints" not in by_text["Yes"]
    assert by_text["Yes"]["layer"] == "dropdown"
    assert by_text["Yes"]["modal_rank"] == 1


def test_browser_state_script_emits_rich_field_and_table_metadata():
    script = build_browser_state_script(include_invisible=False, max_elements=10)

    state = run_browser_state_script(
        script,
        """
const label = makeElement({ tag: "label", text: "Project Name" });
const legend = makeElement({ tag: "legend", text: "Project Fields" });
const fieldset = makeElement({ tag: "fieldset" });
fieldset.querySelector = (selector) => selector === "legend" ? legend : null;
const form = makeElement({ tag: "form", id: "project-form", name: "projectForm" });
const cell = makeElement({ tag: "td", text: "Project Name" });
const row = makeElement({ tag: "tr" });
const table = makeElement({ tag: "table", attrs: { "aria-label": "Projects" } });
row.children = [cell];
table.querySelectorAll = (selector) => selector === "tr, [role='row']" ? [row] : [];
const input = makeElement({
  tag: "input",
  id: "project",
  name: "project",
  type: "text",
  value: "Apollo",
  required: true,
  attrs: {
    "aria-invalid": "true",
    "data-testid": "project-input",
    "placeholder": "Project"
  }
});
input.closest = (selector) => {
  if (selector === "form") return form;
  if (selector === "fieldset") return fieldset;
  if (selector.includes("td")) return cell;
  if (selector.includes("tr")) return row;
  if (selector.includes("table")) return table;
  return null;
};
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame") return [];
  if (selector.startsWith("label[")) return [label];
  return [input];
};
""",
    )

    assert state["status"] == "success"
    assert len(state["elements"]) == 1
    element = state["elements"][0]
    assert element["labels"] == ["Project Name", "Project"]
    assert element["attributes"]["data_testid"] == "project-input"
    assert element["validation"]["required"] is True
    assert element["validation"]["invalid"] is True
    assert element["stable_key"] == "input#project"
    assert element["field_context"]["form_id"] == "project-form"
    assert element["field_context"]["fieldset_legend"] == "Project Fields"
    assert element["table_context"]["table_label"] == "Projects"
    assert element["table_context"]["row_index"] == 1
    assert element["table_context"]["column_index"] == 1
    assert element["control_kind"] == "native_input"
    assert element["scan_anchor"]["row_text"] == "Project Name"
    assert "action_hints" not in element


def test_browser_state_script_emits_adjacent_table_field_context_for_custom_select():
    script = build_browser_state_script(include_invisible=False, max_elements=10)

    state = run_browser_state_script(
        script,
        """
const table = makeElement({ tag: "table", attrs: { "aria-label": "Daily Form" } });
const row = makeElement({ tag: "tr" });
const labelCell = makeElement({ tag: "td", text: "是否休假" });
const controlCell = makeElement({ tag: "td", text: "" });
row.children = [labelCell, controlCell];
table.querySelectorAll = (selector) => selector === "tr, [role='row']" ? [row] : [];
const trigger = makeElement({
  tag: "div",
  role: "combobox",
  id: "field5956",
  name: "sfxj",
  text: "请选择",
  attrs: { "aria-haspopup": "listbox", class: "corp-select-control" }
});
trigger.closest = (selector) => {
  if (selector.includes("td")) return controlCell;
  if (selector.includes("tr")) return row;
  if (selector.includes("table")) return table;
  return null;
};
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
  return [trigger];
};
""",
    )

    assert state["status"] == "success"
    element = state["elements"][0]
    assert element["control_kind"] == "custom_select"
    assert element["field_context"]["nearby_text"] == "是否休假"
    assert element["field_context"]["row_label"] == "是否休假"
    assert element["field_context"]["previous_cell_text"] == "是否休假"
    assert element["field_context"]["field_id"] == "field5956"
    assert element["field_context"]["field_name"] == "sfxj"
    assert element["field_context"]["field_container_hint"] == "td"
    assert element["scan_anchor"] == {
        "near_text": "是否休假",
        "field_label": "是否休假",
        "row_text": "是否休假",
        "column_text": "",
        "layer": "main",
        "frame_path": [],
    }


def test_browser_state_script_omits_recipe_hint_and_keeps_scan_anchor():
    script = build_browser_state_script(include_invisible=False, max_elements=10)

    state = run_browser_state_script(
        script,
        """
const table = makeElement({ tag: "table", attrs: { "aria-label": "Daily Form" } });
const row = makeElement({ tag: "tr" });
const labelCell = makeElement({ tag: "td", text: "工作类型" });
const controlCell = makeElement({ tag: "td", text: "" });
row.children = [labelCell, controlCell];
table.querySelectorAll = (selector) => selector === "tr, [role='row']" ? [row] : [];
const trigger = makeElement({
  tag: "div",
  role: "combobox",
  text: "请选择",
  attrs: { "aria-haspopup": "listbox" }
});
trigger.closest = (selector) => {
  if (selector.includes("td")) return controlCell;
  if (selector.includes("tr")) return row;
  if (selector.includes("table")) return table;
  return null;
};
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
  return [trigger];
};
""",
    )

    assert state["status"] == "success"
    element = state["elements"][0]
    assert element["control_kind"] == "custom_select"
    assert "recipe_hint" not in element
    assert element["scan_anchor"]["field_label"] == "工作类型"
    assert element["scan_anchor"]["near_text"] == "工作类型"


def test_browser_state_script_inherits_field_context_for_browser_search_button():
    script = build_browser_state_script(include_invisible=False, max_elements=10)

    state = run_browser_state_script(
        script,
        """
const row = makeElement({ tag: "tr" });
const labelCell = makeElement({ tag: "td", text: "项目名称" });
const controlCell = makeElement({ tag: "td", text: "" });
row.children = [labelCell, controlCell];
const table = makeElement({ tag: "table" });
table.querySelectorAll = (selector) => selector === "tr, [role='row']" ? [row] : [];
const searchButton = makeElement({
  tag: "button",
  text: "",
  attrs: { class: "anticon anticon-search", "aria-label": "搜索" }
});
searchButton.closest = (selector) => {
  if (selector.includes("td")) return controlCell;
  if (selector.includes("tr")) return row;
  if (selector.includes("table")) return table;
  return null;
};
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
  return [searchButton];
};
""",
    )

    assert state["status"] == "success"
    element = state["elements"][0]
    assert element["control_kind"] == "button"
    assert element["field_context"]["nearby_text"] == "项目名称"
    assert element["field_context"]["field_container_hint"] == "td"
    assert "recipe_hint" not in element
    assert element["scan_anchor"]["field_label"] == "项目名称"


def test_browser_state_script_emits_generic_component_container_hint():
    script = build_browser_state_script(include_invisible=False, max_elements=10)

    state = run_browser_state_script(
        script,
        """
const browserContainer = makeElement({ tag: "div", attrs: { class: "corp-browser-widget" } });
const searchButton = makeElement({
  tag: "button",
  text: "",
  attrs: { "aria-label": "Search" }
});
searchButton.parentElement = browserContainer;
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
  return [searchButton];
};
""",
    )

    assert state["status"] == "success"
    element = state["elements"][0]
    assert element["control_kind"] == "button"
    assert element["field_context"]["field_container_hint"] == "browser"


def test_browser_state_script_inherits_field_attrs_from_deep_ancestor():
    script = build_browser_state_script(include_invisible=False, max_elements=10)

    state = run_browser_state_script(
        script,
        """
const control = makeElement({ tag: "input", type: "text", value: "" });
let child = control;
for (let depth = 0; depth < 8; depth += 1) {
  const parent = makeElement({ tag: "div" });
  child.parentElement = parent;
  child = parent;
}
child.getAttribute = (name) => {
  if (name === "id") return "field7001";
  if (name === "name") return "field7001_0";
  return null;
};
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
  return [control];
};
""",
    )

    assert state["status"] == "success"
    element = state["elements"][0]
    assert element["field_context"]["field_id"] == "field7001"
    assert element["field_context"]["field_name"] == "field7001_0"


def test_browser_state_script_emits_row_and_column_for_later_table_cell():
    script = build_browser_state_script(include_invisible=False, max_elements=10)

    state = run_browser_state_script(
        script,
        """
const table = makeElement({ tag: "table", attrs: { "aria-label": "Daily Detail" } });
const row1 = makeElement({ tag: "tr" });
const row2 = makeElement({ tag: "tr" });
const row2Cell1 = makeElement({ tag: "td", text: "Work content" });
const row2Cell2 = makeElement({ tag: "td", text: "Hours" });
row1.children = [makeElement({ tag: "td", text: "Header A" }), makeElement({ tag: "td", text: "Header B" })];
row2.children = [row2Cell1, row2Cell2];
table.querySelectorAll = (selector) => selector === "tr, [role='row']" ? [row1, row2] : [];
const hoursInput = makeElement({ tag: "input", type: "text", value: "1.00" });
hoursInput.closest = (selector) => {
  if (selector.includes("td")) return row2Cell2;
  if (selector.includes("tr")) return row2;
  if (selector.includes("table")) return table;
  return null;
};
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
  return [hoursInput];
};
""",
    )

    assert state["status"] == "success"
    element = state["elements"][0]
    assert element["table_context"] == {
        "table_role": "table",
        "table_label": "Daily Detail",
        "row_index": 2,
        "column_index": 2,
        "cell_role": "td",
        "cell_text": "Hours",
        "row_text": "Work content Hours",
        "row_header": "Work content",
        "column_header": "Header B",
        "column_text": "Header B",
        "header_text": "Header B",
    }


def test_browser_state_script_emits_table_text_for_row_and_column_locator():
    script = build_browser_state_script(include_invisible=False, max_elements=10)

    state = run_browser_state_script(
        script,
        """
const table = makeElement({ tag: "table", attrs: { "aria-label": "Daily Detail" } });
const headerRow = makeElement({ tag: "tr", text: "姓名 工时" });
const headerName = makeElement({ tag: "th", text: "姓名" });
const headerHours = makeElement({ tag: "th", text: "工时" });
headerRow.children = [headerName, headerHours];
const dataRow = makeElement({ tag: "tr", text: "张三 1.00" });
const nameCell = makeElement({ tag: "td", text: "张三" });
const hoursCell = makeElement({ tag: "td", text: "1.00" });
dataRow.children = [nameCell, hoursCell];
table.querySelectorAll = (selector) => selector === "tr, [role='row']" ? [headerRow, dataRow] : [];
const hoursInput = makeElement({ tag: "input", type: "text", value: "1.00" });
hoursInput.closest = (selector) => {
  if (selector.includes("td")) return hoursCell;
  if (selector.includes("tr")) return dataRow;
  if (selector.includes("table")) return table;
  return null;
};
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
  if (selector.includes("input")) return [hoursInput];
  return [];
};
""",
    )

    assert state["status"] == "success"
    table_context = state["elements"][0]["table_context"]
    assert table_context["row_text"] == "张三 1.00"
    assert table_context["row_header"] == "张三"
    assert table_context["column_header"] == "工时"


def test_browser_state_script_omits_child_elements_when_parent_iframe_is_hidden():
    script = build_browser_state_script(include_invisible=False, max_elements=10)

    state = run_browser_state_script(
        script,
        """
const hiddenIframe = makeElement({ tag: "iframe", visible: false, ownerDocument: document });
const frameWindow = {
  ...window,
  frameElement: hiddenIframe,
  parent: window,
  location: { href: "https://example.test/frame" },
};
const frameDocument = {
  title: "Frame",
  defaultView: frameWindow,
  body: null,
  getElementById: (_id) => null,
  querySelectorAll: (selector) => {
    if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
    return [frameButton];
  },
};
frameDocument.body = makeElement({ tag: "body", ownerDocument: frameDocument });
const frameButton = makeElement({
  tag: "button",
  text: "Inside",
  ownerDocument: frameDocument,
});
hiddenIframe.contentDocument = frameDocument;
hiddenIframe.contentWindow = frameWindow;
document.querySelectorAll = (selector) => selector === "iframe, frame" ? [hiddenIframe] : [];
""",
    )

    assert state["status"] == "success"
    assert state["elements"] == []


def test_browser_state_script_omits_hidden_parent_iframe_children_even_when_include_invisible():
    script = build_browser_state_script(include_invisible=True, max_elements=10)

    state = run_browser_state_script(
        script,
        """
const hiddenIframe = makeElement({ tag: "iframe", visible: false, ownerDocument: document });
const frameWindow = {
  ...window,
  frameElement: hiddenIframe,
  parent: window,
  location: { href: "https://example.test/frame" },
};
const frameDocument = {
  title: "Frame",
  defaultView: frameWindow,
  body: null,
  getElementById: (_id) => null,
  querySelectorAll: (selector) => {
    if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
    return [frameButton];
  },
};
frameDocument.body = makeElement({ tag: "body", ownerDocument: frameDocument });
const frameButton = makeElement({
  tag: "button",
  text: "Inside",
  ownerDocument: frameDocument,
});
hiddenIframe.contentDocument = frameDocument;
hiddenIframe.contentWindow = frameWindow;
document.querySelectorAll = (selector) => selector === "iframe, frame" ? [hiddenIframe] : [];
""",
    )

    assert state["status"] == "success"
    assert state["elements"] == []


def test_browser_state_script_omits_iframe_children_hidden_by_ancestor_container():
    script = build_browser_state_script(include_invisible=True, max_elements=10)

    state = run_browser_state_script(
        script,
        """
const hiddenContainer = makeElement({ tag: "div", ownerDocument: document });
hiddenContainer._style = { display: "none", visibility: "visible", opacity: "1" };
const iframe = makeElement({ tag: "iframe", ownerDocument: document });
iframe.parentElement = hiddenContainer;
const frameWindow = {
  ...window,
  frameElement: iframe,
  parent: window,
  location: { href: "https://example.test/frame" },
};
const frameDocument = {
  title: "Frame",
  defaultView: frameWindow,
  body: null,
  getElementById: (_id) => null,
  querySelectorAll: (selector) => {
    if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
    return [frameButton];
  },
};
frameDocument.body = makeElement({ tag: "body", ownerDocument: frameDocument });
const frameButton = makeElement({
  tag: "button",
  text: "Inside",
  ownerDocument: frameDocument,
});
iframe.contentDocument = frameDocument;
iframe.contentWindow = frameWindow;
document.querySelectorAll = (selector) => selector === "iframe, frame" ? [iframe] : [];
""",
    )

    assert state["status"] == "success"
    assert state["elements"] == []


def test_browser_state_script_omits_child_elements_when_nested_ancestor_iframe_is_hidden():
    script = build_browser_state_script(include_invisible=False, max_elements=10)

    state = run_browser_state_script(
        script,
        """
const hiddenOuterIframe = makeElement({ tag: "iframe", width: 0, height: 0, ownerDocument: document });
const outerWindow = {
  ...window,
  frameElement: hiddenOuterIframe,
  parent: window,
  location: { href: "https://example.test/outer" },
};
const outerDocument = {
  title: "Outer Frame",
  defaultView: outerWindow,
  body: null,
  getElementById: (_id) => null,
  querySelectorAll: (selector) => selector === "iframe, frame" ? [innerIframe] : [],
};
outerDocument.body = makeElement({ tag: "body", ownerDocument: outerDocument });
const innerIframe = makeElement({ tag: "iframe", ownerDocument: outerDocument });

const innerWindow = {
  ...window,
  frameElement: innerIframe,
  parent: outerWindow,
  location: { href: "https://example.test/inner" },
};
const innerDocument = {
  title: "Inner Frame",
  defaultView: innerWindow,
  body: null,
  getElementById: (_id) => null,
  querySelectorAll: (selector) => {
    if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
    return [nestedButton];
  },
};
innerDocument.body = makeElement({ tag: "body", ownerDocument: innerDocument });
const nestedButton = makeElement({
  tag: "button",
  text: "Nested",
  ownerDocument: innerDocument,
});
hiddenOuterIframe.contentDocument = outerDocument;
hiddenOuterIframe.contentWindow = outerWindow;
innerIframe.contentDocument = innerDocument;
innerIframe.contentWindow = innerWindow;
document.contains = (element) => element === hiddenOuterIframe || element === document.body;
outerDocument.contains = (element) => element === innerIframe || element === outerDocument.body;
innerDocument.contains = (element) => element === nestedButton || element === innerDocument.body;
document.querySelectorAll = (selector) => selector === "iframe, frame" ? [hiddenOuterIframe] : [];
""",
    )

    assert state["status"] == "success"
    assert state["elements"] == []


def test_browser_state_script_omits_hidden_ancestor_iframe_children_even_when_include_invisible():
    script = build_browser_state_script(include_invisible=True, max_elements=10)

    state = run_browser_state_script(
        script,
        """
const hiddenOuterIframe = makeElement({ tag: "iframe", width: 0, height: 0, ownerDocument: document });
const outerWindow = {
  ...window,
  frameElement: hiddenOuterIframe,
  parent: window,
  location: { href: "https://example.test/outer" },
};
const outerDocument = {
  title: "Outer Frame",
  defaultView: outerWindow,
  body: null,
  getElementById: (_id) => null,
  querySelectorAll: (selector) => selector === "iframe, frame" ? [innerIframe] : [],
};
outerDocument.body = makeElement({ tag: "body", ownerDocument: outerDocument });
const innerIframe = makeElement({ tag: "iframe", ownerDocument: outerDocument });

const innerWindow = {
  ...window,
  frameElement: innerIframe,
  parent: outerWindow,
  location: { href: "https://example.test/inner" },
};
const innerDocument = {
  title: "Inner Frame",
  defaultView: innerWindow,
  body: null,
  getElementById: (_id) => null,
  querySelectorAll: (selector) => {
    if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
    return [nestedButton];
  },
};
innerDocument.body = makeElement({ tag: "body", ownerDocument: innerDocument });
const nestedButton = makeElement({
  tag: "button",
  text: "Nested",
  ownerDocument: innerDocument,
});
hiddenOuterIframe.contentDocument = outerDocument;
hiddenOuterIframe.contentWindow = outerWindow;
innerIframe.contentDocument = innerDocument;
innerIframe.contentWindow = innerWindow;
document.contains = (element) => element === hiddenOuterIframe || element === document.body;
outerDocument.contains = (element) => element === innerIframe || element === outerDocument.body;
innerDocument.contains = (element) => element === nestedButton || element === innerDocument.body;
document.querySelectorAll = (selector) => selector === "iframe, frame" ? [hiddenOuterIframe] : [];
""",
    )

    assert state["status"] == "success"
    assert state["elements"] == []


def test_browser_state_script_indexes_nested_same_origin_frame_with_full_frame_path():
    script = build_browser_state_script(include_invisible=False, max_elements=10)

    state = run_browser_state_script(
        script,
        """
const outerIframe = makeElement({ tag: "iframe", ownerDocument: document });
const outerWindow = {
  ...window,
  frameElement: outerIframe,
  parent: window,
  location: { href: "https://example.test/outer" },
};
const innerIframe = makeElement({ tag: "iframe" });
const outerDocument = {
  title: "Outer",
  defaultView: outerWindow,
  body: null,
  getElementById: (_id) => null,
  contains: (element) => element === innerIframe || element === outerDocument.body,
  querySelectorAll: (selector) => selector === "iframe, frame" ? [innerIframe] : [],
};
outerDocument.body = makeElement({ tag: "body", ownerDocument: outerDocument });
innerIframe.ownerDocument = outerDocument;

const innerWindow = {
  ...window,
  frameElement: innerIframe,
  parent: outerWindow,
  location: { href: "https://example.test/inner" },
};
const innerDocument = {
  title: "Inner",
  defaultView: innerWindow,
  body: null,
  getElementById: (_id) => null,
  contains: (element) => element === nestedButton || element === innerDocument.body,
  querySelectorAll: (selector) => {
    if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
    return [nestedButton];
  },
};
innerDocument.body = makeElement({ tag: "body", ownerDocument: innerDocument });
const nestedButton = makeElement({ tag: "button", text: "Nested", ownerDocument: innerDocument });
outerIframe.contentDocument = outerDocument;
outerIframe.contentWindow = outerWindow;
innerIframe.contentDocument = innerDocument;
innerIframe.contentWindow = innerWindow;
document.contains = (element) => element === outerIframe || element === document.body;
document.querySelectorAll = (selector) => selector === "iframe, frame" ? [outerIframe] : [];
""",
    )

    assert state["status"] == "success"
    assert len(state["elements"]) == 1
    element = state["elements"][0]
    assert element["text"] == "Nested"
    assert element["frame_path"] == [0, 0]
    assert element["frame_depth"] == 2
    assert element["frame_url"] == "https://example.test/inner"
    assert element["frame_title"] == "Inner"
    assert state["frames"] == [
        {
            "frame_path": [0],
            "frame_depth": 1,
            "selector_hint": "iframe",
            "visible": True,
            "same_origin_accessible": True,
            "url": "https://example.test/outer",
            "title": "Outer",
            "error": "",
        },
        {
            "frame_path": [0, 0],
            "frame_depth": 2,
            "selector_hint": "iframe",
            "visible": True,
            "same_origin_accessible": True,
            "url": "https://example.test/inner",
            "title": "Inner",
            "error": "",
        },
    ]


def test_browser_state_script_emits_page_signals_for_dynamic_page():
    script = build_browser_state_script(include_invisible=False, max_elements=10)

    state = run_browser_state_script(
        script,
        """
const field = makeElement({ tag: "input", id: "search", value: "" });
const spinner = makeElement({ tag: "div", attrs: { class: "ant-spin-spinning" } });
spinner.matches = (selector) => selector.includes(".ant-spin-spinning");
const modal = makeElement({ tag: "div", attrs: { class: "ant-modal" } });
modal.matches = (selector) => selector.includes(".ant-modal");
document.readyState = "interactive";
document.activeElement = field;
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
  if (selector.includes(".ant-spin-spinning")) return [spinner];
  if (selector.includes(".ant-modal")) return [modal];
  return [field];
};
""",
    )

    assert state["status"] == "success"
    assert state["page_signals"] == {
        "ready_state": "interactive",
        "busy": True,
        "loading_count": 1,
        "overlay_count": 1,
        "focused_selector_hint": "input#search",
    }


def test_build_browser_state_script_uses_collision_resistant_token():
    script = build_browser_state_script()

    assert "window.__GA_BROWSER_STATE_COUNTER__" in script
    assert "Math.random().toString(36).slice(2)" in script
    assert "const stateToken = `${Date.now()}:${window.__GA_BROWSER_STATE_COUNTER__}:${randomPart}:${elements.length}`;" in script


def test_browser_state_script_max_elements_can_truncate_later_frame_elements():
    script = build_browser_state_script(include_invisible=False, max_elements=1)

    state = run_browser_state_script(
        script,
        """
const topButton = makeElement({ tag: "button", text: "Top" });
const iframe = makeElement({ tag: "iframe", ownerDocument: document });
const frameWindow = {
  ...window,
  frameElement: iframe,
  parent: window,
  location: { href: "https://example.test/frame" },
};
const frameDocument = {
  title: "Frame",
  defaultView: frameWindow,
  body: null,
  getElementById: (_id) => null,
  querySelectorAll: (selector) => {
    if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
    return [makeElement({ tag: "button", text: "Inside", ownerDocument: frameDocument })];
  },
};
frameDocument.body = makeElement({ tag: "body", ownerDocument: frameDocument });
iframe.contentDocument = frameDocument;
iframe.contentWindow = frameWindow;
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame") return [iframe];
  if (selector.startsWith("label[")) return [];
  return [topButton];
};
""",
    )

    assert state["status"] == "success"
    assert len(state["elements"]) == 1
    assert state["elements"][0]["text"] == "Top"
    assert state["elements"][0]["frame_path"] == []


def test_build_browser_state_script_preserves_same_origin_iframe_elements_under_global_limit():
    script = build_browser_state_script(include_invisible=False, max_elements=3)

    state = run_browser_state_script(
        script,
        """
const mainButtonA = makeElement({ tag: "button", text: "Main A" });
const mainButtonB = makeElement({ tag: "button", text: "Main B" });
const frameDocButtonA = makeElement({ tag: "button", text: "Frame A" });
const frameDocButtonB = makeElement({ tag: "button", text: "Frame B" });
const frameDocument = {
  title: "Frame",
  querySelectorAll: (selector) => selector === selectorValue ? [frameDocButtonA, frameDocButtonB] : [],
  defaultView: {
    frameElement: null,
    location: { href: "https://example.test/frame" },
    getComputedStyle: () => ({ display: "block", visibility: "visible", contentVisibility: "visible", opacity: "1" })
  },
  body: null,
  getElementById: (_id) => null,
};
frameDocument.body = makeElement({ tag: "body", text: "Frame Body", ownerDocument: frameDocument });
const frameElement = makeElement({ tag: "iframe" });
frameDocument.defaultView.frameElement = frameElement;
frameElement.contentWindow = frameDocument.defaultView;
frameElement.contentDocument = frameDocument;
frameElement.getBoundingClientRect = () => ({ width: 100, height: 40 });
frameElement.ownerDocument = document;
frameDocButtonA.ownerDocument = frameDocument;
frameDocButtonB.ownerDocument = frameDocument;
document.contains = (element) => element === frameElement || element === document.body;
const selectorValue = `a[href], button, input, textarea, select, [role="button"], [role="link"], [role="textbox"], [role="checkbox"], [role="radio"], [role="combobox"], [role="listbox"], [role="option"], [aria-haspopup="listbox"], [role="menuitem"], [onclick], [tabindex], [contenteditable="true"], .ant-select-selector, .ant-picker, .ui-browser-item, .ui-browser [role="treeitem"], .ui-browser [role="menuitem"]`;
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame") return [frameElement];
  if (selector === selectorValue) return [mainButtonA, mainButtonB];
  if (selector.startsWith("label[")) return [];
  return [];
};
""",
    )

    assert state["status"] == "success"
    texts = [item["text"] for item in state["elements"]]
    assert "Main A" in texts
    assert "Frame A" in texts
    assert len(state["elements"]) == 3
    assert state["truncated"] is True
    assert state["truncation"]["omitted_count"] == 1
    assert state["truncation"]["iframe_omitted_count"] == 0
    assert state["truncation"]["total_limit"] == 3
    assert state["truncation"]["main_reserved"] == 1
    assert state["truncation"]["frame_reserved"] == 2


def test_build_browser_state_script_reports_overlay_elements_and_frame_origin():
    script = build_browser_state_script(include_invisible=False, max_elements=10)

    state = run_browser_state_script(
        script,
        """
const trigger = makeElement({
  tag: "div",
  role: "combobox",
  text: "请选择",
  attrs: { "aria-haspopup": "listbox", class: "ant-select ant-select-open" }
});
const option = makeElement({
  tag: "div",
  role: "option",
  text: "否",
  attrs: { class: "ant-select-dropdown-menu-item", "aria-selected": "false" }
});
const dropdown = makeElement({ tag: "div", attrs: { class: "ant-select-dropdown ant-select-dropdown-placement-bottomLeft" } });
dropdown.matches = (selector) => selector.includes(".ant-select-dropdown");
dropdown.querySelectorAll = (selector) => selector.includes("[role=\\"option\\"]") ? [option] : [];
option.closest = (selector) => selector.includes(".ant-select-dropdown") ? dropdown : null;
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
  if (selector.includes(".ant-select-dropdown")) return [dropdown];
  return [trigger, option];
};
""",
    )

    assert state["status"] == "success"
    by_text = {item["text"]: item for item in state["elements"] if item.get("text")}
    assert by_text["请选择"]["layer"] == "main"
    assert by_text["否"]["layer"] == "dropdown"
    assert by_text["否"]["frame_path"] == []


def test_browser_state_script_preserves_dropdown_option_under_dense_truncated_main_document():
    script = build_browser_state_script(include_invisible=False, max_elements=3)

    state = run_browser_state_script(
        script,
        """
let layoutReads = 0;
const denseButtons = Array.from({ length: 100 }, (_value, index) => {
  const button = makeElement({ tag: "button", text: `Main ${index}` });
  button.getBoundingClientRect = () => {
    layoutReads += 1;
    return { x: 0, y: 0, width: 10, height: 10 };
  };
  return button;
});
const dropdownA = makeElement({ tag: "div", attrs: { class: "ant-select-dropdown" } });
dropdownA.matches = (selector) => selector.includes(".ant-select-dropdown");
dropdownA.getBoundingClientRect = () => {
  layoutReads += 1;
  return { x: 0, y: 0, width: 100, height: 40 };
};
const dropdownB = makeElement({ tag: "div", attrs: { class: "ant-select-dropdown" } });
dropdownB.matches = (selector) => selector.includes(".ant-select-dropdown");
const overlayOptionsA = Array.from({ length: 3 }, (_value, index) => {
  const option = makeElement({
    tag: "div",
    role: "option",
    text: `否 ${index}`,
    attrs: { class: "ant-select-dropdown-menu-item" },
  });
  option.closest = (selector) => selector.includes(".ant-select-dropdown") ? dropdownA : null;
  option.getBoundingClientRect = () => {
    layoutReads += 1;
    return { x: 0, y: 0, width: 100, height: 20 };
  };
  return option;
});
const overlayOptionsB = Array.from({ length: 2 }, (_value, index) => {
  const option = makeElement({
    tag: "div",
    role: "option",
    text: `否 ${index + 3}`,
    attrs: { class: "ant-select-dropdown-menu-item" },
  });
  option.closest = (selector) => selector.includes(".ant-select-dropdown") ? dropdownB : null;
  option.getBoundingClientRect = () => {
    layoutReads += 1;
    return { x: 0, y: 0, width: 100, height: 20 };
  };
  return option;
});
dropdownB.getBoundingClientRect = () => {
  layoutReads += 1;
  return { x: 0, y: 0, width: 100, height: 40 };
};
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
  if (selector.includes(".ant-select-dropdown")) return [dropdownA, dropdownB];
  return denseButtons.concat(overlayOptionsA, overlayOptionsB);
};
dropdownA.querySelectorAll = (selector) => selector.includes("[role=\\"option\\"]") ? overlayOptionsA : [];
dropdownB.querySelectorAll = (selector) => selector.includes("[role=\\"option\\"]") ? overlayOptionsB : [];
global.__afterBrowserState = (result) => {
  result.layout_reads = layoutReads;
  return result;
};
""",
    )

    assert state["status"] == "success"
    assert [item["text"] for item in state["elements"]] == ["Main 0", "否 0", "Main 1"]
    by_text = {item["text"]: item for item in state["elements"]}
    assert by_text["否 0"]["layer"] == "dropdown"
    assert by_text["否 0"]["frame_path"] == []
    assert state["truncated"] is True
    assert state["truncation"]["omitted_count"] >= 100
    assert state["truncation"]["iframe_omitted_count"] == 0
    assert state["truncation"]["main_reserved"] == 1
    assert state["truncation"]["frame_reserved"] == 2
    assert state["layout_reads"] < 50


def test_browser_state_script_bounds_dense_page_collection_work_under_small_limit():
    script = build_browser_state_script(include_invisible=False, max_elements=3)

    state = run_browser_state_script(
        script,
        """
let layoutReads = 0;
const denseButtons = Array.from({ length: 200 }, (_value, index) => {
  const button = makeElement({ tag: "button", text: `Main ${index}` });
  button.getBoundingClientRect = () => {
    layoutReads += 1;
    return { x: 0, y: 0, width: 10, height: 10 };
  };
  return button;
});
const frame1Buttons = ["Frame 1 A", "Frame 1 B", "Frame 1 C"].map((text) => {
  const button = makeElement({ tag: "button", text });
  button.getBoundingClientRect = () => {
    layoutReads += 1;
    return { x: 0, y: 0, width: 10, height: 10 };
  };
  return button;
});
const frame2Buttons = Array.from({ length: 100 }, (_value, index) => `Frame 2 ${index}`).map((text) => {
  const button = makeElement({ tag: "button", text });
  button.getBoundingClientRect = () => {
    layoutReads += 1;
    return { x: 0, y: 0, width: 10, height: 10 };
  };
  return button;
});
const frame1Document = {
  title: "Frame 1",
  defaultView: null,
  body: null,
  getElementById: (_id) => null,
  querySelectorAll: (selector) => {
    if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
    return frame1Buttons;
  },
};
const frame2Document = {
  title: "Frame 2",
  defaultView: null,
  body: null,
  getElementById: (_id) => null,
  querySelectorAll: (selector) => {
    if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
    return frame2Buttons;
  },
};
const iframe1 = makeElement({ tag: "iframe", ownerDocument: document });
iframe1.getBoundingClientRect = () => {
  layoutReads += 1;
  return { x: 0, y: 0, width: 100, height: 40 };
};
const iframe2 = makeElement({ tag: "iframe", ownerDocument: document });
iframe2.getBoundingClientRect = () => {
  layoutReads += 1;
  return { x: 0, y: 0, width: 100, height: 40 };
};
const frame1Window = {
  ...window,
  frameElement: iframe1,
  parent: window,
  location: { href: "https://example.test/frame-1" },
};
const frame2Window = {
  ...window,
  frameElement: iframe2,
  parent: window,
  location: { href: "https://example.test/frame-2" },
};
frame1Document.defaultView = frame1Window;
frame2Document.defaultView = frame2Window;
frame1Document.body = makeElement({ tag: "body", ownerDocument: frame1Document });
frame2Document.body = makeElement({ tag: "body", ownerDocument: frame2Document });
frame1Buttons.forEach((button) => { button.ownerDocument = frame1Document; });
frame2Buttons.forEach((button) => { button.ownerDocument = frame2Document; });
iframe1.contentDocument = frame1Document;
iframe1.contentWindow = frame1Window;
iframe2.contentDocument = frame2Document;
iframe2.contentWindow = frame2Window;
document.contains = (element) => element === iframe1 || element === iframe2 || element === document.body;
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame") return [iframe1, iframe2];
  if (selector.startsWith("label[")) return [];
  return denseButtons;
};
global.__afterBrowserState = (result) => {
  result.layout_reads = layoutReads;
  return result;
};
""",
    )

    assert state["status"] == "success"
    assert [item["text"] for item in state["elements"]] == ["Main 0", "Frame 1 A", "Frame 1 B"]
    assert state["truncated"] is True
    assert state["truncation"]["omitted_count"] >= 200
    assert state["truncation"]["iframe_omitted_count"] >= 100
    assert state["truncation"]["main_reserved"] == 1
    assert state["truncation"]["frame_reserved"] == 2
    assert state["elements"][0]["text"] == "Main 0"
    assert state["elements"][0]["frame_path"] == []
    assert state["layout_reads"] < 250


def test_browser_state_script_preserves_frame_overlay_after_frame_bucket_exhausted():
    script = build_browser_state_script(include_invisible=False, max_elements=4)

    state = run_browser_state_script(
        script,
        """
const mainButton = makeElement({ tag: "button", text: "Main" });
const frameButtons = Array.from({ length: 20 }, (_value, index) => makeElement({ tag: "button", text: `Frame ${index}` }));
const dropdown = makeElement({ tag: "div", attrs: { class: "ant-select-dropdown" } });
dropdown.matches = (selector) => selector.includes(".ant-select-dropdown");
const option = makeElement({
  tag: "div",
  role: "option",
  text: "Frame Option",
  attrs: { class: "ant-select-dropdown-menu-item" },
});
option.closest = (selector) => selector.includes(".ant-select-dropdown") ? dropdown : null;
dropdown.querySelectorAll = (selector) => selector.includes("[role=\\"option\\"]") ? [option] : [];
const frameDocument = {
  title: "Frame",
  defaultView: null,
  body: null,
  getElementById: (_id) => null,
  querySelectorAll: (selector) => {
    if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
    if (selector.includes(".ant-select-dropdown")) return [dropdown];
    return frameButtons.concat([option]);
  },
};
const iframe = makeElement({ tag: "iframe", ownerDocument: document });
const frameWindow = {
  ...window,
  frameElement: iframe,
  parent: window,
  location: { href: "https://example.test/frame" },
};
frameDocument.defaultView = frameWindow;
frameDocument.body = makeElement({ tag: "body", ownerDocument: frameDocument });
frameButtons.forEach((button) => { button.ownerDocument = frameDocument; });
option.ownerDocument = frameDocument;
dropdown.ownerDocument = frameDocument;
iframe.contentDocument = frameDocument;
iframe.contentWindow = frameWindow;
document.contains = (element) => element === iframe || element === document.body;
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame") return [iframe];
  if (selector.startsWith("label[")) return [];
  return [mainButton];
};
""",
    )

    assert state["status"] == "success"
    by_text = {item["text"]: item for item in state["elements"]}
    assert by_text["Frame Option"]["layer"] == "dropdown"
    assert by_text["Frame Option"]["frame_path"] == [0]
    assert state["truncated"] is True
    assert state["truncation"]["iframe_omitted_count"] >= 1


def test_browser_state_script_discovers_nested_frame_after_parent_frame_bucket_exhausted():
    script = build_browser_state_script(include_invisible=False, max_elements=4)

    state = run_browser_state_script(
        script,
        """
const mainButton = makeElement({ tag: "button", text: "Main" });
const parentButtons = Array.from({ length: 12 }, (_value, index) => makeElement({ tag: "button", text: `Parent ${index}` }));
const childButton = makeElement({ tag: "button", text: "Nested child" });
const parentIframe = makeElement({ tag: "iframe", ownerDocument: document });
const childIframe = makeElement({ tag: "iframe" });
const grandchildIframe = makeElement({ tag: "iframe" });
const parentWindow = {
  ...window,
  frameElement: parentIframe,
  parent: window,
  location: { href: "https://example.test/parent" },
};
const parentDocument = {
  title: "Parent Frame",
  defaultView: parentWindow,
  body: null,
  getElementById: (_id) => null,
  contains: (element) => element === childIframe || element === parentDocument.body,
  querySelectorAll: (selector) => {
    if (selector === "iframe, frame") return [childIframe];
    if (selector.startsWith("label[")) return [];
    return parentButtons;
  },
};
const childWindow = {
  ...window,
  frameElement: childIframe,
  parent: parentWindow,
  location: { href: "https://example.test/child" },
};
const childDocument = {
  title: "Nested Child Frame",
  defaultView: childWindow,
  body: null,
  getElementById: (_id) => null,
  contains: (element) => element === childButton || element === grandchildIframe || element === childDocument.body,
  querySelectorAll: (selector) => {
    if (selector === "iframe, frame") return [grandchildIframe];
    if (selector.startsWith("label[")) return [];
    return [childButton];
  },
};
const grandchildWindow = {
  ...window,
  frameElement: grandchildIframe,
  parent: childWindow,
  location: { href: "https://example.test/grandchild" },
};
const grandchildDocument = {
  title: "Grandchild Frame",
  defaultView: grandchildWindow,
  body: null,
  getElementById: (_id) => null,
  contains: (element) => element === grandchildDocument.body,
  querySelectorAll: (selector) => {
    if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
    return [];
  },
};
parentDocument.body = makeElement({ tag: "body", ownerDocument: parentDocument });
childDocument.body = makeElement({ tag: "body", ownerDocument: childDocument });
grandchildDocument.body = makeElement({ tag: "body", ownerDocument: grandchildDocument });
parentButtons.forEach((button) => { button.ownerDocument = parentDocument; });
childButton.ownerDocument = childDocument;
parentIframe.contentDocument = parentDocument;
parentIframe.contentWindow = parentWindow;
childIframe.ownerDocument = parentDocument;
childIframe.contentDocument = childDocument;
childIframe.contentWindow = childWindow;
grandchildIframe.ownerDocument = childDocument;
grandchildIframe.contentDocument = grandchildDocument;
grandchildIframe.contentWindow = grandchildWindow;
document.contains = (element) => element === parentIframe || element === document.body;
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame") return [parentIframe];
  if (selector.startsWith("label[")) return [];
  return [mainButton];
};
""",
    )

    assert state["status"] == "success"
    frame_paths = [frame["frame_path"] for frame in state["frames"]]
    assert [0] in frame_paths
    assert [0, 0] in frame_paths
    assert [0, 0, 0] in frame_paths
    nested_frame = next(frame for frame in state["frames"] if frame["frame_path"] == [0, 0])
    assert nested_frame["same_origin_accessible"] is True
    assert nested_frame["title"] == "Nested Child Frame"
    grandchild_frame = next(frame for frame in state["frames"] if frame["frame_path"] == [0, 0, 0])
    assert grandchild_frame["same_origin_accessible"] is True
    assert grandchild_frame["title"] == "Grandchild Frame"
    assert state["truncated"] is True
    assert state["truncation"]["iframe_omitted_count"] >= 9


def test_browser_state_script_indexes_interactive_overlay_root():
    script = build_browser_state_script(include_invisible=False, max_elements=5)

    state = run_browser_state_script(
        script,
        """
const trigger = makeElement({ tag: "button", text: "Open" });
const listbox = makeElement({
  tag: "div",
  role: "listbox",
  text: "Root listbox",
  attrs: { class: "dropdown" },
});
listbox.matches = (selector) => selector.includes("[role='listbox']") || selector.includes('[role="listbox"]') || selector.includes(".dropdown");
listbox.closest = (selector) => selector.includes("[role='listbox']") || selector.includes(".dropdown") ? listbox : null;
listbox.querySelectorAll = (_selector) => [];
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
  if (selector.includes("[role='listbox']") || selector.includes(".dropdown")) return [listbox];
  return [trigger, listbox];
};
""",
    )

    assert state["status"] == "success"
    by_text = {item["text"]: item for item in state["elements"]}
    assert by_text["Root listbox"]["layer"] == "dropdown"
    assert by_text["Root listbox"]["role"] == "listbox"


def test_browser_state_script_documents_unsemantic_framework_icon_boundary():
    script = build_browser_state_script(include_invisible=False, max_elements=10)

    state = run_browser_state_script(
        script,
        """
const browserIcon = makeElement({
  tag: "i",
  text: "",
  attrs: { class: "ui-icon ui-browser" },
});
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
  if (selector.includes(".ui-icon") || selector.includes(".ui-browser")) return [browserIcon];
  return [];
};
""",
    )

    assert state["status"] == "success"
    assert state["elements"] == []


def test_build_browser_state_script_bounds_snapshot_text_and_value():
    script = build_browser_state_script()

    assert "return String(value || \"\").slice(0, 240);" in script
    assert "text: boundedText(textOf(element))," in script
    assert "value: boundedText(value)," in script


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


def test_normalize_state_result_adds_top_level_defaults():
    state = normalize_state_result({"status": "success"})

    assert state["backend"] == ""
    assert state["tab_id"] == ""
    assert state["url"] == ""
    assert state["title"] == ""
    assert state["state_token"] == ""
    assert state["viewport"] == {}
    assert state["page_signals"] == {
        "ready_state": "",
        "busy": False,
        "loading_count": 0,
        "overlay_count": 0,
        "focused_selector_hint": "",
    }
    assert state["frames"] == []
    assert state["truncated"] is False
    assert state["truncation"] == {
        "omitted_count": 0,
        "iframe_omitted_count": 0,
        "total_limit": 0,
        "main_reserved": 0,
        "frame_reserved": 0,
    }
    assert state["elements"] == []


def test_normalize_state_result_normalizes_page_signals_and_frames():
    state = normalize_state_result({
        "status": "success",
        "page_signals": {"busy": 1, "loading_count": "2", "overlay_count": "-1"},
        "frames": [{"frame_path": [0], "same_origin_accessible": 1, "url": "https://frame.test"}],
    })

    assert state["page_signals"] == {
        "busy": True,
        "loading_count": 2,
        "overlay_count": 0,
        "ready_state": "",
        "focused_selector_hint": "",
    }
    assert state["frames"] == [
        {
            "frame_path": [0],
            "same_origin_accessible": True,
            "url": "https://frame.test",
            "frame_depth": 1,
            "selector_hint": "",
            "visible": False,
            "title": "",
            "error": "",
        }
    ]


def test_normalize_state_result_preserves_truncation_metadata():
    state = normalize_state_result({
        "status": "success",
        "truncated": True,
        "truncation": {
            "omitted_count": 4,
            "iframe_omitted_count": 2,
            "total_limit": 10,
            "main_reserved": 7,
            "frame_reserved": 3,
        },
    })

    assert state["truncated"] is True
    assert state["truncation"] == {
        "omitted_count": 4,
        "iframe_omitted_count": 2,
        "total_limit": 10,
        "main_reserved": 7,
        "frame_reserved": 3,
    }


def test_normalize_state_result_coerces_truncation_numbers_and_clamps_invalid_values():
    state = normalize_state_result({
        "status": "success",
        "truncated": "0",
        "truncation": {
            "omitted_count": "2",
            "iframe_omitted_count": "-3",
            "total_limit": "7",
            "main_reserved": "-1",
            "frame_reserved": "bad",
        },
        "elements": [{"tag": "button"}, {"tag": "input"}],
    })

    assert state["truncated"] is True
    assert state["truncation"] == {
        "omitted_count": 2,
        "iframe_omitted_count": 0,
        "total_limit": 7,
        "main_reserved": 0,
        "frame_reserved": 0,
    }


def test_normalize_state_result_string_zero_does_not_force_truncated_true():
    state = normalize_state_result({
        "status": "success",
        "truncated": "0",
        "truncation": {
            "omitted_count": "0",
            "iframe_omitted_count": "0",
            "total_limit": "1",
            "main_reserved": "1",
            "frame_reserved": "0",
        },
        "elements": [{"tag": "button"}],
    })

    assert state["truncated"] is False


def test_normalize_state_result_uses_legacy_element_count_for_total_limit_default():
    state = normalize_state_result({
        "status": "success",
        "elements": [{"tag": "button"}, {"tag": "input"}],
    })

    assert state["truncation"]["total_limit"] == 2


def test_normalize_state_result_clamps_non_dict_truncation_to_safe_defaults():
    state = normalize_state_result({
        "status": "success",
        "truncated": "yes",
        "truncation": "bad",
        "elements": [{"tag": "button"}],
    })

    assert state["truncated"] is False
    assert state["truncation"] == {
        "omitted_count": 0,
        "iframe_omitted_count": 0,
        "total_limit": 1,
        "main_reserved": 0,
        "frame_reserved": 0,
    }


def test_normalize_state_result_fills_element_defaults():
    element = normalize_state_result({"elements": [{}]})["elements"][0]

    assert element == {
        "index": 1,
        "tag": "",
        "type": "",
        "role": "",
        "text": "",
        "value": "",
        "visible": True,
        "disabled": False,
        "bbox": {},
        "selector_hint": "",
        "frame_path": [],
        "frame_depth": 0,
        "frame_url": "",
        "frame_title": "",
        "labels": [],
        "attributes": {},
        "validation": {},
        "stable_key": "",
        "field_context": {},
        "table_context": {},
        "scan_anchor": {},
        "layer": "main",
        "layer_root_hint": "",
        "modal_rank": 0,
        "control_kind": "",
    }


def test_normalize_state_result_fills_new_element_metadata_defaults():
    element = normalize_state_result({"elements": [{"tag": "button"}]})["elements"][0]

    assert element["frame_path"] == []
    assert element["frame_depth"] == 0
    assert element["frame_url"] == ""
    assert element["frame_title"] == ""
    assert element["labels"] == []
    assert element["attributes"] == {}
    assert element["validation"] == {}
    assert element["stable_key"] == ""
    assert element["field_context"] == {}
    assert element["table_context"] == {}
    assert element["scan_anchor"] == {}
    assert element["layer"] == "main"
    assert element["layer_root_hint"] == ""
    assert element["modal_rank"] == 0
    assert element["control_kind"] == ""


def test_normalize_state_result_does_not_mutate_nested_field_context():
    field_context = {"labels": ["Project"]}
    raw = {"elements": [{"tag": "button", "field_context": field_context}]}

    state = normalize_state_result(raw)

    assert field_context == {"labels": ["Project"]}
    assert raw["elements"][0]["field_context"] == {"labels": ["Project"]}
    assert state["elements"][0]["field_context"]["nearby_text"] == ""


def test_normalize_state_result_rejects_non_dict():
    state = normalize_state_result("not a dict")

    assert state == {
        "status": "failed",
        "stage": "dom_event",
        "error": "browser_use_index returned a non-object result",
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


def test_normalize_state_result_fills_failed_result_defaults():
    state = normalize_state_result({"status": "failed"})

    assert state == {
        "status": "failed",
        "stage": "dom_event",
        "error": "browser_use_index failed",
    }
