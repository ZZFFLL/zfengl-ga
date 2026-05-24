# GenericAgent Agent Flow and HeroUI Event Contract

This document is the source-backed handoff for HeroUI frontend adaptation. It describes the current GenericAgent execution path and the structured event contract exposed by the HeroUI bridge.

## Scope

- Applies to `frontends/heroui` only.
- Other frontends keep legacy behavior unless they explicitly set `GenericAgent.structured_events = True`.
- Backend structured events are the primary UI contract. Legacy `outputs[]` parsing is fallback only.

## End-to-End Flow

1. HeroUI submits a user prompt with `POST /session/{sid}/prompt`.
   - Code: `frontends/heroui/bridge.py::AgentManager.submit_prompt`
   - The bridge creates the user message, computes `turn_id = ga|{session_id}|{user_message_id}`, records the current `eventSeq`, and starts `run_agent_turn` in a worker thread.
   - Response includes `userMessageId`, `seq`, and `eventSeq`.

2. The frontend starts polling the accepted turn.
   - Code: `frontends/heroui/src/api.ts::createTurn` and `subscribeTurn`
   - `createTurn()` stores the returned `eventSeq` in a per-turn cursor.
   - `subscribeTurn()` polls `/session/{sid}/messages?after={message_id}&after_event={event_seq}`.

3. The bridge sends the prompt to GenericAgent.
   - Code: `frontends/heroui/bridge.py::AgentManager.run_agent_turn`
   - It calls `agent.put_task(prompt, images=...)` and consumes `display_queue` items from `GenericAgent.run`.

4. GenericAgent routes optional structured events into the display queue.
   - Code: `agentmain.py::GenericAgent.run`
   - Default is `structured_events = False`.
   - HeroUI-only `make_agent()` sets `agent.structured_events = True`.
   - When enabled, `event_sink(event)` emits `{"event": event, "source": source}` into `display_queue`.
   - Legacy `next` / `done` queue items still exist for fallback and non-structured consumers.

5. The agent loop emits internal structured events.
   - Code: `agent_loop.py::agent_runner_loop`
   - Events are synchronous and ordered at the source.
   - `_emit_event()` catches sink failures so optional event output cannot break legacy execution.

6. The HeroUI bridge converts and persists events.
   - Code: `frontends/heroui/bridge.py::convert_agent_event` and `add_event`
   - The bridge assigns monotonic per-session `seq`.
   - Events are persisted in SQLite table `events`.
   - `/session/{sid}` returns full historical `events`.
   - `/session/{sid}/messages` returns events after `after_event`.

7. The frontend consumes structured events first.
   - Code: `frontends/heroui/src/api.ts::subscribeTurn`
   - It filters events by exact `turn_id`.
   - It advances the event cursor even for irrelevant older events.
   - If structured events exist for the active turn, raw `partial.content` is not emitted as `answer.delta`.
   - Legacy output parsing runs only when no structured timeline event exists.

8. React state renders events as timeline cards and assistant messages.
   - Code: `frontends/heroui/src/state.ts::applyStreamEvent`
   - `timeline.step` upserts cards and appends `output_delta`.
   - `answer.final` creates normal assistant response records.
   - `turn.done` closes running steps.
   - Code: `frontends/heroui/src/components/ChatSurface.tsx`
   - Tool input/output/error display in collapsible card sections.
   - Assistant final text renders as a normal assistant message, not as a card.

## Internal Agent Events

These events are emitted by `agent_loop.py` before bridge conversion.

| Event type | When emitted | Key fields |
|---|---|---|
| `turn.start` | At the start of each GA loop turn | `turn` |
| `llm.start` | Immediately before `client.chat(...)` | `turn` |
| `llm.end` | After model response is received | `turn`, `text`, `has_tools` |
| `tool.start` | Before a real tool dispatch | `turn`, `index`, `total`, `tool_call_id`, `tool_name`, `tool_kind`, `args` |
| `tool.delta` | For each yielded tool output chunk | `turn`, `index`, `tool_call_id`, `tool_name`, `tool_kind`, `delta` |
| `tool.end` | After tool dispatch completes | `turn`, `index`, `tool_call_id`, `tool_name`, `tool_kind`, `status`, `result`, `output`, `elapsed_ms` |
| `agent.final` | When the agent reaches final answer / exit | `turn`, `text`, `exit_reason` |
| `turn.end` | When a GA loop turn ends | `turn`, `exit_reason` |
| `agent.done` | Before `agent_runner_loop` returns | `turn`, `exit_reason` |

`no_tool` is intentionally not exposed as a tool card. It only leads to final-answer lifecycle events.

## Bridge Event Conversion

The bridge converts internal events into frontend `StreamEvent` records.

| Internal event | Frontend event | UI role |
|---|---|---|
| `turn.start` | not exposed as a card | Internal turn boundary |
| `llm.start` | `phase.update` | Active status label |
| `llm.end` | `timeline.step` with `kind: "phase"` | Model output card with `detail` and `default_open: true` |
| `tool.start` | `timeline.step` | Create running tool card with structured `input` |
| `tool.delta` | `timeline.step` | Append `output_delta` to existing tool card |
| `tool.end` | `timeline.step` | Mark tool card done/failed, set `output`, `error`, `elapsed_ms` |
| `turn.end` | not exposed as a card | Internal turn boundary |
| `agent.final` | `answer.final` | Normal assistant response |
| `agent.done` | `turn.done` | Close active turn |

Canonical tool step id:

```text
{response_id}:tool:{ga_turn}:{index + 1}
```

Required frontend fields for tool cards:

```json
{
  "id": "ga|sess|1:response:1:tool:2:1",
  "turn_id": "ga|sess|1",
  "response_id": "ga|sess|1:response:1",
  "kind": "command",
  "title": "调用 code_run",
  "status": "running",
  "summary": "正在执行 code_run",
  "input": "{ ... }",
  "output_delta": "stream chunk",
  "output": "final output",
  "error": "",
  "elapsed_ms": 123,
  "tool_name": "code_run",
  "tool_label": "GA Turn 2",
  "created_at": "2026-05-24T00:00:00.000Z"
}
```

## Ordering and Cursor Rules

- The source order is the order of `_emit_event()` calls in `agent_loop.py`.
- The bridge assigns `seq` when it stores events. `seq` is the API ordering cursor.
- `submit_prompt()` returns the current `eventSeq` before the new turn starts. The frontend starts polling after that value.
- `subscribeTurn()` filters by exact `turn_id` and advances `lastEventSeq` for every returned event. This prevents previous turns from replaying into the active turn.
- Historical reload uses `/session/{sid}` and rebuilds timeline from persisted `events`; if no timeline events exist, it falls back to legacy `outputs[]`.

## Raw Output Boundary

Structured HeroUI mode must not treat legacy verbose output as primary UI data.

- Bridge still receives legacy `next` / `done` items from `GenericAgent.run`.
- During structured runs, bridge does not update `partial.content` with raw `next` chunks.
- During structured runs, final assistant message content is taken from `agent.final.text` when available.
- Frontend suppresses `partial.content` streaming when structured events are present for the active turn.
- Legacy `outputs[]` parsing remains only for old sessions or non-structured responses.

## Persistence and Delete Semantics

- Session messages are stored in `messages`.
- Frontend-ready events are stored in `events`.
- `delete_session()` explicitly deletes from `events`, then `messages`, then `sessions`.
- Stale worker writes are blocked by `deleted_session_ids` checks in persistence helpers.

## Test Coverage

- `tests/test_agent_loop_events.py`
  - Internal event ordering.
  - Disabled-by-default behavior.
  - GenericAgent default opt-out.
- `frontends/heroui/src/ga_bridge_contract.test.mjs`
  - Bridge persistence and route contract.
  - Event cleanup on delete.
  - Structured final text instead of raw verbose final message.
- `frontends/heroui/src/api_stream.test.mjs`
  - Current-turn event filtering.
  - Raw partial suppression when structured events exist.
- `frontends/heroui/src/state.test.mjs`
  - `output_delta` append behavior.
  - Timeline, final answer, and turn completion reducers.

## Known Frontend Integration Rules

- Use `event.seq` only as a transport cursor; do not use it as a card id.
- Use `turn_id` to bind events to the active UI turn.
- Use `response_id` to group tool cards above the assistant response they belong to.
- Treat `answer.final` as the assistant response source of truth.
- Do not parse `message.outputs` if structured `timeline.step` events exist for that response/session.
- Tool card content should prefer `input`, `output_delta` / `output`, `error`, and `elapsed_ms`.
- Round start/end phase cards are hidden; old persisted `第 N 轮开始/结束` phase events are ignored by the frontend.
- `模型输出完成` cards carry the raw model output in `detail` and default to expanded display via `default_open: true`.

## Remaining Runtime Validation

Automated tests cover event contract behavior. The remaining check is manual UI validation after the user starts HeroUI:

```text
请先用 Python 打印当前工作目录，再读取 package.json 的脚本字段，最后总结结果。
```

Expected UI:

- Tool cards appear while tools run.
- Cards stay in source order.
- Args/results show in collapsible sections.
- Final answer is a normal assistant message.
- No raw `GenericAgent.outputs` card appears when structured events exist.
