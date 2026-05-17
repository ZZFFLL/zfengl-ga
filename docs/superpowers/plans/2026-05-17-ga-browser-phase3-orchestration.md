# GA Browser Phase 3 Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a modular GA browser-use integration package with recovery/fuse guidance, `browser_find`, bounded `browser_recipe`, limited AntD/ui-browser indexing, and SOP updates.

**Architecture:** Keep GA on the existing real-user Chrome + TMWebDriver bridge. Move the current browser action/indexer code behind `ga_browser_use/` while preserving root-level compatibility shims, then add small focused modules for results, finder, and recipes instead of expanding the existing large files.

**Tech Stack:** Python 3, pytest, GA `ga.py` tool handlers, JSON tool schemas in `assets/tools_schema.json` and `assets/tools_schema_cn.json`, existing TMWebDriver execution path.

---

## Scope And Guardrails

- Do not modify `E:\zfengl-ai-project\browser-use`.
- Do not launch Chrome or create a separate browser profile.
- Do not change the public semantics of existing `browser_state` and `browser_action`.
- Do not add cross-origin iframe, Shadow DOM, file upload, screenshot logging, or virtualized-grid paging in this phase.
- Keep every public recipe bounded and enum-based.
- Every new failed result must include `recovery`.
- Ambiguous target selection must fail closed and return candidates.

## File Structure

- Create: `ga_browser_use/__init__.py`
  - Package marker and public imports for the GA browser-use integration.
- Create: `ga_browser_use/indexer.py`
  - New home for `build_browser_state_script` and `normalize_state_result`.
- Modify: `browser_indexer.py`
  - Compatibility shim that re-exports from `ga_browser_use.indexer`.
- Create: `ga_browser_use/actions.py`
  - New home for `BrowserActionLayer`, action constants, and action script builder.
- Modify: `browser_actions.py`
  - Compatibility shim that re-exports from `ga_browser_use.actions`.
- Create: `ga_browser_use/results.py`
  - Structured recovery helpers and repeated-failure fuse.
- Create: `ga_browser_use/finder.py`
  - Deterministic `browser_find` ranking over normalized state.
- Create: `ga_browser_use/recipes.py`
  - Bounded deterministic recipes: `custom_select`, `layer_select`, `table_locate`, `component_wait`.
- Modify: `ga.py`
  - Import from `ga_browser_use.actions`, expose `browser_find`, expose `browser_recipe`, and add handlers.
- Modify: `assets/tools_schema.json`
  - Add English schemas for `browser_find` and `browser_recipe`.
- Modify: `assets/tools_schema_cn.json`
  - Add Chinese schemas for `browser_find` and `browser_recipe`.
- Modify: `memory/browser-use_sop.md`
  - Teach GA recovery, finder, recipe, and stop-retry sequencing after implementation is proven.
- Create: `tests/test_ga_browser_use_package.py`
  - Package migration and compatibility tests.
- Create: `tests/test_ga_browser_use_results.py`
  - Recovery and fuse tests.
- Create: `tests/test_ga_browser_use_finder.py`
  - Finder ranking and ambiguity tests.
- Create: `tests/test_ga_browser_use_recipes.py`
  - Recipe sequencing tests using a fake browser layer.
- Modify: `tests/test_browser_actions.py`
  - Add action-layer recovery/fuse integration tests.
- Modify: `tests/test_browser_indexer.py`
  - Add limited AntD/ui-browser indexing tests.
- Modify: `tests/test_browser_tool_handlers.py`
  - Add `browser_find` and `browser_recipe` handler tests.
- Modify: `tests/test_browser_tool_schemas.py`
  - Add schema assertions for `browser_find` and `browser_recipe`.

## Verification Commands

Use targeted browser-tool verification after each task that touches runtime behavior:

```powershell
python -m pytest tests/test_browser_indexer.py tests/test_browser_actions.py tests/test_browser_tool_handlers.py tests/test_browser_tool_schemas.py tests/test_ga_browser_use_package.py tests/test_ga_browser_use_results.py tests/test_ga_browser_use_finder.py tests/test_ga_browser_use_recipes.py -q
```

Use full-suite verification before final review:

```powershell
python -m pytest tests -q
```

Known unrelated risk: if full-suite still fails on `ModuleNotFoundError: No module named 'simple_http_server'`, report it as unrelated and do not fix it in this phase.

---

### Task 1: Create `ga_browser_use/` Package And Compatibility Shims

**Files:**
- Create: `ga_browser_use/__init__.py`
- Create: `ga_browser_use/indexer.py`
- Create: `ga_browser_use/actions.py`
- Modify: `browser_indexer.py`
- Modify: `browser_actions.py`
- Create: `tests/test_ga_browser_use_package.py`

- [ ] **Step 1: Write package compatibility tests**

Add `tests/test_ga_browser_use_package.py`:

```python
import browser_actions
import browser_indexer
from ga_browser_use import actions, indexer


def test_root_browser_indexer_reexports_package_functions():
    assert browser_indexer.build_browser_state_script is indexer.build_browser_state_script
    assert browser_indexer.normalize_state_result is indexer.normalize_state_result


def test_root_browser_actions_reexports_package_layer():
    assert browser_actions.BrowserActionLayer is actions.BrowserActionLayer
    assert browser_actions.build_browser_action_script is actions.build_browser_action_script
    assert browser_actions.SUPPORTED_ACTIONS == actions.SUPPORTED_ACTIONS
```

- [ ] **Step 2: Run the new test to verify it fails**

Run:

```powershell
python -m pytest tests/test_ga_browser_use_package.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'ga_browser_use'`.

- [ ] **Step 3: Create package marker**

Create `ga_browser_use/__init__.py`:

```python
"""GA browser-use integration package.

This package keeps GA on the existing real-user Chrome / TMWebDriver path.
It does not import or launch the external browser-use runtime.
"""
```

- [ ] **Step 4: Move indexer implementation into package**

Move the current full contents of `browser_indexer.py` into `ga_browser_use/indexer.py`.

After moving, replace root `browser_indexer.py` with:

```python
from ga_browser_use.indexer import (
    DEFAULT_MAX_ELEMENTS,
    INTERACTIVE_SELECTOR,
    MAX_MAX_ELEMENTS,
    MIN_MAX_ELEMENTS,
    build_browser_state_script,
    normalize_state_result,
)

__all__ = [
    "DEFAULT_MAX_ELEMENTS",
    "MIN_MAX_ELEMENTS",
    "MAX_MAX_ELEMENTS",
    "INTERACTIVE_SELECTOR",
    "build_browser_state_script",
    "normalize_state_result",
]
```

- [ ] **Step 5: Move action implementation into package**

Move the current full contents of `browser_actions.py` into `ga_browser_use/actions.py`.

In `ga_browser_use/actions.py`, change the indexer import to:

```python
from ga_browser_use.indexer import build_browser_state_script, normalize_state_result
```

After moving, replace root `browser_actions.py` with:

```python
from ga_browser_use.actions import (
    INDEX_REQUIRED_ACTIONS,
    KEYS_AFTER_INPUT_HINT,
    STATE_MUTATING_ACTIONS,
    SUPPORTED_ACTIONS,
    WAIT_ACTIONS,
    BrowserActionLayer,
    build_browser_action_script,
    failed_result,
    keys_without_index_retry_result,
)

__all__ = [
    "SUPPORTED_ACTIONS",
    "INDEX_REQUIRED_ACTIONS",
    "STATE_MUTATING_ACTIONS",
    "WAIT_ACTIONS",
    "KEYS_AFTER_INPUT_HINT",
    "failed_result",
    "keys_without_index_retry_result",
    "build_browser_action_script",
    "BrowserActionLayer",
]
```

- [ ] **Step 6: Run compatibility and existing browser tests**

Run:

```powershell
python -m pytest tests/test_ga_browser_use_package.py tests/test_browser_indexer.py tests/test_browser_actions.py tests/test_browser_tool_handlers.py tests/test_browser_tool_schemas.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit package migration**

Run:

```powershell
git add ga_browser_use browser_indexer.py browser_actions.py tests/test_ga_browser_use_package.py
git commit -m "refactor: isolate browser use integration package"
```

---

### Task 2: Add Structured Recovery Helpers And Failure Fuse

**Files:**
- Create: `ga_browser_use/results.py`
- Create: `tests/test_ga_browser_use_results.py`

- [ ] **Step 1: Write recovery and fuse tests**

Add `tests/test_ga_browser_use_results.py`:

```python
from ga_browser_use.results import (
    FailureFuse,
    add_recovery,
    failed_result,
    recovery_for_stage,
)


def test_failed_result_includes_recovery_for_state_missing():
    result = failed_result("click", "state_missing", "Run browser_state before browser_action click.", 4)

    assert result["status"] == "failed"
    assert result["stage"] == "state_missing"
    assert result["recovery"]["code"] == "refresh_state"
    assert result["recovery"]["next_tool"] == "browser_state"
    assert result["recovery"]["stop_retry"] is False


def test_recovery_for_custom_select_misuse_points_to_recipe():
    recovery = recovery_for_stage("control_unsupported", action="select")

    assert recovery["code"] == "use_custom_select_recipe"
    assert recovery["next_tool"] == "browser_recipe"
    assert recovery["next_args"]["recipe"] == "custom_select"


def test_add_recovery_preserves_hint_and_suggested_args():
    result = {"status": "failed", "stage": "state_missing", "hint": "old", "suggested_args": {"action": "keys"}}

    updated = add_recovery(result, action="keys", index=8)

    assert updated["hint"] == "old"
    assert updated["suggested_args"] == {"action": "keys"}
    assert updated["recovery"]["code"] == "use_focused_keys"


def test_failure_fuse_blocks_third_identical_failure():
    fuse = FailureFuse()
    result = {"status": "failed", "stage": "stale_index", "action": "click", "index": 5}
    target = {"stable_key": "button#save", "selector_hint": "button#save", "text": "Save"}

    first = fuse.record(result, tab_id="tab-1", url="https://example.test/form", target=target)
    second = fuse.record(result, tab_id="tab-1", url="https://example.test/form", target=target)
    third = fuse.record(result, tab_id="tab-1", url="https://example.test/form", target=target)

    assert first["stage"] == "stale_index"
    assert first["recovery"]["stop_retry"] is False
    assert second["recovery"]["stop_retry"] is True
    assert third["stage"] == "repeat_blocked"
    assert third["recovery"]["code"] == "stop_repeating"


def test_failure_fuse_resets():
    fuse = FailureFuse()
    result = {"status": "failed", "stage": "stale_index", "action": "click", "index": 5}

    fuse.record(result, tab_id="tab-1", url="https://example.test/form", target={})
    fuse.reset()
    after_reset = fuse.record(result, tab_id="tab-1", url="https://example.test/form", target={})

    assert after_reset["stage"] == "stale_index"
    assert after_reset["recovery"]["stop_retry"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_ga_browser_use_results.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'ga_browser_use.results'`.

- [ ] **Step 3: Implement `ga_browser_use/results.py`**

Create `ga_browser_use/results.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _base_recovery(code: str, message: str, *, next_tool: str | None = None, next_args: dict[str, Any] | None = None) -> dict[str, Any]:
    recovery: dict[str, Any] = {
        "code": code,
        "message": message,
        "stop_retry": False,
    }
    if next_tool:
        recovery["next_tool"] = next_tool
    if next_args:
        recovery["next_args"] = next_args
    return recovery


def recovery_for_stage(stage: str, *, action: str | None = None) -> dict[str, Any]:
    stage = str(stage or "").strip()
    action = str(action or "").strip() or None
    if stage == "state_missing":
        if action == "keys":
            return _base_recovery(
                "use_focused_keys",
                "If this follows a successful input, retry keys without index so the key is sent to the focused element.",
                next_tool="browser_action",
                next_args={"action": "keys"},
            )
        return _base_recovery(
            "refresh_state",
            "Run browser_state before retrying indexed browser actions.",
            next_tool="browser_state",
        )
    if stage == "stale_index":
        return _base_recovery(
            "refresh_state_then_find",
            "The cached index is stale. Refresh state and locate the target again before retrying.",
            next_tool="browser_find",
            next_args={"refresh": True, "max_results": 5},
        )
    if stage == "control_unsupported" and action == "select":
        return _base_recovery(
            "use_custom_select_recipe",
            "This target is not a native select. Use the custom select recipe.",
            next_tool="browser_recipe",
            next_args={"recipe": "custom_select"},
        )
    if stage == "verify_failed":
        return _base_recovery(
            "refresh_state_then_find",
            "The action ran but verification failed. Refresh state and inspect the target before retrying.",
            next_tool="browser_find",
            next_args={"refresh": True, "max_results": 5},
        )
    if stage == "repeat_blocked":
        recovery = _base_recovery(
            "stop_repeating",
            "The same action failed repeatedly against the same target. Stop retrying this call.",
        )
        recovery["stop_retry"] = True
        return recovery
    return _base_recovery(
        "fallback_low_level",
        "Use low-level browser inspection when the high-level action cannot classify the recovery path.",
        next_tool="web_execute_js",
    )


def add_recovery(result: dict[str, Any], *, action: str | None = None, index: int | None = None) -> dict[str, Any]:
    updated = dict(result)
    stage = str(updated.get("stage") or "")
    updated.setdefault("status", "failed")
    if action and "action" not in updated:
        updated["action"] = action
    if index is not None and "index" not in updated:
        updated["index"] = index
    updated.setdefault("recovery", recovery_for_stage(stage, action=str(updated.get("action") or action or "")))
    return updated


def failed_result(action: str | None, stage: str, error: str, index: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "failed", "stage": stage, "error": error}
    if action:
        result["action"] = action
    if index is not None:
        result["index"] = index
    return add_recovery(result, action=action, index=index)


@dataclass
class FailureFuse:
    threshold: int = 3
    _counts: dict[tuple[str, ...], int] = field(default_factory=dict)

    def _signature(self, result: dict[str, Any], *, tab_id: str, url: str, target: dict[str, Any] | None) -> tuple[str, ...]:
        target = target or {}
        return (
            str(tab_id or ""),
            str(url or ""),
            str(result.get("action") or ""),
            str(result.get("index") or ""),
            str(result.get("stage") or ""),
            str(target.get("stable_key") or ""),
            str(target.get("selector_hint") or ""),
            str(target.get("text") or target.get("value") or "")[:120],
        )

    def record(self, result: dict[str, Any], *, tab_id: str, url: str, target: dict[str, Any] | None = None) -> dict[str, Any]:
        updated = add_recovery(result, action=result.get("action"), index=result.get("index"))
        signature = self._signature(updated, tab_id=tab_id, url=url, target=target)
        count = self._counts.get(signature, 0) + 1
        self._counts[signature] = count
        if count >= self.threshold:
            blocked = failed_result(
                updated.get("action"),
                "repeat_blocked",
                "The same browser action failed repeatedly against the same target.",
                updated.get("index"),
            )
            blocked["tab_id"] = tab_id
            return blocked
        if count == self.threshold - 1:
            updated["recovery"] = dict(updated["recovery"])
            updated["recovery"]["stop_retry"] = True
        return updated

    def reset(self) -> None:
        self._counts.clear()
```

- [ ] **Step 4: Run results tests**

Run:

```powershell
python -m pytest tests/test_ga_browser_use_results.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit recovery helper**

Run:

```powershell
git add ga_browser_use/results.py tests/test_ga_browser_use_results.py
git commit -m "feat: add browser recovery result helpers"
```

---

### Task 3: Integrate Recovery And Fuse Into BrowserActionLayer

**Files:**
- Modify: `ga_browser_use/actions.py`
- Modify: `tests/test_browser_actions.py`

- [ ] **Step 1: Write action-layer recovery tests**

Append to `tests/test_browser_actions.py`:

```python
def test_run_action_state_missing_includes_structured_recovery():
    layer = BrowserActionLayer()
    driver = FakeDriver([])

    result = layer.run_action(driver, action="click", index=3)

    assert result["stage"] == "state_missing"
    assert result["recovery"]["code"] == "refresh_state"
    assert result["recovery"]["next_tool"] == "browser_state"


def test_run_action_stale_tab_includes_find_recovery():
    layer = BrowserActionLayer()
    layer._last_state = {"tab_id": "old-tab", "state_token": "tok", "elements_by_index": {1: {"index": 1}}}
    driver = FakeDriver([])
    driver.default_session_id = "new-tab"

    result = layer.run_action(driver, action="click", index=1)

    assert result["stage"] == "stale_index"
    assert result["recovery"]["code"] == "refresh_state_then_find"
    assert result["recovery"]["next_tool"] == "browser_find"


def test_run_action_blocks_third_repeated_failure():
    layer = BrowserActionLayer()
    driver = FakeDriver([])

    first = layer.run_action(driver, action="click", index=9)
    second = layer.run_action(driver, action="click", index=9)
    third = layer.run_action(driver, action="click", index=9)

    assert first["stage"] == "state_missing"
    assert second["recovery"]["stop_retry"] is True
    assert third["stage"] == "repeat_blocked"
    assert third["recovery"]["code"] == "stop_repeating"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_browser_actions.py::test_run_action_state_missing_includes_structured_recovery tests/test_browser_actions.py::test_run_action_stale_tab_includes_find_recovery tests/test_browser_actions.py::test_run_action_blocks_third_repeated_failure -q
```

Expected: FAIL because current action-layer failures do not include `recovery` and no fuse exists.

- [ ] **Step 3: Import result helpers in `ga_browser_use/actions.py`**

Near the imports in `ga_browser_use/actions.py`, add:

```python
from ga_browser_use.results import FailureFuse
from ga_browser_use.results import failed_result as structured_failed_result
from ga_browser_use.results import add_recovery
```

Replace the existing `failed_result` function body with:

```python
def failed_result(action: str | None, stage: str, error: str, index: int | None = None) -> dict[str, Any]:
    return structured_failed_result(action, stage, error, index)
```

- [ ] **Step 4: Add fuse state to `BrowserActionLayer`**

In `BrowserActionLayer.__init__`, change:

```python
def __init__(self) -> None:
    self._last_state: dict[str, Any] | None = None
```

to:

```python
def __init__(self) -> None:
    self._last_state: dict[str, Any] | None = None
    self._failure_fuse = FailureFuse()
```

- [ ] **Step 5: Reset fuse after successful state reads and successful actions**

In `get_state`, after `if state.get("status") == "success":`, add:

```python
self._failure_fuse.reset()
```

In `run_action`, after `result = dict(raw)` and `result.setdefault("tab_id", driver.default_session_id)`, add:

```python
if result.get("status") == "success":
    self._failure_fuse.reset()
else:
    result = add_recovery(result, action=action, index=safe_index)
```

- [ ] **Step 6: Route direct Python failures through the fuse**

Add a private helper method to `BrowserActionLayer`:

```python
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
    recorded = self._failure_fuse.record(result, tab_id=tab_id, url=url, target=target)
    recorded.setdefault("tab_id", tab_id)
    return recorded
```

Use `_record_failure` for direct returns after driver availability is confirmed, especially:

```python
return self._record_failure(
    failed_result(action, "state_missing", f"Run browser_state before browser_action {action}.", safe_index),
    driver=driver,
)
```

For stale tab:

```python
return self._record_failure(result, driver=driver)
```

For non-object JS result:

```python
return self._record_failure(result, driver=driver, target=cached_element if isinstance(cached_element, dict) else None)
```

- [ ] **Step 7: Run targeted action tests**

Run:

```powershell
python -m pytest tests/test_browser_actions.py::test_run_action_state_missing_includes_structured_recovery tests/test_browser_actions.py::test_run_action_stale_tab_includes_find_recovery tests/test_browser_actions.py::test_run_action_blocks_third_repeated_failure tests/test_ga_browser_use_results.py -q
```

Expected: PASS.

- [ ] **Step 8: Run broader browser action tests**

Run:

```powershell
python -m pytest tests/test_browser_actions.py tests/test_ga_browser_use_results.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit recovery integration**

Run:

```powershell
git add ga_browser_use/actions.py tests/test_browser_actions.py
git commit -m "feat: add browser action recovery fuse"
```

---

### Task 4: Add Deterministic `browser_find`

**Files:**
- Create: `ga_browser_use/finder.py`
- Create: `tests/test_ga_browser_use_finder.py`
- Modify: `ga.py`
- Modify: `tests/test_browser_tool_handlers.py`
- Modify: `assets/tools_schema.json`
- Modify: `assets/tools_schema_cn.json`
- Modify: `tests/test_browser_tool_schemas.py`

- [ ] **Step 1: Write finder unit tests**

Add `tests/test_ga_browser_use_finder.py`:

```python
from ga_browser_use.finder import find_in_state


def make_state(elements):
    return {"status": "success", "tab_id": "tab-1", "elements": elements}


def test_find_prefers_label_and_control_kind_over_generic_text():
    state = make_state(
        [
            {"index": 1, "text": "签字意见说明", "labels": [], "control_kind": "button", "visible": True, "disabled": False},
            {"index": 2, "text": "", "labels": ["签字意见"], "control_kind": "contenteditable", "visible": True, "disabled": False},
        ]
    )

    result = find_in_state(state, query="签字意见", control_kind="contenteditable", max_results=5)

    assert result["status"] == "success"
    assert result["ambiguous"] is False
    assert result["matches"][0]["index"] == 2
    assert "label" in result["matches"][0]["reason"]


def test_find_table_row_and_column_match_ranks_first():
    state = make_state(
        [
            {
                "index": 1,
                "text": "审批意见",
                "labels": [],
                "visible": True,
                "disabled": False,
                "table_context": {"row_text": "李四", "column_header": "审批意见"},
            },
            {
                "index": 2,
                "text": "",
                "labels": ["输入框"],
                "visible": True,
                "disabled": False,
                "table_context": {"row_text": "张三", "column_header": "审批意见"},
            },
        ]
    )

    result = find_in_state(state, table={"row_text": "张三", "column_text": "审批意见"}, max_results=5)

    assert result["matches"][0]["index"] == 2
    assert "table row" in result["matches"][0]["reason"]


def test_find_marks_near_tie_as_ambiguous():
    state = make_state(
        [
            {"index": 1, "text": "张三", "labels": [], "visible": True, "disabled": False},
            {"index": 2, "text": "张三", "labels": [], "visible": True, "disabled": False},
        ]
    )

    result = find_in_state(state, query="张三", max_results=5)

    assert result["status"] == "success"
    assert result["ambiguous"] is True
    assert [match["index"] for match in result["matches"][:2]] == [1, 2]


def test_find_returns_target_not_found_with_recovery():
    state = make_state([{"index": 1, "text": "保存", "labels": [], "visible": True, "disabled": False}])

    result = find_in_state(state, query="不存在", max_results=5)

    assert result["status"] == "failed"
    assert result["stage"] == "target_not_found"
    assert result["recovery"]["code"] == "refresh_state_then_find"
```

- [ ] **Step 2: Run finder tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_ga_browser_use_finder.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'ga_browser_use.finder'`.

- [ ] **Step 3: Implement `ga_browser_use/finder.py`**

Create `ga_browser_use/finder.py`:

```python
from __future__ import annotations

from typing import Any

from ga_browser_use.results import failed_result


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _contains(haystack: Any, needle: Any) -> bool:
    needle_text = _norm(needle)
    return bool(needle_text and needle_text in _norm(haystack))


def _text_parts(element: dict[str, Any]) -> list[str]:
    parts = [element.get("text"), element.get("value")]
    parts.extend(element.get("labels") or [])
    field_context = element.get("field_context") or {}
    parts.extend(field_context.get("labels") or [])
    parts.extend([field_context.get("nearby_text"), field_context.get("placeholder")])
    attrs = element.get("attributes") or {}
    parts.extend([attrs.get("aria-label"), attrs.get("title"), attrs.get("placeholder")])
    return [str(part) for part in parts if part]


def _table_value(table_context: dict[str, Any], *names: str) -> str:
    for name in names:
        value = table_context.get(name)
        if value:
            return str(value)
    return ""


def _score_element(
    element: dict[str, Any],
    *,
    query: str,
    role: str | None,
    control_kind: str | None,
    layer: str | None,
    frame_path: list[Any] | None,
    table: dict[str, Any] | None,
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    if role and _norm(element.get("role")) != _norm(role):
        return 0.0, []
    if control_kind and _norm(element.get("control_kind")) != _norm(control_kind):
        return 0.0, []
    if layer and _norm(element.get("layer")) != _norm(layer):
        return 0.0, []
    if frame_path is not None and element.get("frame_path") != frame_path:
        return 0.0, []
    if element.get("disabled") is True:
        return 0.0, []

    score = 0.0
    parts = _text_parts(element)
    labels = [str(label) for label in (element.get("labels") or [])]
    if query:
        if any(_norm(label) == _norm(query) for label in labels):
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

    table_context = element.get("table_context") or {}
    if table:
        row_text = table.get("row_text")
        column_text = table.get("column_text") or table.get("header_text")
        if row_text:
            row_value = _table_value(table_context, "row_text", "row_header")
            if not _contains(row_value, row_text):
                return 0.0, []
            score += 35
            reasons.append("table row")
        if column_text:
            column_value = _table_value(table_context, "column_header", "column_text", "header_text")
            if not _contains(column_value, column_text):
                return 0.0, []
            score += 35
            reasons.append("table column")

    if element.get("visible") is True:
        score += 10
        reasons.append("visible")
    if _norm(element.get("layer")) != "main":
        score += 5
        reasons.append("layer")
    if control_kind:
        score += 10
        reasons.append("control_kind")
    return score, reasons


def find_in_state(
    state: dict[str, Any],
    *,
    query: str | None = None,
    role: str | None = None,
    control_kind: str | None = None,
    layer: str | None = None,
    frame_path: list[Any] | None = None,
    table: dict[str, Any] | None = None,
    max_results: int = 5,
) -> dict[str, Any]:
    if not isinstance(state, dict) or state.get("status") != "success":
        return failed_result(None, "state_missing", "browser_find requires a successful browser_state.")
    query_text = str(query or "").strip()
    elements = state.get("elements") if isinstance(state.get("elements"), list) else []
    matches = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        score, reasons = _score_element(
            element,
            query=query_text,
            role=role,
            control_kind=control_kind,
            layer=layer,
            frame_path=frame_path,
            table=table,
        )
        if score <= 0:
            continue
        matches.append(
            {
                "index": element.get("index"),
                "score": round(score / 100, 3),
                "reason": "; ".join(reasons),
                "element": element,
            }
        )
    matches.sort(key=lambda item: item["score"], reverse=True)
    limit = max(1, min(int(max_results or 5), 20))
    matches = matches[:limit]
    if not matches:
        result = failed_result(None, "target_not_found", "No browser element matched the requested criteria.")
        result["recovery"]["code"] = "refresh_state_then_find"
        result["recovery"]["next_tool"] = "browser_find"
        result["recovery"]["next_args"] = {"refresh": True, "query": query_text, "max_results": limit}
        return result
    ambiguous = len(matches) > 1 and abs(matches[0]["score"] - matches[1]["score"]) <= 0.05
    return {"status": "success", "matches": matches, "ambiguous": ambiguous, "recovery": None}
```

- [ ] **Step 4: Run finder unit tests**

Run:

```powershell
python -m pytest tests/test_ga_browser_use_finder.py -q
```

Expected: PASS.

- [ ] **Step 5: Add `browser_find` wrapper and handler tests**

Append to `tests/test_browser_tool_handlers.py`:

```python
def test_browser_find_reuses_layer_state(monkeypatch):
    class FakeLayer:
        def find(self, driver, **kwargs):
            return {"status": "success", "matches": [{"index": 2}], "ambiguous": False}

    fake_driver = SimpleNamespace(default_session_id="9", get_all_sessions=lambda: [{"id": "9"}])
    monkeypatch.setattr(ga, "driver", fake_driver)
    monkeypatch.setattr(ga, "browser_action_layer", FakeLayer())

    result = ga.browser_find(query="签字意见", max_results=3)

    assert result["status"] == "success"
    assert result["matches"][0]["index"] == 2


def test_do_browser_find_formats_execution_output(monkeypatch):
    monkeypatch.setattr(
        ga,
        "browser_find",
        lambda **kwargs: {"status": "success", "matches": [{"index": 2, "reason": "label"}], "ambiguous": False},
    )
    handler = make_handler()

    chunks, outcome = run_generator(handler.do_browser_find({"query": "签字意见"}, SimpleNamespace(content="")))

    assert "Browser find result:" in "".join(chunks)
    assert json.loads(outcome.data)["matches"][0]["index"] == 2
```

- [ ] **Step 6: Add `BrowserActionLayer.find` and `ga.browser_find`**

In `ga_browser_use/actions.py`, import:

```python
from ga_browser_use.finder import find_in_state
```

In `BrowserActionLayer.get_state`, store the normalized state for finder reuse. Replace `_last_state = { ... }` with a dict that also stores `state` and `url`:

```python
self._last_state = {
    "tab_id": state["tab_id"],
    "state_token": state.get("state_token"),
    "elements_by_index": elements_by_index,
    "state": state,
    "url": state.get("url", ""),
}
```

Add this method to `BrowserActionLayer`:

```python
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
    if refresh or not self._last_state:
        state = self.get_state(
            driver,
            switch_tab_id=switch_tab_id,
            include_invisible=include_invisible,
            max_elements=max(120, max_results),
        )
    else:
        state = self._last_state.get("state") or {}
    return find_in_state(
        state,
        query=query,
        role=role,
        control_kind=control_kind,
        layer=layer,
        frame_path=frame_path,
        table=table,
        max_results=max_results,
    )
```

In `ga.py`, add:

```python
def browser_find(
    query=None,
    role=None,
    control_kind=None,
    layer=None,
    frame_path=None,
    table=None,
    max_results=5,
    refresh=False,
    include_invisible=False,
    switch_tab_id=None,
):
    """Find candidate indexed elements from the real Chrome browser state."""
    global driver
    try:
        if driver is None:
            first_init_driver()
        return browser_action_layer.find(
            driver,
            query=query,
            role=role,
            control_kind=control_kind,
            layer=layer,
            frame_path=frame_path,
            table=table,
            max_results=max_results,
            refresh=refresh,
            include_invisible=include_invisible,
            switch_tab_id=switch_tab_id,
        )
    except Exception as e:
        return {"status": "failed", "stage": "browser_unavailable", "error": format_error(e)}
```

In `GenericAgentHandler`, add:

```python
def do_browser_find(self, args, response):
    result = browser_find(
        query=args.get("query"),
        role=args.get("role"),
        control_kind=args.get("control_kind"),
        layer=args.get("layer"),
        frame_path=args.get("frame_path"),
        table=args.get("table"),
        max_results=args.get("max_results", 5),
        refresh=args.get("refresh", False),
        include_invisible=args.get("include_invisible", False),
        switch_tab_id=args.get("switch_tab_id") or args.get("tab_id"),
    )
    result_json = json.dumps(result, ensure_ascii=False, default=json_default)
    maxlen = 8000 // args.get('_tool_num', 1)
    formatted_result = smart_format(result_json, max_str_len=maxlen)
    yield f"Browser find result:\n{formatted_result}\n"
    outcome = StepOutcome(formatted_result, next_prompt="\n")
    outcome.result = formatted_result
    return outcome
```

- [ ] **Step 7: Add English and Chinese schema entries**

In `assets/tools_schema.json`, insert after `browser_state`:

```json
{"type": "function", "function": {
  "name": "browser_find",
  "description": "Read-only locator for indexed browser elements from the real Chrome page. Use after browser_state or when recovery asks for browser_find. Returns candidate indexes with score, reason, and ambiguity instead of acting.",
  "parameters": {"type": "object", "properties": {
    "query": {"type": "string", "description": "Target label/text/value to find"},
    "role": {"type": "string", "description": "Optional role hard filter"},
    "control_kind": {"type": "string", "description": "Optional control kind hard filter such as contenteditable, native_input, custom_select_trigger"},
    "layer": {"type": "string", "description": "Optional layer filter such as main, modal, drawer, popover"},
    "frame_path": {"type": "array", "items": {"type": "integer"}, "description": "Optional same-origin frame path filter"},
    "table": {"type": "object", "description": "Optional table locator with row_text and column_text"},
    "max_results": {"type": "integer", "description": "Maximum candidates to return", "default": 5},
    "refresh": {"type": "boolean", "description": "Refresh browser_state before finding", "default": false},
    "include_invisible": {"type": "boolean", "description": "Include invisible elements while refreshing state", "default": false},
    "switch_tab_id": {"type": "string", "description": "[Optional] Tab ID to switch to before finding"}}}
}},
```

In `assets/tools_schema_cn.json`, insert the equivalent:

```json
{"type": "function", "function": {
  "name": "browser_find",
  "description": "只读定位真实 Chrome 页面中的 indexed 元素。适合在 browser_state 后或 recovery 要求 browser_find 时使用。返回候选 index、评分、原因和是否歧义，不执行点击或输入。",
  "parameters": {"type": "object", "properties": {
    "query": {"type": "string", "description": "要查找的标签、文本或值"},
    "role": {"type": "string", "description": "可选 role 硬过滤"},
    "control_kind": {"type": "string", "description": "可选控件类型硬过滤，例如 contenteditable、native_input、custom_select_trigger"},
    "layer": {"type": "string", "description": "可选层级过滤，例如 main、modal、drawer、popover"},
    "frame_path": {"type": "array", "items": {"type": "integer"}, "description": "可选同源 iframe 路径过滤"},
    "table": {"type": "object", "description": "可选表格定位条件，包含 row_text 和 column_text"},
    "max_results": {"type": "integer", "description": "最多返回候选数量", "default": 5},
    "refresh": {"type": "boolean", "description": "查找前是否刷新 browser_state", "default": false},
    "include_invisible": {"type": "boolean", "description": "刷新 state 时是否包含不可见元素", "default": false},
    "switch_tab_id": {"type": "string", "description": "[可选] 查找前切换到指定标签页"}}}
}},
```

- [ ] **Step 8: Add schema tests**

In `tests/test_browser_tool_schemas.py`, update English and Chinese tests to fetch `browser_find`:

```python
find = tool_by_name(tools, "browser_find")
assert "read-only" in find["description"].lower()
assert "query" in find["parameters"]["properties"]
assert "refresh" in find["parameters"]["properties"]
assert find["parameters"]["properties"]["max_results"]["default"] == 5
```

For Chinese:

```python
find = tool_by_name(tools, "browser_find")
assert "只读定位" in find["description"]
assert "query" in find["parameters"]["properties"]
assert "refresh" in find["parameters"]["properties"]
assert find["parameters"]["properties"]["max_results"]["default"] == 5
```

- [ ] **Step 9: Run finder, handler, and schema tests**

Run:

```powershell
python -m pytest tests/test_ga_browser_use_finder.py tests/test_browser_tool_handlers.py tests/test_browser_tool_schemas.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit `browser_find`**

Run:

```powershell
git add ga.py ga_browser_use/actions.py ga_browser_use/finder.py assets/tools_schema.json assets/tools_schema_cn.json tests/test_ga_browser_use_finder.py tests/test_browser_tool_handlers.py tests/test_browser_tool_schemas.py
git commit -m "feat: add browser find locator"
```

---

### Task 5: Add Limited AntD And `ui-browser` Indexing Enhancements

**Files:**
- Modify: `ga_browser_use/indexer.py`
- Modify: `tests/test_browser_indexer.py`

- [ ] **Step 1: Write indexer boundary tests**

Append to `tests/test_browser_indexer.py`:

```python
def test_build_browser_state_script_includes_antd_picker_and_ui_browser_patterns():
    script = build_browser_state_script()

    assert ".ant-picker" in script
    assert ".ant-select-selector" in script
    assert ".ui-browser" in script


def test_browser_state_script_indexes_ui_browser_actionable_item_but_not_naked_icon():
    script = build_browser_state_script(max_elements=20)
    html = """
    <div class="ui-browser">
      <span class="ui-icon">decorative</span>
      <div class="ui-browser-item" tabindex="0">目标节点</div>
    </div>
    """

    result = run_browser_state_script(script, html)

    texts = [element["text"] for element in result["elements"]]
    assert "目标节点" in texts
    assert "decorative" not in texts
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_browser_indexer.py::test_build_browser_state_script_includes_antd_picker_and_ui_browser_patterns tests/test_browser_indexer.py::test_browser_state_script_indexes_ui_browser_actionable_item_but_not_naked_icon -q
```

Expected: FAIL because the script does not include all limited patterns.

- [ ] **Step 3: Extend `INTERACTIVE_SELECTOR` carefully**

In `ga_browser_use/indexer.py`, update `INTERACTIVE_SELECTOR` to include actionable containers:

```python
INTERACTIVE_SELECTOR = (
    'a[href], button, input, textarea, select, [role="button"], [role="link"], '
    '[role="textbox"], [role="checkbox"], [role="radio"], [role="combobox"], '
    '[role="listbox"], [role="option"], [aria-haspopup="listbox"], [role="menuitem"], [onclick], '
    '[tabindex], [contenteditable="true"], .ant-select-selector, .ant-picker, '
    '.ui-browser-item, .ui-browser [role="treeitem"], .ui-browser [role="menuitem"]'
)
```

- [ ] **Step 4: Keep decorative icon boundary**

In the JavaScript collection logic inside `ga_browser_use/indexer.py`, keep the existing selector-based candidate collection, but do not add `.ui-icon` or icon-font selectors. If a test exposes duplicate decorative children through a parent, update `textOf` or candidate filtering to prefer actionable ancestors and skip nodes with no action signal.

Add this helper inside the generated JS:

```javascript
const isDecorativeIconOnly = (element) => {
  const className = String(element.getAttribute("class") || "");
  const hasActionSignal = element.getAttribute("role") || element.getAttribute("tabindex") || element.getAttribute("onclick");
  return !hasActionSignal && /\b(ui-icon|anticon|iconfont)\b/.test(className);
};
```

Use it before pushing candidates:

```javascript
if (isDecorativeIconOnly(element)) {
  continue;
}
```

- [ ] **Step 5: Run indexer tests**

Run:

```powershell
python -m pytest tests/test_browser_indexer.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit indexing enhancement**

Run:

```powershell
git add ga_browser_use/indexer.py tests/test_browser_indexer.py
git commit -m "feat: improve browser component indexing"
```

---

### Task 6: Add Bounded Browser Recipes

**Files:**
- Create: `ga_browser_use/recipes.py`
- Create: `tests/test_ga_browser_use_recipes.py`
- Modify: `ga.py`
- Modify: `tests/test_browser_tool_handlers.py`
- Modify: `assets/tools_schema.json`
- Modify: `assets/tools_schema_cn.json`
- Modify: `tests/test_browser_tool_schemas.py`

- [ ] **Step 1: Write recipe tests**

Add `tests/test_ga_browser_use_recipes.py`:

```python
from ga_browser_use.recipes import BrowserRecipeRunner


class FakeLayer:
    def __init__(self):
        self.calls = []
        self.find_results = [
            {"status": "success", "matches": [{"index": 10, "score": 0.9, "element": {"index": 10}}], "ambiguous": False},
            {"status": "success", "matches": [{"index": 22, "score": 0.95, "element": {"index": 22}}], "ambiguous": False},
        ]

    def find(self, driver, **kwargs):
        self.calls.append(("find", kwargs))
        return self.find_results.pop(0)

    def run_action(self, driver, **kwargs):
        self.calls.append(("action", kwargs))
        return {"status": "success", "action": kwargs["action"], "index": kwargs.get("index")}

    def get_state(self, driver, **kwargs):
        self.calls.append(("state", kwargs))
        return {"status": "success", "elements": []}


def test_custom_select_recipe_runs_trigger_state_option_click():
    layer = FakeLayer()
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="custom_select", target={"query": "所属部门"}, option_text="研发部")

    assert result["status"] == "success"
    assert [call[0] for call in layer.calls] == ["find", "action", "state", "find", "action"]
    assert result["steps"][-1]["index"] == 22


def test_layer_select_refuses_ambiguous_option():
    layer = FakeLayer()
    layer.find_results = [
        {"status": "success", "matches": [{"index": 10, "element": {"index": 10}}], "ambiguous": False},
        {
            "status": "success",
            "matches": [{"index": 21, "element": {"index": 21}}, {"index": 22, "element": {"index": 22}}],
            "ambiguous": True,
        },
    ]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="layer_select", target={"query": "人员"}, option_text="张三")

    assert result["status"] == "failed"
    assert result["stage"] == "ambiguous_target"
    assert result["recovery"]["code"] == "use_layer_select_recipe"


def test_table_locate_returns_first_match_without_action():
    layer = FakeLayer()
    layer.find_results = [
        {"status": "success", "matches": [{"index": 7, "element": {"index": 7}}], "ambiguous": False}
    ]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="table_locate", table={"row_text": "张三", "column_text": "审批意见"})

    assert result["status"] == "success"
    assert result["matches"][0]["index"] == 7
    assert [call[0] for call in layer.calls] == ["find"]


def test_component_wait_returns_component_not_ready_on_timeout():
    layer = FakeLayer()
    layer.find_results = [{"status": "failed", "stage": "target_not_found", "recovery": {"code": "refresh_state_then_find"}}]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="component_wait", condition="options_visible", target={"query": "研发部"}, timeout=1)

    assert result["status"] == "failed"
    assert result["stage"] == "component_not_ready"
    assert result["recovery"]["code"] == "wait_component"
```

- [ ] **Step 2: Run recipe tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_ga_browser_use_recipes.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'ga_browser_use.recipes'`.

- [ ] **Step 3: Implement `ga_browser_use/recipes.py`**

Create `ga_browser_use/recipes.py`:

```python
from __future__ import annotations

from typing import Any

from ga_browser_use.results import failed_result


SUPPORTED_RECIPES = {"custom_select", "layer_select", "table_locate", "component_wait"}


class BrowserRecipeRunner:
    def __init__(self, layer: Any) -> None:
        self.layer = layer

    def _ambiguous(self, recipe: str, find_result: dict[str, Any]) -> dict[str, Any]:
        result = failed_result(None, "ambiguous_target", "Recipe target is ambiguous.")
        result["recipe"] = recipe
        result["candidates"] = find_result.get("matches", [])
        if recipe == "layer_select":
            result["recovery"]["code"] = "use_layer_select_recipe"
        elif recipe == "custom_select":
            result["recovery"]["code"] = "use_custom_select_recipe"
        return result

    def _find_one(self, driver: Any, *, recipe: str, target: dict[str, Any] | None = None, **kwargs: Any) -> tuple[dict[str, Any], dict[str, Any] | None]:
        target = target or {}
        if target.get("index"):
            return {"status": "success", "matches": [{"index": target["index"], "element": {"index": target["index"]}}], "ambiguous": False}, {"index": target["index"]}
        result = self.layer.find(driver, query=target.get("query") or kwargs.pop("query", None), max_results=kwargs.pop("max_results", 5), **kwargs)
        if result.get("status") != "success":
            return result, None
        if result.get("ambiguous"):
            return self._ambiguous(recipe, result), None
        matches = result.get("matches") or []
        return result, matches[0] if matches else None

    def _custom_select(self, driver: Any, *, target: dict[str, Any] | None, option_text: str, timeout: int, max_results: int) -> dict[str, Any]:
        steps = []
        trigger_find, trigger = self._find_one(driver, recipe="custom_select", target=target, max_results=max_results)
        steps.append({"tool": "browser_find", **trigger_find})
        if not trigger:
            trigger_find["steps"] = steps
            return trigger_find
        trigger_index = trigger["index"]
        click_trigger = self.layer.run_action(driver, action="click", index=trigger_index, timeout=timeout)
        steps.append({"tool": "browser_action", **click_trigger})
        if click_trigger.get("status") != "success":
            click_trigger["recipe"] = "custom_select"
            click_trigger["steps"] = steps
            return click_trigger
        state = self.layer.get_state(driver, max_elements=120)
        steps.append({"tool": "browser_state", "status": state.get("status")})
        option_find, option = self._find_one(
            driver,
            recipe="custom_select",
            target={"query": option_text},
            layer=None,
            max_results=max_results,
        )
        steps.append({"tool": "browser_find", **option_find})
        if not option:
            option_find["steps"] = steps
            return option_find
        option_index = option["index"]
        click_option = self.layer.run_action(driver, action="click", index=option_index, timeout=timeout)
        steps.append({"tool": "browser_action", **click_option})
        if click_option.get("status") != "success":
            click_option["recipe"] = "custom_select"
            click_option["steps"] = steps
            return click_option
        return {"status": "success", "recipe": "custom_select", "steps": steps, "recovery": None}

    def _layer_select(self, driver: Any, *, target: dict[str, Any] | None, option_text: str, confirm_text: str | None, timeout: int, max_results: int) -> dict[str, Any]:
        result = self._custom_select(driver, target=target, option_text=option_text, timeout=timeout, max_results=max_results)
        result["recipe"] = "layer_select"
        if result.get("status") != "success":
            result.setdefault("recovery", {}).update({"code": "use_layer_select_recipe"})
            return result
        if confirm_text:
            confirm_find, confirm = self._find_one(driver, recipe="layer_select", target={"query": confirm_text}, max_results=max_results)
            result["steps"].append({"tool": "browser_find", **confirm_find})
            if not confirm:
                confirm_find["recipe"] = "layer_select"
                confirm_find["steps"] = result["steps"]
                return confirm_find
            confirm_click = self.layer.run_action(driver, action="click", index=confirm["index"], timeout=timeout)
            result["steps"].append({"tool": "browser_action", **confirm_click})
            if confirm_click.get("status") != "success":
                confirm_click["recipe"] = "layer_select"
                confirm_click["steps"] = result["steps"]
                return confirm_click
        return result

    def _table_locate(self, driver: Any, *, table: dict[str, Any] | None, max_results: int) -> dict[str, Any]:
        result = self.layer.find(driver, table=table or {}, max_results=max_results)
        if result.get("status") == "success":
            result["recipe"] = "table_locate"
        return result

    def _component_wait(self, driver: Any, *, condition: str, target: dict[str, Any] | None, timeout: int, max_results: int) -> dict[str, Any]:
        find_result, match = self._find_one(driver, recipe="component_wait", target=target, max_results=max_results)
        if match:
            return {"status": "success", "recipe": "component_wait", "condition": condition, "match": match, "recovery": None}
        result = failed_result(None, "component_not_ready", f"Timed out waiting for component condition: {condition}")
        result["recipe"] = "component_wait"
        result["recovery"]["code"] = "wait_component"
        result["recovery"]["next_tool"] = "browser_recipe"
        result["recovery"]["next_args"] = {"recipe": "component_wait", "condition": condition, "timeout": timeout}
        result["last_find"] = find_result
        return result

    def run(
        self,
        driver: Any,
        *,
        recipe: str,
        target: dict[str, Any] | None = None,
        option_text: str | None = None,
        confirm_text: str | None = None,
        table: dict[str, Any] | None = None,
        condition: str | None = None,
        timeout: int = 10,
        max_results: int = 5,
        **_: Any,
    ) -> dict[str, Any]:
        recipe = str(recipe or "").strip()
        if recipe not in SUPPORTED_RECIPES:
            return failed_result(None, "invalid_args", f"Unsupported browser recipe: {recipe}")
        if recipe == "custom_select":
            if not option_text:
                return failed_result(None, "invalid_args", "option_text is required for custom_select.")
            return self._custom_select(driver, target=target, option_text=option_text, timeout=timeout, max_results=max_results)
        if recipe == "layer_select":
            if not option_text:
                return failed_result(None, "invalid_args", "option_text is required for layer_select.")
            return self._layer_select(driver, target=target, option_text=option_text, confirm_text=confirm_text, timeout=timeout, max_results=max_results)
        if recipe == "table_locate":
            return self._table_locate(driver, table=table, max_results=max_results)
        return self._component_wait(driver, condition=condition or "", target=target, timeout=timeout, max_results=max_results)
```

- [ ] **Step 4: Run recipe unit tests**

Run:

```powershell
python -m pytest tests/test_ga_browser_use_recipes.py -q
```

Expected: PASS.

- [ ] **Step 5: Add `browser_recipe` wrapper and handler tests**

Append to `tests/test_browser_tool_handlers.py`:

```python
def test_browser_recipe_uses_recipe_runner(monkeypatch):
    class FakeLayer:
        pass

    class FakeRunner:
        def __init__(self, layer):
            self.layer = layer

        def run(self, driver, **kwargs):
            return {"status": "success", "recipe": kwargs["recipe"], "steps": []}

    fake_driver = SimpleNamespace(default_session_id="9", get_all_sessions=lambda: [{"id": "9"}])
    monkeypatch.setattr(ga, "driver", fake_driver)
    monkeypatch.setattr(ga, "browser_action_layer", FakeLayer())
    monkeypatch.setattr(ga, "BrowserRecipeRunner", FakeRunner)

    result = ga.browser_recipe(recipe="custom_select", option_text="研发部")

    assert result["status"] == "success"
    assert result["recipe"] == "custom_select"


def test_do_browser_recipe_formats_execution_output(monkeypatch):
    monkeypatch.setattr(
        ga,
        "browser_recipe",
        lambda **kwargs: {"status": "success", "recipe": kwargs["recipe"], "steps": []},
    )
    handler = make_handler()

    chunks, outcome = run_generator(handler.do_browser_recipe({"recipe": "table_locate"}, SimpleNamespace(content="")))

    assert "Browser recipe result:" in "".join(chunks)
    assert json.loads(outcome.data)["recipe"] == "table_locate"
```

- [ ] **Step 6: Add `browser_recipe` wrapper and handler**

In `ga.py`, import:

```python
from ga_browser_use.recipes import BrowserRecipeRunner
```

Add:

```python
def browser_recipe(
    recipe,
    target=None,
    option_text=None,
    confirm_text=None,
    table=None,
    condition=None,
    verify=True,
    timeout=10,
    max_results=5,
    switch_tab_id=None,
):
    """Run a bounded browser recipe against the real Chrome browser state."""
    global driver
    try:
        if driver is None:
            first_init_driver()
        if switch_tab_id:
            driver.default_session_id = switch_tab_id
        runner = BrowserRecipeRunner(browser_action_layer)
        return runner.run(
            driver,
            recipe=recipe,
            target=target,
            option_text=option_text,
            confirm_text=confirm_text,
            table=table,
            condition=condition,
            verify=verify,
            timeout=timeout,
            max_results=max_results,
        )
    except Exception as e:
        return {"status": "failed", "stage": "browser_unavailable", "error": format_error(e)}
```

In `GenericAgentHandler`, add:

```python
def do_browser_recipe(self, args, response):
    result = browser_recipe(
        recipe=args.get("recipe"),
        target=args.get("target"),
        option_text=args.get("option_text"),
        confirm_text=args.get("confirm_text"),
        table=args.get("table"),
        condition=args.get("condition"),
        verify=args.get("verify", True),
        timeout=args.get("timeout", 10),
        max_results=args.get("max_results", 5),
        switch_tab_id=args.get("switch_tab_id") or args.get("tab_id"),
    )
    result_json = json.dumps(result, ensure_ascii=False, default=json_default)
    maxlen = 8000 // args.get('_tool_num', 1)
    formatted_result = smart_format(result_json, max_str_len=maxlen)
    yield f"Browser recipe result:\n{formatted_result}\n"
    outcome = StepOutcome(formatted_result, next_prompt="\n")
    outcome.result = formatted_result
    return outcome
```

- [ ] **Step 7: Add schemas and schema tests**

In `assets/tools_schema.json`, insert after `browser_find`:

```json
{"type": "function", "function": {
  "name": "browser_recipe",
  "description": "Run a bounded browser operation recipe in the real Chrome page. Recipes are deterministic and fail closed on ambiguity. Use for custom_select, layer_select, table_locate, and component_wait.",
  "parameters": {"type": "object", "properties": {
    "recipe": {"type": "string", "enum": ["custom_select", "layer_select", "table_locate", "component_wait"], "description": "Recipe to run"},
    "target": {"type": "object", "description": "Target locator, usually index or query"},
    "option_text": {"type": "string", "description": "Option text for custom_select or layer_select"},
    "confirm_text": {"type": "string", "description": "Explicit confirm button text for layer_select"},
    "table": {"type": "object", "description": "Table locator such as row_text and column_text for table_locate"},
    "condition": {"type": "string", "enum": ["layer_open", "layer_closed", "options_visible", "field_value", "element_enabled", "not_busy"], "description": "Component wait condition"},
    "verify": {"type": "boolean", "description": "Whether the recipe should verify the expected state when supported", "default": true},
    "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 10},
    "max_results": {"type": "integer", "description": "Maximum finder candidates per step", "default": 5},
    "switch_tab_id": {"type": "string", "description": "[Optional] Tab ID to switch to before running recipe"}}}
}},
```

In `assets/tools_schema_cn.json`, insert:

```json
{"type": "function", "function": {
  "name": "browser_recipe",
  "description": "在真实 Chrome 页面运行有边界的浏览器操作编排。recipe 是确定性的，遇到歧义会失败并返回候选。用于 custom_select、layer_select、table_locate、component_wait。",
  "parameters": {"type": "object", "properties": {
    "recipe": {"type": "string", "enum": ["custom_select", "layer_select", "table_locate", "component_wait"], "description": "要运行的 recipe"},
    "target": {"type": "object", "description": "目标定位条件，通常包含 index 或 query"},
    "option_text": {"type": "string", "description": "custom_select 或 layer_select 的选项文本"},
    "confirm_text": {"type": "string", "description": "layer_select 中显式确认按钮文本"},
    "table": {"type": "object", "description": "table_locate 的表格定位条件，例如 row_text 和 column_text"},
    "condition": {"type": "string", "enum": ["layer_open", "layer_closed", "options_visible", "field_value", "element_enabled", "not_busy"], "description": "组件等待条件"},
    "verify": {"type": "boolean", "description": "recipe 支持时是否验证结果", "default": true},
    "timeout": {"type": "integer", "description": "超时时间，单位秒", "default": 10},
    "max_results": {"type": "integer", "description": "每步 finder 最多返回候选数", "default": 5},
    "switch_tab_id": {"type": "string", "description": "[可选] 执行 recipe 前切换标签页"}}}
}},
```

In `tests/test_browser_tool_schemas.py`, add assertions:

```python
recipe = tool_by_name(tools, "browser_recipe")
assert recipe["parameters"]["properties"]["recipe"]["enum"] == [
    "custom_select",
    "layer_select",
    "table_locate",
    "component_wait",
]
assert recipe["parameters"]["properties"]["timeout"]["default"] == 10
assert recipe["parameters"]["properties"]["max_results"]["default"] == 5
```

- [ ] **Step 8: Run recipe, handler, and schema tests**

Run:

```powershell
python -m pytest tests/test_ga_browser_use_recipes.py tests/test_browser_tool_handlers.py tests/test_browser_tool_schemas.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit recipes**

Run:

```powershell
git add ga.py ga_browser_use/recipes.py assets/tools_schema.json assets/tools_schema_cn.json tests/test_ga_browser_use_recipes.py tests/test_browser_tool_handlers.py tests/test_browser_tool_schemas.py
git commit -m "feat: add bounded browser recipes"
```

---

### Task 7: Update Browser-Use SOP

**Files:**
- Modify: `memory/browser-use_sop.md`

- [ ] **Step 1: Add SOP sections for finder, recovery, and recipes**

In `memory/browser-use_sop.md`, add a section near the tool overview:

```markdown
### browser_find

用途：只读定位当前真实 Chrome 页面中的 indexed 元素。它不会点击、输入、选择或按键，只返回候选 index、评分、原因和是否歧义。

优先使用场景：

- `browser_action` 返回 `recovery.next_tool="browser_find"`。
- `browser_state` 输出太长，需要按 label、field、table、layer、frame 缩小目标。
- 旧 index 失效后，需要刷新并重新定位目标。
- 表格、弹层、AntD 选项存在多个相似文本，需要先判断候选。

规则：

- `ambiguous=true` 时不要直接选第一个，先用更具体的 query、table、layer 或 frame_path 缩小范围。
- `status=failed` 且 `stage=target_not_found` 时，按 `recovery` 决定是否 refresh 或转低层工具。
```

Add recipe guidance:

```markdown
### browser_recipe

用途：运行有边界的常见组件操作编排。它不是自动浏览器代理，只支持固定 recipe。

支持：

- `custom_select`：AntD/React 自定义下拉，走 trigger -> state -> option -> click。
- `layer_select`：弹窗、抽屉、popover 中选择人员/项目/文档等通用选择流程。
- `table_locate`：按 row_text + column_text 定位表格中的 indexed 目标。
- `component_wait`：等待 layer/options/field/enabled/not_busy 等组件条件。

规则：

- recipe 返回 `ambiguous_target` 时不要强行点击，必须补充更具体条件。
- recipe 返回的 `steps` 是诊断依据，失败后先读最后一个失败 step。
- `table_locate` 只定位，不做通用表格编辑。
- 跨域 iframe、文件上传、截图、CDP 坐标、私有组件 API 仍走 `tmwebdriver_sop`。
```

Add recovery usage:

```markdown
### recovery 字段优先级

失败结果里如果有 `recovery`，优先按它执行，不要自己猜。

- `recovery.next_tool` 指定下一步工具。
- `recovery.next_args` 给出下一步参数骨架。
- `recovery.stop_retry=true` 时停止重复同一个动作。
- `stage=repeat_blocked` 表示工具已阻止重复撞墙，必须换定位、recipe 或低层路径。
```

- [ ] **Step 2: Search SOP for outdated two-tool-only wording**

Run:

```powershell
Select-String -Path .\memory\browser-use_sop.md -Pattern '两个|2个|browser_state.*browser_action|只支持' -CaseSensitive:$false
```

Expected: Review results and update wording so SOP acknowledges `browser_find` and `browser_recipe` without overstating capability.

- [ ] **Step 3: Run doc grep verification**

Run:

```powershell
Select-String -Path .\memory\browser-use_sop.md -Pattern 'browser_find|browser_recipe|recovery|repeat_blocked|custom_select|layer_select|table_locate|component_wait'
```

Expected: Output contains all listed terms.

- [ ] **Step 4: Commit SOP**

Run:

```powershell
git add memory/browser-use_sop.md
git commit -m "docs: update browser use sop for phase 3"
```

---

### Task 8: Final Verification And Review Prep

**Files:**
- No new files unless verification exposes defects in Phase 3 files.

- [ ] **Step 1: Run targeted browser-tool verification**

Run:

```powershell
python -m pytest tests/test_browser_indexer.py tests/test_browser_actions.py tests/test_browser_tool_handlers.py tests/test_browser_tool_schemas.py tests/test_ga_browser_use_package.py tests/test_ga_browser_use_results.py tests/test_ga_browser_use_finder.py tests/test_ga_browser_use_recipes.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run:

```powershell
python -m pytest tests -q
```

Expected: PASS, or only pre-existing unrelated `simple_http_server` import errors. If unrelated errors remain, record exact error count and do not fix them in this phase.

- [ ] **Step 3: Inspect changed files**

Run:

```powershell
git status --short --branch
git log --oneline -8
```

Expected: branch is `ga-browser-use`; working tree is clean after commits; recent commits correspond to Phase 3 tasks.

- [ ] **Step 4: Request code review**

Invoke `superpowers:requesting-code-review` for this Phase 3 range.

Review scope:

- `ga_browser_use/`
- `browser_actions.py`
- `browser_indexer.py`
- `ga.py`
- `assets/tools_schema.json`
- `assets/tools_schema_cn.json`
- `memory/browser-use_sop.md`
- New and modified browser tests

Review prompt:

```text
Review Phase 3 GA browser-use integration. Focus on recovery/fuse correctness, browser_find ranking ambiguity, browser_recipe boundedness, backwards compatibility of browser_state/browser_action, schema-handler consistency, and whether the new ga_browser_use package introduces import or circular dependency risks.
```

- [ ] **Step 5: Fix review findings with TDD**

For each review finding:

1. Write or adjust a failing test that captures the issue.
2. Run the specific test and confirm it fails.
3. Implement the smallest fix.
4. Run the specific test and targeted browser-tool verification.
5. Commit with a focused message.

- [ ] **Step 6: Final status report**

Report:

- Commit range.
- Targeted verification result.
- Full-suite result and unrelated failures if present.
- Public tool changes: `browser_find`, `browser_recipe`.
- Boundary reminders: no separate browser-use runtime, no external repo changes, no automatic Chrome launch.
