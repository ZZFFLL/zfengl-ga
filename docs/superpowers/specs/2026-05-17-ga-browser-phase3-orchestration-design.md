# GA Browser Phase 3 Orchestration Design

## Goal

Phase 3 strengthens GA's browser-use inspired high-level browser tools by adding an anti-dead-end orchestration layer and common component adapters.

The goal is not to make GA "handle every web page". The goal is to reduce repeated failed tool calls on common enterprise web UI patterns while preserving GA's current first-person browser model.

## Hard Constraints

- GA only operates the user's already-open Chrome session through the existing TMWebDriver / Chrome extension bridge.
- GA does not start Chrome automatically.
- GA does not create a new browser profile, browser workspace, browser-use runtime session, or cloud browser.
- GA does not copy, import, or migrate login state.
- GA does not modify `E:\zfengl-ai-project\browser-use`.
- Browser-use remains an implementation reference, not a runtime dependency for browser lifecycle.
- Existing `browser_state` and `browser_action` behavior remains backward compatible.
- New capabilities must fail closed when target selection is ambiguous.
- New capabilities must stay page-operation oriented, not OA business-process oriented.

## Current Baseline

The current implementation has two large root modules:

- `browser_indexer.py`: builds the indexed browser state, including same-origin iframe traversal and rich metadata such as labels, field context, table context, layer context, control kind, and action hints.
- `browser_actions.py`: executes indexed actions, wait actions, verification, state-token checks, same-origin frame targeting, and current failure shaping.

The current exposed high-level tools are:

- `browser_state`: read indexed state from the current real Chrome tab.
- `browser_action`: execute bounded actions against the latest indexed state.

The current implementation already covers:

- Indexed `click`, `input`, `select`, `keys`.
- Waits: `wait_index`, `wait_text`, `wait_selector`, `wait_dom_stable`, `wait_not_busy`, `wait_enabled`, `wait_route`.
- Same-origin iframe indexing and frame-aware action execution.
- Contenteditable and same-origin designMode iframe body input basics.
- Read-only table metadata.
- Verification for mutating actions.

The main remaining problem is not raw browser reach. The main problem is orchestration: when an index becomes stale, a custom component rejects direct input, or an overlay changes the DOM, GA needs a smaller and clearer next-step path instead of repeatedly trying the same failing action.

## Design Direction

Phase 3 introduces a dedicated package for the GA browser-use integration:

```text
ga_browser_use/
  __init__.py
  actions.py
  indexer.py
  results.py
  finder.py
  recipes.py
```

The package becomes the home for browser-use inspired high-level browser capability. Root-level `browser_actions.py` and `browser_indexer.py` should remain as compatibility shims during Phase 3 so existing imports and tests keep working.

This gives GA a clean engineering boundary without forcing a risky one-shot rewrite.

## Package Responsibilities

### `ga_browser_use.indexer`

Owns browser state generation and normalization.

Initial migration target:

- Move the current `build_browser_state_script` and `normalize_state_result` implementation here without behavior change.
- Keep root `browser_indexer.py` as a compatibility import shim.

Phase 3 enhancement scope:

- Add limited AntD and `ui-browser` component indexing patterns.
- Preserve the existing boundary that naked visual icons are not automatically treated as actionable targets.
- Prefer indexing the actionable trigger/container/option over indexing decorative children.

### `ga_browser_use.actions`

Owns action execution and state caching.

Initial migration target:

- Move the current `BrowserActionLayer`, `build_browser_action_script`, supported action constants, and argument sanitizers here without behavior change.
- Keep root `browser_actions.py` as a compatibility import shim.

Phase 3 enhancement scope:

- Attach structured `recovery` guidance to failures.
- Add repeated-failure fuse logic.
- Call `ga_browser_use.results` for standardized failures.
- Use `ga_browser_use.recipes` only for recovery suggestions, not for hidden broad automation inside ordinary `browser_action`.

### `ga_browser_use.results`

Owns structured tool result helpers.

Responsibilities:

- Build consistent failure results.
- Attach a structured `recovery` object.
- Normalize old `hint` and `suggested_args` fields into backward-compatible recovery guidance.
- Track repeated failures in a small in-memory fuse owned by `BrowserActionLayer`.

Failure result shape:

```json
{
  "status": "failed",
  "stage": "stale_index",
  "error": "Run browser_state before browser_action for the current tab.",
  "action": "click",
  "index": 12,
  "recovery": {
    "code": "refresh_state_then_find",
    "message": "The cached index is stale. Refresh state and locate the target again before retrying.",
    "next_tool": "browser_find",
    "next_args": {
      "query": "original target text if known",
      "max_results": 5,
      "refresh": true
    },
    "stop_retry": true
  }
}
```

The old fields `hint` and `suggested_args` may remain for compatibility, but new code and SOP should teach GA to prefer `recovery`.

### `ga_browser_use.finder`

Owns deterministic candidate search over normalized `browser_state`.

This is inspired by browser-use's `find_elements` and selector-map ideas, but adapted to GA's existing state snapshot model.

`browser_find` is read-only:

- It can reuse the latest cached `browser_state`.
- It can refresh state when `refresh=true`.
- It never clicks, inputs, selects, or presses keys.
- It returns candidate indexed elements with score and reason.
- It marks ambiguous matches instead of choosing silently.

Initial public arguments:

```json
{
  "query": "签字意见",
  "role": "textbox",
  "control_kind": "contenteditable",
  "layer": "main",
  "frame_path": [0],
  "table": {
    "row_text": "张三",
    "column_text": "审批意见"
  },
  "max_results": 5,
  "refresh": false,
  "include_invisible": false
}
```

Return shape:

```json
{
  "status": "success",
  "matches": [
    {
      "index": 38,
      "score": 0.92,
      "reason": "label and control_kind matched; table column matched",
      "element": {
        "index": 38,
        "role": "textbox",
        "control_kind": "contenteditable",
        "text": "",
        "labels": ["签字意见"],
        "frame_path": [0],
        "table_context": {}
      }
    }
  ],
  "ambiguous": false,
  "recovery": null
}
```

Ranking rules:

- Exact label / field-context match ranks highest.
- Exact table row and column match ranks above generic text match.
- Control-kind / role / layer / frame filters are hard filters when provided.
- Visible enabled controls rank above hidden or disabled controls.
- Overlay/layer matches rank above main-page matches when the query indicates option selection and an overlay is visible.
- If top candidates are too close, return `ambiguous=true` with candidates and no suggested action.

### `ga_browser_use.recipes`

Owns bounded deterministic recipes for common component operation.

This is a formal Phase 3 capability, not an optional future idea.

The recipe layer exists because some common UI flows require a short sequence, and asking the model to manually stitch `browser_state -> browser_action -> browser_state -> browser_action -> verify` is where the current chain breaks.

Initial recipes:

1. `custom_select`

   Use for AntD / React-style custom selects and search selects.

   Flow:

   - Locate trigger by index or `browser_find` query.
   - Click trigger.
   - Refresh state.
   - Locate option in visible overlay/layer by option text.
   - Click option.
   - Verify selected text or field value if a verification target is available.

   Fail-closed rules:

   - If multiple triggers match, return candidates.
   - If multiple options match with similar score, return candidates.
   - If no visible overlay appears after trigger click, return recovery that suggests `wait_dom_stable`, `wait_not_busy`, or low-level inspection.

2. `layer_select`

   Use for modal/drawer/popover selection flows such as choosing a person, project, document, or menu item.

   Flow:

   - Open layer when an opener is provided.
   - Refresh state.
   - Restrict search to `layer != "main"` when a layer is visible.
   - Locate option by text or field filters.
   - Click option.
   - Optionally click a confirm button when explicitly requested.
   - Verify that the layer closed or that the target field was backfilled.

   Fail-closed rules:

   - Do not click a confirm button unless `confirm_text` or `confirm_index` is explicitly supplied.
   - Do not choose among duplicate names without a disambiguating label, row text, or secondary text.

3. `table_locate`

   Use for locating elements or cells inside native tables and role-based grids.

   Flow:

   - Use current `table_context`.
   - Match by `row_text`, `column_text`, `header_text`, and optional control type.
   - Return the target indexed element and table coordinates.

   Boundary:

   - This recipe locates table targets.
   - It does not implement generic spreadsheet-like editing or virtualized-grid paging.

4. `component_wait`

   Use for common component-level waits that are more precise than page-level `wait_dom_stable`.

   Supported conditions:

   - `layer_open`
   - `layer_closed`
   - `options_visible`
   - `field_value`
   - `element_enabled`
   - `not_busy`

   Boundary:

   - This is still bounded polling over state and existing wait primitives.
   - It is not a network-idle detector and not a business-success guarantee.

Recipe return shape:

```json
{
  "status": "success",
  "recipe": "custom_select",
  "steps": [
    {"tool": "browser_find", "status": "success", "selected_index": 12},
    {"tool": "browser_action", "action": "click", "status": "success", "index": 12},
    {"tool": "browser_find", "status": "success", "selected_index": 31},
    {"tool": "browser_action", "action": "click", "status": "success", "index": 31}
  ],
  "verification": {
    "status": "success",
    "type": "field_value",
    "value": "研发部"
  },
  "recovery": null
}
```

Implementation note:

- Recipes are exposed through one public tool: `browser_recipe`.
- `browser_recipe` must stay enum-based and bounded. It must not become a free-form autonomous browser agent.
- `browser_action` failures can still suggest a recipe through `recovery.next_tool="browser_recipe"`.

## Public Tool Contract

### Existing: `browser_state`

No user-facing breaking change.

Expected Phase 3 additions:

- More component-aware metadata for AntD / `ui-browser` patterns.
- Metadata remains optional and has stable defaults.

### Existing: `browser_action`

No action-name breaking change.

Expected Phase 3 additions:

- Failure results include `recovery`.
- Repeated identical failures can return `stage=repeat_blocked`.
- Successful mutating actions may include `next_recommended_tool="browser_state"` when the page likely changed.

### New: `browser_find`

Read-only candidate locator.

This should become GA's preferred step after:

- A stale index.
- A state refresh.
- A table/field/overlay target needs semantic narrowing.
- A custom component exposes too many similarly named elements.

### New: `browser_recipe`

Bounded deterministic recipe runner.

Initial recipes:

- `custom_select`
- `layer_select`
- `table_locate`
- `component_wait`

Initial public arguments:

```json
{
  "recipe": "custom_select",
  "target": {
    "index": 12,
    "query": "所属部门"
  },
  "option_text": "研发部",
  "confirm_text": "",
  "verify": true,
  "timeout": 10,
  "max_results": 5
}
```

Rules:

- `recipe` is required and must be one of the supported enum values.
- `target.index` is preferred when GA already has a recent state.
- `target.query` is used through `browser_find` when index is missing or stale.
- `option_text` is required for `custom_select` and `layer_select`.
- `confirm_text` is only used by `layer_select`.
- `table_locate` uses `table.row_text` and `table.column_text` instead of `option_text`.
- Every result returns internal `steps` so GA and the user can inspect what happened.
- Ambiguous recipes return `status=failed`, `stage=ambiguous_target`, candidates, and recovery; they do not choose silently.

## Recovery And Fuse Design

The current failure model tells GA what went wrong, but not consistently what to do next.

Phase 3 standardizes recovery.

Recovery codes:

- `refresh_state`: call `browser_state` before retrying an indexed action.
- `refresh_state_then_find`: call `browser_find(refresh=true)` to relocate the target.
- `use_focused_keys`: retry `keys` without index after successful input.
- `use_custom_select_recipe`: use the custom select recipe instead of native `select`.
- `use_layer_select_recipe`: use the layer selection recipe.
- `use_table_locate`: locate table target by row and column before action.
- `wait_component`: wait for layer/options/enabled/not-busy condition.
- `fallback_low_level`: use `tmwebdriver_sop` / `web_execute_js` for CDP, screenshot, cross-origin iframe, file upload, or component-private API.
- `stop_repeating`: stop retrying the same action against the same target.

Fuse signature:

```text
tab_id + url + action + index + stage + stable_key + selector_hint + normalized_text_or_value
```

Fuse behavior:

- First failure: return normal failure plus recovery.
- Second same-signature failure: return normal failure plus stronger `stop_retry=true`.
- Third same-signature failure: return `stage=repeat_blocked` and do not execute the action.
- Fuse resets on successful `browser_state`, successful action, tab switch, or materially different target signature.

The fuse must be conservative. It should block obvious repeated wall-hitting, not prevent legitimate retries after the page changes.

## AntD And `ui-browser` Indexing Boundary

Phase 3 should not index every framework DOM node.

Allowed additions:

- AntD select trigger/container when it behaves like a combobox or opens a listbox.
- AntD dropdown/menu/listbox options when visible.
- AntD picker trigger/input when it is an actual field target.
- `ui-browser` tree/menu/list entries when they are visibly actionable through role, tabindex, onclick, cursor pointer, or known item classes.

Rejected additions:

- Naked `.ui-icon` or icon-font elements without an actionable ancestor.
- Hidden overlay options outside the visible frame chain.
- Disabled options.
- Decorative spans inside buttons when the button ancestor is already indexed.

The purpose is to improve target discovery without making indexes noisy and unstable.

## Table And Field Location Boundary

Phase 3 table work should remain a locator capability.

Supported:

- Native `<table>`.
- Basic role-based grids using `role=grid`, `role=table`, `role=row`, `role=cell`, and `role=columnheader`.
- Matching by visible row text and column/header text.
- Returning candidate indexed controls inside the matched cell.

Not supported in this phase:

- Virtualized table paging.
- Infinite scroll table search.
- Spreadsheet-style keyboard navigation.
- Generic cell editing wrapper for every grid library.

If a matched cell contains an input, textarea, select, contenteditable, button, or actionable custom trigger, GA can then use `browser_action` or a recipe on that returned index.

## Error Classification

Existing failure stages remain valid.

Phase 3 may add:

- `repeat_blocked`: repeated identical failure was blocked before executing another action.
- `ambiguous_target`: finder or recipe found multiple viable targets.
- `target_not_found`: finder or recipe could not locate a target after state refresh.
- `recipe_failed`: recipe failed after one or more internal steps; step details are returned.
- `component_not_ready`: component-level wait timed out.

All new stages must include `recovery`.

## SOP Updates

`memory/browser-use_sop.md` should be updated after implementation.

New SOP guidance:

- Prefer `browser_find` after state refresh instead of manually scanning long `browser_state` output.
- Use `recovery.next_tool` and `recovery.next_args` instead of guessing the next action.
- Stop repeating when `recovery.stop_retry=true`.
- Use `custom_select` recipe for AntD/React select-like controls.
- Use `layer_select` recipe for modal/drawer/popover selection.
- Use `table_locate` before operating table cells.
- Use component waits for overlays/options/field backfill instead of blind repeated state/action calls.

The SOP must continue to state that cross-origin iframe, file upload, screenshot diagnosis, CDP-level coordinates, and component-private APIs remain low-level `tmwebdriver_sop` territory.

## Testing Strategy

Targeted tests should be added before implementation code.

Test files:

- `tests/test_ga_browser_use_results.py`
- `tests/test_ga_browser_use_finder.py`
- `tests/test_ga_browser_use_recipes.py`
- Existing `tests/test_browser_actions.py`
- Existing `tests/test_browser_indexer.py`
- Existing `tests/test_browser_tool_handlers.py`
- Existing `tests/test_browser_tool_schemas.py`

Required test coverage:

- `recovery` is added to stale index, state missing, custom select misuse, verification failure, and DOM event failures.
- Fuse blocks repeated identical failures but resets after successful state refresh.
- `browser_find` ranks label/field-context/table-context matches above generic text matches.
- `browser_find` returns `ambiguous=true` for near-tie candidates and does not choose silently.
- AntD trigger and visible option indexing improves while naked icon indexing stays rejected.
- `ui-browser` actionable item indexing works only when there is an actionable signal.
- `table_locate` finds row/column targets from current `table_context`.
- `custom_select` recipe performs the bounded trigger-state-option-click sequence with fake browser layer calls.
- `layer_select` refuses ambiguous duplicate options.
- `component_wait` times out with `component_not_ready` and recovery.
- Tool schemas expose new public tools only after handlers are implemented.
- Existing browser tool tests still pass.

Verification command for the browser tool scope:

```powershell
python -m pytest tests/test_browser_indexer.py tests/test_browser_actions.py tests/test_browser_tool_handlers.py tests/test_browser_tool_schemas.py tests/test_ga_browser_use_results.py tests/test_ga_browser_use_finder.py tests/test_ga_browser_use_recipes.py -q
```

Full-suite verification remains useful, but current unrelated environment failures such as missing `simple_http_server` should not be fixed as part of this phase unless the user asks.

## Implementation Milestones

1. Create `ga_browser_use/` package and compatibility shims.
2. Move current action and indexer implementations into the package without behavior changes.
3. Add `results.py` and recovery/fuse tests.
4. Add `finder.py`, `browser_find` handler, schema, and tests.
5. Add limited AntD / `ui-browser` indexing enhancements and tests.
6. Add `recipes.py` with `custom_select`, `layer_select`, `table_locate`, and `component_wait` tests.
7. Expose `browser_recipe` handler and schema after recipe unit tests pass.
8. Update SOP after implementation behavior is proven by tests.

## Success Criteria

- GA can recover from stale-index and state-missing failures using structured `recovery` instead of repeatedly retrying the same call.
- GA can ask `browser_find` for a small candidate list instead of manually searching a large state dump.
- Common AntD/custom select and visible overlay options are easier to target.
- Table row/column targets can be located deterministically from existing state metadata.
- `browser_recipe` reduces the number of manual tool calls for custom select and layer selection without hiding ambiguity.
- Existing `browser_state` and `browser_action` contracts remain backward compatible.
- The browser-use integration has a clear package boundary under `ga_browser_use/`.

## Non-Goals

- No separate browser-use runtime.
- No external browser-use repo changes.
- No automatic Chrome launch.
- No cross-origin iframe high-level automation.
- No Shadow DOM deep automation.
- No file upload wrapper.
- No screenshot log or replay system in this phase.
- No generic virtualized-grid paging/search.
- No business-specific OA workflow automation.
