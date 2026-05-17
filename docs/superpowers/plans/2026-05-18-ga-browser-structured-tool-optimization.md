# GA Browser Structured Tool Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce `browser_*`撞墙 in common enterprise form pages by strengthening structured field context, semantic find scoring, recovery hints, and bounded recipe discoverability without changing GA legacy browser tools or external `browser-use`.

**Architecture:** Keep `web_execute_js` as a peer low-level track. Enhance only the `ga_browser_use` structured layer: `indexer.py` emits richer generic metadata, `finder.py` scores that metadata, `actions.py/results.py` return more actionable recovery, and `recipes.py` keeps the existing fixed recipe enum while tightening fail-closed behavior.

**Tech Stack:** Python 3, pytest, embedded JavaScript snippets executed through Node-based unit tests, GA tool schemas in JSON.

---

## Scope Boundaries

- Modify only `ga_browser_use/*`, `browser_indexer.py`/`browser_actions.py` wrappers if needed, `assets/tools_schema*.json`, `memory/browser-use_sop.md`, and focused tests.
- Do not modify `web_execute_js`, `web_scan`, `TMWebDriver.py`, `simphtml.py`, or `E:\zfengl-ai-project\browser-use`.
- Do not add OA business-specific recipes or field names.
- Do not add arbitrary selector click/input.
- Do not add cross-origin iframe, file upload, screenshot log, recording/replay, or multi-page concurrent session support.
- Keep `browser_recipe` limited to `custom_select`, `layer_select`, `table_locate`, and `component_wait`.

## File Structure

- `ga_browser_use/indexer.py`: enrich state snapshots with field-context v2 and advisory `recipe_hint`.
- `ga_browser_use/finder.py`: score new generic field metadata and return better context-aware miss reasons.
- `ga_browser_use/actions.py`: attach target-aware `suggested_args`, `next_action_hint`, and repeated-failure alternatives.
- `ga_browser_use/results.py`: keep stage-level default recovery small; add only generic recovery shape support if action-layer augmentation needs it.
- `ga_browser_use/recipes.py`: tighten fixed recipes around query targets, overlay option ambiguity, and non-timeout error propagation.
- `assets/tools_schema.json`: clarify English tool descriptions for field context, recipe hints, and recovery without changing tool priority.
- `assets/tools_schema_cn.json`: same as English, Chinese wording.
- `memory/browser-use_sop.md`: update GA-facing SOP so agents know when `recipe_hint` is advisory and when to switch tracks.
- `tests/test_browser_indexer.py`: field-context v2 and `recipe_hint` tests.
- `tests/test_ga_browser_use_finder.py`: scoring and recovery tests.
- `tests/test_browser_actions.py`: action recovery tests.
- `tests/test_ga_browser_use_recipes.py`: recipe fail-closed tests.
- `tests/test_browser_tool_schemas.py`: schema boundary wording tests.

## Task 0: Baseline Verification

**Files:**
- Read: `docs/superpowers/specs/2026-05-18-ga-browser-structured-tool-optimization-design.md`
- Test: existing focused browser-use suite

- [ ] **Step 1: Confirm branch and working tree**

Run:

```powershell
git status --short --branch
```

Expected:

```text
## ga-browser-use...origin/ga-browser-use [ahead N]
```

If there are unrelated modified files, do not edit them and do not stage them.

- [ ] **Step 2: Run focused baseline tests**

Run:

```powershell
python -m pytest tests/test_browser_indexer.py tests/test_ga_browser_use_finder.py tests/test_browser_actions.py tests/test_ga_browser_use_recipes.py tests/test_browser_tool_handlers.py tests/test_browser_tool_schemas.py -q
```

Expected:

```text
passed
```

If baseline fails, stop and investigate before implementing. Do not mix baseline repair with this feature unless the failure is caused by this branch's existing browser-use code.

## Task 1: Field Context V2 In `browser_state`

**Files:**
- Modify: `ga_browser_use/indexer.py`
- Test: `tests/test_browser_indexer.py`

- [ ] **Step 1: Add failing tests for left-label/right-control forms**

Append this test near existing field/table metadata tests in `tests/test_browser_indexer.py`:

```python
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
  attrs: { "aria-haspopup": "listbox", class: "ant-select wea-select" }
});
trigger.closest = (selector) => {
  if (selector.includes(".wea-select") || selector.includes(".ant-select")) return trigger;
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
```

- [ ] **Step 2: Add failing test for button/icon inheriting field context**

Append:

```python
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
const browser = makeElement({ tag: "div", attrs: { class: "wea-browser" } });
const searchButton = makeElement({
  tag: "button",
  text: "",
  attrs: { class: "anticon anticon-search", "aria-label": "搜索" }
});
searchButton.closest = (selector) => {
  if (selector.includes(".wea-browser")) return browser;
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
```

- [ ] **Step 3: Run the failing tests**

Run:

```powershell
python -m pytest tests/test_browser_indexer.py::test_browser_state_script_emits_adjacent_table_field_context_for_custom_select tests/test_browser_indexer.py::test_browser_state_script_inherits_field_context_for_browser_search_button -q
```

Expected: both tests fail because `nearby_text`, `row_label`, `previous_cell_text`, `field_id`, and `field_name` are not yet emitted.

- [ ] **Step 4: Implement field-context helper functions**

In `ga_browser_use/indexer.py`, replace the current `fieldContextOf` body with helpers equivalent to this code inside the generated JavaScript:

```javascript
  const textFromNode = (node) => boundedText(node ? (node.innerText || node.textContent || "") : "");

  const previousCellTextOf = (element) => {
    const cell = element.closest && element.closest("td, th, [role='cell'], [role='gridcell'], [role='columnheader'], [role='rowheader']");
    const row = element.closest && element.closest("tr, [role='row']");
    if (!cell || !row) return "";
    const children = Array.from(row.children || []);
    const columnIndex = children.indexOf(cell);
    if (columnIndex <= 0) return "";
    for (let index = columnIndex - 1; index >= 0; index -= 1) {
      const text = textFromNode(children[index]);
      if (text) return text;
    }
    return "";
  };

  const fieldAttrFrom = (element, attrName) => {
    let current = element;
    for (let depth = 0; current && depth < 6; depth += 1) {
      const value = current.getAttribute && current.getAttribute(attrName);
      if (value && /field\d+(?:_\d+)?/i.test(String(value))) return String(value);
      current = current.parentElement;
    }
    const own = element && element.getAttribute && element.getAttribute(attrName);
    return own ? String(own) : "";
  };

  const fieldContainerHintOf = (element) => {
    const container = element.closest && element.closest(".wea-field, .wea-browser, .wea-select, .ant-select, .ant-picker, td, th, [role='cell'], [role='gridcell']");
    if (!container) return "";
    const className = String(container.getAttribute && container.getAttribute("class") || "");
    if (className.includes("wea-browser")) return "wea-browser";
    if (className.includes("wea-select")) return "wea-select";
    if (className.includes("ant-select")) return "ant-select";
    if (className.includes("ant-picker")) return "ant-picker";
    return String(container.tagName || container.getAttribute && container.getAttribute("role") || "").toLowerCase();
  };

  const fieldContextOf = (element) => {
    const form = element.closest && element.closest("form");
    const fieldset = element.closest && element.closest("fieldset");
    const legend = fieldset && fieldset.querySelector("legend");
    const previousCellText = previousCellTextOf(element);
    const fieldId = fieldAttrFrom(element, "id");
    const fieldName = fieldAttrFrom(element, "name");
    return {
      labels: labelsOf(element),
      placeholder: element.getAttribute("placeholder") || "",
      form_id: form ? (form.getAttribute("id") || "") : "",
      form_name: form ? (form.getAttribute("name") || "") : "",
      fieldset_legend: legend ? boundedText(legend.innerText || legend.textContent || "") : "",
      nearby_text: previousCellText,
      row_label: previousCellText,
      previous_cell_text: previousCellText,
      next_cell_text: "",
      field_id: fieldId,
      field_name: fieldName,
      field_container_hint: fieldContainerHintOf(element),
    };
  };
```

Keep helper names scoped inside `build_browser_state_script`; do not add a separate JS file.

- [ ] **Step 5: Normalize new defaults**

In `normalize_state_result`, add defaults without changing existing metadata:

```python
field_context = normalized.setdefault("field_context", {})
if isinstance(field_context, dict):
    field_context.setdefault("nearby_text", "")
    field_context.setdefault("row_label", "")
    field_context.setdefault("previous_cell_text", "")
    field_context.setdefault("next_cell_text", "")
    field_context.setdefault("field_id", "")
    field_context.setdefault("field_name", "")
    field_context.setdefault("field_container_hint", "")
```

If the existing test expects `field_context == {}` for minimal normalized elements, update that assertion to check individual defaults only if the implementation now always creates them. Prefer preserving `{}` for missing field contexts if possible; do not break output compatibility unless necessary.

- [ ] **Step 6: Run indexer tests**

Run:

```powershell
python -m pytest tests/test_browser_indexer.py -q
```

Expected: all indexer tests pass.

- [ ] **Step 7: Commit Task 1**

Run:

```powershell
git add ga_browser_use/indexer.py tests/test_browser_indexer.py
git commit -m "feat: enrich browser field context"
```

## Task 2: Finder Scoring V2

**Files:**
- Modify: `ga_browser_use/finder.py`
- Test: `tests/test_ga_browser_use_finder.py`

- [ ] **Step 1: Add failing tests for field-context matching**

Append:

```python
def test_find_matches_adjacent_row_label_for_custom_select():
    state = make_state(
        [
            {
                "index": 4,
                "text": "请选择",
                "labels": [],
                "control_kind": "custom_select",
                "visible": True,
                "disabled": False,
                "field_context": {
                    "nearby_text": "是否休假",
                    "row_label": "是否休假",
                    "previous_cell_text": "是否休假",
                    "field_id": "field5956",
                    "field_name": "sfxj",
                },
            },
            {
                "index": 9,
                "text": "是否休假说明",
                "labels": [],
                "control_kind": "button",
                "visible": True,
                "disabled": False,
            },
        ]
    )

    result = find_in_state(state, query="是否休假", control_kind="custom_select", max_results=5)

    assert result["status"] == "success"
    assert result["ambiguous"] is False
    assert result["matches"][0]["index"] == 4
    assert "field row label" in result["matches"][0]["reason"]
```

Append:

```python
def test_find_matches_field_id_and_field_name():
    state = make_state(
        [
            {
                "index": 3,
                "text": "",
                "labels": [],
                "control_kind": "native_input",
                "visible": True,
                "disabled": False,
                "field_context": {"field_id": "field6358_0", "field_name": "workType"},
            }
        ]
    )

    by_id = find_in_state(state, query="field6358_0", control_kind="native_input", max_results=5)
    by_name = find_in_state(state, query="workType", control_kind="native_input", max_results=5)

    assert by_id["matches"][0]["index"] == 3
    assert "field id" in by_id["matches"][0]["reason"]
    assert by_name["matches"][0]["index"] == 3
    assert "field name" in by_name["matches"][0]["reason"]
```

- [ ] **Step 2: Run the failing finder tests**

Run:

```powershell
python -m pytest tests/test_ga_browser_use_finder.py::test_find_matches_adjacent_row_label_for_custom_select tests/test_ga_browser_use_finder.py::test_find_matches_field_id_and_field_name -q
```

Expected: tests fail because scoring currently treats `nearby_text` as generic text and does not include row label, previous cell, field id, or field name with strong weights.

- [ ] **Step 3: Add explicit field scoring**

In `ga_browser_use/finder.py`, add helpers near `_table_value`:

```python
def _field_value(field_context: dict[str, Any], *names: str) -> str:
    for name in names:
        value = field_context.get(name)
        if value:
            return str(value)
    return ""


def _score_field_context(field_context: dict[str, Any], query: str) -> tuple[float, list[str]]:
    if not query:
        return 0.0, []
    score = 0.0
    reasons: list[str] = []
    row_label = _field_value(field_context, "row_label", "previous_cell_text")
    nearby_text = _field_value(field_context, "nearby_text")
    field_id = _field_value(field_context, "field_id")
    field_name = _field_value(field_context, "field_name")
    if row_label and _norm(row_label) == _norm(query):
        score += 68
        reasons.append("field row label")
    elif row_label and _contains(row_label, query):
        score += 52
        reasons.append("field row label")
    elif nearby_text and _contains(nearby_text, query):
        score += 44
        reasons.append("nearby field text")
    if field_id and _norm(field_id) == _norm(query):
        score += 70
        reasons.append("field id")
    if field_name and _norm(field_name) == _norm(query):
        score += 70
        reasons.append("field name")
    return score, reasons
```

Then update `_score_element` so field context scoring happens before generic text fallback:

```python
    field_context = element.get("field_context") or {}
    if query:
        field_score, field_reasons = _score_field_context(field_context, query)
        if field_score:
            score += field_score
            reasons.extend(field_reasons)
        elif any(_norm(label) == _norm(query) for label in labels):
            score += 70
            reasons.append("exact label")
        elif any(_contains(label, query) for label in labels):
            score += 50
            reasons.append("label")
        elif any(_contains(part, query) for part in parts):
            score += 25
            reasons.append("text")
        else:
            return 0.0, []
```

Do not remove the existing hard filters for `role`, `control_kind`, `layer`, or `frame_path`.

- [ ] **Step 4: Preserve ambiguity semantics**

Add this test:

```python
def test_find_keeps_ambiguous_for_duplicate_field_labels():
    state = make_state(
        [
            {
                "index": 1,
                "text": "",
                "labels": [],
                "control_kind": "custom_select",
                "visible": True,
                "disabled": False,
                "field_context": {"row_label": "工作类型", "previous_cell_text": "工作类型"},
            },
            {
                "index": 2,
                "text": "",
                "labels": [],
                "control_kind": "custom_select",
                "visible": True,
                "disabled": False,
                "field_context": {"row_label": "工作类型", "previous_cell_text": "工作类型"},
            },
        ]
    )

    result = find_in_state(state, query="工作类型", control_kind="custom_select", max_results=5)

    assert result["status"] == "success"
    assert result["ambiguous"] is True
    assert [match["index"] for match in result["matches"][:2]] == [1, 2]
```

- [ ] **Step 5: Run finder tests**

Run:

```powershell
python -m pytest tests/test_ga_browser_use_finder.py tests/test_browser_tool_handlers.py::test_browser_find_refresh_miss_stops_same_refresh_loop -q
```

Expected: all selected tests pass, including the existing refresh-miss stop behavior in `BrowserActionLayer.find`.

- [ ] **Step 6: Commit Task 2**

Run:

```powershell
git add ga_browser_use/finder.py tests/test_ga_browser_use_finder.py
git commit -m "feat: score browser find field context"
```

## Task 3: Advisory Recipe Hints In State

**Files:**
- Modify: `ga_browser_use/indexer.py`
- Test: `tests/test_browser_indexer.py`

- [ ] **Step 1: Add failing tests for `recipe_hint`**

Append:

```python
def test_browser_state_script_emits_custom_select_recipe_hint_with_query_target():
    script = build_browser_state_script(include_invisible=False, max_elements=10)

    state = run_browser_state_script(
        script,
        """
const row = makeElement({ tag: "tr" });
const labelCell = makeElement({ tag: "td", text: "工作类型" });
const controlCell = makeElement({ tag: "td", text: "" });
row.children = [labelCell, controlCell];
const table = makeElement({ tag: "table" });
table.querySelectorAll = (selector) => selector === "tr, [role='row']" ? [row] : [];
const trigger = makeElement({
  tag: "div",
  role: "combobox",
  text: "请选择",
  attrs: { "aria-haspopup": "listbox", class: "ant-select-selector" }
});
trigger.closest = (selector) => {
  if (selector.includes(".ant-select")) return trigger;
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

    hint = state["elements"][0]["recipe_hint"]
    assert hint == {
        "recipe": "custom_select",
        "target": {"query": "工作类型"},
        "requires": ["option_text"],
    }
```

Append:

```python
def test_browser_state_script_does_not_emit_recipe_hint_for_plain_button():
    script = build_browser_state_script(include_invisible=False, max_elements=10)

    state = run_browser_state_script(
        script,
        """
const button = makeElement({ tag: "button", text: "保存" });
document.querySelectorAll = (selector) => {
  if (selector === "iframe, frame" || selector.startsWith("label[")) return [];
  return [button];
};
""",
    )

    assert state["elements"][0].get("recipe_hint") in ({}, None)
```

- [ ] **Step 2: Run the failing recipe hint tests**

Run:

```powershell
python -m pytest tests/test_browser_indexer.py::test_browser_state_script_emits_custom_select_recipe_hint_with_query_target tests/test_browser_indexer.py::test_browser_state_script_does_not_emit_recipe_hint_for_plain_button -q
```

Expected: the first test fails because `recipe_hint` is not emitted.

- [ ] **Step 3: Implement advisory `recipeHintOf`**

In `ga_browser_use/indexer.py`, add a helper after `actionHintsOf`:

```javascript
  const recipeHintOf = (element, controlKind, fieldContext) => {
    if (controlKind !== "custom_select") return {};
    const query = boundedText(
      (fieldContext && (fieldContext.row_label || fieldContext.nearby_text || fieldContext.previous_cell_text)) || ""
    );
    const hint = {
      recipe: "custom_select",
      requires: ["option_text"],
    };
    if (query) hint.target = { query };
    return hint;
  };
```

Then update the snapshot mapping to compute `fieldContext` once:

```javascript
    const fieldContext = fieldContextOf(element);
    const recipeHint = recipeHintOf(element, controlKind, fieldContext);
```

And emit:

```javascript
      field_context: fieldContext,
      recipe_hint: recipeHint,
```

Keep `recipe_hint` advisory; do not call `browser_recipe` from the state reader.

- [ ] **Step 4: Normalize `recipe_hint` default**

In `normalize_state_result`, add:

```python
normalized.setdefault("recipe_hint", {})
```

Update `test_normalize_state_result_fills_new_element_metadata_defaults` to assert:

```python
assert element["recipe_hint"] == {}
```

- [ ] **Step 5: Run indexer tests**

Run:

```powershell
python -m pytest tests/test_browser_indexer.py -q
```

Expected: all indexer tests pass.

- [ ] **Step 6: Commit Task 3**

Run:

```powershell
git add ga_browser_use/indexer.py tests/test_browser_indexer.py
git commit -m "feat: expose browser recipe hints"
```

## Task 4: Action Recovery V2

**Files:**
- Modify: `ga_browser_use/actions.py`
- Modify if needed: `ga_browser_use/results.py`
- Test: `tests/test_browser_actions.py`
- Test: `tests/test_ga_browser_use_results.py`

- [ ] **Step 1: Add failing test for custom select recovery using field query**

Update the existing `test_run_action_select_custom_control_recovery_includes_target_and_option` cached element to include field context:

```python
4: {
    "index": 4,
    "text": "所属部门",
    "labels": ["所属部门"],
    "stable_key": "combo#dept",
    "selector_hint": "#dept",
    "field_context": {"nearby_text": "所属部门", "row_label": "所属部门"},
}
```

Change the assertion to prefer query target:

```python
assert result["recovery"]["next_args"] == {
    "recipe": "custom_select",
    "target": {"query": "所属部门"},
    "option_text": "研发部",
}
```

- [ ] **Step 2: Add failing test for zero-rect field recovery**

Append:

```python
def test_run_action_visibility_failure_suggests_clickable_in_same_field():
    layer = BrowserActionLayer()
    layer._last_state = {
        "tab_id": "7",
        "state_token": "tok-1",
        "url": "https://example.test/form",
        "elements_by_index": {
            9: {
                "index": 9,
                "text": "",
                "stable_key": "div#project",
                "selector_hint": "#project",
                "control_kind": "custom_select",
                "field_context": {"nearby_text": "项目名称", "row_label": "项目名称"},
            }
        },
    }
    driver = FakeDriver(
        [
            {
                "data": {
                    "status": "failed",
                    "action": "click",
                    "index": 9,
                    "stage": "visibility",
                    "error": "Element is not visible.",
                }
            }
        ]
    )

    result = layer.run_action(driver, action="click", index=9)

    assert result["stage"] == "visibility"
    assert result["recovery"]["code"] == "find_clickable_in_same_field"
    assert result["recovery"]["next_tool"] == "browser_find"
    assert result["recovery"]["next_args"] == {
        "query": "项目名称",
        "control_kind": "button",
        "refresh": True,
        "max_results": 5,
    }
```

- [ ] **Step 3: Add failing test for custom select click success hint**

Append:

```python
def test_run_action_custom_select_click_success_returns_next_action_hint():
    layer = BrowserActionLayer()
    layer._last_state = {
        "tab_id": "7",
        "state_token": "tok-1",
        "url": "https://example.test/form",
        "elements_by_index": {
            4: {
                "index": 4,
                "text": "工作类型",
                "stable_key": "combo#work",
                "selector_hint": "#work",
                "control_kind": "custom_select",
                "field_context": {"nearby_text": "工作类型", "row_label": "工作类型"},
            }
        },
    }
    driver = FakeDriver([{"data": {"status": "success", "action": "click", "index": 4, "page_changed": True}}])

    result = layer.run_action(driver, action="click", index=4)

    assert result["status"] == "success"
    assert result["next_action_hint"] == {
        "message": "Custom select may have opened an overlay. Refresh browser_state or run browser_recipe custom_select with option_text.",
        "next_tools": ["browser_state", "browser_recipe"],
        "recipe": {"recipe": "custom_select", "target": {"query": "工作类型"}},
    }
```

- [ ] **Step 4: Run the failing action tests**

Run:

```powershell
python -m pytest tests/test_browser_actions.py::test_run_action_select_custom_control_recovery_includes_target_and_option tests/test_browser_actions.py::test_run_action_visibility_failure_suggests_clickable_in_same_field tests/test_browser_actions.py::test_run_action_custom_select_click_success_returns_next_action_hint -q
```

Expected: tests fail until target-aware recovery is added.

- [ ] **Step 5: Add target-context helpers in action layer**

In `ga_browser_use/actions.py`, add private helpers on `BrowserActionLayer`:

```python
    def _field_query_for_target(self, target: dict[str, Any] | None) -> str:
        if not isinstance(target, dict):
            return ""
        field_context = target.get("field_context") or {}
        for key in ("row_label", "nearby_text", "previous_cell_text"):
            value = str(field_context.get(key) or "").strip()
            if value:
                return value
        for key in ("text", "value"):
            value = str(target.get(key) or "").strip()
            if value:
                return value
        labels = target.get("labels") or []
        if labels:
            return str(labels[0] or "").strip()
        return ""

    def _recipe_target_for_cached_element(self, index: int | None, target: dict[str, Any] | None) -> dict[str, Any]:
        query = self._field_query_for_target(target)
        if query:
            return {"query": query}
        if index is not None:
            return {"index": index}
        return {}
```

- [ ] **Step 6: Use query target for custom select misuse**

In `run_action`, replace the current `suggested_args` assignment for `select` + `control_unsupported` with:

```python
            if action == "select" and result.get("stage") == "control_unsupported" and safe_index is not None:
                option_text = str(value if value is not None else text or "").strip()
                recipe_target = self._recipe_target_for_cached_element(safe_index, cached_element)
                if option_text and recipe_target:
                    result["suggested_args"] = {"target": recipe_target, "option_text": option_text}
```

- [ ] **Step 7: Augment visibility and repeat recovery**

After `result = add_recovery(...)` and before `_record_failure`, add target-aware recovery augmentation:

```python
            result = self._augment_action_recovery(result, action=action, index=safe_index, target=cached_element)
```

Add this method:

```python
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
            recovery.update(
                {
                    "code": "find_clickable_in_same_field",
                    "message": "The indexed wrapper is not clickable. Find a visible clickable control in the same field.",
                    "stop_retry": False,
                    "next_tool": "browser_find",
                    "next_args": {"query": query, "control_kind": "button", "refresh": True, "max_results": 5},
                }
            )
        elif updated.get("stage") == "repeat_blocked":
            alternatives = []
            if query:
                alternatives.append({"tool": "browser_find", "args": {"query": query, "refresh": True, "max_results": 5}})
            if control_kind == "custom_select" and query:
                alternatives.append({"tool": "browser_recipe", "args": {"recipe": "custom_select", "target": {"query": query}}})
            alternatives.append({"tool": "web_execute_js", "reason": "Use low-level probing if structured metadata is insufficient."})
            recovery["alternatives"] = alternatives
        updated["recovery"] = recovery
        return updated
```

If `_record_failure` converts a result into `repeat_blocked`, call `_augment_action_recovery` again when returning that blocked result so alternatives are present on the final response.

- [ ] **Step 8: Add custom select success hint**

After receiving a successful action result but before clearing cached state, add:

```python
            if action == "click" and isinstance(cached_element, dict) and cached_element.get("control_kind") == "custom_select":
                recipe_target = self._recipe_target_for_cached_element(safe_index, cached_element)
                if recipe_target:
                    result = dict(result)
                    result["next_action_hint"] = {
                        "message": "Custom select may have opened an overlay. Refresh browser_state or run browser_recipe custom_select with option_text.",
                        "next_tools": ["browser_state", "browser_recipe"],
                        "recipe": {"recipe": "custom_select", "target": recipe_target},
                    }
```

Do not auto-run `browser_recipe`.

- [ ] **Step 9: Run action and result tests**

Run:

```powershell
python -m pytest tests/test_browser_actions.py tests/test_ga_browser_use_results.py -q
```

Expected: all tests pass.

- [ ] **Step 10: Commit Task 4**

Run:

```powershell
git add ga_browser_use/actions.py ga_browser_use/results.py tests/test_browser_actions.py tests/test_ga_browser_use_results.py
git commit -m "feat: improve browser action recovery"
```

## Task 5: Recipe Reliability Tightening

**Files:**
- Modify: `ga_browser_use/recipes.py`
- Test: `tests/test_ga_browser_use_recipes.py`

- [ ] **Step 1: Add test that trigger lookup uses field query target**

Append:

```python
def test_custom_select_query_target_keeps_trigger_lookup_bounded():
    layer = FakeLayer()
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="custom_select", target={"query": "工作类型"}, option_text="代码开发", max_results=3)

    assert result["status"] == "success"
    assert layer.calls[0] == (
        "find",
        {
            "query": "工作类型",
            "role": None,
            "control_kind": "custom_select",
            "layer": None,
            "frame_path": None,
            "table": None,
            "max_results": 3,
            "refresh": False,
            "include_invisible": False,
            "switch_tab_id": None,
        },
    )
```

If current `_find_single_target` uses different keyword defaults, adjust the expected dictionary to match the actual call shape after inspecting the function; keep the assertion strict.

- [ ] **Step 2: Add test that non-target errors are not swallowed by component wait**

Append:

```python
def test_component_wait_returns_non_target_find_errors_immediately():
    layer = FakeLayer()
    layer.find_results = [
        {"status": "failed", "stage": "browser_unavailable", "error": "bridge failed", "recovery": {"code": "fallback_low_level"}}
    ]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="component_wait", target={"query": "保存"}, condition="element_enabled", timeout=1)

    assert result["status"] == "failed"
    assert result["stage"] == "browser_unavailable"
    assert result["recovery"]["code"] == "fallback_low_level"
```

- [ ] **Step 3: Run the recipe tests**

Run:

```powershell
python -m pytest tests/test_ga_browser_use_recipes.py -q
```

Expected: if the current implementation already satisfies these cases, tests pass and no recipe code change is needed. If a test fails, make the smallest targeted change.

- [ ] **Step 4: Fix only failing recipe behavior**

If trigger lookup does not hard-filter `custom_select`, update `_find_single_target` or `_custom_select` so query targets for `custom_select` call `layer.find(..., control_kind="custom_select", ...)`.

Use code equivalent to:

```python
trigger_find = self._find_single_target(
    driver,
    recipe="custom_select",
    target=target,
    max_results=max_results,
    switch_tab_id=switch_tab_id,
    control_kind="custom_select",
)
```

If `component_wait` swallows `browser_unavailable`, keep the existing `target_not_found` retry loop but return other stages immediately:

```python
if find_result.get("status") != "success":
    if find_result.get("stage") == "target_not_found":
        pass
    else:
        find_result["recipe"] = "component_wait"
        return self._with_steps(find_result, steps)
```

- [ ] **Step 5: Run recipe tests**

Run:

```powershell
python -m pytest tests/test_ga_browser_use_recipes.py -q
```

Expected: all recipe tests pass.

- [ ] **Step 6: Commit Task 5**

Run:

```powershell
git add ga_browser_use/recipes.py tests/test_ga_browser_use_recipes.py
git commit -m "fix: tighten browser recipe reliability"
```

If no production code changed because tests already passed, commit only the added tests:

```powershell
git add tests/test_ga_browser_use_recipes.py
git commit -m "test: cover browser recipe reliability"
```

## Task 6: Tool Descriptions And SOP Alignment

**Files:**
- Modify: `assets/tools_schema.json`
- Modify: `assets/tools_schema_cn.json`
- Modify: `memory/browser-use_sop.md`
- Test: `tests/test_browser_tool_schemas.py`

- [ ] **Step 1: Add schema tests for new wording**

Extend `test_browser_tool_descriptions_use_parallel_boundary_terms`:

```python
assert "field context" in en_state["description"]
assert "recipe_hint" in en_state["description"]
assert "field labels" in en_find["description"]
assert "recovery" in en_action["description"]
assert "advisory" in en_recipe["description"]

assert "字段上下文" in cn_state["description"]
assert "recipe_hint" in cn_state["description"]
assert "字段标签" in cn_find["description"]
assert "恢复建议" in cn_action["description"]
assert "提示" in cn_recipe["description"]
```

- [ ] **Step 2: Run schema test to verify it fails before wording changes**

Run:

```powershell
python -m pytest tests/test_browser_tool_schemas.py::test_browser_tool_descriptions_use_parallel_boundary_terms -q
```

Expected: fails on missing new wording.

- [ ] **Step 3: Update English schema descriptions**

In `assets/tools_schema.json`, keep the existing boundary wording and add concise guidance:

```json
"description": "Get a structured indexed snapshot from the real Chrome page for recoverable element targeting, including same-origin iframe metadata, field context, control/layer context, and advisory recipe_hint for bounded recipes. This is not full-page extraction and not complex DOM reasoning. Use before browser_action when indexes may have changed."
```

For `browser_find`, include:

```text
It scores visible text, labels, field labels, table context, and field ids/names.
```

For `browser_recipe`, include:

```text
recipe_hint is advisory; recipes still require bounded arguments and fail closed.
```

For `browser_action`, include:

```text
Failures include structured recovery suggestions when a safer next browser_* step is available.
```

- [ ] **Step 4: Update Chinese schema descriptions**

In `assets/tools_schema_cn.json`, mirror the English changes:

```text
包含同源 iframe 元数据、字段上下文、control/layer 上下文，以及用于有界 recipe 的提示性 recipe_hint。
```

For `browser_find`, include:

```text
会对可见文本、标签、字段标签、表格上下文以及字段 id/name 进行评分。
```

For `browser_recipe`, include:

```text
recipe_hint 只是提示；recipe 仍需要有边界参数，并在歧义时 fail closed。
```

For `browser_action`, include:

```text
失败时会在可判断的场景返回结构化恢复建议。
```

- [ ] **Step 5: Update SOP**

In `memory/browser-use_sop.md`, add a section named `结构化 browser_* 工具编排建议` with this content:

```markdown
## 结构化 browser_* 工具编排建议

- `browser_state` 用于刷新索引和读取字段上下文；看到 `recipe_hint` 时，只表示该控件适合某个固定 recipe，不表示工具会自动执行 recipe。
- `browser_find` 用于只读定位。优先提供真实语义条件，例如字段名、表格行列、字段 id/name；`role`、`control_kind`、`layer`、`frame_path` 只是过滤条件，不能单独作为定位。
- `browser_action` 用于有界索引动作。失败时必须读取 `recovery`，不要对同一 index 反复执行同一动作。
- `browser_recipe` 只用于固定场景：`custom_select`、`layer_select`、`table_locate`、`component_wait`。它不是通用表单规划器，遇到歧义会返回候选并停止。
- 如果 `browser_find(refresh=true)` 后仍然 `target_not_found` 且 `recovery.stop_retry=true`，不要继续重复同一查询；改用更窄的字段/层级约束，或切换到平级的 `web_execute_js` 做低层探测。
```

Do not mention the two historical manual test checklists as superpowers deliverables.

- [ ] **Step 6: Run schema tests**

Run:

```powershell
python -m pytest tests/test_browser_tool_schemas.py -q
```

Expected: schema tests pass and forbidden overclaim wording is still absent.

- [ ] **Step 7: Commit Task 6**

Run:

```powershell
git add assets/tools_schema.json assets/tools_schema_cn.json memory/browser-use_sop.md tests/test_browser_tool_schemas.py
git commit -m "docs: clarify browser structured tool guidance"
```

## Task 7: Final Focused Verification

**Files:**
- Test only

- [ ] **Step 1: Run full focused browser-use suite**

Run:

```powershell
python -m pytest tests/test_browser_indexer.py tests/test_ga_browser_use_finder.py tests/test_browser_actions.py tests/test_ga_browser_use_results.py tests/test_ga_browser_use_recipes.py tests/test_browser_tool_handlers.py tests/test_browser_tool_schemas.py -q
```

Expected:

```text
passed
```

- [ ] **Step 2: Run whitespace check**

Run:

```powershell
git diff --check
```

Expected: no output.

- [ ] **Step 3: Inspect final commit stack**

Run:

```powershell
git log --oneline -8
git status --short --branch
```

Expected:

```text
## ga-browser-use...origin/ga-browser-use [ahead N]
```

Working tree should be clean except for unrelated pre-existing user files.

## Self-Review Checklist

- Spec coverage: Task 1 covers Field Context V2; Task 2 covers Finder Scoring V2; Task 3 covers Recipe Discoverability; Task 4 covers Action Recovery V2; Task 5 covers Recipe Reliability Tightening; Task 6 covers schema/SOP alignment.
- Boundary check: no task modifies GA legacy browser tools, `web_execute_js`, `web_scan`, or external `browser-use`.
- Simplicity check: no new framework, no new planner, no business-specific OA recipe, no arbitrary selector automation.
- Verification check: each production change has a focused pytest command and a commit boundary.
- Risk check: if a recipe reliability test already passes, do not edit production recipe code for that case.
