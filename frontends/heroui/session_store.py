from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
    messages: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)


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

    def upsert_session(self, session: dict[str, Any]) -> None:
        with self.connect() as conn:
            self.upsert_session_row(conn, session)
            conn.commit()

    def upsert_session_row(self, conn: sqlite3.Connection, session: dict[str, Any]) -> None:
        now = time.time()
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
                float(session.get("created_at") or now),
                float(session.get("updated_at") or now),
                str(session.get("status") or "idle"),
                int(session.get("msg_seq") or 0),
                str(session.get("last_error") or ""),
            ),
        )

    def upsert_message(self, session_id: str, message: dict[str, Any]) -> None:
        with self.connect() as conn:
            self.upsert_message_row(conn, session_id, message)
            conn.commit()

    def upsert_message_row(
        self,
        conn: sqlite3.Connection,
        session_id: str,
        message: dict[str, Any],
    ) -> None:
        payload = {
            key: value
            for key, value in message.items()
            if key not in {"id", "role", "content", "ts"}
        }
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
                str(session_id),
                int(message["id"]),
                str(message["role"]),
                str(message["content"]),
                float(message["ts"]),
                json.dumps(payload, ensure_ascii=False, default=str),
            ),
        )

    def upsert_event(self, session_id: str, event: dict[str, Any]) -> None:
        with self.connect() as conn:
            self.upsert_event_row(conn, session_id, event)
            conn.commit()

    def upsert_event_row(
        self,
        conn: sqlite3.Connection,
        session_id: str,
        event: dict[str, Any],
    ) -> None:
        payload = {
            key: value
            for key, value in event.items()
            if key not in {"session_id", "seq", "turn_id", "type", "ts"}
        }
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
                str(session_id),
                int(event["seq"]),
                str(event.get("turn_id") or ""),
                str(event["type"]),
                float(event.get("ts") or time.time()),
                json.dumps(payload, ensure_ascii=False, default=str),
            ),
        )

    def upsert_agent_state(self, session_id: str, state: dict[str, Any]) -> None:
        with self.connect() as conn:
            self.upsert_agent_state_row(conn, session_id, state)
            conn.commit()

    def upsert_agent_state_row(
        self,
        conn: sqlite3.Connection,
        session_id: str,
        state: dict[str, Any],
    ) -> None:
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
                str(session_id),
                json.dumps(list(state.get("ga_history") or []), ensure_ascii=False, default=str),
                json.dumps(list(state.get("backend_history") or []), ensure_ascii=False, default=str),
                json.dumps(dict(state.get("working") or {}), ensure_ascii=False, default=str),
                state.get("llm_no"),
                int(state.get("state_version") or STATE_VERSION),
                float(state.get("updated_at") or time.time()),
            ),
        )

    def load_agent_state(self, session_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT ga_history_json, backend_history_json, working_json, llm_no, state_version
                FROM agent_state
                WHERE session_id = ?
                """,
                (str(session_id),),
            ).fetchone()
        if not row:
            return None
        ga_history = _json_loads_strict(row["ga_history_json"])
        backend_history = _json_loads_strict(row["backend_history_json"])
        working = _json_loads_strict(row["working_json"])
        if not isinstance(ga_history, list) or not isinstance(backend_history, list) or not isinstance(working, dict):
            return None
        return {
            "ga_history": ga_history,
            "backend_history": backend_history,
            "working": working,
            "llm_no": row["llm_no"],
            "state_version": int(row["state_version"]),
        }

    def load_all_sessions(self) -> dict[str, StoredSession]:
        sessions: dict[str, StoredSession] = {}
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, title, cwd, created_at, updated_at, status, msg_seq, last_error
                FROM sessions
                ORDER BY updated_at ASC
                """
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

            for row in conn.execute(
                """
                SELECT session_id, id, role, content, ts, payload
                FROM messages
                ORDER BY session_id ASC, id ASC
                """
            ):
                session = sessions.get(row["session_id"])
                if not session:
                    continue
                message = {
                    "id": int(row["id"]),
                    "role": row["role"],
                    "content": row["content"],
                    "ts": float(row["ts"]),
                }
                message.update(_json_loads(row["payload"], {}))
                session.messages.append(message)

            for row in conn.execute(
                """
                SELECT session_id, seq, turn_id, type, ts, payload
                FROM events
                ORDER BY session_id ASC, seq ASC
                """
            ):
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
                event.update(_json_loads(row["payload"], {}))
                session.events.append(event)
        return sessions

    def delete_session(self, session_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM agent_state WHERE session_id = ?", (str(session_id),))
            conn.execute("DELETE FROM messages WHERE session_id = ?", (str(session_id),))
            conn.execute("DELETE FROM events WHERE session_id = ?", (str(session_id),))
            conn.execute("DELETE FROM sessions WHERE id = ?", (str(session_id),))
            conn.commit()

    def delete_agent_state(self, session_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM agent_state WHERE session_id = ?", (str(session_id),))
            conn.commit()


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _json_loads_strict(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
