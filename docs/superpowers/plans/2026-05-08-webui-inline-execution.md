# WebUI Inline Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the React WebUI render assistant answers smoothly while showing each GA turn's execution details inline under the message, without changing GA core files.

**Architecture:** Keep GA's current text queue protocol intact. Add a WebUI projection layer in `frontends/webui_server.py` that parses one raw GA snapshot into visible chat content and turn-level execution metadata, then render that metadata inline in `frontends/webui/src/App.tsx` while preserving the existing smooth text reveal.

**Tech Stack:** Python stdlib HTTP/SSE server, unittest, React, TypeScript, Tailwind CSS, Vite.

---

### Task 1: Backend Projection Contract

**Files:**
- Modify: `tests/test_webui_server.py`
- Modify: `frontends/webui_server.py`

- [ ] **Step 1: Write failing backend tests**

Add tests under `WebUILogParserTests` for:

```python
def test_parse_execution_log_ignores_turn_marker_inside_fenced_tool_result(self):
    text = (
        "**LLM Running (Turn 1) ...**\n"
        "<summary>\n运行脚本\n</summary>\n"
        "🛠️ Tool: `code_run`  📥 args:\n"
        "````text\n"
        '{"script": "echo nested"}\n'
        "````\n"
        "`````\n"
        "[Stdout]\n"
        "LLM Running (Turn 999) ... should stay inside result\n"
        "`````\n"
        "最终回答。"
    )
    turns = parse_execution_log(text)
    self.assertEqual([turn["turn"] for turn in turns], [1])
    self.assertIn("Turn 999", turns[0]["tool_calls"][0]["result"])
```

```python
def test_project_ga_response_marks_only_latest_turn_active(self):
    projection = project_ga_response(
        "**LLM Running (Turn 1) ...**\n"
        "<summary>读取文件</summary>\n"
        "已读取。\n"
        "**LLM Running (Turn 2) ...**\n"
        "<summary>运行测试</summary>\n",
        running=True,
    )
    self.assertEqual(projection["content"], "已读取。")
    self.assertEqual([turn["state"] for turn in projection["turns"]], ["completed", "active"])
```

```python
def test_project_ga_response_returns_structured_ask_user_interaction(self):
    projection = project_ga_response(
        "**LLM Running (Turn 2) ...**\n"
        "🛠️ Tool: `ask_user`  📥 args:\n"
        "````text\n"
        '{"question": "请选择方向", "candidates": ["A", "B"]}\n'
        "````\n"
        "`````\nWaiting for your answer ...\n`````\n",
        running=False,
    )
    self.assertEqual(projection["interaction"]["type"], "ask_user")
    self.assertEqual(projection["interaction"]["question"], "请选择方向")
    self.assertEqual(projection["interaction"]["candidates"], ["A", "B"])
    self.assertIn("1. A", projection["content"])
```

- [ ] **Step 2: Run tests to verify failure**

Run: `py -3 -m unittest tests.test_webui_server.WebUILogParserTests -v`

Expected: fail because `project_ga_response` does not exist and turn markers inside fenced blocks are still treated as real turns.

- [ ] **Step 3: Implement backend projection**

In `frontends/webui_server.py`:

- Add fenced block masking helper used by `parse_execution_log`.
- Add `_parse_ask_user_payload(tool_call)`.
- Add `_decorate_turns(turns, running=False)`.
- Add `project_ga_response(raw_text, running=False)` returning `{"content", "turns", "interaction"}`.
- Keep `extract_visible_reply_text()` and `parse_execution_log()` as public compatibility functions.

- [ ] **Step 4: Run backend parser tests**

Run: `py -3 -m unittest tests.test_webui_server.WebUILogParserTests -v`

Expected: all parser tests pass.

### Task 2: SSE Projection Wiring

**Files:**
- Modify: `frontends/webui_server.py`
- Modify: `tests/test_webui_server.py`

- [ ] **Step 1: Add streaming-path test**

Add a manager streaming test that asserts `execution_update` includes turn `state` values during `next`, and the persisted assistant message stores the final decorated execution log.

- [ ] **Step 2: Wire `drain_task()` to projection**

In `drain_task()`:

- On `next`, call `project_ga_response(task.current_response, running=True)`.
- Emit `message_delta` from `projection["content"]`.
- Emit `execution_update` from `projection["turns"]`.
- On `done`, call `project_ga_response(task.current_response, running=False)`.
- Persist `projection["content"]` and `projection["turns"]`.

- [ ] **Step 3: Run full backend tests**

Run: `py -3 -m unittest tests.test_webui_server -v`

Expected: all backend tests pass.

### Task 3: Frontend Inline Execution UI

**Files:**
- Modify: `frontends/webui/src/types.ts`
- Modify: `frontends/webui/src/App.tsx`
- Modify: `frontends/webui/src/execution-panel-state.ts`
- Modify: `frontends/webui/src/styles.css`

- [ ] **Step 1: Update TypeScript types**

Add optional fields:

```ts
state?: "active" | "completed";
summary?: string;
result_preview?: string;
result_length?: number;
```

on execution turns/tool calls as needed, while keeping existing fields compatible.

- [ ] **Step 2: Replace primary execution chip with inline turns**

In `ChatMessageView`, render `InlineExecutionTurns` below the assistant bubble when `effectiveExecutionLog.length > 0`. Keep a compact details button only as a secondary affordance.

- [ ] **Step 3: Build inline components**

Create local components in `App.tsx`:

- `InlineExecutionTurns`
- `InlineExecutionTurn`

Behavior:

- Completed turns default collapsed.
- Active latest turn default open.
- Tool call args/results remain nested collapsible details.
- `state === "active"` shows a subtle pulse badge.

- [ ] **Step 4: Remove layout pressure from right panel**

Keep `ExecutionPanel` available but avoid making it the primary visible process UI. The inline block should be usable without opening the right panel.

- [ ] **Step 5: Run frontend checks**

Run:

```powershell
npm test
npm run build
```

from `frontends/webui`.

Expected: tests pass and Vite build succeeds.

### Task 4: Final Verification

**Files:**
- Verify only.

- [ ] **Step 1: Run backend tests**

Run: `py -3 -m unittest tests.test_webui_server -v`

Expected: all tests pass.

- [ ] **Step 2: Check git diff**

Run: `git diff -- frontends/webui_server.py tests/test_webui_server.py frontends/webui/src/types.ts frontends/webui/src/App.tsx frontends/webui/src/execution-panel-state.ts frontends/webui/src/styles.css docs/superpowers/plans/2026-05-08-webui-inline-execution.md`

Expected: only planned files changed.
