# browser_use_index Navigation Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the public `browser_state` surface to `browser_use_index` and turn it into a dynamic-page, multi-frame navigation index that guides `web_scan` and `browser_action` while deleting redundant state hints.

**Architecture:** Keep `web_execute_js` unchanged and keep `browser_recipe` frozen. Rebuild the state payload around one job: expose stable action indexes, dynamic page signals, and same-origin frame discovery in a form that helps the agent map `web_scan` text to a concrete `browser_action` target. Remove weak advisory fields that do not materially improve navigation.

**Tech Stack:** Python, pytest, JSON schema files, GA/TMWebDriver browser bridge.

---

### Task 1: Rename the public browser index surface

**Files:**
- Modify: `ga.py`
- Modify: `ga_browser_use/actions.py`
- Modify: `assets/tools_schema.json`
- Modify: `assets/tools_schema_cn.json`
- Modify: `memory/browser-use_sop.md`
- Modify: `tests/test_browser_tool_handlers.py`
- Modify: `tests/test_browser_tool_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
def test_public_tool_is_browser_use_index():
    tools = load_tools("assets/tools_schema.json")
    names = [item["function"]["name"] for item in tools]
    assert "browser_use_index" in names
    assert "browser_state" not in names


def test_do_browser_use_index_formats_execution_output(monkeypatch):
    monkeypatch.setattr(
        ga,
        "browser_use_index",
        lambda **kwargs: {"status": "success", "tab_id": "7", "elements": []},
    )
    handler = make_handler()
    chunks, outcome = run_generator(handler.do_browser_use_index({"max_elements": 10}, SimpleNamespace(content="")))
    assert "Browser index result:" in "".join(chunks)
    assert json.loads(outcome.data)["status"] == "success"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_browser_tool_schemas.py tests/test_browser_tool_handlers.py -v`
Expected: fail because `browser_use_index` is not exposed yet and `do_browser_use_index` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
def browser_use_index(switch_tab_id=None, include_invisible=False, max_elements=120):
    return browser_action_layer.get_state(
        driver,
        switch_tab_id=switch_tab_id,
        include_invisible=include_invisible,
        max_elements=max_elements,
    )
```

Update the tool schema entries and handler wiring so the exposed tool name, prompt text, and runtime log label use `browser_use_index`. Keep internal helper names only where they do not leak into user-facing output.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_browser_tool_schemas.py tests/test_browser_tool_handlers.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ga.py ga_browser_use/actions.py assets/tools_schema.json assets/tools_schema_cn.json memory/browser-use_sop.md tests/test_browser_tool_handlers.py tests/test_browser_tool_schemas.py
git commit -m "feat: rename browser_state to browser_use_index"
```

### Task 2: Rebuild the state payload around dynamic page and frame discovery

**Files:**
- Modify: `ga_browser_use/indexer.py`
- Modify: `tests/test_browser_indexer.py`
- Modify: `tests/test_ga_browser_use_finder.py`

- [ ] **Step 1: Write the failing test**

```python
def test_browser_use_index_emits_page_signals_and_frames():
    state = run_browser_state_script(script, setup_js)
    assert state["page_signals"]["busy"] is True
    assert state["frames"][0]["same_origin_accessible"] is True
    assert state["elements"][0]["scan_anchor"]["row_text"] == "是否休假"
    assert "recipe_hint" not in state["elements"][0]
    assert "action_hints" not in state["elements"][0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_browser_indexer.py tests/test_ga_browser_use_finder.py -v`
Expected: fail because `page_signals`, `frames`, and `scan_anchor` do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```javascript
const loadingSelector = "[aria-busy='true'], [role='progressbar'], .ant-spin-spinning, .loading, .spinner";
const visibleLoading = Array.from(document.querySelectorAll(loadingSelector))
  .filter(node => isVisible(node, node.getBoundingClientRect(), node.ownerDocument.defaultView || window));
const visibleOverlays = Array.from(document.querySelectorAll(overlaySelector))
  .filter(node => isVisible(node, node.getBoundingClientRect(), node.ownerDocument.defaultView || window));

const pageSignals = {
  ready_state: document.readyState || "",
  busy: visibleLoading.length > 0 || document.body.getAttribute("aria-busy") === "true",
  overlay_count: visibleOverlays.length,
  loading_count: visibleLoading.length,
  focused_selector_hint: document.activeElement ? selectorHint(document.activeElement) : "",
};

const scanAnchorOf = (fieldContext, tableContext, layerContext, framePath) => ({
  near_text: fieldContext.nearby_text || "",
  field_label: fieldContext.row_label || "",
  row_text: tableContext.row_text || "",
  column_text: tableContext.column_text || tableContext.column_header || "",
  layer: layerContext.layer || "main",
  frame_path: framePath,
});
```

Remove `recipe_hint` and `action_hints` from the returned element payload. Keep `selector_hint`, `stable_key`, `field_context`, `table_context`, `attributes`, and `validation` for the next stage of navigation and recovery.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_browser_indexer.py tests/test_ga_browser_use_finder.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ga_browser_use/indexer.py tests/test_browser_indexer.py tests/test_ga_browser_use_finder.py
git commit -m "feat: turn browser index into navigation state"
```

### Task 3: Tighten downstream consumers and remove stale state assumptions

**Files:**
- Modify: `ga_browser_use/actions.py`
- Modify: `ga_browser_use/finder.py`
- Modify: `ga_browser_use/results.py`
- Modify: `ga_browser_use/runtime_log.py`
- Modify: `tests/test_browser_actions.py`
- Modify: `tests/test_ga_browser_use_results.py`
- Modify: `tests/test_browser_tool_handlers.py`

- [ ] **Step 1: Write the failing test**

```python
def test_action_recovery_mentions_browser_use_index(monkeypatch):
    layer = BrowserActionLayer()
    driver = FakeDriver()
    layer._last_state = {"tab_id": "tab-a", "state": {"status": "success", "elements": []}}

    result = layer.run_action(driver, action="click", index=1)
    assert "browser_use_index" in result["error"] or "browser_use_index" in result.get("recovery", {}).get("message", "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_browser_actions.py tests/test_ga_browser_use_results.py tests/test_browser_tool_handlers.py -v`
Expected: fail because stale messages still refer to `browser_state` and logs still emit old names/hints.

- [ ] **Step 3: Write minimal implementation**

```python
result = failed_result(action, "state_missing", f"Run browser_use_index before browser_action {action}.", index)
log_event(
    "browser_use_index",
    "start",
    fields={
        "include_invisible": include_invisible,
        "max_elements": max_elements,
        "switch_tab_id": switch_tab_id,
    },
)
```

Update `browser_find` scoring and recovery messages to treat `scan_anchor`, `field_context`, `table_context`, `frame_path`, and `layer` as the real navigation contract. Stop depending on `recipe_hint` or `action_hints` anywhere in the runtime path.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_browser_actions.py tests/test_ga_browser_use_results.py tests/test_browser_tool_handlers.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ga_browser_use/actions.py ga_browser_use/finder.py ga_browser_use/results.py ga_browser_use/runtime_log.py tests/test_browser_actions.py tests/test_ga_browser_use_results.py tests/test_browser_tool_handlers.py
git commit -m "feat: tighten browser index recovery and logs"
```

### Task 4: Update SOP text and run the focused regression suite

**Files:**
- Modify: `memory/browser-use_sop.md`
- Modify: `assets/tools_schema.json`
- Modify: `assets/tools_schema_cn.json`

- [ ] **Step 1: Write the failing test**

```python
def test_schema_and_sop_describe_browser_use_index_not_browser_state():
    tools = load_tools("assets/tools_schema_cn.json")
    names = [item["function"]["name"] for item in tools]
    assert "browser_use_index" in names
    assert "browser_state" not in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_browser_tool_schemas.py -v`
Expected: fail until the docs and schemas are updated together.

- [ ] **Step 3: Write minimal implementation**

```markdown
- 先调用 `browser_use_index` 获取动态页面、frame、layer、table 与 scan_anchor。
- `web_scan` 负责读文本，`browser_use_index` 负责把文本映射为可操作 index。
- `recipe_hint` / `action_hints` 不再作为主路径。
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_browser_indexer.py tests/test_browser_actions.py tests/test_browser_tool_schemas.py tests/test_browser_tool_handlers.py tests/test_ga_browser_use_finder.py tests/test_ga_browser_use_results.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add memory/browser-use_sop.md assets/tools_schema.json assets/tools_schema_cn.json
git commit -m "docs: align browser_use_index navigation contract"
```

## Self-Review

- Spec coverage: rename, state shape, consumer updates, docs, and regression tests are all covered.
- Placeholder scan: no TBD/TODO steps, no vague validation language.
- Type consistency: `browser_use_index`, `page_signals`, `frames`, and `scan_anchor` are used consistently across tasks.
- Scope check: still one subsystem. `browser_recipe` and `web_execute_js` stay frozen.
