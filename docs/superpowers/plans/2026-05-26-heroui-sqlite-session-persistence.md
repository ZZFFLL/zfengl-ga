# HeroUI SQLite Session Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist every HeroUI-created conversation through the Bridge into SQLite so UI transcript, structured tool history, and Bridge-owned continuation state survive bridge restarts.

**Architecture:** Keep GenericAgent's core session model unchanged. Move HeroUI Bridge SQLite responsibilities into a small `session_store.py`, add Bridge-owned `agent_state` capture/restore helpers, and wire them into the existing `AgentManager` lifecycle. `temp/model_responses` remains a debug log and is never read by the restore path.

**Tech Stack:** Python 3.10+, `sqlite3`, `dataclasses`, existing `aiohttp` HeroUI bridge, existing Node `tsx` frontend contract tests, existing Python `pytest` tests.

---

## File Structure

- Create `frontends/heroui/session_store.py`
  - Owns SQLite schema creation/migration.
  - Owns CRUD helpers for sessions, messages, events, and `agent_state`.
  - Does not import `agentmain`, `ga.py`, React files, or `temp/model_responses`.

- Create `frontends/heroui/agent_state.py`
  - Owns conversion between a live Bridge-created `GenericAgent` and serialized `agent_state`.
  - Owns SQLite-message fallback for old HeroUI sessions with no `agent_state`.
  - Does not read `temp/model_responses`.

- Modify `frontends/heroui/bridge.py`
  - Keeps HTTP/SSE/thread orchestration.
  - Delegates SQLite reads/writes to `session_store.py`.
  - Restores Bridge-owned state before `agent.put_task(...)`.
  - Captures Bridge-owned state at turn completion/error/cancel boundaries.

- Create `tests/test_heroui_session_store.py`
  - Pure Python tests for schema, migration, data round-trip, delete, and old-session fallback.

- Create `tests/test_heroui_agent_state.py`
  - Pure Python tests for capture/restore helpers using fake agent objects.

- Modify `frontends/heroui/src/ga_bridge_contract.test.mjs`
  - Static and bridge-script contract checks for `agent_state` persistence and no `model_responses` restore dependency.

---

### Task 1: Lock the Persistence Boundary With Failing Tests

**Files:**
- Create: `tests/test_heroui_session_store.py`
- Create: `tests/test_heroui_agent_state.py`
- Modify: `frontends/heroui/src/ga_bridge_contract.test.mjs`

- [ ] **Step 1: Create Python tests for SQLite schema and data round-trip**

Create `tests/test_heroui_session_store.py`:

```python
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STORE_PATH = ROOT / "frontends" / "heroui" / "session_store.py"


def load_store():
    spec = importlib.util.spec_from_file_location("heroui_session_store_under_test", STORE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_init_store_creates_agent_state_without_log_restore(tmp_path):
    store_mod = load_store()
    db_path = tmp_path / "sessions.sqlite3"

    store = store_mod.SessionStore(db_path)

    with sqlite3.connect(db_path) as conn:
        names = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }

    assert {"sessions", "messages", "events", "agent_state"}.issubset(names)
    assert "model_responses" not in db_path.read_text(errors="ignore")
    assert not hasattr(store, "import_model_responses")


def test_session_message_event_and_agent_state_round_trip(tmp_path):
    store_mod = load_store()
    store = store_mod.SessionStore(tmp_path / "sessions.sqlite3")

    session = {
        "id": "sess-1",
        "title": "SQLite test",
        "cwd": "E:/tmp/ga",
        "created_at": 100.0,
        "updated_at": 101.0,
        "status": "idle",
        "msg_seq": 2,
        "last_error": "",
    }
    user_message = {
        "id": 1,
        "role": "user",
        "content": "之前我们讨论了什么？",
        "ts": 102.0,
        "turn_id": "ga|sess-1|1",
        "source": "user",
    }
    event = {
        "seq": 1,
        "turn_id": "ga|sess-1|1",
        "type": "timeline.step",
        "ts": 103.0,
        "session_id": "sess-1",
        "data": {"id": "tool-1", "tool_name": "file_read", "status": "done"},
    }
    state = {
        "ga_history": ["[USER]: 之前我们讨论了什么？", "[Agent] 讨论了 SQLite 持久化"],
        "backend_history": [{"role": "user", "content": [{"type": "text", "text": "之前我们讨论了什么？"}]}],
        "working": {"key_info": "Bridge-owned state"},
        "llm_no": 1,
    }

    store.upsert_session(session)
    store.upsert_message("sess-1", user_message)
    store.upsert_event("sess-1", event)
    store.upsert_agent_state("sess-1", state)

    loaded = store.load_all_sessions()
    assert list(loaded) == ["sess-1"]
    assert loaded["sess-1"].messages[0]["content"] == "之前我们讨论了什么？"
    assert loaded["sess-1"].events[0]["data"]["tool_name"] == "file_read"
    assert store.load_agent_state("sess-1")["ga_history"] == state["ga_history"]
    assert store.load_agent_state("sess-1")["backend_history"] == state["backend_history"]
    assert store.load_agent_state("sess-1")["working"] == state["working"]
    assert store.load_agent_state("sess-1")["llm_no"] == 1


def test_delete_session_removes_messages_events_and_agent_state(tmp_path):
    store_mod = load_store()
    store = store_mod.SessionStore(tmp_path / "sessions.sqlite3")
    store.upsert_session({
        "id": "sess-delete",
        "title": "Delete",
        "cwd": "E:/tmp/ga",
        "created_at": 100.0,
        "updated_at": 101.0,
        "status": "idle",
        "msg_seq": 1,
        "last_error": "",
    })
    store.upsert_message("sess-delete", {"id": 1, "role": "user", "content": "x", "ts": 102.0})
    store.upsert_event("sess-delete", {"seq": 1, "turn_id": "ga|sess-delete|1", "type": "turn.done", "ts": 103.0})
    store.upsert_agent_state("sess-delete", {"ga_history": ["[USER]: x"], "backend_history": [], "working": {}, "llm_no": 0})

    store.delete_session("sess-delete")

    assert store.load_all_sessions() == {}
    assert store.load_agent_state("sess-delete") is None
```

- [ ] **Step 2: Create Python tests for Bridge-owned agent state conversion**

Create `tests/test_heroui_agent_state.py`:

```python
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_STATE_PATH = ROOT / "frontends" / "heroui" / "agent_state.py"


class FakeBackend:
    def __init__(self):
        self.history = []


class FakeLlmClient:
    def __init__(self):
        self.backend = FakeBackend()


class FakeHandler:
    def __init__(self):
        self.working = {}


class FakeAgent:
    def __init__(self):
        self.history = []
        self.llmclient = FakeLlmClient()
        self.handler = FakeHandler()
        self.llm_no = 0
        self.restored_llm = None

    def next_llm(self, llm_no):
        self.restored_llm = llm_no
        self.llm_no = llm_no


def load_agent_state():
    spec = importlib.util.spec_from_file_location("heroui_agent_state_under_test", AGENT_STATE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_capture_agent_state_reads_existing_ga_runtime_fields():
    module = load_agent_state()
    agent = FakeAgent()
    agent.history = ["[USER]: one", "[Agent] two"]
    agent.llmclient.backend.history = [{"role": "user", "content": [{"type": "text", "text": "one"}]}]
    agent.handler.working = {"key_info": "important"}
    agent.llm_no = 2

    captured = module.capture_agent_state(agent)

    assert captured == {
        "ga_history": ["[USER]: one", "[Agent] two"],
        "backend_history": [{"role": "user", "content": [{"type": "text", "text": "one"}]}],
        "working": {"key_info": "important"},
        "llm_no": 2,
    }


def test_restore_agent_state_sets_runtime_before_prompt_submission():
    module = load_agent_state()
    agent = FakeAgent()
    state = {
        "ga_history": ["[USER]: restored", "[Agent] restored summary"],
        "backend_history": [{"role": "assistant", "content": [{"type": "text", "text": "restored"}]}],
        "working": {"passed_sessions": 3},
        "llm_no": 4,
    }

    module.restore_agent_state(agent, state)

    assert agent.history == state["ga_history"]
    assert agent.llmclient.backend.history == state["backend_history"]
    assert agent.handler.working == state["working"]
    assert agent.restored_llm == 4


def test_build_state_from_messages_uses_sqlite_messages_only():
    module = load_agent_state()
    messages = [
        {"role": "user", "content": "第一轮问题"},
        {"role": "assistant", "content": "第一轮回答"},
        {"role": "user", "content": "第二轮问题"},
    ]

    state = module.build_state_from_messages(messages, llm_no=0)

    assert state["ga_history"] == [
        "[USER]: 第一轮问题",
        "[Agent] 第一轮回答",
        "[USER]: 第二轮问题",
    ]
    assert state["backend_history"] == []
    assert state["working"] == {}
    assert state["llm_no"] == 0
```

- [ ] **Step 3: Add Node contract checks for Bridge scope**

Append this test to `frontends/heroui/src/ga_bridge_contract.test.mjs`:

```javascript
test("HeroUI bridge persists Bridge-owned agent state without model_responses restore", () => {
  assert.equal(existsSync(bridgePath), true);
  const bridge = readFileSync(bridgePath, "utf8");

  assert.match(bridge, /from session_store import|import session_store/);
  assert.match(bridge, /from agent_state import|import agent_state/);
  assert.match(bridge, /agent_state/);
  assert.match(bridge, /restore_agent_state/);
  assert.match(bridge, /capture_agent_state/);
  assert.match(bridge, /upsert_agent_state/);
  assert.doesNotMatch(bridge, /extract_history/);
  assert.doesNotMatch(bridge, /compress_session/);
  assert.doesNotMatch(bridge, /model_responses.*restore/);
});
```

- [ ] **Step 4: Run tests and verify they fail for the intended missing modules**

Run:

```bash
rtk proxy powershell -Command "python -m pytest tests/test_heroui_session_store.py tests/test_heroui_agent_state.py -q"
rtk pnpm --prefix frontends/heroui test
```

Expected:

- Python fails because `frontends/heroui/session_store.py` and `frontends/heroui/agent_state.py` do not exist yet.
- Node contract test fails because `bridge.py` does not yet reference `session_store`, `agent_state`, or `agent_state` helpers.

- [ ] **Step 5: Keep failing tests as the implementation checkpoint**

Do not commit at this point. The expected state is a red checkpoint proving the missing behavior. Commit each test file with the implementation task that makes it pass:

- `tests/test_heroui_session_store.py` is committed in Task 2.
- `tests/test_heroui_agent_state.py` is committed in Task 3.
- `frontends/heroui/src/ga_bridge_contract.test.mjs` is committed in Tasks 5 and 6 as each bridge behavior passes.

---

### Task 2: Add the HeroUI SQLite Store Module

**Files:**
- Create: `frontends/heroui/session_store.py`
- Test: `tests/test_heroui_session_store.py`

- [ ] **Step 1: Implement `SessionStore` and store DTO**

Create `frontends/heroui/session_store.py`:

```python
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


STATE_VERSION = 1


@dataclass
class StoredSession:
    id: str
    title: str = "New chat"
    cwd: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    status: str = "idle"
    msg_seq: int = 0
    last_error: str = ""
    messages: List[dict] = field(default_factory=list)
    events: List[dict] = field(default_factory=list)


class SessionStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.init_schema()

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    cwd TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    status TEXT NOT NULL,
                    msg_seq INTEGER NOT NULL,
                    last_error TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    session_id TEXT NOT NULL,
                    id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    ts REAL NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (session_id, id),
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
                """
            )
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_state (
                    session_id TEXT PRIMARY KEY,
                    ga_history_json TEXT NOT NULL,
                    backend_history_json TEXT NOT NULL,
                    working_json TEXT NOT NULL,
                    llm_no INTEGER,
                    state_version INTEGER NOT NULL,
                    updated_at REAL NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
                """
            )
            conn.commit()

    def upsert_session(self, session: dict) -> None:
        with self.connect() as conn:
            self.upsert_session_row(conn, session)
            conn.commit()

    def upsert_session_row(self, conn: sqlite3.Connection, session: dict) -> None:
        conn.execute(
            """
            INSERT INTO sessions (id, title, cwd, created_at, updated_at, status, msg_seq, last_error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                cwd=excluded.cwd,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at,
                status=excluded.status,
                msg_seq=excluded.msg_seq,
                last_error=excluded.last_error
            """,
            (
                str(session["id"]),
                str(session.get("title") or "New chat"),
                str(session.get("cwd") or ""),
                float(session.get("created_at") or time.time()),
                float(session.get("updated_at") or time.time()),
                str(session.get("status") or "idle"),
                int(session.get("msg_seq") or 0),
                str(session.get("last_error") or ""),
            ),
        )

    def upsert_message(self, session_id: str, message: dict) -> None:
        with self.connect() as conn:
            self.upsert_message_row(conn, session_id, message)
            conn.commit()

    def upsert_message_row(self, conn: sqlite3.Connection, session_id: str, message: dict) -> None:
        payload = {key: value for key, value in message.items() if key not in {"id", "role", "content", "ts"}}
        conn.execute(
            """
            INSERT INTO messages (session_id, id, role, content, ts, payload)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, id) DO UPDATE SET
                role=excluded.role,
                content=excluded.content,
                ts=excluded.ts,
                payload=excluded.payload
            """,
            (
                session_id,
                int(message["id"]),
                str(message["role"]),
                str(message["content"]),
                float(message["ts"]),
                json.dumps(payload, ensure_ascii=False, default=str),
            ),
        )

    def upsert_event(self, session_id: str, event: dict) -> None:
        with self.connect() as conn:
            self.upsert_event_row(conn, session_id, event)
            conn.commit()

    def upsert_event_row(self, conn: sqlite3.Connection, session_id: str, event: dict) -> None:
        payload = {key: value for key, value in event.items() if key not in {"session_id", "seq", "turn_id", "type", "ts"}}
        conn.execute(
            """
            INSERT INTO events (session_id, seq, turn_id, type, ts, payload)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, seq) DO UPDATE SET
                turn_id=excluded.turn_id,
                type=excluded.type,
                ts=excluded.ts,
                payload=excluded.payload
            """,
            (
                session_id,
                int(event["seq"]),
                str(event.get("turn_id") or ""),
                str(event["type"]),
                float(event.get("ts") or time.time()),
                json.dumps(payload, ensure_ascii=False, default=str),
            ),
        )

    def upsert_agent_state(self, session_id: str, state: dict) -> None:
        with self.connect() as conn:
            self.upsert_agent_state_row(conn, session_id, state)
            conn.commit()

    def upsert_agent_state_row(self, conn: sqlite3.Connection, session_id: str, state: dict) -> None:
        conn.execute(
            """
            INSERT INTO agent_state (
                session_id, ga_history_json, backend_history_json, working_json,
                llm_no, state_version, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                ga_history_json=excluded.ga_history_json,
                backend_history_json=excluded.backend_history_json,
                working_json=excluded.working_json,
                llm_no=excluded.llm_no,
                state_version=excluded.state_version,
                updated_at=excluded.updated_at
            """,
            (
                session_id,
                json.dumps(list(state.get("ga_history") or []), ensure_ascii=False, default=str),
                json.dumps(list(state.get("backend_history") or []), ensure_ascii=False, default=str),
                json.dumps(dict(state.get("working") or {}), ensure_ascii=False, default=str),
                state.get("llm_no"),
                STATE_VERSION,
                float(state.get("updated_at") or time.time()),
            ),
        )

    def load_agent_state(self, session_id: str) -> Optional[dict]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT ga_history_json, backend_history_json, working_json, llm_no, state_version FROM agent_state WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "ga_history": json.loads(row["ga_history_json"] or "[]"),
            "backend_history": json.loads(row["backend_history_json"] or "[]"),
            "working": json.loads(row["working_json"] or "{}"),
            "llm_no": row["llm_no"],
            "state_version": int(row["state_version"]),
        }

    def load_all_sessions(self) -> Dict[str, StoredSession]:
        sessions: Dict[str, StoredSession] = {}
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, title, cwd, created_at, updated_at, status, msg_seq, last_error FROM sessions ORDER BY updated_at ASC"
            ).fetchall()
            for row in rows:
                sessions[row["id"]] = StoredSession(
                    id=row["id"],
                    title=row["title"],
                    cwd=row["cwd"],
                    created_at=float(row["created_at"]),
                    updated_at=float(row["updated_at"]),
                    status=str(row["status"]),
                    msg_seq=int(row["msg_seq"]),
                    last_error=str(row["last_error"] or ""),
                )
            for row in conn.execute("SELECT session_id, id, role, content, ts, payload FROM messages ORDER BY session_id ASC, id ASC"):
                session = sessions.get(row["session_id"])
                if not session:
                    continue
                message = {"id": int(row["id"]), "role": row["role"], "content": row["content"], "ts": float(row["ts"])}
                message.update(json.loads(row["payload"] or "{}"))
                session.messages.append(message)
            for row in conn.execute("SELECT session_id, seq, turn_id, type, ts, payload FROM events ORDER BY session_id ASC, seq ASC"):
                session = sessions.get(row["session_id"])
                if not session:
                    continue
                event = {
                    "session_id": row["session_id"],
                    "seq": int(row["seq"]),
                    "turn_id": row["turn_id"],
                    "type": row["type"],
                    "ts": float(row["ts"]),
                }
                event.update(json.loads(row["payload"] or "{}"))
                session.events.append(event)
        return sessions

    def delete_session(self, session_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM agent_state WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
```

- [ ] **Step 2: Run store tests**

Run:

```bash
rtk proxy powershell -Command "python -m pytest tests/test_heroui_session_store.py -q"
```

Expected:

```text
3 passed
```

- [ ] **Step 3: Commit store module**

```bash
rtk git add frontends/heroui/session_store.py tests/test_heroui_session_store.py
rtk git commit -m "feat(heroui): add sqlite session store"
```

---

### Task 3: Add Bridge-Owned Agent State Helpers

**Files:**
- Create: `frontends/heroui/agent_state.py`
- Test: `tests/test_heroui_agent_state.py`

- [ ] **Step 1: Implement state capture, restore, and SQLite-message fallback**

Create `frontends/heroui/agent_state.py`:

```python
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _as_list(value: Any) -> list:
    return list(value) if isinstance(value, list) else []


def _as_dict(value: Any) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def capture_agent_state(agent: Any) -> Dict[str, Any]:
    llmclient = getattr(agent, "llmclient", None)
    backend = getattr(llmclient, "backend", None)
    handler = getattr(agent, "handler", None)
    return {
        "ga_history": _as_list(getattr(agent, "history", [])),
        "backend_history": _as_list(getattr(backend, "history", [])),
        "working": _as_dict(getattr(handler, "working", {})),
        "llm_no": getattr(agent, "llm_no", None),
    }


def restore_agent_state(agent: Any, state: Optional[dict]) -> None:
    if not state:
        return
    agent.history = _as_list(state.get("ga_history"))
    llmclient = getattr(agent, "llmclient", None)
    backend = getattr(llmclient, "backend", None)
    if backend is not None:
        backend.history = _as_list(state.get("backend_history"))
    llm_no = state.get("llm_no")
    if llm_no is not None and hasattr(agent, "next_llm"):
        agent.next_llm(int(llm_no))
    elif llm_no is not None:
        agent.llm_no = int(llm_no)
    handler = getattr(agent, "handler", None)
    if handler is not None:
        handler.working = _as_dict(state.get("working"))


def restore_handler_working(handler: Any, state: Optional[dict]) -> None:
    if handler is not None and state:
        handler.working = _as_dict(state.get("working"))


def build_state_from_messages(messages: List[dict], llm_no: Optional[int] = None) -> Dict[str, Any]:
    ga_history: List[str] = []
    for message in messages:
        role = str(message.get("role") or "")
        content = " ".join(str(message.get("content") or "").split())
        if not content:
            continue
        if role == "user":
            ga_history.append(f"[USER]: {content}")
        elif role == "assistant":
            ga_history.append(f"[Agent] {content}")
    return {
        "ga_history": ga_history,
        "backend_history": [],
        "working": {},
        "llm_no": llm_no,
    }
```

- [ ] **Step 2: Run agent-state tests**

Run:

```bash
rtk proxy powershell -Command "python -m pytest tests/test_heroui_agent_state.py -q"
```

Expected:

```text
3 passed
```

- [ ] **Step 3: Commit state helpers**

```bash
rtk git add frontends/heroui/agent_state.py tests/test_heroui_agent_state.py
rtk git commit -m "feat(heroui): add bridge-owned agent state helpers"
```

---

### Task 4: Wire SessionStore Into the Existing Bridge Without Behavior Drift

**Files:**
- Modify: `frontends/heroui/bridge.py`
- Test: `tests/test_heroui_session_store.py`
- Test: `frontends/heroui/src/ga_bridge_contract.test.mjs`

- [ ] **Step 1: Import new store classes**

Modify the import area in `frontends/heroui/bridge.py`:

```python
try:
    from .session_store import SessionStore, StoredSession
except ImportError:
    from session_store import SessionStore, StoredSession
```

- [ ] **Step 2: Add a store instance in `AgentManager.__init__`**

Change the current `AgentManager.__init__` store setup from direct `_init_store()` use to:

```python
self.db_path = Path(db_path or os.environ.get("HEROUI_BRIDGE_DB") or DEFAULT_HEROUI_DB_PATH)
self.store = SessionStore(self.db_path)
self._load_sessions()
```

Keep `self.db_path` because diagnostics and tests may still inspect it.

- [ ] **Step 3: Make `_connect()` delegate to the store**

Replace the body of `_connect()` with:

```python
return self.store.connect()
```

Keep `_connect()` in `bridge.py` for compatibility during the transition.

- [ ] **Step 4: Make `_init_store()` delegate to the store**

Replace the body of `_init_store()` with:

```python
self.store.init_schema()
```

This keeps any remaining callers stable while moving schema ownership into `session_store.py`.

- [ ] **Step 5: Make `_load_sessions()` use `SessionStore.load_all_sessions()`**

Replace `_load_sessions()` with:

```python
def _load_sessions(self) -> None:
    loaded = self.store.load_all_sessions()
    sessions: Dict[str, Session] = {}
    for sid, stored in loaded.items():
        sess = Session(
            id=stored.id,
            title=stored.title,
            cwd=stored.cwd,
            created_at=stored.created_at,
            updated_at=stored.updated_at,
            msg_seq=stored.msg_seq,
            status=self._restore_status(stored.status),
            last_error=stored.last_error,
        )
        sess.messages = list(stored.messages)
        sess.events = list(stored.events)
        sess.event_seq = max((int(event.get("seq", 0)) for event in sess.events), default=0)
        sessions[sid] = sess
    with self.lock:
        self.sessions = sessions
        self.active_session_id = next(reversed(sessions), None) if sessions else None
```

- [ ] **Step 6: Make persistence helpers delegate rows to the store**

Update these methods in `bridge.py`:

```python
def _persist_session_row(self, conn: sqlite3.Connection, sess: Session) -> None:
    if sess.id in self.deleted_session_ids:
        return
    self.store.upsert_session_row(conn, self.snapshot(sess, include_messages=False))

def _persist_message_row(self, conn: sqlite3.Connection, sess: Session, msg: dict) -> None:
    if sess.id in self.deleted_session_ids:
        return
    self.store.upsert_message_row(conn, sess.id, msg)

def _persist_event_row(self, conn: sqlite3.Connection, sess: Session, event: dict) -> None:
    if sess.id in self.deleted_session_ids:
        return
    self.store.upsert_event_row(conn, sess.id, event)
```

- [ ] **Step 7: Make delete use `SessionStore.delete_session()`**

Inside `delete_session`, replace the manual SQL delete block with:

```python
self.store.delete_session(sid)
```

- [ ] **Step 8: Run bridge contract tests**

Run:

```bash
rtk pnpm --prefix frontends/heroui test
rtk proxy powershell -Command "python -m pytest tests/test_heroui_session_store.py -q"
```

Expected:

- Node tests pass except the new `agent_state` bridge contract check may still fail until Task 5.
- Python session store tests pass.

- [ ] **Step 9: Commit store wiring**

```bash
rtk git add frontends/heroui/bridge.py frontends/heroui/session_store.py
rtk git commit -m "refactor(heroui): route bridge sqlite writes through session store"
```

---

### Task 5: Restore Bridge-Owned Agent State Before Prompt Submission

**Files:**
- Modify: `frontends/heroui/bridge.py`
- Test: `tests/test_heroui_agent_state.py`
- Test: `frontends/heroui/src/ga_bridge_contract.test.mjs`

- [ ] **Step 1: Import agent-state helpers**

Add this near the `session_store` import:

```python
try:
    from .agent_state import build_state_from_messages, capture_agent_state, restore_agent_state, restore_handler_working
except ImportError:
    from agent_state import build_state_from_messages, capture_agent_state, restore_agent_state, restore_handler_working
```

- [ ] **Step 2: Add state-load helper to `AgentManager`**

Add this method to `AgentManager`:

```python
def load_continuation_state(self, sess: Session) -> dict:
    state = self.store.load_agent_state(sess.id)
    if state is not None:
        return state
    return build_state_from_messages(sess.messages, llm_no=self.selected_llm_no)
```

- [ ] **Step 3: Restore state in `make_agent()`**

In `make_agent`, after `agent = GA()` and before `agent.next_llm(...)`, add:

```python
state = self.load_continuation_state(sess)
restore_agent_state(agent, state)
```

Then keep the existing selected-profile override:

```python
if self.selected_llm_no is not None and hasattr(agent, "next_llm"):
    agent.next_llm(self.selected_llm_no)
```

This preserves explicit UI model switching while restoring the session's saved state first.

- [ ] **Step 4: Restore handler working when a new handler is created**

In `agentmain.py`, `GenericAgent.run()` creates a new `GenericAgentHandler` internally. Do not refactor that file. Instead, in `bridge.py`, after `agent.put_task(...)` has returned and before consuming queue items, add:

```python
state = self.load_continuation_state(sess)
restore_handler_working(getattr(agent, "handler", None), state)
```

If `agent.handler` is still `None` at that exact moment, this is harmless because `agent.history` and backend history were already restored before `put_task`.

- [ ] **Step 5: Add bridge script test for restore-before-put_task**

Append this test to `frontends/heroui/src/ga_bridge_contract.test.mjs`:

```javascript
test("HeroUI bridge restores sqlite agent state before submitting a restored session prompt", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-state-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_state_restore", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class FakeBackend:
    def __init__(self):
        self.history = []

class FakeClient:
    def __init__(self):
        self.backend = FakeBackend()

class FakeAgent:
    def __init__(self):
        self.history = []
        self.llmclient = FakeClient()
        self.handler = None
        self.llm_no = 0
        self.structured_events = False
        self.inc_out = False
        self.verbose = False
        self.seen_prompt = None

    def next_llm(self, n):
        self.llm_no = n

    def run(self):
        return None

    def put_task(self, prompt, images=None):
        self.seen_prompt = prompt
        import queue
        q = queue.Queue()
        q.put({"done": "restored answer", "turn": 1, "outputs": []})
        return q

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="restore")
manager.add_message(session, "user", "旧问题", turn_id="ga|" + session.id + "|1", source="user")
manager.store.upsert_agent_state(session.id, {
    "ga_history": ["[USER]: 旧问题", "[Agent] 旧回答"],
    "backend_history": [{"role": "user", "content": [{"type": "text", "text": "旧问题"}]}],
    "working": {"key_info": "old context"},
    "llm_no": 3,
})

fake = FakeAgent()
manager.make_agent = lambda sess: (bridge.restore_agent_state(fake, manager.load_continuation_state(sess)) or fake)
manager.run_agent_turn(session, "ga|" + session.id + "|2", "之前聊了什么？")

assert fake.history == ["[USER]: 旧问题", "[Agent] 旧回答"]
assert fake.llmclient.backend.history == [{"role": "user", "content": [{"type": "text", "text": "旧问题"}]}]
assert fake.llm_no == 3
assert fake.seen_prompt == "之前聊了什么？"
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});
```

- [ ] **Step 6: Run restore tests**

Run:

```bash
rtk proxy powershell -Command "python -m pytest tests/test_heroui_agent_state.py -q"
rtk pnpm --prefix frontends/heroui test
```

Expected:

- Python agent-state tests pass.
- Node contract tests pass through the restore-before-submit case.

- [ ] **Step 7: Commit restore wiring**

```bash
rtk git add frontends/heroui/bridge.py frontends/heroui/agent_state.py tests/test_heroui_agent_state.py frontends/heroui/src/ga_bridge_contract.test.mjs
rtk git commit -m "feat(heroui): restore bridge-owned agent state from sqlite"
```

---

### Task 6: Capture Bridge-Owned State at Stable Turn Boundaries

**Files:**
- Modify: `frontends/heroui/bridge.py`
- Test: `frontends/heroui/src/ga_bridge_contract.test.mjs`

- [ ] **Step 1: Add state persistence helper to `AgentManager`**

Add this method to `AgentManager`:

```python
def persist_continuation_state(self, sess: Session) -> None:
    agent = getattr(sess, "agent", None)
    if agent is None or sess.id in self.deleted_session_ids:
        return
    state = capture_agent_state(agent)
    if state.get("llm_no") is None and self.selected_llm_no is not None:
        state["llm_no"] = self.selected_llm_no
    self.store.upsert_agent_state(sess.id, state)
```

- [ ] **Step 2: Capture state after successful assistant completion**

In `run_agent_turn`, after assistant message persistence and before `emit_session_state(sess, "done")`, add:

```python
self.persist_continuation_state(sess)
```

The call must happen after `agent.put_task(...)` finishes because `GenericAgent.run()` updates `agent.history` after the turn.

- [ ] **Step 3: Capture state on cancellation**

In the `if sess.cancel_requested:` block in `run_agent_turn`, before `emit_session_state(sess, "cancelled")`, add:

```python
self.persist_continuation_state(sess)
```

- [ ] **Step 4: Capture state on bridge exception**

In the `except Exception` block in `run_agent_turn`, before `emit_session_state(sess, "error")`, add:

```python
self.persist_continuation_state(sess)
```

- [ ] **Step 5: Add bridge script test for post-turn state capture**

Append this test to `frontends/heroui/src/ga_bridge_contract.test.mjs`:

```javascript
test("HeroUI bridge writes updated agent state after a completed turn", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-state-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_state_capture", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class FakeBackend:
    def __init__(self):
        self.history = []

class FakeClient:
    def __init__(self):
        self.backend = FakeBackend()

class FakeAgent:
    def __init__(self):
        self.history = []
        self.llmclient = FakeClient()
        self.handler = type("Handler", (), {"working": {"key_info": "captured"}})()
        self.llm_no = 2
        self.structured_events = False
        self.inc_out = False

    def put_task(self, prompt, images=None):
        self.history = ["[USER]: " + prompt, "[Agent] captured answer"]
        self.llmclient.backend.history = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        import queue
        q = queue.Queue()
        q.put({"done": "captured answer", "turn": 1, "outputs": []})
        return q

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="capture")
session.agent = FakeAgent()
manager.run_agent_turn(session, "ga|" + session.id + "|1", "保存状态")

state = manager.store.load_agent_state(session.id)
assert state["ga_history"] == ["[USER]: 保存状态", "[Agent] captured answer"]
assert state["backend_history"] == [{"role": "user", "content": [{"type": "text", "text": "保存状态"}]}]
assert state["working"] == {"key_info": "captured"}
assert state["llm_no"] == 2
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});
```

- [ ] **Step 6: Run state-capture tests**

Run:

```bash
rtk pnpm --prefix frontends/heroui test
```

Expected:

```text
all HeroUI Node tests pass
```

- [ ] **Step 7: Commit capture wiring**

```bash
rtk git add frontends/heroui/bridge.py frontends/heroui/src/ga_bridge_contract.test.mjs
rtk git commit -m "feat(heroui): persist agent continuation state after turns"
```

---

### Task 7: Audit, Regression Verification, and Manual Restart Check

**Files:**
- Verify: `frontends/heroui/bridge.py`
- Verify: `frontends/heroui/session_store.py`
- Verify: `frontends/heroui/agent_state.py`
- Verify: `tests/test_heroui_session_store.py`
- Verify: `tests/test_heroui_agent_state.py`
- Verify: `frontends/heroui/src/ga_bridge_contract.test.mjs`

- [ ] **Step 1: Static scope audit**

Run:

```bash
rtk proxy powershell -Command "Select-String -Path 'frontends\\heroui\\*.py','frontends\\heroui\\src\\*.mjs' -Pattern 'model_responses|extract_history|compress_session|L4_raw_sessions' -Context 1,1"
```

Expected:

- No restore/import logic references `model_responses`.
- No references to `extract_history`, `compress_session`, or `L4_raw_sessions` in the HeroUI Bridge path.
- Existing log writing outside restore path is acceptable only if already present before this work.

- [ ] **Step 2: Python unit verification**

Run:

```bash
rtk proxy powershell -Command "python -m pytest tests/test_heroui_session_store.py tests/test_heroui_agent_state.py -q"
```

Expected:

```text
6 passed
```

- [ ] **Step 3: Existing Python event regression**

Run:

```bash
rtk proxy powershell -Command "python -m pytest tests/test_agent_loop_events.py -q"
```

Expected:

```text
all selected tests pass
```

If this file does not exist in the current branch, record that the structured-event regression is covered by the Node HeroUI contract tests in Step 4.

- [ ] **Step 4: HeroUI frontend and bridge contract verification**

Run:

```bash
rtk pnpm --prefix frontends/heroui test
rtk pnpm --prefix frontends/heroui build
```

Expected:

- `pnpm test` passes all configured `tsx --test` files.
- `pnpm build` completes TypeScript check and Vite build.

- [ ] **Step 5: Diff hygiene verification**

Run:

```bash
rtk git diff --check
rtk git status --short
```

Expected:

- `git diff --check` prints no whitespace errors.
- `git status --short` only shows files touched by this plan.

- [ ] **Step 6: Manual restart validation**

Start HeroUI in the normal project workflow:

```bash
rtk proxy powershell -Command "Start-Process -FilePath 'frontends\\heroui\\start.cmd' -WorkingDirectory 'frontends\\heroui' -WindowStyle Hidden"
```

Manual browser steps:

1. Open the HeroUI URL printed by the bridge or the known local port.
2. Create a new session.
3. Ask: `请先用工具读取 frontends/heroui/package.json，然后总结 test 脚本。`
4. Confirm the UI shows the user message, tool timeline, tool result, and assistant answer.
5. Stop the bridge process.
6. Start HeroUI again with the same command.
7. Reopen the same session.
8. Ask: `之前聊了什么？`

Expected:

- The restored session displays the previous user message, tool timeline, tool result, and assistant answer from SQLite.
- The new answer references the previous package.json/test-script discussion.
- The restore path does not read `temp/model_responses`.

- [ ] **Step 7: Review checklist before final commit**

Inspect the final diff:

```bash
rtk git diff -- frontends/heroui/session_store.py frontends/heroui/agent_state.py frontends/heroui/bridge.py tests/test_heroui_session_store.py tests/test_heroui_agent_state.py frontends/heroui/src/ga_bridge_contract.test.mjs
```

Review points:

- `frontends/desktop_bridge.py` is untouched.
- `agentmain.py`, `ga.py`, and `llmcore.py` are untouched unless the user explicitly expands scope.
- `session_store.py` does not import `agentmain`.
- `agent_state.py` does not read files.
- `bridge.py` remains the only runtime integration point.
- Delete removes `agent_state`.
- Restored state is applied before `put_task`.
- Captured state is written after a stable turn boundary.

- [ ] **Step 8: Final commit**

```bash
rtk git add frontends/heroui/session_store.py frontends/heroui/agent_state.py frontends/heroui/bridge.py tests/test_heroui_session_store.py tests/test_heroui_agent_state.py frontends/heroui/src/ga_bridge_contract.test.mjs
rtk git commit -m "feat(heroui): persist bridge sessions in sqlite"
```
