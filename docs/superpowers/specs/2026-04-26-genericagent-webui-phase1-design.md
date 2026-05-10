# GenericAgent WebUI Phase 1 Design

Date: 2026-04-26
Branch: zfengl-ga
Status: Approved design baseline, pending implementation plan

## Goal

Build a new browser-accessible WebUI for GenericAgent while keeping phase 1 functionally equivalent to the existing default Streamlit UI.

The new UI should feel like a light, professional Agent operations console: chat remains the primary workspace, but model state, control actions, and `LLM Running (Turn n)` execution logs are easier to see and operate than in the current Streamlit page.

## Current Baseline

The current default UI is started by `launch.pyw`.

- `launch.pyw` starts Streamlit with `frontends/stapp.py`.
- `launch.pyw` then opens `http://localhost:{port}` inside a `pywebview` desktop window.
- The same localhost URL can also be opened directly in a browser.
- `frontends/stapp.py` owns the default Streamlit chat page.
- `frontends/stapp2.py` is an alternate Streamlit-styled UI, not the current default.
- The frontend talks to the Agent through `GeneraticAgent` methods:
  - `put_task(query, source="user", images=None)`
  - `abort()`
  - `next_llm(n=-1)`
  - `list_llms()`
  - `get_llm_name()`

Phase 1 should not modify the Agent core loop or model request path.

## Selected Approach

Use a modern frontend project with a local Python bridge server.

```text
frontends/webui_server.py
frontends/webui/package.json
frontends/webui/src/
frontends/webui/src/App.tsx
frontends/webui/src/components/
frontends/webui/src/styles/
```

Recommended frontend stack:

- Vite
- React
- TypeScript
- Tailwind CSS
- shadcn/ui-style component primitives where useful, but only for phase-1 needs

Recommended backend shape:

- Python local HTTP API/SSE bridge.
- Reuse existing `GeneraticAgent` public methods.
- Keep the old Streamlit UI available as a fallback.
- Add a new optional `launch.pyw` mode before changing the default startup behavior.

## Non-Invasive Rule

Phase 1 must be additive by default.

Allowed:

- Add `frontends/webui_server.py`.
- Add `frontends/webui/`.
- Add a small optional launch mode in `launch.pyw`, such as `--webui`.
- Reuse existing helper functions from `frontends/continue_cmd.py` and `frontends/chatapp_common.py` where appropriate.

Avoid:

- Rewriting `agentmain.py`.
- Removing or replacing `frontends/stapp.py`.
- Changing default `python launch.pyw` behavior until the new UI is verified.
- Reimplementing `/continue` history parsing from scratch.
- Adding authentication, cloud deployment, plugin marketplace, or multi-user semantics in phase 1.

## Visual Direction

The default style is a light professional Agent operations console.

Design traits:

- Calm light background, not pure white.
- White primary panels.
- Deep gray body text.
- Blue-gray primary actions.
- Green for running/success state.
- Red for stop/error state.
- Amber for warning state.
- Small-radius controls, around 6-8px.
- Subtle borders and minimal shadows.
- No large gradients, decorative blobs, or marketing-page hero sections.
- No emoji as functional icons; use SVG icons from a consistent icon set.
- System fonts first to keep local startup reliable.

The UI should communicate control, clarity, and long-session readability rather than entertainment or monitoring-wall spectacle.

## Layout

Use an adaptive operations-console layout.

### Wide Desktop

Three columns:

1. Left control sidebar
2. Center chat workspace
3. Right execution log panel

The center chat workspace is always the primary region.

### Medium Width

Keep the chat workspace primary.

- The left control sidebar may stay visible if width permits.
- The execution log becomes a slide-over panel or collapsible side panel.

### Narrow Window / pywebview Default

Prioritize the chat.

- Show only the chat workspace by default.
- Provide top-level buttons for controls and execution log.
- Open controls/logs as drawers or panels.
- The chat input must remain reachable and must not be squeezed by side panels.

## Phase 1 Features

Phase 1 must preserve the default Streamlit UI's practical feature set.

### Chat

- Submit user prompts.
- Stream assistant output.
- Show user and assistant messages.
- Preserve messages during the current UI session.
- Disable input while a task is running in phase 1.
- Support Enter to send and Shift+Enter for newline.

### Agent Control

- Show current LLM index and name.
- List available LLM backends.
- Switch LLM backend.
- Stop the current task.
- Reinject tools/System Prompt by clearing the relevant cached marker.
- Start desktop pet using existing pet script behavior.
- Toggle idle autonomous action.

### Slash Commands

Support existing command behavior:

- `/new`
- `/continue`
- `/continue N`

The UI should call existing frontend command helpers instead of inventing a separate session parser.

### Execution Log

Render `LLM Running (Turn n)` blocks as collapsible execution-log items.

Behavior:

- Current turn expands by default.
- Completed historical turns collapse by default.
- Each turn shows a compact heading.
- If a `<summary>...</summary>` block is present, use its first line as the turn title.
- Preserve access to full raw turn content in the expanded body.
- Avoid destructive formatting that hides code fences or tool output.

### Idle Monitor Compatibility

Keep compatibility with `launch.pyw` idle monitoring.

The new page should expose a hidden DOM value equivalent to:

```html
<div id="last-reply-time" style="display:none">...</div>
```

The value should update after assistant completion and when relevant reset actions occur.

### Error States

If no LLM is configured, show a clear local error screen.

The error should explain that `mykey.py` needs a valid model configuration and should not start an unusable chat UI.

## API Boundary

The Python bridge should expose small local endpoints. Exact paths can change in implementation, but phase 1 should keep this boundary:

```text
GET  /api/state
POST /api/chat
GET  /api/chat/{task_id}/stream
POST /api/abort
POST /api/llm
POST /api/reinject
POST /api/new
POST /api/continue
POST /api/autonomous
POST /api/pet
```

Streaming should use SSE unless implementation discovers a clear blocker. SSE is enough for queue events shaped like existing `{'next': ...}` and `{'done': ...}` messages, and it avoids a heavier WebSocket layer in phase 1.

## Data Flow

1. User submits a prompt in React.
2. React calls `POST /api/chat`.
3. Python bridge calls `agent.put_task(prompt, source="user")`.
4. Python bridge returns a `task_id`.
5. React opens `GET /api/chat/{task_id}/stream`.
6. Python bridge reads the display queue.
7. Queue item with `next` updates the streaming assistant message.
8. Queue item with `done` finalizes the assistant message and updates `last_reply_time`.
9. Stop action calls `POST /api/abort`, which delegates to `agent.abort()`.

## State Management

The backend owns active task state.

Minimum backend task state:

- `task_id`
- display queue
- status: `running`, `done`, `aborted`, or `error`
- current response text
- created time
- completed time

The frontend owns visual state:

- open or closed drawers
- selected execution-log item
- local message list for the active browser session
- input draft

Phase 1 should allow a page refresh to lose unsent UI-only state. Durable multi-session history is out of scope.

## Accessibility and UX Requirements

- Text contrast should meet WCAG AA for normal text.
- Interactive targets should be at least 44px high where practical.
- Icon-only buttons need accessible labels or visible text.
- Focus states must remain visible.
- Keyboard users must be able to reach chat input, send, stop, model selector, and panel toggles.
- Motion should be minimal and should respect reduced-motion preferences.
- Layout must avoid horizontal scrolling at narrow widths.
- Loading/running state must be visible within 100ms of task submission.

## Phase 1 Non-Goals

Do not include these in phase 1:

- Full dark theme.
- Login or multi-user access control.
- Cloud deployment.
- Persistent conversation database.
- Plugin marketplace UI.
- Tool-call graph visualization.
- Mobile-first redesign beyond basic responsive usability.
- Replacing all chat platform frontends.
- Replacing the existing Streamlit UI as the default before verification.

## Verification Criteria

Implementation is complete when these checks pass:

1. Existing default Streamlit path still works.
2. New WebUI starts through an explicit launch mode.
3. Browser access to localhost works.
4. `pywebview` access works.
5. A prompt can be submitted and streamed to completion.
6. Stop action aborts an active task.
7. LLM list displays and switching works.
8. `/new` resets the conversation.
9. `/continue` behavior matches the existing frontend helper behavior.
10. `LLM Running (Turn n)` content is visible as collapsible execution log items.
11. `last-reply-time` exists in the DOM and updates after a completed assistant response.
12. LLM missing configuration shows a useful error screen.
13. Narrow window layout keeps chat usable.
14. No unrelated untracked files are staged or committed.

## Open Implementation Decisions

These are implementation choices, not design blockers:

- Whether the Python bridge uses Bottle or the Python standard library.
- Whether Tailwind is configured with a minimal local component layer or a small shadcn/ui subset.
- Whether frontend build output is served from `frontends/webui/dist` or proxied during development.

The implementation plan should pick the simplest option that keeps local Windows startup reliable.
