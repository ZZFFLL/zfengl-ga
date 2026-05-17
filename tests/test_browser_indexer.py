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
console.log(JSON.stringify(result));
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
    assert '"verify_field_value"' in script


def test_build_browser_state_script_indexes_same_origin_editor_frame_body():
    script = build_browser_state_script()

    assert "editorBodyCandidate" in script
    assert "frameDocument.designMode" in script
    assert "isContentEditableTarget(frameDocument.body)" in script


def test_build_browser_state_script_includes_custom_select_roles():
    script = build_browser_state_script()

    assert "[role=\"option\"]" in script
    assert "[role=\"listbox\"]" in script


def test_build_browser_state_script_includes_aria_haspopup_listbox_trigger():
    script = build_browser_state_script()

    assert '[aria-haspopup="listbox"]' in script


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
        "actionHintsOf",
    ]:
        assert f"const {helper} = " in script

    for field in [
        "labels: labelsOf(element),",
        "attributes: attributesOf(element),",
        "validation: validationOf(element),",
        "stable_key: stableKeyOf(element, tag, role),",
        "field_context: fieldContextOf(element),",
        "table_context: tableContextOf(element),",
        "layer: layerContext.layer,",
        "layer_root_hint: layerContext.layer_root_hint,",
        "modal_rank: layerContext.modal_rank,",
        "control_kind: controlKind,",
        "action_hints: actionHintsOf(element, tag, role, controlKind),",
    ]:
        assert field in script


def test_build_browser_state_script_includes_overlay_patterns_and_action_hints():
    script = build_browser_state_script()

    assert ".ant-modal" in script
    assert ".ant-drawer" in script
    assert ".ant-select-dropdown" in script
    assert ".ant-dropdown" in script
    assert "custom_select" in script
    assert "native_select" in script
    assert "click_to_open" in script
    assert "state_after_open" in script


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
    assert element["action_hints"] == ["input", "verify_field_value"]


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
    assert by_kind["textarea"]["action_hints"] == ["input", "verify_field_value", "keys_after_input"]
    assert by_kind["date_input"]["action_hints"] == ["input", "verify_field_value", "keys_after_input"]


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
    assert element["action_hints"] == ["input", "verify_field_value", "keys_after_input"]


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


def test_build_browser_state_script_uses_collision_resistant_token():
    script = build_browser_state_script()

    assert "window.__GA_BROWSER_STATE_COUNTER__" in script
    assert "Math.random().toString(36).slice(2)" in script
    assert "const stateToken = `${Date.now()}:${window.__GA_BROWSER_STATE_COUNTER__}:${randomPart}:${elements.length}`;" in script


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
    assert state["elements"] == []


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
        "layer": "main",
        "layer_root_hint": "",
        "modal_rank": 0,
        "control_kind": "",
        "action_hints": [],
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
    assert element["layer"] == "main"
    assert element["layer_root_hint"] == ""
    assert element["modal_rank"] == 0
    assert element["control_kind"] == ""
    assert element["action_hints"] == []


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


def test_normalize_state_result_fills_failed_result_defaults():
    state = normalize_state_result({"status": "failed"})

    assert state == {
        "status": "failed",
        "stage": "dom_event",
        "error": "browser_state failed",
    }
