# GA Browser V1 Hardening Design

## Goal

Strengthen the existing `browser_state` and `browser_action` tools so GA can handle more real-world page operation scenarios while preserving the current first-person Chrome session model.

This is a v1 hardening effort, not a v2 tool split and not a browser-use runtime integration.

## Hard Constraints

- GA only operates the user's already-open Chrome browser session.
- GA does not start Chrome automatically.
- GA does not create a new browser profile, browser workspace, browser-use session, or cloud session.
- GA does not copy, import, or migrate login state.
- GA does not modify `E:\zfengl-ai-project\browser-use`.
- Browser-use code is used as implementation reference only: DOM/frame/action/wait/verification ideas may be borrowed, but browser lifecycle stays in GA.
- Existing tool names remain `browser_state` and `browser_action`.
- Existing v1 fields and behavior remain backward compatible.
- If no browser tab is available, the tools return `browser_unavailable` and tell GA to ask the user to open Chrome first.

## Existing Baseline

Current GA browser operation has two layers:

- Low-level layer: `web_scan` and `web_execute_js`, backed by TMWebDriver and the Chrome extension bridge.
- High-level layer: `browser_state` and `browser_action`, backed by `browser_indexer.py` and `browser_actions.py`.

The high-level layer currently covers:

- Main-document interactive element indexing.
- Indexed `click`, `input`, `select`, `keys`, `wait_index`, `wait_text`, and `wait_selector`.
- State-token protection against stale indexes.
- Structured failures such as `browser_unavailable`, `state_missing`, `stale_index`, `invalid_args`, `visibility`, `timeout`, and `dom_event`.
- Basic recovery hint for `input -> keys Enter` without reusing old index.

Current hard gaps:

- No first-class same-origin iframe indexing/action path.
- No rich field context beyond basic tag/role/text/value.
- No table/grid semantics.
- No generic operation-after-verification contract.
- No high-level AntD/custom combobox strategy.
- No high-level SPA stability wait beyond text/selector/index waits.
- No high-level rich text editor strategy beyond raw contenteditable input.

## Design Direction

Enhance the existing v1 tools in place.

`browser_state` remains the single high-level page-state tool. It should return richer metadata while keeping existing fields unchanged.

`browser_action` remains the single high-level page-action tool. It should keep existing action names and semantics, while internally using richer state metadata to locate elements inside same-origin frames, verify post-action effects, and return better recovery guidance.

No new user-facing browser runtime is introduced.

## Capability Scope

### P0: Same-Origin iframe And Frame-Aware Actions

`browser_state` should recursively index interactive elements inside same-origin iframes.

Each element keeps existing fields and gains:

- `frame_path`: array describing the iframe path from top document to the element document.
- `frame_depth`: numeric depth.
- `frame_url`: URL of the owning frame when readable.
- `frame_title`: title of the owning frame when readable.

`browser_action` should use the cached `frame_path` to re-enter the correct same-origin frame before resolving and acting on the indexed element.

Boundaries:

- Same-origin iframe only for direct DOM traversal.
- Cross-origin iframe remains a `tmwebdriver_sop` / CDP bridge fallback path.
- Detached or changed iframe paths should fail as `stale_index` or `frame_unavailable`, not silently act in the wrong document.

### P0: Operation-After-Verification

Mutating actions should return a verification suggestion and, when requested, a verification result.

Initial verification types:

- `field_value`: read the target field value/text after input/select/rich text changes.
- `text`: check page text contains expected text.
- `selector`: check selector exists.
- `element_text`: read indexed element text after action.

Tool behavior:

- Verification is opt-in for strict checks, but `browser_action` should always return `verify_hint` for common cases.
- Verification failure should not be reported as action success. It should return structured `status=failed`, `stage=verify_failed`, and the observed value.
- If action succeeds but no verification was requested, return `status=success` with `verify_hint`.

### P0: SPA Stability Waits

Extend waiting support without making the tool a full Playwright clone.

New wait behavior can be implemented as additional `browser_action` actions or bounded options on existing wait actions.

Required stable waits:

- `wait_dom_stable`: repeated DOM snapshots stop changing for a short bounded interval.
- `wait_not_busy`: common loading indicators disappear or become hidden.
- `wait_enabled`: an indexed button/input becomes enabled and visible.
- `wait_route`: URL or pathname changes to an expected value.

Boundaries:

- No network-level idle promise is required in this phase.
- Timeouts must stay bounded.
- Waits must return structured timeout details.

### P0: Custom Input Controls

Support common custom controls as page-operation patterns, not business-specific OA flows.

Initial target patterns:

- AntD-like `combobox`, `listbox`, `option`, `aria-expanded`, and `aria-controls`.
- React/Vue custom select where click opens a portal/dropdown and options become indexed.
- Date input and date picker patterns where a text input or popup option is visible.

Implementation posture:

- Do not make native `select` pretend to support custom selects.
- Keep `select` restricted to native `<select>`.
- Add metadata in `browser_state` so GA can choose click/open-option flows.
- Add helper results and hints when `select` is attempted on a custom control.

### P0: Modal, Popup, Drawer, And Overlay Context

`browser_state` should detect likely active overlays and annotate elements inside them.

Element metadata should include:

- `layer`: `main`, `modal`, `drawer`, `popover`, `dropdown`, or `unknown`.
- `layer_root_hint`: short selector-like hint for the overlay root.
- `modal_rank`: order or priority when multiple layers exist.

Behavior:

- Visible overlay elements should be prioritized in output.
- Background elements hidden or blocked by modal overlays should not be preferred.
- Escape remains supported through `keys`.

### P0: Rich Text Editor Basics

Support common rich text editing paths at the page-operation layer.

Initial scope:

- Plain `contenteditable`.
- Same-origin iframe editor body, including common CKEditor/TinyMCE-style editing iframe.
- Read-back after writing.
- Clear and replace content.

Boundaries:

- Do not promise all editor instance APIs.
- Do not handle cross-origin editor iframes in the high-level tool.
- If DOM write plus input/change events are not accepted, return a clear fallback hint to use `tmwebdriver_sop` or component-specific SOP.

### P1: Table And Grid Context

Add read-oriented table/grid context before cell editing.

`browser_state` should add optional table context for elements inside or near tables/grids:

- `table_id`
- `row_index`
- `col_index`
- `row_header`
- `col_header`
- `cell_text`
- `row_text`

Initial targets:

- Native `<table>`.
- ARIA `role=grid`, `row`, `cell`, `columnheader`, `rowheader`.
- Simple div-based grids where headers and rows are visible.

Cell editing should come after table read context is stable.

### P1: CDP-Style Real Click/Input Fallback

Current `browser_action` uses DOM click and JS value setting. Some applications require more realistic mouse/key events.

Add a bounded fallback path through the existing GA CDP bridge where available:

- Scroll element into view.
- Compute viewport coordinates.
- Dispatch CDP mouse events for click fallback.
- Dispatch CDP text/key events for input fallback when JS value setting is rejected.

Boundaries:

- Do not make CDP fallback the default for every action.
- Use fallback only after DOM action is rejected or when metadata indicates the control likely needs real events.
- Return which path was used: `dom`, `js_value`, `cdp_mouse`, `cdp_key`, or `fallback_failed`.

### P1: Screenshot And Evidence Log

Add lightweight evidence support without turning GA into a replay framework.

Capabilities:

- Optional screenshot capture for current tab through existing CDP bridge.
- Optional per-action evidence record: state summary, action args, result, verification, screenshot path.
- Evidence files should go under an ignored runtime directory, not tracked test fixtures.

This is for diagnosis and user-visible proof, not for deterministic replay.

## Non-Goals

- No browser-use BrowserSession integration.
- No browser-use Cloud integration.
- No automatic Chrome startup.
- No new user-data-dir or browser profile.
- No cross-origin iframe high-level automation in this phase.
- No closed Shadow DOM support.
- No full recording/replay engine.
- No business-specific OA process automation.
- No guarantee to operate canvas/WebGL/custom rendered UI.
- No attempt to bypass site security, CAPTCHA, or anti-automation checks.

## Data Contract Changes

Existing element fields remain:

- `index`
- `tag`
- `role`
- `type`
- `text`
- `value`
- `visible`
- `disabled`
- `bbox`
- `selector_hint`

New optional fields can be added:

- `frame_path`
- `frame_depth`
- `frame_url`
- `frame_title`
- `labels`
- `attributes`
- `validation`
- `stable_key`
- `field_context`
- `table_context`
- `layer`
- `layer_root_hint`
- `modal_rank`
- `control_kind`
- `action_hints`

Backward compatibility rule:

- Existing consumers that ignore unknown fields must continue to work.
- Existing tests for old fields must keep passing.
- Existing action names and required args must keep their current meaning.

## Error Contract Changes

Keep current structured failure shape:

```json
{"status":"failed","stage":"...","error":"..."}
```

Add only bounded new stages:

- `frame_unavailable`
- `verify_failed`
- `control_unsupported`
- `fallback_failed`
- `dom_unstable`

Failures should include actionable fields when available:

- `hint`
- `suggested_args`
- `suggested_next_action`
- `observed`
- `expected`
- `retryable`
- `fallback`

## Testing Strategy

Use local fixture pages injected through `web_execute_js` or unit-level script assertions. Real browser smoke tests remain manual or checklist-based.

Required test groups:

- Unit tests for indexer output shape and normalization.
- Unit tests for frame path encoding and action script generation.
- Unit tests for action validation and error stages.
- Tool schema tests for new optional args and descriptions.
- Handler tests for `ga.py` delegation and formatted tool output.
- Checklist updates for same-origin iframe, custom controls, rich text, verification, and waits.

No test should require browser-use to launch a browser.

## Rollout Plan

Implementation should be split into small commits:

1. Frame-aware state metadata and tests.
2. Frame-aware indexed actions and tests.
3. Verification hint/result contract and tests.
4. SPA wait actions and tests.
5. Field/custom-control metadata and AntD-style click flow tests.
6. Rich text basics and tests.
7. Table/grid context read support and tests.
8. Documentation and SOP update.

Screenshot and CDP fallback are outside the default P0 implementation plan. They should be planned after P0 unless explicitly pulled forward.

## Success Criteria

- Existing `browser_state` and `browser_action` calls still work unchanged.
- Same-origin iframe elements appear in `browser_state` with `frame_path`.
- Indexed actions can click/input same-origin iframe elements.
- Mutating actions provide verification hints.
- Requested verification can fail explicitly with `verify_failed`.
- SPA waits return success or structured timeout, never silent success.
- Native `select` remains native-only.
- Custom controls return useful hints and can be operated through click/open-option flow when options are visible.
- Rich text contenteditable and same-origin iframe editor basics can be written and read back.
- No browser-use source files are modified.
- No new browser process or profile is required.
