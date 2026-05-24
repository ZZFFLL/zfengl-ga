# HeroUI Model Thinking and SSE Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HeroUI receive ordered GA execution events through a real SSE stream, show safe per-round model-process summaries, and stream final assistant text without relying on browser-side parsing of raw GenericAgent logs.

**Architecture:** Keep HeroUI as the only frontend that opts into structured events. Add an SSE transport beside the existing polling API, preserve SQLite `events.seq` as the ordering and reconnect cursor, and keep polling as fallback. Add backend-owned model output filtering so UI receives `answer.delta`, `answer.retract`, `timeline.step`, `answer.final`, and `turn.done` records from stable structured events instead of parsing `<thinking>`, `<tool_use>`, or verbose text logs.

**Tech Stack:** Python `queue`, `sqlite3`, `asyncio`, `aiohttp` SSE, existing `agent_loop.py` and `llmcore.py`; React + TypeScript HeroUI frontend; Node `tsx` tests and Python `pytest`.

---

## Success Criteria

- HeroUI prefers `EventSource` against a new `/session/{sid}/events` SSE endpoint and falls back to current polling when `EventSource` is unavailable or fails before receiving stream data.
- SSE events and polling events use the same persisted `seq` cursor, so refresh, disconnect, and reconnect cannot reorder or lose events.
- Every GA tool call remains represented by structured cards in source order.
- Every non-final model/tool round can show a collapsed "第N轮 模型过程" card with safe summary content and elapsed time.
- Final assistant prose is rendered as assistant message text, never as a model-process card.
- Final assistant prose streams through `answer.delta` where classification allows it, then `answer.final` reconciles the complete final text.
- If streamed text is later classified as a tool-call turn, frontend handles `answer.retract` and moves the completed model output into the model-process card produced by `llm.end`.
- Raw chain-of-thought is not exposed. The UI receives only safe summaries derived from `<summary>`, sanitized response text, or bounded first-line thinking summary.
- Existing non-HeroUI frontends remain unchanged because `GenericAgent.structured_events` stays default `False`.

## File Structure

- Create `agent_streaming.py`: backend-owned helpers for safe display filtering and bounded process-summary extraction.
- Modify `agent_loop.py`: emit clean model output deltas, safe model process summaries, elapsed time, and final reconciliation events through the existing optional `event_sink`.
- Modify `tests/test_agent_streaming.py`: unit tests for filtering `<thinking>`, `<tool_use>`, `<file_content>`, partial tags, and summary extraction.
- Modify `tests/test_agent_loop_events.py`: event-order tests for `llm.visible_delta`, `llm.end.thinking_summary`, `agent.final`, and legacy behavior when `event_sink` is absent.
- Modify `frontends/heroui/bridge.py`: add SSE subscriber hub and endpoint; convert new agent events to frontend stream events; preserve polling endpoint behavior.
- Modify `frontends/heroui/src/types.ts`: add `answer.retract` to the frontend stream event union.
- Modify `frontends/heroui/src/state.ts`: reduce `answer.retract`, keep final-answer reconciliation idempotent, and preserve timeline ordering.
- Modify `frontends/heroui/src/api.ts`: prefer native `EventSource`, parse SSE events, close on `turn.done`, and keep the existing polling path as fallback.
- Modify `frontends/heroui/src/components/ChatSurface.tsx`: keep existing rendering model; no frontend parsing of model protocol tags.
- Modify `frontends/heroui/src/api_stream.test.mjs`, `frontends/heroui/src/state.test.mjs`, `frontends/heroui/src/ga_bridge_contract.test.mjs`, `frontends/heroui/src/ui_contract.test.mjs`: lock transport, reducer, bridge, and UI contracts.
- Modify `docs/superpowers/specs/2026-05-24-ga-agent-event-flow.md`: update event contract and runtime validation instructions.

---

### Task 1: Add Safe Model Stream Filter Tests

**Files:**
- Create: `tests/test_agent_streaming.py`
- Create later: `agent_streaming.py`

- [ ] **Step 1: Write failing tests for safe filtering and summary extraction**

Create `tests/test_agent_streaming.py`:

```python
from agent_streaming import ModelDisplayStreamFilter, extract_model_process_summary


def drain_filter(chunks):
    stream_filter = ModelDisplayStreamFilter()
    visible = []
    for chunk in chunks:
        text = stream_filter.feed(chunk)
        if text:
            visible.append(text)
    tail = stream_filter.finish()
    if tail:
        visible.append(tail)
    return "".join(visible)


def test_filter_removes_thinking_tool_use_and_file_content_blocks():
    text = (
        "before "
        "<thinking>private reasoning</thinking>"
        "<summary>需要读取 package.json</summary>"
        "visible "
        "<tool_use>{\"name\":\"file_read\",\"arguments\":{\"path\":\"package.json\"}}</tool_use>"
        "<file_content>secret file body</file_content>"
        "after"
    )

    assert drain_filter([text]) == "<summary>需要读取 package.json</summary>visible after"


def test_filter_handles_protocol_tags_split_across_chunks():
    assert drain_filter([
        "hello <thin",
        "king>private</thinking> wor",
        "ld <tool_",
        "use>{}</tool_use> done",
    ]) == "hello world  done"


def test_extract_model_process_summary_prefers_summary_tag():
    assert extract_model_process_summary(
        "<summary>已经拿到脚本字段，准备总结</summary>\n正文",
        thinking="private reasoning",
    ) == "已经拿到脚本字段，准备总结"


def test_extract_model_process_summary_uses_bounded_thinking_first_line_when_no_summary():
    text = extract_model_process_summary(
        "正文没有摘要",
        thinking="第一行推理内容会被截断到安全长度。" * 10,
    )

    assert text.startswith("第一行推理内容")
    assert len(text) <= 90


def test_extract_model_process_summary_uses_visible_text_fallback():
    assert extract_model_process_summary(
        "我会先查看当前目录。\n然后调用工具。",
        thinking="",
    ) == "我会先查看当前目录。"
```

- [ ] **Step 2: Run the test and verify it fails because the helper module does not exist**

Run:

```powershell
rtk proxy powershell -Command "python -m pytest tests/test_agent_streaming.py -q"
```

Expected:

```text
ModuleNotFoundError: No module named 'agent_streaming'
```

- [ ] **Step 3: Commit the failing test**

Run:

```powershell
rtk git add tests/test_agent_streaming.py
rtk git commit -m "test: cover safe model stream filtering"
```

---

### Task 2: Implement Backend-Owned Model Output Filtering

**Files:**
- Create: `agent_streaming.py`
- Test: `tests/test_agent_streaming.py`

- [ ] **Step 1: Create `agent_streaming.py` with deterministic filtering**

Create `agent_streaming.py`:

```python
import re


_BLOCK_TAGS = ("thinking", "think", "tool_use", "tool_call", "file_content")
_SUMMARY_RE = re.compile(r"<summary>\s*([\s\S]*?)\s*</summary>", re.IGNORECASE)
_TAG_RE = re.compile(r"</?([a-zA-Z_][a-zA-Z0-9_]*)[^>]*>")


class ModelDisplayStreamFilter:
    """Remove GA protocol/private blocks from model text before UI streaming."""

    def __init__(self):
        self._buffer = ""
        self._blocked_tag = ""

    def feed(self, chunk):
        self._buffer += str(chunk or "")
        return self._drain(final=False)

    def finish(self):
        return self._drain(final=True)

    def _drain(self, final):
        visible = []
        while self._buffer:
            if self._blocked_tag:
                close_tag = f"</{self._blocked_tag}>"
                close_idx = self._buffer.lower().find(close_tag)
                if close_idx < 0:
                    if final:
                        self._buffer = ""
                        self._blocked_tag = ""
                    else:
                        self._buffer = self._buffer[-64:]
                    break
                self._buffer = self._buffer[close_idx + len(close_tag):]
                self._blocked_tag = ""
                continue

            tag_match = _TAG_RE.search(self._buffer)
            if not tag_match:
                if final:
                    visible.append(self._buffer)
                    self._buffer = ""
                else:
                    keep = min(len(self._buffer), 64)
                    emit_len = max(0, len(self._buffer) - keep)
                    visible.append(self._buffer[:emit_len])
                    self._buffer = self._buffer[emit_len:]
                break

            start, end = tag_match.span()
            tag_name = tag_match.group(1).lower()
            is_close = self._buffer[start + 1:start + 2] == "/"
            if tag_name not in _BLOCK_TAGS:
                visible.append(self._buffer[:end])
                self._buffer = self._buffer[end:]
                continue

            visible.append(self._buffer[:start])
            self._buffer = self._buffer[end:]
            if not is_close:
                self._blocked_tag = tag_name

        return "".join(visible)


def extract_model_process_summary(text, thinking="", limit=90):
    raw_text = str(text or "").strip()
    match = _SUMMARY_RE.search(raw_text)
    if match:
        return _single_line(match.group(1), limit)

    raw_thinking = str(thinking or "").strip()
    if raw_thinking:
        return _single_line(raw_thinking.splitlines()[0], limit)

    for line in raw_text.splitlines():
        line = _strip_protocol_tags(line).strip()
        if line:
            return _single_line(line, limit)
    return ""


def _single_line(text, limit):
    line = " ".join(str(text or "").split())
    if len(line) <= limit:
        return line
    return line[: limit - 1].rstrip() + "…"


def _strip_protocol_tags(text):
    out = str(text or "")
    for tag in _BLOCK_TAGS:
        out = re.sub(rf"<{tag}[^>]*>[\s\S]*?</{tag}>", "", out, flags=re.IGNORECASE)
    return out
```

- [ ] **Step 2: Run the focused tests**

Run:

```powershell
rtk proxy powershell -Command "python -m pytest tests/test_agent_streaming.py -q"
```

Expected:

```text
5 passed
```

- [ ] **Step 3: Commit the filter implementation**

Run:

```powershell
rtk git add agent_streaming.py tests/test_agent_streaming.py
rtk git commit -m "feat: add safe model stream filtering"
```

---

### Task 3: Add Agent Loop Tests for Model Deltas and Safe Thinking Summaries

**Files:**
- Modify: `tests/test_agent_loop_events.py`
- Modify later: `agent_loop.py`

- [ ] **Step 1: Extend `FakeResponse` to carry thinking text**

In `tests/test_agent_loop_events.py`, update `FakeResponse`:

```python
class FakeResponse:
    def __init__(self, content="", tool_calls=None, thinking=""):
        self.content = content
        self.thinking = thinking
        self.tool_calls = tool_calls or []
```

- [ ] **Step 2: Add a fake client that streams protocol text**

Append this class to `tests/test_agent_loop_events.py`:

```python
class StreamingProtocolClient:
    def __init__(self):
        self.last_tools = ""

    def chat(self, messages, tools):
        yield "Visible "
        yield "<thinking>private reasoning</thinking>"
        yield "<summary>准备调用命令</summary>"
        yield "text"
        return FakeResponse(
            content="<summary>准备调用命令</summary>Visible text",
            thinking="private reasoning",
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
```

- [ ] **Step 3: Add the failing structured delta test**

Append this test:

```python
def test_agent_runner_loop_emits_clean_model_delta_and_thinking_summary():
    events = []
    handler = EventHandler()

    list(
        agent_runner_loop(
            StreamingProtocolClient(),
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
    deltas = [event["delta"] for event in events if event["type"] == "llm.visible_delta"]
    llm_end = next(event for event in events if event["type"] == "llm.end")

    assert "llm.visible_delta" in event_types
    assert "".join(deltas) == "Visible <summary>准备调用命令</summary>text"
    assert "private reasoning" not in "".join(deltas)
    assert llm_end["summary"] == "准备调用命令"
    assert llm_end["thinking_summary"] == "准备调用命令"
```

- [ ] **Step 4: Run the test and verify it fails because `llm.visible_delta` is not emitted**

Run:

```powershell
rtk proxy powershell -Command "python -m pytest tests/test_agent_loop_events.py::test_agent_runner_loop_emits_clean_model_delta_and_thinking_summary -q"
```

Expected:

```text
AssertionError: assert 'llm.visible_delta' in [...]
```

- [ ] **Step 5: Commit the failing test**

Run:

```powershell
rtk git add tests/test_agent_loop_events.py
rtk git commit -m "test: cover clean model delta events"
```

---

### Task 4: Emit Clean Model Deltas and Process Summaries From `agent_loop.py`

**Files:**
- Modify: `agent_loop.py`
- Test: `tests/test_agent_loop_events.py`, `tests/test_agent_streaming.py`

- [ ] **Step 1: Import the filtering helpers**

Add near the imports in `agent_loop.py`:

```python
from agent_streaming import ModelDisplayStreamFilter, extract_model_process_summary
```

- [ ] **Step 2: Replace the `yield from response_gen` block with explicit iteration**

In `agent_runner_loop`, replace the current `if verbose: response = yield from response_gen ... else: response = exhaust(response_gen)` block with:

```python
        stream_filter = ModelDisplayStreamFilter()
        if verbose:
            try:
                while True:
                    chunk = next(response_gen)
                    clean_delta = stream_filter.feed(chunk)
                    if clean_delta:
                        _emit_event(event_sink, "llm.visible_delta", turn=turn, delta=clean_delta)
                    yield chunk
            except StopIteration as e:
                response = e.value
            clean_tail = stream_filter.finish()
            if clean_tail:
                _emit_event(event_sink, "llm.visible_delta", turn=turn, delta=clean_tail)
            yield '\n\n'
        else:
            raw_chunks = []
            try:
                while True:
                    chunk = next(response_gen)
                    raw_chunks.append(str(chunk))
                    clean_delta = stream_filter.feed(chunk)
                    if clean_delta:
                        _emit_event(event_sink, "llm.visible_delta", turn=turn, delta=clean_delta)
            except StopIteration as e:
                response = e.value
            clean_tail = stream_filter.finish()
            if clean_tail:
                _emit_event(event_sink, "llm.visible_delta", turn=turn, delta=clean_tail)
            cleaned = _clean_content(getattr(response, "content", "") or "".join(raw_chunks))
            if cleaned:
                yield cleaned + '\n'
```

- [ ] **Step 3: Add summary fields to `llm.end`**

Immediately before `_emit_event(... "llm.end" ...)`, add:

```python
        response_text = getattr(response, "content", "") or ""
        thinking_text = getattr(response, "thinking", "") or ""
        process_summary = extract_model_process_summary(response_text, thinking=thinking_text)
```

Then change the existing `llm.end` event fields to:

```python
            text=response_text,
            has_tools=bool(getattr(response, "tool_calls", None)),
            elapsed_ms=llm_elapsed_ms,
            summary=process_summary,
            thinking_summary=process_summary,
```

- [ ] **Step 4: Run focused Python tests**

Run:

```powershell
rtk proxy powershell -Command "python -m pytest tests/test_agent_streaming.py tests/test_agent_loop_events.py -q"
```

Expected:

```text
8 passed
```

- [ ] **Step 5: Commit the agent-loop event enhancement**

Run:

```powershell
rtk git add agent_loop.py tests/test_agent_loop_events.py agent_streaming.py tests/test_agent_streaming.py
rtk git commit -m "feat: emit clean model stream events"
```

---

### Task 5: Add Bridge SSE Contract Tests

**Files:**
- Modify: `frontends/heroui/src/ga_bridge_contract.test.mjs`
- Modify later: `frontends/heroui/bridge.py`

- [ ] **Step 1: Add a source contract test for the SSE endpoint and hub**

Append to `frontends/heroui/src/ga_bridge_contract.test.mjs`:

```javascript
test("HeroUI bridge exposes persisted structured events through an SSE endpoint", () => {
  const bridge = readFileSync(new URL("../bridge.py", import.meta.url), "utf8");

  assert.match(bridge, /class EventStreamHub/);
  assert.match(bridge, /async def events_handler\(request\):/);
  assert.match(bridge, /text\/event-stream/);
  assert.match(bridge, /id: \{event\["seq"\]\}/);
  assert.match(bridge, /app\.router\.add_get\("\/session\/\{sid\}\/events", events_handler\)/);
  assert.match(bridge, /event_hub\.publish\(stored\)/);
});
```

- [ ] **Step 2: Run the contract test and verify it fails**

Run:

```powershell
rtk proxy powershell -Command "pnpm --dir frontends/heroui exec tsx --test src/ga_bridge_contract.test.mjs"
```

Expected:

```text
not ok ... HeroUI bridge exposes persisted structured events through an SSE endpoint
```

- [ ] **Step 3: Commit the failing bridge contract**

Run:

```powershell
rtk git add frontends/heroui/src/ga_bridge_contract.test.mjs
rtk git commit -m "test: cover HeroUI SSE event endpoint contract"
```

---

### Task 6: Implement Persisted SSE Event Transport in the HeroUI Bridge

**Files:**
- Modify: `frontends/heroui/bridge.py`
- Test: `frontends/heroui/src/ga_bridge_contract.test.mjs`

- [ ] **Step 1: Add `EventStreamHub` after `WsHub`**

Insert after the existing `hub = WsHub()`:

```python
class EventStreamHub:
    def __init__(self):
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.queues: Set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.queues.discard(queue)

    def publish(self, event: dict) -> None:
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self._publish(dict(event)), self.loop)

    async def _publish(self, event: dict) -> None:
        dead = set()
        for queue in list(self.queues):
            try:
                if queue.full():
                    with contextlib.suppress(asyncio.QueueEmpty):
                        queue.get_nowait()
                queue.put_nowait(event)
            except Exception:
                dead.add(queue)
        self.queues.difference_update(dead)


event_hub = EventStreamHub()
```

- [ ] **Step 2: Publish every stored event from `add_event`**

In `AgentManager.add_event`, after persistence succeeds and before returning `stored`, add:

```python
        event_hub.publish(stored)
```

Keep this after `self._persist_event(sess, stored)` so SSE never sends an event that cannot be replayed from SQLite.

- [ ] **Step 3: Add SSE formatting helpers**

Add before route handlers:

```python
def sse_format_event(event: dict) -> bytes:
    data = json.dumps(event, ensure_ascii=False, default=str)
    return f'id: {event["seq"]}\nevent: message\ndata: {data}\n\n'.encode("utf-8")


async def sse_write_event(resp: web.StreamResponse, event: dict) -> None:
    await resp.write(sse_format_event(event))
```

- [ ] **Step 4: Add `events_handler`**

Add near `messages_handler`:

```python
async def events_handler(request):
    sid = request.match_info["sid"]
    after_event = int(request.query.get("after_event") or request.headers.get("Last-Event-ID") or 0)
    turn_id = request.query.get("turn_id") or ""

    resp = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
    await resp.prepare(request)

    def matches(event: dict) -> bool:
        if event.get("session_id") != sid:
            return False
        if turn_id and event.get("turn_id") != turn_id:
            return False
        return True

    backlog = manager.messages(sid, after=0, limit=0, after_event=after_event).get("events", [])
    for event in backlog:
        if matches(event):
            await sse_write_event(resp, event)
            if event.get("type") in {"turn.done", "turn.error"} and turn_id:
                await resp.write_eof()
                return resp

    queue = event_hub.subscribe()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
            except asyncio.TimeoutError:
                await resp.write(b": heartbeat\n\n")
                continue
            if not matches(event):
                continue
            await sse_write_event(resp, event)
            if event.get("type") in {"turn.done", "turn.error"} and turn_id:
                break
    except (asyncio.CancelledError, ConnectionResetError, RuntimeError):
        pass
    finally:
        event_hub.unsubscribe(queue)
        with contextlib.suppress(Exception):
            await resp.write_eof()
    return resp
```

- [ ] **Step 5: Register the route and startup loop**

In `create_app`, add:

```python
    app.router.add_get("/session/{sid}/events", events_handler)
```

In the existing startup hook where `hub.loop` is set, also set:

```python
        event_hub.loop = asyncio.get_running_loop()
```

- [ ] **Step 6: Run bridge contract tests**

Run:

```powershell
rtk proxy powershell -Command "pnpm --dir frontends/heroui exec tsx --test src/ga_bridge_contract.test.mjs"
```

Expected:

```text
all subtests pass
```

- [ ] **Step 7: Commit SSE transport**

Run:

```powershell
rtk git add frontends/heroui/bridge.py frontends/heroui/src/ga_bridge_contract.test.mjs
rtk git commit -m "feat: expose HeroUI structured events over SSE"
```

---

### Task 7: Prefer EventSource in the HeroUI Frontend With Polling Fallback

**Files:**
- Modify: `frontends/heroui/src/api_stream.test.mjs`
- Modify: `frontends/heroui/src/api.ts`

- [ ] **Step 1: Add a failing EventSource test**

Append to `frontends/heroui/src/api_stream.test.mjs`:

```javascript
test("subscribeTurn prefers EventSource SSE and closes on turn.done", async () => {
  const { subscribeTurn } = await import("./api.ts");
  const events = [];
  const originalEventSource = globalThis.EventSource;
  const originalFetch = globalThis.fetch;
  const created = [];

  class FakeEventSource {
    constructor(url) {
      this.url = url;
      this.closed = false;
      this.onmessage = null;
      this.onerror = null;
      created.push(this);
    }

    close() {
      this.closed = true;
    }
  }

  globalThis.EventSource = FakeEventSource;
  globalThis.fetch = async () => {
    throw new Error("polling should not run when EventSource is available");
  };

  try {
    const source = subscribeTurn("ga|sess-1|1", (event) => events.push(event));
    assert.equal(created.length, 1);
    assert.match(created[0].url, /\/session\/sess-1\/events\?/);
    assert.match(created[0].url, /turn_id=ga%7Csess-1%7C1/);
    created[0].onmessage({
      data: JSON.stringify({
        seq: 2,
        type: "turn.done",
        turn_id: "ga|sess-1|1",
        session_id: "sess-1",
        data: { ok: true },
      }),
    });

    assert.equal(events[0].type, "turn.done");
    assert.equal(created[0].closed, true);
    source.close();
  } finally {
    globalThis.EventSource = originalEventSource;
    globalThis.fetch = originalFetch;
  }
});
```

- [ ] **Step 2: Add a fallback test**

Append:

```javascript
test("subscribeTurn falls back to polling when EventSource is unavailable", async () => {
  const { subscribeTurn } = await import("./api.ts");
  const events = [];
  const originalEventSource = globalThis.EventSource;
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;

  delete globalThis.EventSource;
  globalThis.window = { setTimeout: () => 0 };
  globalThis.fetch = async () => ({
    ok: true,
    async json() {
      return {
        status: "idle",
        messages: [{ id: 2, role: "assistant", content: "done", ts: 1 }],
        events: [],
      };
    },
  });

  try {
    const source = subscribeTurn("ga|sess-1|1", (event) => events.push(event));
    await Promise.resolve();
    assert.equal(events.some((event) => event.type === "answer.final"), true);
    source.close();
  } finally {
    globalThis.EventSource = originalEventSource;
    globalThis.fetch = originalFetch;
    globalThis.window = originalWindow;
  }
});
```

- [ ] **Step 3: Run the new tests and verify they fail**

Run:

```powershell
rtk proxy powershell -Command "pnpm --dir frontends/heroui exec tsx --test src/api_stream.test.mjs"
```

Expected: the EventSource test fails because `subscribeTurn()` still uses polling.

- [ ] **Step 4: Split polling into a named helper**

In `frontends/heroui/src/api.ts`, rename the current `subscribeTurn` implementation to:

```typescript
function subscribeTurnPolling(
  turnId: string,
  onEvent: (event: StreamEvent) => void,
  onError?: (error: Event) => void,
): EventSource {
```

Keep the existing polling body unchanged inside this helper.

- [ ] **Step 5: Add the EventSource implementation**

Add this new exported `subscribeTurn` above `subscribeTurnPolling`:

```typescript
export function subscribeTurn(
  turnId: string,
  onEvent: (event: StreamEvent) => void,
  onError?: (error: Event) => void,
): EventSource {
  if (typeof EventSource === "undefined") {
    return subscribeTurnPolling(turnId, onEvent, onError);
  }

  const { sessionId } = parseTurnId(turnId);
  const afterEvent = TURN_EVENT_CURSORS.get(turnId) ?? 0;
  const params = new URLSearchParams({
    after_event: String(afterEvent),
    turn_id: turnId,
  });
  const source = new EventSource(apiUrl(`/session/${encodeURIComponent(sessionId)}/events?${params.toString()}`));
  let closed = false;
  let sawEvent = false;

  const close = () => {
    closed = true;
    TURN_EVENT_CURSORS.delete(turnId);
    source.close();
  };

  source.onmessage = (message) => {
    if (closed) {
      return;
    }
    try {
      const event = JSON.parse(message.data) as StreamEvent & { seq?: number };
      sawEvent = true;
      if (typeof event.seq === "number") {
        TURN_EVENT_CURSORS.set(turnId, Math.max(TURN_EVENT_CURSORS.get(turnId) ?? 0, event.seq));
      }
      onEvent(event);
      if (event.type === "turn.done" || event.type === "turn.error") {
        close();
      }
    } catch (error) {
      onError?.(toEvent(error));
      close();
    }
  };

  source.onerror = (error) => {
    if (closed) {
      return;
    }
    if (!sawEvent) {
      source.close();
      const fallback = subscribeTurnPolling(turnId, onEvent, onError);
      (source as EventSource & { close: () => void }).close = fallback.close.bind(fallback);
      return;
    }
    onError?.(toEvent(error));
    close();
  };

  return { close } as EventSource;
}
```

- [ ] **Step 6: Run API stream tests**

Run:

```powershell
rtk proxy powershell -Command "pnpm --dir frontends/heroui exec tsx --test src/api_stream.test.mjs"
```

Expected:

```text
all subtests pass
```

- [ ] **Step 7: Commit frontend SSE subscription**

Run:

```powershell
rtk git add frontends/heroui/src/api.ts frontends/heroui/src/api_stream.test.mjs
rtk git commit -m "feat: prefer SSE for HeroUI turn streams"
```

---

### Task 8: Convert Model Delta, Retract, and Summary Events in the Bridge

**Files:**
- Modify: `frontends/heroui/bridge.py`
- Modify: `frontends/heroui/src/ga_bridge_contract.test.mjs`

- [ ] **Step 1: Add a bridge conversion contract test**

Append to `frontends/heroui/src/ga_bridge_contract.test.mjs`:

```javascript
test("HeroUI bridge maps model deltas, retracts, and process summaries", () => {
  const bridge = readFileSync(new URL("../bridge.py", import.meta.url), "utf8");

  assert.match(bridge, /event_type == "llm\.visible_delta"/);
  assert.match(bridge, /"type": "answer\.delta"/);
  assert.match(bridge, /"type": "answer\.retract"/);
  assert.match(bridge, /thinking_summary/);
  assert.match(bridge, /第\{ga_turn\}轮 模型过程/);
});
```

- [ ] **Step 2: Run the contract test and verify it fails**

Run:

```powershell
rtk proxy powershell -Command "pnpm --dir frontends/heroui exec tsx --test src/ga_bridge_contract.test.mjs"
```

Expected: the new bridge mapping contract fails.

- [ ] **Step 3: Map `llm.visible_delta` to `answer.delta`**

In `AgentManager.convert_agent_event`, add before the `llm.end` block:

```python
        if event_type == "llm.visible_delta":
            return {
                "type": "answer.delta",
                "turn_id": turn_id,
                "session_id": sess.id,
                "data": {
                    "delta": str(raw.get("delta") or ""),
                    "response_id": response_id,
                    "created_at": created_at,
                },
            }
```

- [ ] **Step 4: Emit `answer.retract` and a model-process card when `llm.end` has tools**

Replace the current `llm.end` conversion block with:

```python
        if event_type == "llm.end":
            if not raw.get("has_tools"):
                return None
            text = str(raw.get("text") or "")
            summary = str(raw.get("summary") or "") or _extract_summary_text(text) or "模型过程"
            thinking_summary = str(raw.get("thinking_summary") or summary)
            detail_lines = []
            if summary:
                detail_lines.append(f"摘要：{summary}")
            if thinking_summary and thinking_summary != summary:
                detail_lines.append(f"过程：{thinking_summary}")
            if text.strip():
                detail_lines.append(text)
            return {
                "type": "timeline.step",
                "turn_id": turn_id,
                "session_id": sess.id,
                "data": {
                    "id": f"{response_id}:phase:{ga_turn}:llm",
                    "turn_id": turn_id,
                    "response_id": response_id,
                    "kind": "phase",
                    "title": f"第{ga_turn}轮 模型过程" if ga_turn else summary,
                    "status": "done",
                    "summary": summary,
                    "detail": "\n\n".join(detail_lines),
                    "elapsed_ms": raw.get("elapsed_ms"),
                    "default_open": False,
                    "created_at": created_at,
                    "retract_response_id": response_id,
                },
            }
```

- [ ] **Step 5: Emit `answer.retract` from `run_agent_turn` before storing tool-turn model cards**

In `run_agent_turn`, when `converted` is a `timeline.step` whose `data.retract_response_id` is present, store a retract event first:

```python
                            if converted and converted.get("type") == "timeline.step":
                                data = converted.get("data") or {}
                                retract_response_id = data.pop("retract_response_id", "")
                                if retract_response_id:
                                    with self.lock:
                                        self.add_event(sess, {
                                            "type": "answer.retract",
                                            "turn_id": turn_id,
                                            "session_id": sess.id,
                                            "data": {"response_id": retract_response_id},
                                        })
```

Keep the existing `self.add_event(sess, converted)` immediately after this block.

- [ ] **Step 6: Run bridge contract tests**

Run:

```powershell
rtk proxy powershell -Command "pnpm --dir frontends/heroui exec tsx --test src/ga_bridge_contract.test.mjs"
```

Expected:

```text
all subtests pass
```

- [ ] **Step 7: Commit bridge model event conversion**

Run:

```powershell
rtk git add frontends/heroui/bridge.py frontends/heroui/src/ga_bridge_contract.test.mjs
rtk git commit -m "feat: map model stream events for HeroUI"
```

---

### Task 9: Add Frontend State Support for `answer.retract`

**Files:**
- Modify: `frontends/heroui/src/types.ts`
- Modify: `frontends/heroui/src/state.ts`
- Modify: `frontends/heroui/src/state.test.mjs`

- [ ] **Step 1: Add a failing reducer test**

Append to `frontends/heroui/src/state.test.mjs`:

```javascript
test("answer.retract clears only the matching streaming draft", () => {
  let state = createInitialTurnState("turn-1");
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "answer.delta",
    data: { response_id: "turn-1:response:1", delta: "draft text" },
  });
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "answer.retract",
    data: { response_id: "turn-1:response:1" },
  });

  assert.equal(state.answer, "");
  assert.equal(state.currentResponseId, "");
  assert.equal(state.responses.length, 0);
});
```

- [ ] **Step 2: Run the reducer test and verify it fails**

Run:

```powershell
rtk proxy powershell -Command "pnpm --dir frontends/heroui exec tsx --test src/state.test.mjs"
```

Expected: TypeScript or reducer failure because `answer.retract` is not supported.

- [ ] **Step 3: Add the event type**

In `frontends/heroui/src/types.ts`, update `StreamEventType`:

```typescript
export type StreamEventType =
  | "answer.delta"
  | "answer.retract"
  | "answer.final"
  | "phase.update"
  | "timeline.step"
  | "tool.start"
  | "tool.end"
  | "artifact.created"
  | "suggestion.created"
  | "turn.error"
  | "turn.done";
```

- [ ] **Step 4: Reduce `answer.retract`**

In `applyStreamEvent`, add this case after `answer.delta`:

```typescript
    case "answer.retract": {
      const responseId = readResponseId(event.data.response_id);
      if (!responseId || responseId !== state.currentResponseId) {
        return state;
      }
      return {
        ...state,
        currentResponseId: "",
        answer: "",
      };
    }
```

- [ ] **Step 5: Run reducer tests**

Run:

```powershell
rtk proxy powershell -Command "pnpm --dir frontends/heroui exec tsx --test src/state.test.mjs"
```

Expected:

```text
all subtests pass
```

- [ ] **Step 6: Commit frontend retract support**

Run:

```powershell
rtk git add frontends/heroui/src/types.ts frontends/heroui/src/state.ts frontends/heroui/src/state.test.mjs
rtk git commit -m "feat: support retracting streamed model drafts"
```

---

### Task 10: Lock UI Contract for Safe Model Process Cards

**Files:**
- Modify: `frontends/heroui/src/ui_contract.test.mjs`
- Modify: `frontends/heroui/src/components/ChatSurface.tsx`

- [ ] **Step 1: Add a UI contract test**

Append to `frontends/heroui/src/ui_contract.test.mjs`:

```javascript
test("model process cards stay collapsed and final answers stay normal messages", () => {
  assert.match(components, /isModelSummaryStep/);
  assert.match(components, /default_open: false|default_open/);
  assert.match(components, /readStepHeadline/);
  assert.match(components, /第N轮|第\{ga_turn\}轮|模型过程/);
  assert.doesNotMatch(components, /<thinking>/);
  assert.doesNotMatch(components, /<tool_use>/);
  assert.doesNotMatch(components, /file_content/);
});
```

- [ ] **Step 2: Run UI contract tests**

Run:

```powershell
rtk proxy powershell -Command "pnpm --dir frontends/heroui exec tsx --test src/ui_contract.test.mjs"
```

Expected: pass if Task 8 reused existing collapsed model card behavior; if it fails because the literal `模型过程` is only in `bridge.py`, change the assertion to read `bridge.py` in this same test file and assert the backend card title there.

- [ ] **Step 3: Keep `ChatSurface.tsx` free of raw protocol parsing**

If Task 10 Step 2 fails due to missing backend source read, add this near the top of `ui_contract.test.mjs`:

```javascript
const bridge = readFileSync(new URL("../bridge.py", import.meta.url), "utf8");
```

Then change the card-title assertion to:

```javascript
assert.match(bridge, /模型过程/);
```

- [ ] **Step 4: Commit the UI contract**

Run:

```powershell
rtk git add frontends/heroui/src/ui_contract.test.mjs frontends/heroui/src/components/ChatSurface.tsx
rtk git commit -m "test: lock safe model process UI contract"
```

---

### Task 11: Update the Agent Event Flow Documentation

**Files:**
- Modify: `docs/superpowers/specs/2026-05-24-ga-agent-event-flow.md`

- [ ] **Step 1: Update transport section**

Replace the current line that says HeroUI uses HTTP polling with:

```markdown
   - `subscribeTurn()` prefers `/session/{sid}/events?after_event={event_seq}&turn_id={turn_id}` through browser `EventSource`.
   - The SSE endpoint and polling endpoint both use persisted `events.seq` as the cursor.
   - If `EventSource` is unavailable or fails before receiving stream data, `subscribeTurn()` falls back to `/session/{sid}/messages?after=...&after_event=...`.
```

- [ ] **Step 2: Update internal event table**

Add these rows to the internal event table:

```markdown
| `llm.visible_delta` | During model text streaming after backend protocol filtering | `turn`, `delta` |
| `llm.end` | After model response is received | `turn`, `text`, `has_tools`, `elapsed_ms`, `summary`, `thinking_summary` |
```

Remove the older `llm.end` row that lacks `summary` and `thinking_summary`.

- [ ] **Step 3: Update bridge conversion table**

Add:

```markdown
| `llm.visible_delta` | `answer.delta` | Temporary streaming assistant draft; retracted if the turn later contains tool calls |
| `llm.end` with tools | `answer.retract` then `timeline.step` | Remove temporary answer draft and create collapsed "第N轮 模型过程" card |
```

- [ ] **Step 4: Update raw output boundary**

Replace the old token-streaming limitation with:

```markdown
- During structured runs, UI-visible model text must come from backend-filtered `llm.visible_delta`, not raw `partial.content`.
- Raw model protocol blocks such as `<thinking>`, `<tool_use>`, and `<file_content>` are filtered before any frontend event is emitted.
- Final assistant text uses `answer.delta` for streaming when available and `answer.final` as the reconciliation source of truth.
```

- [ ] **Step 5: Commit the documentation update**

Run:

```powershell
rtk git add docs/superpowers/specs/2026-05-24-ga-agent-event-flow.md
rtk git commit -m "docs: update HeroUI streaming event contract"
```

---

### Task 12: Full Verification and Review

**Files:**
- Verify all modified files from Tasks 1-11.

- [ ] **Step 1: Run Python event tests**

Run:

```powershell
rtk proxy powershell -Command "python -m pytest tests/test_agent_streaming.py tests/test_agent_loop_events.py -q"
```

Expected:

```text
all tests pass
```

- [ ] **Step 2: Run HeroUI frontend tests**

Run:

```powershell
rtk proxy powershell -Command "pnpm --dir frontends/heroui test"
```

Expected:

```text
all subtests pass
```

- [ ] **Step 3: Build HeroUI**

Run:

```powershell
rtk proxy powershell -Command "pnpm --dir frontends/heroui build"
```

Expected:

```text
✓ built
```

The existing Vite chunk-size warning is acceptable if it remains the only warning.

- [ ] **Step 4: Check whitespace**

Run:

```powershell
rtk git diff --check
```

Expected: no output.

- [ ] **Step 5: Manual runtime validation after the user starts HeroUI**

Use this prompt in HeroUI after the user manually starts the app:

```text
请先用 Python 打印当前工作目录，再读取 package.json 的脚本字段，最后总结结果。
```

Expected UI behavior:

- The active turn connects through `/session/{sid}/events`.
- "正在理解请求" appears only as a compact phase line.
- The final answer streams in the assistant message area.
- If a streamed draft becomes a tool turn, the draft disappears and a collapsed "第N轮 模型过程" card appears before the tool card.
- Tool cards remain ordered and show input, output, status, and elapsed time.
- The final answer is a normal assistant message, not a card.

- [ ] **Step 6: Commit final verification notes if docs changed during validation**

If runtime validation changes only documentation, run:

```powershell
rtk git add docs/superpowers/specs/2026-05-24-ga-agent-event-flow.md
rtk git commit -m "docs: record HeroUI streaming validation"
```

If runtime validation finds a code defect, fix it with a failing test first, then commit the code and test together.

---

## Plan Self-Review

**Spec coverage:** Covered SSE transport, persisted ordering, EventSource fallback, backend-owned model filtering, safe per-round process summaries, final answer streaming, draft retraction, non-HeroUI isolation, tests, docs, and manual validation.

**Placeholder scan:** No placeholder markers, no deferred implementation wording, no vague test instructions, and no unspecified validation commands.

**Type consistency:** Internal events use `llm.visible_delta`, existing `llm.end`, existing `agent.final`, and frontend additions use `answer.retract`; `response_id`, `turn_id`, `seq`, `elapsed_ms`, `summary`, and `thinking_summary` are named consistently across Python and TypeScript tasks.

**Scope check:** This is one cohesive plan because both requested capabilities share the same event pipeline: `llmcore/client stream -> agent_loop event_sink -> HeroUI bridge persistence/SSE -> frontend state/rendering`.
