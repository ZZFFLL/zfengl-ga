# GA Browser Semantic MVP Design

## Goal

Build a small DOM semantic enhancement MVP for GA's existing browser structured layer so `browser_use_index -> browser_find -> browser_action/browser_recipe` can handle common advanced web controls more reliably.

This design borrows the useful ideas from Playwright and Stagehand, but does not integrate their runtimes. The target is better semantic state, better target selection, and a minimal action loop for high-frequency component shapes.

## Scope

### In Scope

- AntD-like custom selects and generic combobox controls.
- Portal, dropdown, modal, popover, and drawer layers.
- Same-origin iframe rich text editors, including CKEditor-like `contenteditable` or designMode bodies.
- React-like controlled text inputs and textareas.
- Tool descriptions, SOP text, tests, and runtime logs for the new semantic fields.

### Out Of Scope

- Cross-origin iframe traversal.
- Closed Shadow DOM.
- Visual recognition, OCR, screenshot grounding, or VLM-based targeting.
- Private business component adapters or business-system-specific component names.
- Replacing `web_execute_js`, `web_scan`, `TMWebDriver`, or the Chrome extension bridge.
- Adding Playwright, Stagehand, browser-use runtime sessions, or any new browser workspace.

## Architecture

The MVP stays inside `ga_browser_use`. It strengthens the existing structured browser layer instead of adding a new public tool.

The core flow remains:

```text
browser_use_index
-> browser_find
-> browser_action / browser_recipe
-> browser_action verify / browser_recipe component_wait
```

The implementation should keep fields flat and bounded. The indexer may produce richer semantic metadata, but it must not become a large page extraction engine.

## Design Principles

- Prefer DOM and accessibility semantics over CSS class-name guesses.
- Keep component hints generic, such as `combobox_like`, `portal_option`, `rich_text_editor`, and `controlled_input_candidate`.
- Never emit business-specific hints such as a product name, OA vendor name, or workflow-specific field type.
- Let `browser_use_index` describe the page, `browser_find` rank targets, `browser_action` perform bounded indexed actions, and `browser_recipe` handle only small fixed flows.
- Preserve `web_execute_js` as the peer low-level path for cases outside this structured layer.

## Module Responsibilities

### `ga_browser_use/indexer.py`

Enhance the element snapshot with DOM semantic metadata:

- `accessible_name`: normalized name from `aria-label`, `aria-labelledby`, associated label text, `title`, `placeholder`, and visible text where appropriate.
- `aria`: small object with `expanded`, `haspopup`, `controls`, `owns`, `selected`, and `disabled` when present.
- `role`: normalized ARIA or inferred role, including `combobox`, `listbox`, `option`, `dialog`, `menu`, `textbox`, and `button`.
- `control_kind`: existing GA action class, with stronger classification for `custom_select`, `contenteditable`, and text inputs.
- `layer`: `main`, `dropdown`, `modal`, `popover`, or `drawer`.
- `layer_root`: stable summary of the closest visible layer root.
- `frame_path`: existing same-origin frame path.
- `field_context`: nearby field anchors, including `field_label`, `nearby_text`, `row_label`, and `placeholder`.
- `component_hint`: generic semantic hint.
- `action_hints`: bounded suggested actions such as `click`, `input`, `keys_after_input`, `custom_select`, `layer_select`, and `verify_field_value`.

### `ga_browser_use/finder.py`

Consume the new index metadata without turning filters into standalone locators:

- Rank `accessible_name` and exact labels above generic text.
- Prefer matching `field_context.field_label` and `scan_anchor.field_label` for form fields.
- Use `layer`, `frame_path`, `role`, and `control_kind` as filters and tie-breakers.
- Keep ambiguity when multiple elements have equivalent semantic matches.
- Include recovery advice that suggests refreshing `browser_use_index` with larger `max_elements` when truncation or frame omission may hide the target.

### `ga_browser_use/actions.py`

Keep actions indexed and bounded:

- For text input and textarea targets, use a React-friendly input sequence: focus, native value setter where applicable, `input`, `change`, and blur when appropriate.
- Keep post-action verification as the main success guard, especially `verify=field_value`.
- Preserve state-token and stale-index protections.
- Keep iframe action execution frame-aware through existing `frame_path`.

### `ga_browser_use/recipes.py`

Only tune existing fixed flows:

- `custom_select` should open the trigger and find options in visible dropdown/listbox layers.
- `layer_select` should prefer visible modal/popover/drawer layers and avoid selecting same-named controls from `main`.
- Recipes should preserve `frame_path` and layer context across the trigger -> option -> verify sequence.
- Do not add business-specific recipes.

### `ga_browser_use/results.py`

Make recovery specific:

- For semantic misses, recommend `browser_use_index` refresh and narrower `query`, `control_kind`, `layer`, or `frame_path`.
- For unsupported controls, recommend the existing `browser_recipe` path when available.
- For repeated bridge or DOM event failures, keep `web_execute_js` as the low-level alternative.

### `ga_browser_use/runtime_log.py`

Add readable output for the new fields where logs already print elements and matches:

- `accessible_name`
- `layer`
- `layer_root`
- `component_hint`
- selected `aria` fields

The logging output must stay concise and respect existing sensitivity controls.

## Scenario Behavior

### AntD-Like Select

Indexer should classify the trigger as `control_kind=custom_select`, `role=combobox`, and include `aria.expanded`, `aria.haspopup`, and field context. Open options should be indexed as `role=option` inside `layer=dropdown` or `role=listbox`.

The preferred flow is:

```text
browser_find(query=<field label>, control_kind=custom_select)
browser_recipe(recipe=custom_select, target=<match>, option_text=<option>)
```

Success requires the selected field text or value to include the option, or the dropdown to close with the trigger field updated.

### Portal And Overlay Layers

Indexer should identify visible layer roots and tag child elements with `layer` and `layer_root`.

Finder should prefer explicit layer filters. Recipes should avoid selecting a `main` layer element when the current flow is acting inside an overlay.

Success requires selecting the intended visible overlay target without matching same-text controls in the main page.

### CKEditor-Like Iframe Editors

Indexer should traverse same-origin frames, preserve `frame_path`, and classify editor bodies as `control_kind=contenteditable` with `component_hint=rich_text_editor` when the target is contenteditable or designMode.

The preferred flow is:

```text
browser_find(query=<field label>, control_kind=contenteditable)
browser_action(action=input, index=<match.index>, text=<content>, verify=field_value)
```

Success requires iframe editor text to change and verification to read back the expected content.

### React-Like Controlled Inputs

Indexer should mark normal text inputs and textareas as input targets and may add `component_hint=controlled_input_candidate` when the element appears framework-managed.

`browser_action(input)` should use a user-like input path and post-action verification.

Success requires the field value to read back through the DOM after the event chain runs.

## Testing

The MVP should be verified with unit-level fixture tests, not live business systems.

### Required Test Files

- `tests/test_browser_indexer.py`
- `tests/test_ga_browser_use_finder.py`
- `tests/test_browser_actions.py`
- `tests/test_ga_browser_use_recipes.py`
- `tests/test_browser_tool_schemas.py`
- Existing browser handler tests if any public contract changes.

### Required Coverage

- AntD-like combobox trigger and dropdown option metadata.
- Portal layer root classification and same-text main-layer avoidance.
- Same-origin iframe contenteditable indexing with frame path.
- React-like controlled input setter and event dispatch verification.
- Finder scoring for `accessible_name`, field context, layer, frame path, and control kind.
- Recipe option lookup constrained to dropdown/overlay layer.
- Tool schema and SOP wording that states the MVP boundary and avoids claiming private component coverage.

### Non-Pass Criteria

These cases may be manually explored later but do not gate the MVP:

- Real AntD documentation page end-to-end tests.
- Real CKEditor CDN page end-to-end tests.
- Cross-origin iframe.
- Closed Shadow DOM.
- Visual recognition.
- CDP physical mouse/keyboard clicks.
- Private business component support.

## Risks

- Accessibility metadata may be missing or lazily created by component libraries. The MVP should use semantics when available and keep generic DOM fallback paths.
- Overlay remnants can remain in the DOM after closing. The layer classifier must prefer visible layer roots.
- Controlled input handling varies across frameworks. The action path should stay conservative and rely on read-back verification.
- Rich text editors expose different editing surfaces. The MVP covers same-origin `contenteditable` and designMode bodies only.

## Acceptance Criteria

- `browser_use_index` returns the new semantic fields for the four in-scope fixture families.
- `browser_find` can locate targets using field label, accessible name, layer, control kind, and frame path.
- `browser_action(input)` can update and verify React-like controlled input fixtures.
- `browser_recipe(custom_select/layer_select)` uses dropdown/overlay semantics to avoid same-text main-page targets.
- Browser tool schemas and SOP explain the boundary clearly.
- Focused browser tests pass.

