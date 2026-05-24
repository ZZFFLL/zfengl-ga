# HeroUI Structured Agent Events Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HeroUI show GenericAgent's multi-turn execution process in real time, in the exact execution order, using backend-provided structured events instead of parsing unstable text logs in the browser.

**Architecture:** Add an optional structured event sink to `agent_loop.py` and `agentmain.py`; default behavior remains unchanged for all non-HeroUI frontends. `frontends/heroui/bridge.py` is the only consumer that enables the sink, persists ordered events, and exposes them through the existing polling API. The React UI consumes bridge events as `timeline.step`, `answer.delta`, `answer.final`, and `turn.done` records, with `outputs[]` parsing kept only as a legacy fallback.

**Tech Stack:** Python `queue`, `sqlite3`, `dataclasses`, existing GenericAgent loop; aiohttp HeroUI bridge; React + TypeScript HeroUI frontend; Node `tsx` tests and Python `pytest`.

---

## Success Criteria

- HeroUI displays every GA internal turn and every tool call in execution order while the run is still active.
- Tool cards are created from backend structured events, not browser-side parsing of `message.outputs`.
- Tool args, incremental output, final result, error, status, elapsed time, GA turn number, and response binding are represented as explicit fields.
- The final assistant reply is rendered as an assistant message only, never as a tool/output card.
- Existing non-HeroUI frontends keep working because the new event sink defaults to disabled.
- Historical sessions reload with the same ordered timeline after a bridge restart.

## Event Contract

Agent-loop internal events use this shape before bridge conversion:

```python
{
    "type": "tool.start",
    "turn": 2,
    "tool_call_id": "call-1",
    "tool_name": "code_run",
    "args": {"type": "python", "code": "print('ok')"},
    "ts": 1760000000.0,
}
```

HeroUI bridge stores and returns frontend-ready events using the existing `StreamEvent` contract:

```json
{
  "seq": 12,
  "type": "timeline.step",
  "turn_id": "ga|sess-1|1",
  "session_id": "sess-1",
  "data": {
    "id": "ga|sess-1|1:response:1:tool:2:1",
    "turn_id": "ga|sess-1|1",
    "response_id": "ga|sess-1|1:response:1",
    "kind": "command",
    "title": "调用 code_run",
    "status": "running",
    "summary": "正在执行 code_run",
    "detail": "",
    "input": "{\n  \"type\": \"python\",\n  \"code\": \"print('ok')\"\n}",
    "tool_name": "code_run",
    "tool_label": "GA Turn 2",
    "created_at": "2026-05-24T12:00:00.000Z"
  }
}
```

## File Structure

- Modify `agent_loop.py`: add optional `event_sink`, emit ordered structured events around LLM turns and tool dispatch.
- Modify `agentmain.py`: add default-disabled `structured_events`; route loop events into the existing per-task `display_queue` only when enabled.
- Create `tests/test_agent_loop_events.py`: verify event ordering and disabled-by-default behavior.
- Modify `frontends/heroui/bridge.py`: enable structured events for HeroUI agents, persist `events`, expose `eventSeq`, return `events` from session detail and polling endpoints.
- Modify `frontends/heroui/src/types.ts`: add bridge event fields and `tool.delta` only if needed; prefer `timeline.step` upserts.
- Modify `frontends/heroui/src/api.ts`: consume bridge `events` first; keep `parseGenericAgentOutputSteps` only for legacy messages with no event timeline.
- Modify `frontends/heroui/src/state.ts`: ensure repeated `timeline.step` events append/update tool output without losing order.
- Modify `frontends/heroui/src/components/ChatSurface.tsx`: render streaming tool cards from structured steps; avoid card creation for assistant final text.
- Modify `frontends/heroui/src/ga_bridge_contract.test.mjs`, `src/state.test.mjs`, `src/ui_contract.test.mjs`: lock the new bridge/UI contract.

---

### Task 1: Add Agent Loop Structured Event Tests

**Files:**
- Create: `tests/test_agent_loop_events.py`
- Modify later: `agent_loop.py`

- [ ] **Step 1: Write the failing test for event order**

Create `tests/test_agent_loop_events.py` with this content:

```python
import json
from dataclasses import dataclass

from agent_loop import BaseHandler, StepOutcome, agent_runner_loop


@dataclass
class FakeFunction:
    name: str
    arguments: str


@dataclass
class FakeToolCall:
    id: str
    function: FakeFunction


class FakeResponse:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.thinking = ""
        self.tool_calls = tool_calls or []


class FakeClient:
    def __init__(self):
        self.last_tools = ""
        self.calls = 0

    def chat(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            yield "I will run a command."
            return FakeResponse(
                content="I will run a command.",
                tool_calls=[
                    FakeToolCall(
                        id="call-1",
                        function=FakeFunction(
                            name="code_run",
                            arguments=json.dumps({"type": "python", "code": "print('ok')"}),
                        ),
                    )
                ],
            )
        yield "Done."
        return FakeResponse(content="Done.", tool_calls=[])


class FakeParent:
    task_dir = None


class EventHandler(BaseHandler):
    def __init__(self):
        self.parent = FakeParent()
        self._done_hooks = []
        self.current_turn = 0

    def do_code_run(self, args, response):
        yield "[stdout]\nok\n"
        return StepOutcome("ok", next_prompt="continue")

    def do_no_tool(self, args, response):
        yield "[Info] Final response to user.\n"
        return StepOutcome(response, next_prompt=None)


def test_agent_runner_loop_emits_ordered_structured_events():
    events = []
    handler = EventHandler()
    chunks = list(
        agent_runner_loop(
            FakeClient(),
            "system",
            "run it",
            handler,
            tools_schema=[],
            verbose=True,
            yield_info=True,
            event_sink=events.append,
        )
    )

    event_types = [event["type"] for event in events]

    assert "LLM Running" in "".join(str(chunk) for chunk in chunks)
    assert event_types == [
        "turn.start",
        "llm.start",
        "llm.end",
        "tool.start",
        "tool.delta",
        "tool.end",
        "turn.end",
        "turn.start",
        "llm.start",
        "llm.end",
        "agent.final",
        "turn.end",
        "agent.done",
    ]
    tool_start = events[event_types.index("tool.start")]
    tool_delta = events[event_types.index("tool.delta")]
    tool_end = events[event_types.index("tool.end")]
    final_event = events[event_types.index("agent.final")]

    assert tool_start["tool_name"] == "code_run"
    assert tool_start["args"] == {"type": "python", "code": "print('ok')"}
    assert tool_delta["delta"] == "[stdout]\nok\n"
    assert tool_end["status"] == "done"
    assert tool_end["result"] == "ok"
    assert final_event["text"] == "Done."


def test_agent_runner_loop_without_event_sink_keeps_legacy_chunks_only():
    handler = EventHandler()
    chunks = list(
        agent_runner_loop(
            FakeClient(),
            "system",
            "run it",
            handler,
            tools_schema=[],
            verbose=True,
            yield_info=True,
        )
    )

    assert any(isinstance(chunk, dict) and chunk.get("turn") == 1 for chunk in chunks)
    assert not any(isinstance(chunk, dict) and chunk.get("type") == "tool.start" for chunk in chunks)
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
rtk proxy powershell -Command "python -m pytest tests/test_agent_loop_events.py -q"
```

Expected failure:

```text
TypeError: agent_runner_loop() got an unexpected keyword argument 'event_sink'
```

- [ ] **Step 3: Do not edit production code in this task**

The failing test is the artifact for Task 1.

- [ ] **Step 4: Commit this task**

```powershell
rtk git add tests/test_agent_loop_events.py
rtk git commit -m "test: cover structured agent loop events"
```

---

### Task 2: Emit Optional Structured Events From `agent_loop.py`

**Files:**
- Modify: `agent_loop.py`
- Test: `tests/test_agent_loop_events.py`

- [ ] **Step 1: Add event helpers near `get_pretty_json`**

Insert this code in `agent_loop.py` after `get_pretty_json`:

```python
def _emit_event(event_sink, event_type, **data):
    if event_sink is None:
        return
    event = {"type": event_type, **data}
    try:
        event_sink(event)
    except Exception:
        pass


def _tool_kind(tool_name):
    name = str(tool_name or "").lower()
    if "code" in name or "shell" in name or "command" in name:
        return "command"
    if "web" in name or "scan" in name or "search" in name or "browse" in name:
        return "search"
    if "read" in name:
        return "read"
    if "file" in name or "write" in name or "patch" in name:
        return "file"
    return "tool"
```

- [ ] **Step 2: Extend the `agent_runner_loop` signature**

Change:

```python
def agent_runner_loop(client, system_prompt, user_input, handler, tools_schema, 
                      max_turns=40, verbose=True, initial_user_content=None, yield_info=False):
```

to:

```python
def agent_runner_loop(client, system_prompt, user_input, handler, tools_schema,
                      max_turns=40, verbose=True, initial_user_content=None,
                      yield_info=False, event_sink=None):
```

- [ ] **Step 3: Emit turn and LLM events**

Inside the `while turn < handler.max_turns:` block, after `turn += 1`, add:

```python
        _emit_event(event_sink, "turn.start", turn=turn)
```

Before `response_gen = client.chat(...)`, add:

```python
        _emit_event(event_sink, "llm.start", turn=turn)
```

After `_hook('llm_after', locals())`, add:

```python
        _emit_event(
            event_sink,
            "llm.end",
            turn=turn,
            text=getattr(response, "content", "") or "",
            has_tools=bool(getattr(response, "tool_calls", None)),
        )
```

- [ ] **Step 4: Emit tool lifecycle events around `handler.dispatch`**

Replace the current generator proxy block:

```python
            gen = handler.dispatch(tool_name, args, response, index=ii, tool_num=len(tool_calls))
            try:
                v = next(gen)
                def proxy(): yield v; return (yield from gen)
                if verbose: yield '`````\n'
                outcome = (yield from proxy()) if verbose else exhaust(proxy())
                if verbose: yield '`````\n'
            except StopIteration as e: outcome = e.value
```

with:

```python
            gen = handler.dispatch(tool_name, args, response, index=ii, tool_num=len(tool_calls))
            tool_started_at = __import__("time").time()
            if tool_name != "no_tool":
                _emit_event(
                    event_sink,
                    "tool.start",
                    turn=turn,
                    index=ii,
                    total=len(tool_calls),
                    tool_call_id=tid,
                    tool_name=tool_name,
                    tool_kind=_tool_kind(tool_name),
                    args={k: v for k, v in args.items() if k not in ("_index", "_tool_num")},
                )
            tool_chunks = []
            try:
                v = next(gen)
                def proxy():
                    yield v
                    return (yield from gen)
                if verbose:
                    yield '`````\n'
                proxy_gen = proxy()
                while True:
                    try:
                        chunk = next(proxy_gen)
                    except StopIteration as e:
                        outcome = e.value
                        break
                    if tool_name != "no_tool":
                        text_chunk = str(chunk)
                        tool_chunks.append(text_chunk)
                        _emit_event(
                            event_sink,
                            "tool.delta",
                            turn=turn,
                            index=ii,
                            tool_call_id=tid,
                            tool_name=tool_name,
                            delta=text_chunk,
                        )
                    if verbose:
                        yield chunk
                if verbose:
                    yield '`````\n'
            except StopIteration as e:
                outcome = e.value
            if tool_name != "no_tool":
                elapsed_ms = int((__import__("time").time() - tool_started_at) * 1000)
                failed = isinstance(getattr(outcome, "data", None), str) and "[Error]" in outcome.data
                _emit_event(
                    event_sink,
                    "tool.end",
                    turn=turn,
                    index=ii,
                    tool_call_id=tid,
                    tool_name=tool_name,
                    status="failed" if failed else "done",
                    result=getattr(outcome, "data", None),
                    output="".join(tool_chunks),
                    elapsed_ms=elapsed_ms,
                )
```

- [ ] **Step 5: Emit final and done events**

Immediately after:

```python
            if outcome.should_exit: 
                exit_reason = {'result': 'EXITED', 'data': outcome.data}; break
```

add:

```python
                _emit_event(event_sink, "agent.final", turn=turn, text=str(getattr(response, "content", "") or ""), exit_reason=exit_reason)
```

Immediately after:

```python
            if not outcome.next_prompt: 
                exit_reason = {'result': 'CURRENT_TASK_DONE', 'data': outcome.data}; break
```

add:

```python
                _emit_event(event_sink, "agent.final", turn=turn, text=str(getattr(response, "content", "") or ""), exit_reason=exit_reason)
```

Before `_hook('turn_after', locals())`, add:

```python
        _emit_event(event_sink, "turn.end", turn=turn, exit_reason=exit_reason)
```

Before `return exit_reason or {'result': 'MAX_TURNS_EXCEEDED'}`, add:

```python
    _emit_event(event_sink, "agent.done", turn=turn, exit_reason=exit_reason or {'result': 'MAX_TURNS_EXCEEDED'})
```

- [ ] **Step 6: Run the focused Python test**

Run:

```powershell
rtk proxy powershell -Command "python -m pytest tests/test_agent_loop_events.py -q"
```

Expected:

```text
2 passed
```

- [ ] **Step 7: Commit this task**

```powershell
rtk git add agent_loop.py tests/test_agent_loop_events.py
rtk git commit -m "feat: emit optional structured agent loop events"
```

---

### Task 3: Route Structured Events Through `GenericAgent.put_task`

**Files:**
- Modify: `agentmain.py`
- Test: `tests/test_agent_loop_events.py`

- [ ] **Step 1: Add default-disabled flags in `GenericAgent.__init__`**

In `agentmain.py`, inside `GenericAgent.__init__`, after:

```python
        self.inc_out = False; self.verbose = True; self.show_mode = 'text'
```

add:

```python
        self.structured_events = False
```

- [ ] **Step 2: Pass an event sink only when explicitly enabled**

In `GenericAgent.run`, immediately before `gen = agent_runner_loop(...)`, add:

```python
            event_sink = None
            if self.structured_events:
                def event_sink(event):
                    display_queue.put({'event': event, 'source': source})
```

Then add the keyword argument to the existing `agent_runner_loop` call:

```python
                event_sink=event_sink,
```

- [ ] **Step 3: Add a regression test for disabled default**

Append this test to `tests/test_agent_loop_events.py`:

```python
def test_generic_agent_structured_events_default_disabled():
    from agentmain import GenericAgent

    agent = GenericAgent.__new__(GenericAgent)

    assert not getattr(agent, "structured_events", False)
```

- [ ] **Step 4: Run the focused tests**

Run:

```powershell
rtk proxy powershell -Command "python -m pytest tests/test_agent_loop_events.py -q"
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit this task**

```powershell
rtk git add agentmain.py tests/test_agent_loop_events.py
rtk git commit -m "feat: gate structured events behind HeroUI opt in"
```

---

### Task 4: Persist Ordered Events in the HeroUI Bridge

**Files:**
- Modify: `frontends/heroui/bridge.py`
- Modify: `frontends/heroui/src/ga_bridge_contract.test.mjs`

- [ ] **Step 1: Write bridge contract assertions first**

In `frontends/heroui/src/ga_bridge_contract.test.mjs`, extend `HeroUI frontend has a dedicated GenericAgent bridge copy` with:

```javascript
  assert.match(bridge, /events: List\[dict\] = field\(default_factory=list\)/);
  assert.match(bridge, /event_seq: int = 0/);
  assert.match(bridge, /CREATE TABLE IF NOT EXISTS events/);
  assert.match(bridge, /def add_event/);
  assert.match(bridge, /def convert_agent_event/);
  assert.match(bridge, /agent\.structured_events = True/);
```

Extend `HeroUI api adapter speaks the GA bridge polling contract` with:

```javascript
  assert.match(api, /after_event=/);
  assert.match(api, /payload\.events/);
```

- [ ] **Step 2: Run the bridge contract test and verify it fails**

Run:

```powershell
rtk proxy powershell -Command "pnpm --dir frontends/heroui exec tsx --test src/ga_bridge_contract.test.mjs"
```

Expected failure includes at least one missing bridge assertion.

- [ ] **Step 3: Add event fields to `Session`**

In `frontends/heroui/bridge.py`, add to the `Session` dataclass:

```python
    events: List[dict] = field(default_factory=list)
    event_seq: int = 0
```

- [ ] **Step 4: Create the `events` table**

Inside `_init_store`, after the `messages` table creation, add:

```python
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    session_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    turn_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    ts REAL NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (session_id, seq),
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
                """
            )
```

- [ ] **Step 5: Load persisted events**

In `_load_sessions`, after loading `messages`, add:

```python
                event_rows = conn.execute(
                    "SELECT session_id, seq, turn_id, type, ts, payload FROM events ORDER BY session_id ASC, seq ASC"
                ).fetchall()
                for row in event_rows:
                    sess = sessions.get(row["session_id"])
                    if not sess:
                        continue
                    try:
                        event = json.loads(row["payload"])
                    except Exception:
                        event = {}
                    event["seq"] = int(row["seq"])
                    event["turn_id"] = row["turn_id"]
                    event["type"] = row["type"]
                    event["ts"] = float(row["ts"])
                    sess.events.append(event)
                    sess.event_seq = max(sess.event_seq, int(row["seq"]))
```

- [ ] **Step 6: Add event persistence helpers**

Add methods to `AgentManager` near `add_message`:

```python
    def add_event(self, sess: Session, event: dict, persist: bool = True) -> dict:
        sess.event_seq += 1
        stored = dict(event)
        stored["seq"] = sess.event_seq
        stored["ts"] = float(stored.get("ts") or time.time())
        stored["turn_id"] = str(stored.get("turn_id") or "")
        stored["type"] = str(stored.get("type") or "")
        sess.events.append(stored)
        sess.updated_at = time.time()
        if persist:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO events(session_id, seq, turn_id, type, ts, payload) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        sess.id,
                        stored["seq"],
                        stored["turn_id"],
                        stored["type"],
                        stored["ts"],
                        json.dumps(stored, ensure_ascii=False),
                    ),
                )
                conn.commit()
        return stored
```

- [ ] **Step 7: Convert agent events to frontend events**

Add this method to `AgentManager`:

```python
    def convert_agent_event(self, sess: Session, turn_id: str, response_id: str, raw: dict) -> Optional[dict]:
        event_type = str(raw.get("type") or "")
        ga_turn = int(raw.get("turn") or 0)
        now_iso = to_iso_timestamp(raw.get("ts") or time.time())
        if event_type == "tool.start":
            tool_name = str(raw.get("tool_name") or "tool")
            step_id = f"{response_id}:tool:{ga_turn}:{int(raw.get('index') or 0) + 1}"
            return {
                "type": "timeline.step",
                "turn_id": turn_id,
                "session_id": sess.id,
                "data": {
                    "id": step_id,
                    "turn_id": turn_id,
                    "response_id": response_id,
                    "kind": raw.get("tool_kind") or "tool",
                    "title": f"调用 {tool_name}",
                    "status": "running",
                    "summary": f"正在执行 {tool_name}",
                    "detail": "",
                    "input": json.dumps(raw.get("args") or {}, ensure_ascii=False, indent=2),
                    "tool_name": tool_name,
                    "tool_label": f"GA Turn {ga_turn}",
                    "created_at": now_iso,
                },
            }
        if event_type == "tool.delta":
            tool_name = str(raw.get("tool_name") or "tool")
            step_id = f"{response_id}:tool:{ga_turn}:{int(raw.get('index') or 0) + 1}"
            return {
                "type": "timeline.step",
                "turn_id": turn_id,
                "session_id": sess.id,
                "data": {
                    "id": step_id,
                    "turn_id": turn_id,
                    "response_id": response_id,
                    "kind": "tool",
                    "title": f"调用 {tool_name}",
                    "status": "running",
                    "summary": f"正在执行 {tool_name}",
                    "detail": "",
                    "output_delta": str(raw.get("delta") or ""),
                    "tool_name": tool_name,
                    "tool_label": f"GA Turn {ga_turn}",
                    "created_at": now_iso,
                },
            }
        if event_type == "tool.end":
            tool_name = str(raw.get("tool_name") or "tool")
            step_id = f"{response_id}:tool:{ga_turn}:{int(raw.get('index') or 0) + 1}"
            status = str(raw.get("status") or "done")
            return {
                "type": "timeline.step",
                "turn_id": turn_id,
                "session_id": sess.id,
                "data": {
                    "id": step_id,
                    "turn_id": turn_id,
                    "response_id": response_id,
                    "kind": "tool",
                    "title": f"调用 {tool_name}",
                    "status": "failed" if status == "failed" else "done",
                    "summary": "执行失败" if status == "failed" else "执行完成",
                    "detail": "",
                    "output": str(raw.get("output") or raw.get("result") or ""),
                    "error": str(raw.get("result") or "") if status == "failed" else "",
                    "elapsed_ms": raw.get("elapsed_ms"),
                    "tool_name": tool_name,
                    "tool_label": f"GA Turn {ga_turn}",
                    "created_at": now_iso,
                },
            }
        if event_type == "agent.final":
            return {
                "type": "answer.final",
                "turn_id": turn_id,
                "session_id": sess.id,
                "data": {
                    "text": str(raw.get("text") or ""),
                    "response_id": response_id,
                    "created_at": now_iso,
                },
            }
        return None
```

- [ ] **Step 8: Enable structured events only for HeroUI agents**

In `make_agent`, after `agent.inc_out = True`, add:

```python
            agent.structured_events = True
```

- [ ] **Step 9: Consume `{"event": ...}` items in `run_agent_turn`**

Inside the display queue loop in `run_agent_turn`, before handling `"turn"` and `"outputs"`, add:

```python
                        if isinstance(item.get("event"), dict):
                            converted = self.convert_agent_event(sess, turn_id, response_id, item["event"])
                            if converted:
                                with self.lock:
                                    self.add_event(sess, converted)
                                    sess.updated_at = time.time()
                            continue
```

- [ ] **Step 10: Return events from detail and polling endpoints**

In `messages`, add `after_event: int = 0` to the method signature and return payload:

```python
            events = [e for e in sess.events if int(e.get("seq", 0)) > after_event]
```

Include in the returned dict:

```python
                "events": events,
                "eventSeq": sess.event_seq,
```

Update `messages_handler` to parse:

```python
    after_event = int(request.query.get("after_event", "0") or 0)
```

and call:

```python
    return json_ok(manager.messages(sid, after=after, limit=limit, after_event=after_event))
```

In `get_session_handler`, include:

```python
        "events": list(sess.events),
        "eventSeq": sess.event_seq,
```

- [ ] **Step 11: Run bridge contract tests**

Run:

```powershell
rtk proxy powershell -Command "pnpm --dir frontends/heroui exec tsx --test src/ga_bridge_contract.test.mjs"
```

Expected:

```text
pass
```

- [ ] **Step 12: Commit this task**

```powershell
rtk git add frontends/heroui/bridge.py frontends/heroui/src/ga_bridge_contract.test.mjs
rtk git commit -m "feat: persist HeroUI structured agent events"
```

---

### Task 5: Consume Structured Events in the HeroUI API Adapter

**Files:**
- Modify: `frontends/heroui/src/types.ts`
- Modify: `frontends/heroui/src/api.ts`
- Modify: `frontends/heroui/src/ui_contract.test.mjs`

- [ ] **Step 1: Extend bridge response types in `api.ts`**

Add:

```typescript
type BridgeTimelineEvent = StreamEvent & {
  seq?: number;
  ts?: number;
};
```

Add `events?: BridgeTimelineEvent[]; eventSeq?: number;` to both `BridgeSessionDetail` and `BridgeMessages`.

- [ ] **Step 2: Add live event sequence tracking**

In `subscribeTurn`, extend `state`:

```typescript
    lastEventSeq: 0,
```

Change the poll URL to include event offset:

```typescript
      const response = await fetch(
        apiUrl(`/session/${encodeURIComponent(sessionId)}/messages?after=${state.lastMessageId}&after_event=${state.lastEventSeq}&limit=200`),
      );
```

- [ ] **Step 3: Emit bridge events before assistant final messages**

After reading `payload`, before `for (const message of payload.messages ?? [])`, add:

```typescript
      for (const event of payload.events ?? []) {
        if (typeof event.seq === "number") {
          state.lastEventSeq = Math.max(state.lastEventSeq, event.seq);
        }
        onEvent(event);
      }
```

- [ ] **Step 4: Build historical timeline from events first**

In `listTranscript`, change:

```typescript
    timeline: mapOutputsToTimeline(messages),
```

to:

```typescript
    timeline: mapEventsToTimeline(payload.events ?? [], messages),
```

Add:

```typescript
function mapEventsToTimeline(events: BridgeTimelineEvent[], messages: MessageRecord[]): ExecutionStep[] {
  const eventSteps = events
    .filter((event) => event.type === "timeline.step")
    .map((event) => event.data)
    .filter((data): data is Record<string, unknown> => Boolean(data));
  if (eventSteps.length > 0) {
    return eventSteps.map((data): ExecutionStep => ({
      id: String(data.id ?? ""),
      turn_id: typeof data.turn_id === "string" ? data.turn_id : undefined,
      response_id: typeof data.response_id === "string" ? data.response_id : undefined,
      kind: readStepKindFromData(data.kind),
      title: String(data.title ?? "执行步骤"),
      status: data.status === "failed" ? "failed" : data.status === "running" ? "running" : "done",
      summary: String(data.summary ?? ""),
      detail: String(data.detail ?? ""),
      input: typeof data.input === "string" ? data.input : undefined,
      output: typeof data.output === "string" ? data.output : undefined,
      error: typeof data.error === "string" ? data.error : undefined,
      elapsed_ms: typeof data.elapsed_ms === "number" ? data.elapsed_ms : undefined,
      tool_name: typeof data.tool_name === "string" ? data.tool_name : undefined,
      tool_label: typeof data.tool_label === "string" ? data.tool_label : undefined,
      created_at: typeof data.created_at === "string" ? data.created_at : undefined,
    }));
  }
  return mapOutputsToTimeline(messages);
}
```

Add:

```typescript
function readStepKindFromData(kind: unknown): ExecutionStep["kind"] {
  const value = String(kind ?? "tool");
  const allowed: ExecutionStep["kind"][] = ["thought", "search", "read", "file", "command", "skill", "tape", "agent", "help", "control", "tool", "phase", "complete"];
  return allowed.includes(value as ExecutionStep["kind"]) ? (value as ExecutionStep["kind"]) : "tool";
}
```

- [ ] **Step 5: Stop emitting parser-derived cards when structured events exist**

In the message loop inside `subscribeTurn`, wrap `emitBridgeOutputs`:

```typescript
        if (!(payload.events ?? []).some((event) => event.type === "timeline.step")) {
          emitBridgeOutputs(message, turnId, sessionId, responseId, createdAt, onEvent);
        }
```

- [ ] **Step 6: Update contract tests**

In `frontends/heroui/src/ui_contract.test.mjs`, add:

```javascript
  assert.match(api, /mapEventsToTimeline/);
  assert.match(api, /after_event=/);
  assert.match(api, /payload\.events/);
  assert.match(api, /return mapOutputsToTimeline\(messages\)/);
```

- [ ] **Step 7: Run frontend contract tests**

Run:

```powershell
rtk proxy powershell -Command "pnpm --dir frontends/heroui exec tsx --test src/ui_contract.test.mjs src/ga_bridge_contract.test.mjs"
```

Expected:

```text
pass
```

- [ ] **Step 8: Commit this task**

```powershell
rtk git add frontends/heroui/src/api.ts frontends/heroui/src/types.ts frontends/heroui/src/ui_contract.test.mjs frontends/heroui/src/ga_bridge_contract.test.mjs
rtk git commit -m "feat: consume HeroUI structured timeline events"
```

---

### Task 6: Preserve Incremental Tool Output in Frontend State

**Files:**
- Modify: `frontends/heroui/src/state.ts`
- Modify: `frontends/heroui/src/state.test.mjs`

- [ ] **Step 1: Write the failing state test**

Append to `frontends/heroui/src/state.test.mjs`:

```javascript
test("timeline.step output_delta appends to an existing tool card", () => {
  let state = createInitialTurnState("turn-1");
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "timeline.step",
    data: {
      id: "turn-1:tool:1",
      response_id: "turn-1:response:1",
      kind: "command",
      title: "调用 code_run",
      status: "running",
      summary: "正在执行 code_run",
      detail: "",
      input: "{}",
    },
  });
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "timeline.step",
    data: {
      id: "turn-1:tool:1",
      response_id: "turn-1:response:1",
      kind: "command",
      title: "调用 code_run",
      status: "running",
      summary: "正在执行 code_run",
      detail: "",
      output_delta: "line 1\n",
    },
  });
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "timeline.step",
    data: {
      id: "turn-1:tool:1",
      response_id: "turn-1:response:1",
      kind: "command",
      title: "调用 code_run",
      status: "done",
      summary: "执行完成",
      detail: "",
      output_delta: "line 2\n",
    },
  });

  assert.equal(state.steps[0].output, "line 1\nline 2\n");
  assert.equal(state.steps[0].status, "done");
});
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
rtk proxy powershell -Command "pnpm --dir frontends/heroui exec tsx --test src/state.test.mjs"
```

Expected failure:

```text
Expected values to be strictly equal
```

- [ ] **Step 3: Implement `output_delta` merge**

In `reduceTimelineStep`, before building `step`, find existing step:

```typescript
  const stepId = String(event.data.id ?? `${state.turnId}:step:${state.steps.length + 1}`);
  const current = state.steps.find((item) => item.id === stepId);
  const outputDelta = typeof event.data.output_delta === "string" ? event.data.output_delta : "";
```

Change the `id` and `output` fields inside `step`:

```typescript
    id: stepId,
```

```typescript
    output:
      typeof event.data.output === "string"
        ? event.data.output
        : outputDelta
          ? `${current?.output ?? ""}${outputDelta}`
          : current?.output,
```

Also preserve current `input` when a delta event has no input:

```typescript
    input: typeof event.data.input === "string" ? event.data.input : current?.input,
```

- [ ] **Step 4: Run the state tests**

Run:

```powershell
rtk proxy powershell -Command "pnpm --dir frontends/heroui exec tsx --test src/state.test.mjs"
```

Expected:

```text
pass
```

- [ ] **Step 5: Commit this task**

```powershell
rtk git add frontends/heroui/src/state.ts frontends/heroui/src/state.test.mjs
rtk git commit -m "feat: append streaming tool output in HeroUI state"
```

---

### Task 7: Final Integration Verification

**Files:**
- Verify only unless tests expose a defect.

- [ ] **Step 1: Run Python event tests**

```powershell
rtk proxy powershell -Command "python -m pytest tests/test_agent_loop_events.py -q"
```

Expected:

```text
3 passed
```

- [ ] **Step 2: Run HeroUI frontend tests**

```powershell
rtk proxy powershell -Command "pnpm --dir frontends/heroui test"
```

Expected:

```text
pass
```

- [ ] **Step 3: Build HeroUI**

```powershell
rtk proxy powershell -Command "pnpm --dir frontends/heroui build"
```

Expected:

```text
✓ built
```

The existing Vite large chunk warning is acceptable if it remains the only warning.

- [ ] **Step 4: Check whitespace**

```powershell
rtk proxy powershell -Command "git diff --check"
```

Expected: no output.

- [ ] **Step 5: Manual runtime check without starting services from this plan**

Because the user starts services manually, do not launch the server in the implementation agent. After the user starts HeroUI, validate one multi-tool prompt:

```text
请先用 Python 打印当前工作目录，再读取 package.json 的脚本字段，最后总结结果。
```

Expected UI behavior:

- The first tool card appears while the first tool is running.
- The second tool card appears after the first, not above it.
- Tool input and output are in structured collapsible sections.
- The assistant final answer appears below the tool cards as a normal reply.
- No `GenericAgent.outputs` raw card appears when structured events are present.

- [ ] **Step 6: Commit verification adjustments only if needed**

If verification required a small fix, commit only those changed files:

```powershell
rtk git status --short
rtk git add <changed-files>
rtk git commit -m "fix: stabilize HeroUI structured event integration"
```

---

## Self-Review

- **Spec coverage:** Covered backend event emission, HeroUI opt-in boundary, bridge persistence, frontend event consumption, incremental tool output, historical reload, and verification.
- **Scope control:** Other frontends are protected by `structured_events = False` by default. Only HeroUI bridge enables the new sink.
- **No unstable parsing as primary path:** `parseGenericAgentOutputSteps` remains only as a legacy fallback when no structured timeline events exist.
- **Type consistency:** Backend internal event names are converted by the bridge into existing frontend `StreamEvent` types, mainly `timeline.step` and `answer.final`.
- **Ordering:** Bridge assigns monotonically increasing `seq`; frontend polling uses `after_event`.
- **Persistence:** New `events` table reloads historical timeline after bridge restart.
- **Verification:** Plan includes focused Python tests, focused frontend tests, full HeroUI test suite, build, and `git diff --check`.
