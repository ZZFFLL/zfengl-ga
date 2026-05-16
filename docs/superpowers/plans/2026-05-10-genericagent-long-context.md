# GenericAgent Long-Run Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Increase GenericAgent's long-run turn capacity and checkpoint pressure while preserving the existing runtime mode design.

**Architecture:** Keep the existing Agent loop and handler architecture. Update only the explicit normal/Plan thresholds in `agentmain.py` and `ga.py`, and add focused unit tests around `GenericAgentHandler.turn_end_callback` and `_get_anchor_prompt`.

**Tech Stack:** Python, unittest/pytest-compatible tests, existing GenericAgent runtime modules.

---

## File Map

- Modify: `agentmain.py`
  - Change the normal runtime call from `max_turns=140` to `max_turns=240`.

- Modify: `ga.py`
  - Add module-level constants for long-run thresholds.
  - Change Plan-mode max turns from `200` to `480`.
  - Change normal working-memory direct history window to `80`.
  - Add Plan working-memory direct history window of `120`.
  - Change non-Plan `ask_user` pressure to turn `120`, then repeat every `60` turns.
  - Add non-Plan checkpoint reminder every `30` turns.
  - Change non-Plan stall warning to every `10` turns.
  - Change non-Plan global memory refresh to every `20` turns.
  - Change Plan-mode `ask_user` pressure to turn `180`, then repeat every `90` turns.
  - Add Plan-mode checkpoint reminder every `30` turns.
  - Change Plan file read hint to every `10` turns starting at turn `10`.

- Create: `tests/test_long_run_context.py`
  - Test normal-mode threshold prompt behavior.
  - Test Plan-mode threshold prompt behavior.
  - Test checkpoint reminders.
  - Test working-memory direct window size.

---

### Task 1: Add Failing Long-Run Threshold Tests

**Files:**
- Create: `tests/test_long_run_context.py`

- [ ] **Step 1: Write tests for existing desired behavior**

Create `tests/test_long_run_context.py` with:

```python
import unittest
from types import SimpleNamespace

import agentmain
from ga import GenericAgentHandler


class LongRunContextTests(unittest.TestCase):
    def make_handler(self):
        parent = SimpleNamespace(verbose=False, task_dir=None)
        return GenericAgentHandler(parent, [], "./temp")

    def make_response(self, summary="继续执行"):
        return SimpleNamespace(content=f"<summary>{summary}</summary>")

    def callback_prompt(self, handler, turn, plan=False):
        if plan:
            handler.working["in_plan_mode"] = "./temp/plan.md"
        return handler.turn_end_callback(
            self.make_response(),
            [{"tool_name": "no_tool", "args": {}}],
            [],
            turn,
            "NEXT",
            {},
        )

    def test_normal_mode_long_run_ask_user_pressure_starts_at_turn_120_then_repeats_every_60(self):
        handler = self.make_handler()

        prompt_70 = self.callback_prompt(handler, 70)
        prompt_120 = self.callback_prompt(handler, 120)
        prompt_121 = self.callback_prompt(handler, 121)
        prompt_180 = self.callback_prompt(handler, 180)

        self.assertNotIn("必须总结情况进行ask_user", prompt_70)
        self.assertIn("已连续执行第 120 轮", prompt_120)
        self.assertIn("必须总结情况进行ask_user", prompt_120)
        self.assertNotIn("必须总结情况进行ask_user", prompt_121)
        self.assertIn("已连续执行第 180 轮", prompt_180)

    def test_normal_mode_max_turns_is_240(self):
        self.assertEqual(agentmain.NORMAL_RUNNER_MAX_TURNS, 240)

    def test_normal_mode_checkpoint_every_30_turns(self):
        handler = self.make_handler()

        prompt = self.callback_prompt(handler, 30)

        self.assertIn("update_working_checkpoint", prompt)
        self.assertIn("用户补充的关键约束", prompt)
        self.assertIn("已验证结论", prompt)

    def test_plan_mode_max_turns_and_ask_user_pressure_starts_at_180_then_repeats_every_90(self):
        handler = self.make_handler()
        handler.enter_plan_mode("./temp/plan.md")

        prompt_100 = self.callback_prompt(handler, 100, plan=True)
        prompt_180 = self.callback_prompt(handler, 180, plan=True)
        prompt_181 = self.callback_prompt(handler, 181, plan=True)
        prompt_270 = self.callback_prompt(handler, 270, plan=True)

        self.assertEqual(handler.max_turns, 480)
        self.assertNotIn("必须 ask_user 汇报进度并确认是否继续", prompt_100)
        self.assertIn("Plan模式已运行 180 轮", prompt_180)
        self.assertIn("必须 ask_user 汇报进度并确认是否继续", prompt_180)
        self.assertNotIn("必须 ask_user 汇报进度并确认是否继续", prompt_181)
        self.assertIn("Plan模式已运行 270 轮", prompt_270)

    def test_plan_mode_checkpoint_every_30_turns(self):
        handler = self.make_handler()
        handler.enter_plan_mode("./temp/plan.md")

        prompt = self.callback_prompt(handler, 30, plan=True)

        self.assertIn("update_working_checkpoint", prompt)
        self.assertIn("计划文件之外的用户关键约束", prompt)
        self.assertIn("已验证执行状态", prompt)

    def test_normal_working_memory_keeps_latest_80_lines_directly(self):
        history = [f"[Agent] step {i}" for i in range(90)]
        handler = GenericAgentHandler(SimpleNamespace(verbose=False, task_dir=None), history, "./temp")
        handler.current_turn = 1

        prompt = handler._get_anchor_prompt()

        self.assertIn("[Agent] step 10", prompt)
        self.assertIn("[Agent] step 89", prompt)
        self.assertIn("<earlier_context>", prompt)
        self.assertNotIn("[Agent] step 9\n[Agent] step 10", prompt)

    def test_plan_working_memory_keeps_latest_120_lines_directly(self):
        history = [f"[Agent] step {i}" for i in range(130)]
        handler = GenericAgentHandler(SimpleNamespace(verbose=False, task_dir=None), history, "./temp")
        handler.current_turn = 1
        handler.working["in_plan_mode"] = "./temp/plan.md"

        prompt = handler._get_anchor_prompt()

        self.assertIn("[Agent] step 10", prompt)
        self.assertIn("[Agent] step 129", prompt)
        self.assertIn("<earlier_context>", prompt)
        self.assertNotIn("[Agent] step 9\n[Agent] step 10", prompt)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail before implementation**

Run:

```powershell
python -m pytest tests/test_long_run_context.py -q
```

Expected:

- The new tests fail because the current code still uses the older long-run limits and checkpoint intervals.

---

### Task 2: Implement Long-Run Constants And Thresholds

**Files:**
- Modify: `agentmain.py`
- Modify: `ga.py`

- [ ] **Step 1: Update normal runtime max turns**

In `agentmain.py`, change the `agent_runner_loop` call:

```python
gen = agent_runner_loop(self.llmclient, sys_prompt, raw_query, 
                    handler, TOOLS_SCHEMA, max_turns=240, verbose=self.verbose)
```

- [ ] **Step 2: Add constants near the top of `ga.py` after imports**

Add:

```python
NORMAL_WORKING_MEMORY_WINDOW = 80
PLAN_WORKING_MEMORY_WINDOW = 120
NORMAL_LONG_RUN_ASK_USER_TURN = 120
NORMAL_ASK_USER_REPEAT_EVERY = 60
NORMAL_CHECKPOINT_EVERY = 30
NORMAL_STALL_WARNING_EVERY = 10
NORMAL_GLOBAL_MEMORY_EVERY = 20
PLAN_MAX_TURNS = 480
PLAN_LONG_RUN_ASK_USER_TURN = 180
PLAN_ASK_USER_REPEAT_EVERY = 90
PLAN_CHECKPOINT_EVERY = 30
PLAN_HINT_START_TURN = 10
PLAN_HINT_EVERY = 10
```

- [ ] **Step 3: Update Plan-mode max turns**

Ensure `enter_plan_mode` uses the shared constant:

```python
self.working['in_plan_mode'] = plan_path; self.max_turns = PLAN_MAX_TURNS
```

- [ ] **Step 4: Update working-memory direct window**

Change `_get_anchor_prompt` from:

```python
h = self.history_info; W = 30
```

to:

```python
h = self.history_info
W = PLAN_WORKING_MEMORY_WINDOW if self._in_plan_mode() else NORMAL_WORKING_MEMORY_WINDOW
```

- [ ] **Step 5: Add checkpoint prompt helper**

Add this method before `turn_end_callback`:

```python
    def _checkpoint_prompt(self, plan=False):
        if plan:
            return (
                "\n\n[DANGER] 长程Plan任务checkpoint：如有新增信息，请调用 update_working_checkpoint "
                "保存计划文件之外的用户关键约束、当前目标、已验证执行状态、失败路径和下一步。"
            )
        return (
            "\n\n[DANGER] 长程任务checkpoint：如有新增信息，请调用 update_working_checkpoint "
            "保存用户补充的关键约束、当前目标、已验证结论、失败路径和下一步。"
        )
```

- [ ] **Step 6: Update non-Plan threshold branch**

Replace:

```python
if turn % 65 == 0 and (not _plan):
    next_prompt += f"\n\n[DANGER] 已连续执行第 {turn} 轮。必须总结情况进行ask_user，不允许继续重试。"
elif turn % 7 == 0:
    next_prompt += f"\n\n[DANGER] 已连续执行第 {turn} 轮。禁止无效重试。若无有效进展，必须切换策略：1. 探测物理边界 2. 请求用户协助。如有需要，可调用 update_working_checkpoint 保存关键上下文。"
elif turn % 10 == 0: next_prompt += get_global_memory()
```

with:

```python
if (
    not _plan
    and turn >= NORMAL_LONG_RUN_ASK_USER_TURN
    and (turn - NORMAL_LONG_RUN_ASK_USER_TURN) % NORMAL_ASK_USER_REPEAT_EVERY == 0
):
    next_prompt += f"\n\n[DANGER] 已连续执行第 {turn} 轮。必须总结情况进行ask_user，不允许继续重试。"
elif not _plan and turn % NORMAL_STALL_WARNING_EVERY == 0:
    next_prompt += f"\n\n[DANGER] 已连续执行第 {turn} 轮。禁止无效重试。若无有效进展，必须切换策略：1. 探测物理边界 2. 请求用户协助。如有需要，可调用 update_working_checkpoint 保存关键上下文。"
elif not _plan and turn % NORMAL_GLOBAL_MEMORY_EVERY == 0:
    next_prompt += get_global_memory()
if not _plan and turn % NORMAL_CHECKPOINT_EVERY == 0:
    next_prompt += self._checkpoint_prompt(plan=False)
```

- [ ] **Step 7: Update Plan threshold branch**

Replace:

```python
if _plan and turn >= PLAN_HINT_START_TURN and turn % PLAN_HINT_EVERY == 0:
    next_prompt = f"[Plan Hint] 正在计划模式。必须 file_read({_plan}) 确认当前步骤，回复开头引用：📌 当前步骤：...\n\n" + next_prompt
```

with:

```python
if _plan and turn % PLAN_CHECKPOINT_EVERY == 0:
    next_prompt += self._checkpoint_prompt(plan=True)
if (
    _plan
    and turn >= PLAN_LONG_RUN_ASK_USER_TURN
    and (turn - PLAN_LONG_RUN_ASK_USER_TURN) % PLAN_ASK_USER_REPEAT_EVERY == 0
):
    next_prompt += f"\n\n[DANGER] Plan模式已运行 {turn} 轮，已达上限。必须 ask_user 汇报进度并确认是否继续。"
```

---

### Task 3: Verify And Commit

**Files:**
- Test: `tests/test_long_run_context.py`
- Test existing relevant backend projection tests if needed.

- [ ] **Step 1: Run focused tests**

Run:

```powershell
python -m pytest tests/test_long_run_context.py -q
```

Expected:

- `6 passed`

- [ ] **Step 2: Run relevant existing tests**

Run:

```powershell
python -m pytest tests/test_webui_server.py -q
```

Expected:

- All tests in `tests/test_webui_server.py` pass.

- [ ] **Step 3: Inspect final diff**

Run:

```powershell
git diff -- agentmain.py ga.py tests/test_long_run_context.py
```

Expected:

- Only the planned thresholds, checkpoint prompt helper, and focused tests changed.

- [ ] **Step 4: Commit implementation**

Run:

```powershell
git add -- agentmain.py ga.py tests/test_long_run_context.py
git commit -m "feat: extend GA long-run context thresholds"
```

Expected:

- A new implementation commit on `zfengl-ga-long`.

---

## Self-Review

Spec coverage:

- Normal `max_turns=240`: Task 2 Step 1.
- Normal `ask_user_at=120` and repeat every `60`: Task 2 Step 6, Task 1 test.
- Normal `checkpoint_every=30`: Task 2 Step 6, Task 1 test.
- Normal `stall_warning_every=10`: Task 2 Step 6.
- Normal `global_memory_every=20`: Task 2 Step 6.
- Plan `max_turns=480`: Task 2 Step 3, Task 1 test.
- Plan `ask_user_at=180` and repeat every `90`: Task 2 Step 7, Task 1 test.
- Plan `checkpoint_every=30`: Task 2 Step 7, Task 1 test.
- Normal Working Memory `80`: Task 2 Step 4, Task 1 test.
- Plan Working Memory `120`: Task 2 Step 4, Task 1 test.
- Plan file-read hint every `10` turns starting at turn `10`: Task 2 Step 7.
- Do not touch LibreChat: no frontend adapter files are listed.

Placeholder scan:

- No `TBD`, `TODO`, or undefined implementation references.

Type consistency:

- Tests use existing `GenericAgentHandler`, `turn_end_callback`, `enter_plan_mode`, and `_get_anchor_prompt`.
- Constants are module-level names used only in `ga.py`.
