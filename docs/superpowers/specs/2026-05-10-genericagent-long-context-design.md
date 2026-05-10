# GenericAgent Long-Run Context Design

Date: 2026-05-10
Branch: zfengl-ga-long
Status: Draft for user review

## Goal

Improve GenericAgent's ability to handle long-running tasks and multi-turn user guidance without redesigning the Agent runtime.

The target use case is an Agent task that may require more than 100 tool/action turns, while still preserving critical user constraints and avoiding direction drift during a long execution.

## Current Baseline

GenericAgent already has a layered runtime design:

- `agent_loop.py` defines the low-level loop default as `max_turns=40`.
- `agentmain.py` is the normal runtime entry and currently calls `agent_runner_loop(..., max_turns=70)`.
- `ga.py` raises the handler limit to `100` when Plan mode starts.
- Non-Plan mode currently warns at turn `65` that the Agent must summarize and call `ask_user`.
- Plan mode currently warns at turn `90` that the Agent has reached its limit and must call `ask_user`.
- Plan mode also keeps the existing rule that every 5 turns, the Agent must read the plan file and quote the current step.
- `ga.py` injects `[WORKING MEMORY]` each turn and keeps the latest `30` history lines directly visible.
- Older `history_info` lines are folded into `<earlier_context>` through the existing `_fold_earlier(...)` mechanism.

This design should preserve that structure. The change is a proportional upward adjustment plus periodic checkpoint pressure, not a new context architecture.

## Selected Approach

Use a low-intrusion update to existing thresholds and prompts.

### Non-Plan Mode

- Raise normal runtime `max_turns` from `70` to `140`.
- Move the long-run `ask_user` pressure point from turn `65` to turn `70`.
- Add a periodic checkpoint reminder every `25` turns.

The checkpoint reminder should not stop execution by itself. It should tell the Agent to update `update_working_checkpoint` when useful, focusing on:

- current user goal
- critical user-supplied constraints
- verified conclusions
- failed paths already tried
- next concrete action

### Plan Mode

- Raise Plan mode `max_turns` from `100` to `200`.
- Move the Plan-mode `ask_user` pressure point from turn `90` to turn `100`.
- Add a periodic checkpoint reminder every `35` turns.
- Keep the existing Plan-mode every-5-turn plan-read rule unchanged.

The Plan checkpoint should complement the plan file, not replace it. It should preserve the user's extra constraints and execution facts that may not be represented in the plan checklist.

### Working Memory Window

- Raise the directly visible working-memory history window from `30` to `60`.
- Keep `_fold_earlier(... parts[-150:])` unchanged in this pass.

This gives recent user corrections and Agent findings more room without allowing old low-signal history to dominate each prompt.

### LLM Context Window

Do not change the global `context_win` default in `llmcore.py` in this pass.

`context_win` depends on the actual model/provider capability. It can still be raised through existing model config or `/session.context_win=...` after runtime behavior is verified.

## Explicit Non-Goals

- Do not redesign GA execution modes.
- Do not change LibreChat adapter behavior.
- Do not introduce a new memory subsystem.
- Do not replace `history_info`, `<history>`, `<earlier_context>`, or `update_working_checkpoint`.
- Do not globally increase model `context_win` for every provider.
- Do not remove existing `ask_user` protections.

## Expected Behavior

For normal long tasks:

- The Agent can continue beyond the old 70-turn ceiling.
- Around turn 70, the Agent is pushed to ask the user if progress is uncertain.
- Every 25 turns, the Agent is reminded to checkpoint durable task state.
- Recent user details survive longer in direct working memory.

For Plan-mode tasks:

- The Agent can continue up to 200 turns.
- It still rereads the plan every 5 turns.
- Around turn 100, it is pushed to report progress and ask whether to continue.
- Every 35 turns, it is reminded to checkpoint user constraints and verified execution state.

## Files Expected To Change

- `agentmain.py`
  - Update the normal runtime `max_turns` passed to `agent_runner_loop`.

- `ga.py`
  - Update Plan-mode max-turn threshold.
  - Update normal and Plan-mode long-run warning thresholds.
  - Add periodic checkpoint reminders.
  - Increase the working-memory visible history window.

Potential test files:

- `tests/`
  - Add focused tests if there are existing test helpers around `GenericAgentHandler.turn_end_callback`.
  - If no local tests exist for this behavior, add narrow unit coverage rather than broad runtime tests.

## Verification

Minimum verification after implementation:

- Run focused Python tests for handler loop behavior if added.
- Run existing relevant backend tests that cover `ask_user` and `update_working_checkpoint` display/projection if touched indirectly.
- Manually inspect source to confirm:
  - normal mode uses `140`
  - normal `ask_user` pressure is `70`
  - normal checkpoint interval is `25`
  - Plan mode uses `200`
  - Plan `ask_user` pressure is `100`
  - Plan checkpoint interval is `35`
  - working-memory window is `60`

## Open Risks

- Larger turn limits can increase API cost and runtime duration.
- Larger working memory can increase prompt size and may accelerate `context_win` trimming on smaller models.
- A checkpoint reminder is still model-followed behavior, not a hard state-machine guarantee.

These risks are acceptable for this pass because the change stays within existing GA mechanisms and keeps the human confirmation points.
