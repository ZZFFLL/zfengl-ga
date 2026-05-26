# HeroUI SQLite Session Persistence Design

## Goal

Make HeroUI sessions survive bridge or machine restarts without losing GenericAgent context.

This is not a GenericAgent session-management refactor. It changes how the HeroUI Bridge persists the sessions that are created and continued through the HeroUI UI:

- The UI renders the HeroUI session data stored in SQLite.
- The Bridge stores the full conversation record it produces: messages, structured tool-call events, assistant output, and the minimal Bridge-owned state needed to continue that same HeroUI session.
- GenericAgent itself keeps its normal execution model; the Bridge only serializes/restores the data needed for Bridge-created agents.
- `temp/model_responses` remains a debug log only and is not part of restore, import, or normalization.

## Current Problem

HeroUI already persists visible session data in `frontends/heroui/.data/sessions.sqlite3`.
The bridge loads `sessions`, `messages`, and `events` on startup, and the React app reloads the selected transcript from the bridge.

The missing part is Bridge-level continuity. When a restored HeroUI session receives a new prompt, the bridge can create a new `GenericAgent()` for that session. A new agent starts with empty in-memory state, while the old HeroUI conversation only exists as UI transcript rows.

That means the page can show previous messages, but the model can still answer as if the current prompt is the first turn.

## Non-Goals

- Do not parse or normalize `temp/model_responses`.
- Do not add a second history source.
- Do not redesign the HeroUI conversation model.
- Do not refactor GenericAgent's global session management or introduce a GA-wide session database.
- Do not change external dependency projects.
- Do not persist speculative state that the HeroUI Bridge does not need for UI display or for continuing Bridge-created agents.

## Source of Truth

SQLite is the only source of truth for sessions created and operated through HeroUI.

This source of truth is Bridge-owned. It does not replace any non-HeroUI frontend behavior and does not require GenericAgent itself to adopt SQLite as a global session manager.

`model_responses` remains unchanged:

- it can keep receiving raw prompt/response logs;
- it can still be useful for manual debugging;
- it must not be read by the restart/restore path.

## Data Model

Keep the current tables and add only the data required to store the full HeroUI conversation and continue a Bridge-created agent.

### `sessions`

Existing session metadata remains the session index.

Required fields:

- `id`
- `title`
- `cwd`
- `created_at`
- `updated_at`
- `status`
- `msg_seq`
- `last_error`
- current model/profile id if the bridge needs to restore per-session model selection

### `messages`

Existing user and assistant transcript table remains the UI message source.

Required fields:

- `session_id`
- `id`
- `role`
- `content`
- `ts`
- `payload`

`payload` continues to hold bridge-owned metadata such as `turn_id`, `response_id`, `gaTurn`, image ids, and other fields already attached to messages.

### `events`

Existing event table remains the source for UI timeline replay and structured tool-call history.

It should store frontend-ready structured events, including tool-call cards, tool deltas, final answers, turn completion, and errors. This keeps refresh/reconnect behavior aligned with what the UI saw during live execution.

### `agent_state`

New table for the minimal Bridge-owned agent continuation state for a HeroUI session.

Suggested schema:

```sql
CREATE TABLE IF NOT EXISTS agent_state (
    session_id TEXT PRIMARY KEY,
    ga_history_json TEXT NOT NULL,
    backend_history_json TEXT NOT NULL,
    working_json TEXT NOT NULL,
    llm_no INTEGER,
    state_version INTEGER NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
```

Field meaning:

- `ga_history_json`: serialized `GenericAgent.history` for the Bridge-created agent, using the existing `[USER]` / `[Agent]` working-memory shape.
- `backend_history_json`: serialized `agent.llmclient.backend.history` for the Bridge-created agent.
- `working_json`: serialized `agent.handler.working` when available, including key info and other working-memory fields.
- `llm_no`: active model index for this session.
- `state_version`: explicit migration boundary for future shape changes.
- `updated_at`: last successful runtime-state write.

This table is not a new GA session manager. It is the persisted form of the in-memory state the Bridge needs to recreate the agent it owns for a HeroUI session.

## Runtime Flow

### Bridge Startup

1. Initialize/migrate SQLite schema.
2. Load sessions, messages, events, and agent state.
3. Mark sessions that were `running` as `idle`, preserving the last persisted state.
4. Do not create `GenericAgent` instances until a HeroUI session actually needs to run.

### Selecting a Session

1. Frontend requests `/session/{sid}`.
2. Bridge returns messages and events from SQLite.
3. UI renders only this persisted data.
4. No model log files are read.

### Continuing a Restored Session

When `POST /session/{sid}/prompt` arrives:

1. Load the session from memory-backed SQLite objects.
2. If `sess.agent` is missing, create a new `GenericAgent`.
3. Restore runtime state from `agent_state` before submitting the prompt:
   - set `agent.history`;
   - set `agent.llmclient.backend.history`;
   - restore selected `llm_no` / model profile;
   - restore `handler.working` on the next handler when possible.
4. Submit the prompt with the existing `agent.put_task(...)` path.

If `agent_state` is missing because the session predates this feature, the bridge may derive a minimal `ga_history_json` from `messages`. That is a compatibility fallback from SQLite data only, not a log import path.

This does not change how GenericAgent handles sessions outside HeroUI. It only makes the Bridge recreate the same in-memory context it previously held for the selected HeroUI session.

### During a Turn

Persist the same facts the HeroUI UI and Bridge runtime already produce:

1. User message is inserted into `messages`.
2. Structured timeline events are inserted into `events`.
3. Assistant final message is inserted into `messages`.
4. Session metadata is updated.

Existing event persistence already covers much of this path. The new requirement is to make the Bridge persist the complete HeroUI conversation record plus the continuation state after the turn reaches a stable boundary.

### End of Turn

After the agent finishes, errors, or is cancelled:

1. Capture `agent.history`.
2. Capture `agent.llmclient.backend.history`.
3. Capture `agent.handler.working` if present.
4. Capture active `llm_no`.
5. Upsert `agent_state` in SQLite.
6. Commit the session/message/event/state changes as a consistent update.

The exact transaction boundary can stay pragmatic. The important rule is that a completed turn must not leave a visible assistant answer without a corresponding restorable GA state.

## Restore Semantics

Restored HeroUI sessions must behave like paused Bridge-owned in-memory sessions:

- UI transcript comes from `messages` and `events`.
- Bridge-created agent continuation comes from `agent_state`.
- `running` sessions become `idle` after restart.
- The next user prompt continues from the last successful persisted state.
- If state JSON is corrupt, the bridge sets `last_error`, falls back to SQLite messages where possible, and writes a fresh state after the next successful turn.

## Module Boundaries

Keep `frontends/heroui/bridge.py` as the HTTP/SSE orchestration layer for HeroUI-created sessions, but do not keep growing persistence logic directly inside it.

Add small HeroUI-local modules:

- `frontends/heroui/session_store.py`
  - Owns SQLite schema, migrations, CRUD helpers, and transaction helpers.
  - Does not import React-facing code.
  - Does not import `agentmain` unless unavoidable.

- `frontends/heroui/agent_state.py`
  - Converts between SQLite continuation-state rows and live Bridge-created `GenericAgent` objects.
  - Owns compatibility reconstruction from SQLite `messages` when `agent_state` is absent.
  - Does not read `temp/model_responses`.

- `frontends/heroui/bridge.py`
  - Calls the store and runtime-state helpers.
  - Keeps route handling, SSE, session locking, and worker-thread orchestration.

This split is limited to the HeroUI Bridge persistence boundary. It avoids turning `bridge.py` into a combined HTTP server, database layer, and runtime serializer, and it avoids moving this concern into GenericAgent core.

## Compatibility and Migration

Existing SQLite files must continue to load.

Migration rules:

1. `CREATE TABLE IF NOT EXISTS agent_state`.
2. Add missing columns to `sessions` only if needed for model/profile restore.
3. Existing `messages` and `events` are not rewritten.
4. Existing sessions without `agent_state` continue to show in the UI.
5. First continuation of an old session builds minimal runtime state from SQLite messages, then stores `agent_state`.

## Testing

### Python Bridge Tests

Add focused tests around the HeroUI bridge/store layer:

- Schema migration creates `agent_state` without damaging existing `sessions`, `messages`, or `events`.
- A session with messages/events reloads after a new `AgentManager`.
- A restored HeroUI session creates a Bridge-owned agent with `agent.history` and backend history loaded before `put_task`.
- A completed turn persists updated `agent_state`.
- A session without `agent_state` falls back to SQLite `messages`, not `model_responses`.
- Deleting a session cascades or explicitly removes `agent_state`.

### Frontend Contract Tests

Existing frontend tests should continue to assert:

- `/session/{sid}` returns persisted transcript data.
- structured `events` replay into timeline state;
- final assistant messages render from persisted messages/events;
- no client behavior depends on `model_responses`.

### Manual Runtime Validation

1. Start HeroUI.
2. Create a session and ask a multi-step question that uses at least one tool.
3. Confirm the UI shows user message, tool timeline, tool output, and final answer.
4. Stop and restart the bridge.
5. Open the same session.
6. Ask: `之前聊了什么？`
7. Expected result: the answer references the previous session content and tool activity without reading `temp/model_responses`.

## Success Criteria

- Restarting the bridge does not lose HeroUI session context.
- UI display and GA continuation both read from SQLite.
- Tool-call timeline and assistant messages survive restart.
- Continuing a restored HeroUI session uses persisted Bridge-owned continuation state before submitting the new prompt.
- `temp/model_responses` is untouched by the restore path.
- Existing sessions still load after schema migration.
- Tests cover migration, restore, continuation, and delete behavior.

## Implementation Order

1. Extract SQLite access from `bridge.py` into `session_store.py` without changing behavior.
2. Add `agent_state` schema and store helpers.
3. Add `agent_state.py` restore/capture helpers.
4. Wire restore into `make_agent` / submit path before `put_task`.
5. Wire capture/upsert into turn completion and error/cancel boundaries.
6. Add migration and restore tests.
7. Run the existing HeroUI Python/Node verification set plus the manual restart validation.
