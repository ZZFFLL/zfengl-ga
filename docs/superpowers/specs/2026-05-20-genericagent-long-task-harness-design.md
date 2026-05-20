# GenericAgent Long Task Harness Design

## Goal

Add a lightweight Long Task Harness to GenericAgent so long-running tasks can survive context trimming, process restarts, and multi-turn drift without turning GA into a new framework.

This design focuses on two user-visible failures:

1. When GA is closed or restarted, the next session cannot tell whether the previous task completed, stopped for user input, failed, or was interrupted.
2. During long exploration or implementation work, user-supplied details and verified findings are not stored reliably enough, so the task drifts, repeats work, or asks the user for details that were already provided.

The harness should also reduce repeated empty loops, false completion claims, poor resume quality, and low-quality long-term memory extraction.

## Non-Goals

- Do not replace `agent_runner_loop`.
- Do not introduce LangGraph, OpenAI Agents SDK, or another external agent framework.
- Do not redesign Plan Mode, Goal Mode, Reflect Mode, or Goal Hive in this pass.
- Do not add a WebUI surface in this pass.
- Do not persist raw chain-of-thought.
- Do not make MemPalace a required dependency.
- Do not change GA's current tool schema in the first pass unless a test proves it is necessary.

## Current GA Context Model

GA currently has several context layers:

- `agentmain.py`
  - Builds system prompt with date and `get_global_memory()`.
  - Appends a shortened `[USER]: ...` line into `self.history`.
  - Creates a fresh `GenericAgentHandler` per user task.
  - Preserves previous `key_info` across user tasks when present.
- `agent_loop.py`
  - Runs the turn loop.
  - Sends only the latest `next_prompt` into the next request.
  - Relies on the LLM session backend to retain full message history.
- `ga.py`
  - Stores task-local `history_info`.
  - Extracts one `<summary>` line per turn and appends it as `[Agent] ...`.
  - Builds `### [WORKING MEMORY]` from recent `history_info`, folded older context, and optional `key_info`.
  - Injects soft review, hard `ask_user`, global memory refresh, checkpoint reminders, and Plan hints at fixed turn cadences.
- `llmcore.py`
  - Owns backend chat history.
  - Compresses old `<history>`, `<key_info>`, and `<earlier_context>` blocks.
  - Trims old messages when the configured context budget is exceeded.

The weak point is that important task state exists mostly as prompt text. Once context is long enough, user details, verified findings, and completion evidence are vulnerable to summarization, truncation, or model omission.

## Design Principle

The harness should make long-task state a runtime artifact, not a memory of the model.

The model should receive a compact, stable `ContextPack` each turn, but the source of truth should be persisted structured files under `temp/long_task_harness/`.

## Architecture

Create a small module:

```text
harness/
  __init__.py
  long_task.py
tests/
  test_long_task_harness.py
```

`harness/long_task.py` owns:

- `LongTaskHarness`
- `RunState`
- `RunEvent`
- `ContextPack`
- JSON load/save helpers
- deterministic state update rules

GA integration stays surgical:

- `agentmain.py`
  - Create or resume a harness run before starting `agent_runner_loop`.
  - Record raw user input in the run state before shortening it for `history_info`.
  - Mark stale runs on startup when previous heartbeat indicates interruption.
- `ga.py`
  - Attach the harness to `GenericAgentHandler`.
  - Add the harness `ContextPack` to `_get_anchor_prompt()`.
  - Notify the harness from `turn_end_callback()`.
  - Sync `do_update_working_checkpoint()` into harness state.
- `agent_loop.py`
  - No first-pass changes unless tests show the harness needs a loop-level callback.
- `llmcore.py`
  - No first-pass changes. The harness should work even when backend history is trimmed.

## Persistence Layout

Use a run-local directory:

```text
temp/long_task_harness/
  active_run.json
  runs/
    <run_id>/
      state.json
      events.jsonl
      context_pack.txt
```

`active_run.json` points to the latest run:

```json
{
  "run_id": "20260520-153000-abc123",
  "state_path": "temp/long_task_harness/runs/20260520-153000-abc123/state.json",
  "status": "running",
  "updated_at": "2026-05-20T15:30:00+08:00"
}
```

## RunState

`state.json` is the durable source of truth:

```json
{
  "run_id": "20260520-153000-abc123",
  "status": "running",
  "created_at": "2026-05-20T15:30:00+08:00",
  "updated_at": "2026-05-20T15:35:00+08:00",
  "last_heartbeat_at": "2026-05-20T15:35:00+08:00",
  "last_turn": 18,
  "source": "user",
  "goal": "用户原始任务目标",
  "latest_user_input": "用户最近一次完整输入",
  "user_constraints": [],
  "current_phase": "exploring",
  "verified_facts": [],
  "decisions": [],
  "failed_paths": [],
  "open_questions": [],
  "next_actions": [],
  "evidence_refs": [],
  "last_progress_turn": 18,
  "completion": {
    "claimed": false,
    "verified": false,
    "reason": "",
    "evidence_refs": []
  },
  "termination_reason": ""
}
```

Allowed `status` values:

- `running`
- `waiting_user`
- `completed_unverified`
- `completed_verified`
- `failed`
- `aborted`
- `max_turns`
- `stale`

Only `completed_verified` means GA has evidence that the task is actually done.

## RunEvent

`events.jsonl` records one event per line. Events should be concise and structured:

```json
{
  "type": "turn_end",
  "turn": 18,
  "timestamp": "2026-05-20T15:35:00+08:00",
  "summary": "已确认 pytest 通过，准备更新文档",
  "tool_calls": ["code_run"],
  "tool_result_digest": "66 passed in 3.02s",
  "state_delta": {
    "verified_facts": ["tests/test_long_run_context.py passed with 66 tests"],
    "next_actions": ["inspect git diff"]
  }
}
```

The harness must not store raw tool output by default. It stores digests and paths. Full raw output remains in existing GA logs.

## ContextPack

`ContextPack` is a compact prompt block injected into `_get_anchor_prompt()`:

```text
<long_task_harness>
status: running
goal: ...
phase: ...
user_constraints:
- ...
verified_facts:
- ...
failed_paths:
- ...
open_questions:
- ...
next_actions:
- ...
completion_gate: not_verified
</long_task_harness>
```

Rules:

- Keep it short enough to survive repeated injection.
- Prefer facts with evidence over narrative.
- Do not include raw logs, full file contents, or long reasoning.
- Include user constraints every time.
- Include failed paths when they prevent repeated work.
- Include open questions only when they require user or environment confirmation.

## State Update Rules

The first implementation should use deterministic rules rather than a second LLM call.

From raw user input:

- Store the full latest user input.
- If the input contains clear constraints, append them to `user_constraints`.
- If it appears to change the task goal, update `goal` and record a decision.

From `update_working_checkpoint`:

- Merge `key_info` into `user_constraints`, `verified_facts`, `failed_paths`, and `next_actions` using simple labeled-section parsing.
- Store unparsed content as a `decision` or `verified_fact` only when it contains concrete task facts.

From `turn_end_callback`:

- Record `summary`.
- Record tool names.
- Digest tool results.
- Update heartbeat and `last_turn`.
- If tool result includes clear success signals such as `passed`, `success`, `0 failed`, or file paths, add a verified fact or evidence ref.
- If result includes clear failure signals such as `failed`, `error`, `Traceback`, or non-zero exit indicators, add a failed path with the tool name and digest.

Completion detection:

- If `exit_reason` is `CURRENT_TASK_DONE`, mark `completed_unverified`.
- Promote to `completed_verified` only when one of these exists:
  - test pass evidence
  - explicit verification subagent verdict
  - user confirmation
  - file/output evidence matching a known acceptance criterion

Interruption detection:

- On GA startup, if `active_run.json` points to `running` or `waiting_user` and `last_heartbeat_at` is older than a configured threshold, mark it `stale`.
- Do not auto-resume without telling the model and user-facing channel what was found.

## Resume Behavior

When a stale or waiting run exists, GA should be able to surface:

```text
[Harness Resume]
上次任务: ...
状态: stale
最后轮次: 87
最后进展: ...
未解决问题:
- ...
建议下一步:
- resume
- summarize and close
- start fresh
```

First pass behavior can be conservative:

- In interactive mode, inject the resume summary into the next prompt.
- In task/reflect mode, log the stale run and start a new run unless a future flag explicitly resumes it.

## Progress Detection

The harness should distinguish turn count from progress.

Track `last_progress_turn`. A turn counts as progress when it adds at least one of:

- new verified fact
- new evidence ref
- new completed action
- new accepted decision
- new user constraint
- new failed path that rules out an approach

If no progress occurs for a configured number of turns, inject a stronger anti-stall prompt:

```text
[Harness Stall]
最近 N 轮没有新增 verified_facts/evidence_refs/decisions。
禁止重复同一路径。请执行以下之一：
1. 切换策略并说明差异
2. 读取关键日志/文件获取新证据
3. ask_user 请求缺失决策
4. 若任务已完成，提供验证证据
```

This should complement, not replace, the existing cadence prompts in `ga.py`.

## Error Handling

Harness failures must not break GA task execution.

- If harness load fails, write a warning and continue without harness.
- If harness save fails, append a warning to `next_prompt` only once per run.
- If JSON is corrupt, move it to `state.corrupt.<timestamp>.json` and create a new run.
- If event append fails, continue running and mark harness as degraded.

## Security and Privacy

- Do not persist raw chain-of-thought.
- Do not persist full tool output unless a later explicit design adds opt-in raw artifact capture.
- Do not store secrets from tool results. First pass can use simple redaction for common token/password/key patterns.
- Store paths and short digests instead of full file contents.

## Tests

Minimum tests:

- Creates a new run and writes `active_run.json`.
- Records full raw user input without using the shortened `[USER]` history line.
- Builds a compact `ContextPack` with goal, constraints, facts, failed paths, and next actions.
- Marks stale run when heartbeat is old.
- Marks `completed_unverified` on task done without evidence.
- Promotes to `completed_verified` when test pass evidence exists.
- Records progress when verified facts or evidence refs are added.
- Emits anti-stall prompt when no progress is detected for the configured interval.
- Syncs `update_working_checkpoint` into run state.
- Continues without raising when state file is corrupt or unwritable.

Existing regression tests to keep running:

```bash
python -m pytest tests/test_long_run_context.py tests/test_goal_mode.py tests/test_webui_server.py -q
```

New focused tests:

```bash
python -m pytest tests/test_long_task_harness.py -q
```

## Implementation Phases

### Phase 1: Passive Harness

Add `harness/long_task.py` and tests. It can create runs, record events, build `ContextPack`, and detect stale/completed states. Integrate only enough to observe turns and inject context.

Expected outcome:

- GA can tell what happened to the previous run.
- GA receives stable task facts even if backend LLM history is trimmed.

### Phase 2: Progress and Completion Gates

Add deterministic progress detection and completion verification state.

Expected outcome:

- GA can distinguish false completion from verified completion.
- GA can detect empty loops based on lack of state change, not just turn count.

### Phase 3: Resume UX and Mode Coverage

Refine resume behavior for interactive, task, reflect, Plan, and Goal mode.

Expected outcome:

- Restarted GA can present a useful recovery summary.
- Background modes can avoid accidentally continuing stale runs without explicit intent.

## Acceptance Criteria

The design is successful when:

- A killed GA process leaves a durable run state that the next GA startup can classify.
- Full user follow-up details are available in harness state even when `history_info` stores only a shortened `[USER]` line.
- A long run can retain verified facts, failed paths, open questions, and next actions independently of LLM backend history.
- A model completion claim without verification is visible as `completed_unverified`, not silently treated as done.
- Existing long-run cadence tests still pass.
- Harness failure does not prevent normal GA execution.

## Recommended First Implementation Scope

Implement only Phase 1 and the minimal pieces of Phase 2 needed for completion status.

Do not implement UI, multi-agent orchestration changes, MemPalace sync, or external framework adapters in the first implementation.
