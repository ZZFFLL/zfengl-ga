# GenericAgent Long-Run Context Design

Date: 2026-05-10
Branch: zfengl-ga-long
Status: Updated with 2026-05-16 threshold tuning

## Goal

Improve GenericAgent's ability to handle long-running tasks and multi-turn user guidance without redesigning the Agent runtime.

The target use case is an Agent task that may require more than 100 tool/action turns, while still preserving critical user constraints and avoiding direction drift during a long execution.

## Current Baseline

GenericAgent already has a layered runtime design:

- `agent_loop.py` defines the low-level loop default as `max_turns=40`.
- `agentmain.py` is the normal runtime entry and calls `agent_runner_loop(..., max_turns=240)`.
- `ga.py` raises the handler limit to `480` when Plan mode starts.
- Non-Plan mode soft-reviews at turn `120`, then starts hard `ask_user` pressure at turn `180` and repeats every `60` turns.
- Plan mode soft-reviews at turn `180`, then starts hard `ask_user` pressure at turn `270` and repeats every `90` turns.
- Plan mode reads the plan file every `10` turns starting at turn `10`.
- `ga.py` injects `[WORKING MEMORY]` each turn and keeps the latest `80` normal-mode history lines or latest `120` Plan-mode history lines directly visible.
- Older `history_info` lines are folded into `<earlier_context>` through the existing `_fold_earlier(...)` mechanism.

This design should preserve that structure. The change is a proportional upward adjustment plus periodic checkpoint pressure, not a new context architecture.

## Selected Approach

Use a low-intrusion update to existing thresholds and prompts.

### Non-Plan Mode

- Keep normal runtime `max_turns` at `240`.
- Add a soft long-run review at turn `120`.
- Move the hard long-run `ask_user` pressure point to turn `180`, then repeat every `60` turns.
- Add a periodic checkpoint reminder every `30` turns.
- Use a normal-mode stall warning every `30` turns.
- Refresh global memory every `30` turns.

The checkpoint reminder should not stop execution by itself. It should tell the Agent to update `update_working_checkpoint` when useful, focusing on:

- current user goal
- critical user-supplied constraints
- verified conclusions
- failed paths already tried
- next concrete action

### Plan Mode

- Keep Plan mode `max_turns` at `480`.
- Add a soft Plan-mode review at turn `180`.
- Move the hard Plan-mode `ask_user` pressure point to turn `270`, then repeat every `90` turns.
- Add a periodic checkpoint reminder every `30` turns.
- Add a Plan-mode stall warning every `60` turns.
- Read the plan file every `10` turns starting at turn `10`.

The Plan checkpoint should complement the plan file, not replace it. It should preserve the user's extra constraints and execution facts that may not be represented in the plan checklist.

### Working Memory Window

- Keep the directly visible normal working-memory history window at `80`.
- Use a larger Plan working-memory history window of `120`.
- Keep `_fold_earlier(... parts[-100:])` unchanged in this pass.

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

- The Agent can continue beyond the old 140-turn ceiling.
- Around turn 120, the Agent is asked to review state and checkpoint, but it should continue if the path is clear.
- Around turn 180, the Agent is pushed to ask the user if progress is uncertain; after that, hard pressure repeats every 60 turns.
- Every 30 turns, the Agent is reminded to checkpoint durable task state.
- Recent user details survive longer in direct working memory.

For Plan-mode tasks:

- The Agent can continue up to 480 turns.
- It rereads the plan every 10 turns starting at turn 10.
- Around turn 180, it reviews plan progress and checkpoints without stopping solely because of turn count.
- Around turn 270, it is pushed to report progress and ask whether to continue; after that, hard pressure repeats every 90 turns.
- Every 30 turns, it is reminded to checkpoint user constraints and verified execution state.

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
  - normal mode uses `240`
  - normal soft review is `120`
  - normal hard `ask_user` pressure starts at `180` and repeats every `60`
  - normal checkpoint interval is `30`
  - normal stall warning interval is `30`
  - normal global memory refresh interval is `30`
  - Plan mode uses `480`
  - Plan soft review is `180`
  - Plan hard `ask_user` pressure starts at `270` and repeats every `90`
  - Plan checkpoint interval is `30`
  - Plan stall warning interval is `60`
  - Plan hint starts at `10` and repeats every `10`
  - normal working-memory window is `80`
  - Plan working-memory window is `120`

## Open Risks

- Larger turn limits can increase API cost and runtime duration.
- Larger working memory can increase prompt size and may accelerate `context_win` trimming on smaller models.
- A checkpoint reminder is still model-followed behavior, not a hard state-machine guarantee.

These risks are acceptable for this pass because the change stays within existing GA mechanisms and keeps the human confirmation points.
