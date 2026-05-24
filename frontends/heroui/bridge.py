#!/usr/bin/env python3
"""
GenericAgent HeroUI Bridge.

Clear split:
1) AgentManager: owns GenericAgent instances, sessions and histories.
2) Transport: HTTP is the command/data channel; WebSocket only pushes small
   session-state notifications.

HTTP API:
  GET    /status
  GET    /config
  POST   /config
  GET    /model-profiles
  POST   /model-profile
  GET    /sessions
  POST   /session/new
  GET    /session/{sid}
  DELETE /session/{sid}
  POST   /session/{sid}/prompt
  GET    /session/{sid}/messages?after=0&limit=200
  POST   /session/{sid}/cancel

WS API:
  GET /ws -> events only, e.g.
  {"type":"session-state","sessionId":"sess-...","state":"running","seq":3,"updatedAt":...}
"""
from __future__ import annotations

import asyncio, contextlib, importlib, json, os, re, sqlite3, sys
import threading, time, traceback, uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from aiohttp import web, WSMsgType

APP_DIR = Path(__file__).resolve().parent


def find_default_ga_root() -> Path:
    candidates = [
        APP_DIR / "..",
        APP_DIR / ".." / "..",
        APP_DIR / ".." / "GenericAgent",
        APP_DIR / ".." / ".." / "GenericAgent",
    ]
    for p in candidates:
        root = p.resolve()
        if (root / "agentmain.py").exists():
            return root
    return APP_DIR.parent.parent.resolve()


DEFAULT_GA_ROOT = find_default_ga_root()
DEFAULT_HEROUI_DB_PATH = APP_DIR / ".data" / "sessions.sqlite3"


def to_iso_timestamp(value: Any) -> str:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        seconds = time.time()
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _extract_summary_text(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    match = re.search(r"<summary>\s*([\s\S]*?)\s*</(?:summary|parameter)>", raw, flags=re.IGNORECASE)
    if match:
        return " ".join(match.group(1).split())
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[0]


def _round_label(turn_no: int) -> str:
    return f"第{turn_no}轮"


def _ask_user_interaction_payload(raw: dict) -> Optional[dict]:
    result = raw.get("result")
    if not isinstance(result, dict):
        return None
    intent = str(result.get("intent") or "")
    status = str(result.get("status") or "")
    if intent != "HUMAN_INTERVENTION":
        return None
    data = result.get("data")
    payload = data if isinstance(data, dict) else {}
    candidates = payload.get("candidates") or []
    if not isinstance(candidates, list):
        candidates = []
    candidate_texts = [str(candidate) for candidate in candidates if str(candidate).strip()]
    if not candidate_texts:
        return None
    return {
        "status": status,
        "intent": intent,
        "question": str(payload.get("question") or ""),
        "candidates": candidate_texts,
    }


for _s in (sys.stdout, sys.stderr):
    with contextlib.suppress(Exception):
        _s.reconfigure(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Agent management layer
# ---------------------------------------------------------------------------

@dataclass
class Session:
    id: str
    title: str = "New chat"
    cwd: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    messages: List[dict] = field(default_factory=list)
    events: List[dict] = field(default_factory=list)
    msg_seq: int = 0
    event_seq: int = 0
    partial: Optional[dict] = None
    status: str = "idle"  # idle|running|error|cancelled
    agent: Any = None
    thread: Optional[threading.Thread] = None
    cancel_requested: bool = False
    last_error: str = ""


class AgentManager:
    def __init__(self, db_path: Optional[str] = None):
        self.lock = threading.RLock()
        self.ga_root = str(DEFAULT_GA_ROOT)
        self.config: Dict[str, Any] = {}
        self.selected_llm_no: Optional[int] = None
        self.sessions: Dict[str, Session] = {}
        self.active_session_id: Optional[str] = None
        self.deleted_session_ids: Set[str] = set()
        self.db_path = Path(db_path or os.environ.get("HEROUI_BRIDGE_DB") or DEFAULT_HEROUI_DB_PATH)
        self._init_store()
        self._load_sessions()

    @property
    def mykey_path(self) -> str:
        return str(Path(self.ga_root) / "mykey.txt")

    def ensure_ga_import_path(self) -> Path:
        root = Path(self.ga_root).resolve()
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        return root

    def make_turn_id(self, session_id: str, turn_no: int) -> str:
        return f"ga|{session_id}|{turn_no}"

    def make_response_id(self, turn_id: str, response_no: int) -> str:
        return f"{turn_id}:response:{response_no}"

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_store(self) -> None:
        with self._connect() as conn:
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
            conn.commit()

    def _load_sessions(self) -> None:
        sessions: Dict[str, Session] = {}
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, title, cwd, created_at, updated_at, status, msg_seq, last_error FROM sessions ORDER BY updated_at ASC"
            ).fetchall()
            for row in rows:
                sessions[row["id"]] = Session(
                    id=row["id"],
                    title=row["title"],
                    cwd=row["cwd"],
                    created_at=float(row["created_at"]),
                    updated_at=float(row["updated_at"]),
                    msg_seq=int(row["msg_seq"]),
                    status=self._restore_status(str(row["status"])),
                    last_error=str(row["last_error"] or ""),
                )
            if sessions:
                msg_rows = conn.execute(
                    "SELECT session_id, id, role, content, ts, payload FROM messages ORDER BY session_id ASC, id ASC"
                ).fetchall()
                for row in msg_rows:
                    sess = sessions.get(row["session_id"])
                    if not sess:
                        continue
                    msg = {
                        "id": int(row["id"]),
                        "role": row["role"],
                        "content": row["content"],
                        "ts": float(row["ts"]),
                    }
                    payload = str(row["payload"] or "")
                    if payload:
                        with contextlib.suppress(Exception):
                            msg.update(json.loads(payload))
                    sess.messages.append(msg)
                event_rows = conn.execute(
                    "SELECT session_id, seq, turn_id, type, ts, payload FROM events ORDER BY session_id ASC, seq ASC"
                ).fetchall()
                for row in event_rows:
                    sess = sessions.get(row["session_id"])
                    if not sess:
                        continue
                    event = {
                        "seq": int(row["seq"]),
                        "turn_id": row["turn_id"],
                        "type": row["type"],
                        "ts": float(row["ts"]),
                    }
                    payload = str(row["payload"] or "")
                    if payload:
                        with contextlib.suppress(Exception):
                            event.update(json.loads(payload))
                    sess.events.append(event)
                    sess.event_seq = max(sess.event_seq, int(row["seq"]))
        with self.lock:
            self.sessions = sessions
            self.active_session_id = next(reversed(sessions), None) if sessions else None

    def _restore_status(self, status: str) -> str:
        if status == "running":
            return "idle"
        if status in {"idle", "error", "cancelled"}:
            return status
        return "idle"

    def _persist_session(self, sess: Session) -> None:
        self._persist_session_and_message(sess)

    def _persist_session_row(self, conn: sqlite3.Connection, sess: Session) -> None:
        if sess.id in self.deleted_session_ids:
            return
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
                sess.id,
                sess.title,
                sess.cwd,
                sess.created_at,
                sess.updated_at,
                sess.status,
                sess.msg_seq,
                sess.last_error,
            ),
        )

    def _persist_message_row(self, conn: sqlite3.Connection, sess: Session, msg: dict) -> None:
        if sess.id in self.deleted_session_ids:
            return
        payload = {k: v for k, v in msg.items() if k not in {"id", "role", "content", "ts"}}
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
                sess.id,
                int(msg["id"]),
                str(msg["role"]),
                str(msg["content"]),
                float(msg["ts"]),
                json.dumps(payload, ensure_ascii=False, default=str),
            ),
        )

    def _persist_event_row(self, conn: sqlite3.Connection, sess: Session, event: dict) -> None:
        if sess.id in self.deleted_session_ids:
            return
        payload = {k: v for k, v in event.items() if k not in {"seq", "turn_id", "type", "ts"}}
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
                sess.id,
                int(event["seq"]),
                str(event["turn_id"]),
                str(event["type"]),
                float(event["ts"]),
                json.dumps(payload, ensure_ascii=False, default=str),
            ),
        )

    def _persist_session_and_message(self, sess: Session, msg: Optional[dict] = None) -> None:
        if sess.id in self.deleted_session_ids:
            return
        with self._connect() as conn:
            self._persist_session_row(conn, sess)
            if msg is not None:
                self._persist_message_row(conn, sess, msg)
            conn.commit()

    def add_event(self, sess: Session, event: dict, persist: bool = True) -> dict:
        sess.event_seq += 1
        stored = dict(event)
        stored["seq"] = sess.event_seq
        stored["ts"] = float(stored.get("ts") or time.time())
        stored["turn_id"] = str(stored.get("turn_id") or "")
        stored["type"] = str(stored.get("type") or "")
        stored["session_id"] = str(stored.get("session_id") or sess.id)
        sess.events.append(stored)
        sess.updated_at = time.time()
        if persist:
            with self._connect() as conn:
                self._persist_event_row(conn, sess, stored)
                conn.commit()
            if sess.id not in self.deleted_session_ids:
                event_hub.publish(stored)
        return stored

    def convert_agent_event(self, sess: Session, turn_id: str, response_id: str, raw: dict) -> Optional[dict]:
        event_type = str(raw.get("type") or "")
        ga_turn = int(raw.get("turn") or 0)
        created_at = to_iso_timestamp(raw.get("ts") or time.time())
        tool_name = str(raw.get("tool_name") or "tool")
        tool_kind = str(raw.get("tool_kind") or "tool")
        index = int(raw.get("index") or 0) + 1
        step_id = f"{response_id}:tool:{ga_turn}:{index}"
        round_label = _round_label(ga_turn) if ga_turn else "GA"
        tool_title = f"{round_label} 调用了 {tool_name}"

        if event_type == "turn.start":
            return None
        if event_type == "llm.start":
            return {
                "type": "phase.update",
                "turn_id": turn_id,
                "session_id": sess.id,
                "data": {"phase": "understanding", "label": "正在思考"},
            }
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
        if event_type == "llm.end":
            if not raw.get("has_tools"):
                return None
            text = str(raw.get("text") or "")
            summary = str(raw.get("summary") or "") or _extract_summary_text(text) or "模型输出"
            thinking_summary = str(raw.get("thinking_summary") or "")
            detail = thinking_summary if thinking_summary and thinking_summary != summary else ""
            return {
                "type": "timeline.step",
                "turn_id": turn_id,
                "session_id": sess.id,
                "data": {
                    "id": f"{response_id}:phase:{ga_turn}:llm",
                    "turn_id": turn_id,
                    "response_id": response_id,
                    "kind": "phase",
                    "title": summary,
                    "status": "done",
                    "summary": summary,
                    "detail": detail,
                    "elapsed_ms": raw.get("elapsed_ms"),
                    "default_open": False,
                    "created_at": created_at,
                    "retract_response_id": response_id,
                },
            }
        if event_type == "tool.start":
            data = {
                "id": step_id,
                "turn_id": turn_id,
                "response_id": response_id,
                "kind": tool_kind,
                "title": tool_title,
                "status": "running",
                "summary": tool_title,
                "detail": "",
                "input": json.dumps(raw.get("args") or {}, ensure_ascii=False, indent=2),
                "tool_name": tool_name,
                "tool_label": round_label,
                "created_at": created_at,
            }
            interaction = _ask_user_interaction_payload(raw)
            if interaction is not None:
                data["interaction"] = interaction
            return {
                "type": "timeline.step",
                "turn_id": turn_id,
                "session_id": sess.id,
                "data": data,
            }
        if event_type == "tool.delta":
            return {
                "type": "timeline.step",
                "turn_id": turn_id,
                "session_id": sess.id,
                "data": {
                    "id": step_id,
                    "turn_id": turn_id,
                    "response_id": response_id,
                    "kind": tool_kind,
                    "title": tool_title,
                    "status": "running",
                    "summary": tool_title,
                    "detail": "",
                    "detail_delta": str(raw.get("delta") or ""),
                    "tool_name": tool_name,
                    "tool_label": round_label,
                    "created_at": created_at,
                },
            }
        if event_type == "tool.end":
            status = str(raw.get("status") or "done")
            error = str(raw.get("error") or "")
            if status == "failed" and not error:
                error = str(raw.get("result") or "")
            data = {
                "id": step_id,
                "turn_id": turn_id,
                "response_id": response_id,
                "kind": tool_kind,
                "title": tool_title,
                "status": "failed" if status == "failed" else "done",
                "summary": tool_title,
                "detail": str(raw.get("detail") or ""),
                "output": str(raw.get("output") or ""),
                "error": error if status == "failed" else "",
                "elapsed_ms": raw.get("elapsed_ms"),
                "tool_name": tool_name,
                "tool_label": round_label,
                "created_at": created_at,
            }
            interaction = _ask_user_interaction_payload(raw)
            if tool_name == "ask_user":
                data["default_open"] = interaction is None
            if interaction is not None:
                data["interaction"] = interaction
            return {
                "type": "timeline.step",
                "turn_id": turn_id,
                "session_id": sess.id,
                "data": data,
            }
        if event_type == "turn.end":
            return None
        if event_type == "agent.final":
            return {
                "type": "answer.final",
                "turn_id": turn_id,
                "session_id": sess.id,
                "data": {
                    "text": str(raw.get("text") or ""),
                    "response_id": response_id,
                    "created_at": created_at,
                },
            }
        if event_type == "agent.done":
            return {
                "type": "turn.done",
                "turn_id": turn_id,
                "session_id": sess.id,
                "data": {"ok": True},
            }
        return None

    def make_agent(self, sess: Session):
        root = self.ensure_ga_import_path()
        old_cwd = os.getcwd()
        try:
            os.chdir(sess.cwd or str(root))
            agentmain = importlib.import_module("agentmain")
            GA = getattr(agentmain, "GenericAgent")
            agent = GA()
            if self.selected_llm_no is not None and hasattr(agent, "next_llm"):
                agent.next_llm(self.selected_llm_no)
            agent.inc_out = True
            agent.verbose = True
            agent.structured_events = True
            threading.Thread(target=agent.run, daemon=True, name=f"GA-{sess.id}").start()
            return agent
        finally:
            with contextlib.suppress(Exception):
                os.chdir(old_cwd)

    def list_model_profiles(self):
        self.ensure_ga_import_path()
        try:
            agentmain = importlib.import_module("agentmain")
            agent = agentmain.GenericAgent()
            if hasattr(agent, "load_llm_sessions"):
                agent.load_llm_sessions()
            clients = getattr(agent, "llmclients", [])
            active_no = self.selected_llm_no if self.selected_llm_no is not None else getattr(agent, "llm_no", None)
            if clients and hasattr(agent, "get_llm_name"):
                return [
                    {
                        "id": str(i),
                        "name": agent.get_llm_name(client),
                        "model": agent.get_llm_name(client, model=True),
                        "active": i == active_no,
                    }
                    for i, client in enumerate(clients)
                ]
            if hasattr(agent, "list_llms"):
                selected = self.selected_llm_no
                return [{"id": str(i), "name": name, "active": i == selected if selected is not None else active} for i, name, active in agent.list_llms()]
        except Exception as e:
            print(f"get model profiles failed: {e}", file=sys.stderr)
        return []

    def switch_model_profile(self, profile_id: Any, session_id: Optional[str] = None) -> dict:
        try:
            next_llm_no = int(str(profile_id))
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(text=json.dumps({"error": "invalid profile id"}, ensure_ascii=False), content_type="application/json")

        profiles = self.list_model_profiles()
        if not any(str(profile.get("id")) == str(next_llm_no) for profile in profiles):
            raise web.HTTPBadRequest(text=json.dumps({"error": f"profile not found: {profile_id}"}, ensure_ascii=False), content_type="application/json")

        with self.lock:
            sess = self.sessions.get(session_id) if session_id else None
            if session_id and not sess:
                raise web.HTTPNotFound(text=json.dumps({"error": f"session not found: {session_id}"}, ensure_ascii=False), content_type="application/json")
            if sess and sess.status == "running":
                raise web.HTTPConflict(text=json.dumps({"error": "session is running; switch after the current turn finishes"}, ensure_ascii=False), content_type="application/json")

            self.selected_llm_no = next_llm_no
            self.config["activeProfileId"] = str(next_llm_no)
            if sess and sess.agent and hasattr(sess.agent, "next_llm"):
                sess.agent.next_llm(next_llm_no)

        return {"ok": True, "activeProfileId": str(next_llm_no), "profiles": self.list_model_profiles()}

    def snapshot(self, sess: Session, include_messages: bool = True) -> dict:
        out = {
            "sessionId": sess.id,
            "id": sess.id,
            "title": sess.title,
            "cwd": sess.cwd,
            "status": sess.status,
            "createdAt": sess.created_at,
            "updatedAt": sess.updated_at,
            "lastError": sess.last_error,
            "msgSeq": sess.msg_seq,
            "eventSeq": sess.event_seq,
        }
        if include_messages:
            out["messages"] = list(sess.messages)
            out["events"] = list(sess.events)
            out["partial"] = dict(sess.partial) if sess.partial else None
        return out

    def add_message(self, sess: Session, role: str, content: str, persist: bool = True, **extra) -> dict:
        sess.msg_seq += 1
        msg = {"id": sess.msg_seq, "role": role, "content": content, "ts": time.time()}
        msg.update(extra)
        sess.messages.append(msg)
        sess.updated_at = time.time()
        if role == "user" and content.strip() and sess.title == "New chat":
            sess.title = content.strip().replace("\n", " ")[:40]
        if persist:
            self._persist_session_and_message(sess, msg)
        return msg

    def create_session(self, cwd: Optional[str] = None, title: str = "New chat") -> Session:
        sid = "sess-" + uuid.uuid4().hex[:12]
        sess = Session(id=sid, title=title or "New chat", cwd=str(cwd or self.ga_root))
        with self.lock:
            self.sessions[sid] = sess
            self.deleted_session_ids.discard(sid)
            self.active_session_id = sid
        self._persist_session(sess)
        emit_session_state(sess, "created")
        return sess

    def get_session(self, sid: str) -> Session:
        with self.lock:
            sess = self.sessions.get(sid)
            if not sess:
                raise web.HTTPNotFound(text=json.dumps({"error": f"session not found: {sid}"}, ensure_ascii=False), content_type="application/json")
            return sess

    def delete_session(self, sid: str) -> dict:
        with self.lock:
            sess = self.sessions.pop(sid, None)
            if not sess:
                raise web.HTTPNotFound(text=json.dumps({"error": f"session not found: {sid}"}, ensure_ascii=False), content_type="application/json")
            self.deleted_session_ids.add(sid)
            sess.cancel_requested = True
            if self.active_session_id == sid:
                self.active_session_id = next(iter(self.sessions), None)
            if sess.agent and hasattr(sess.agent, "abort"):
                with contextlib.suppress(Exception):
                    sess.agent.abort()
        with self._connect() as conn:
            conn.execute("DELETE FROM events WHERE session_id = ?", (sid,))
            conn.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
            conn.commit()
        emit_session_state(sess, "closed")
        return {"ok": True, "sessionId": sid}

    def submit_prompt(self, sid: str, prompt: Any, images: Optional[list] = None) -> dict:
        prompt, image_ids = normalize_prompt(prompt, images)
        with self.lock:
            sess = self.sessions.get(sid)
            if not sess:
                raise web.HTTPNotFound(text=json.dumps({"error": f"session not found: {sid}"}, ensure_ascii=False), content_type="application/json")
            if sess.status == "running":
                raise web.HTTPConflict(text=json.dumps({"error": "session is already running"}, ensure_ascii=False), content_type="application/json")
            extra = {}
            if image_ids:
                extra["image_ids"] = image_ids
            user_msg = self.add_message(sess, "user", prompt, persist=False, **extra)
            turn_id = self.make_turn_id(sid, user_msg["id"])
            user_msg["turn_id"] = turn_id
            user_msg["source"] = "user"
            sess.status = "running"
            sess.cancel_requested = False
            sess.last_error = ""
            event_seq = sess.event_seq
            self._persist_session_and_message(sess, user_msg)
            sess.partial = {
                "id": sess.msg_seq + 1,
                "role": "assistant",
                "content": "",
                "ts": time.time(),
                "partial": True,
                "turn_id": turn_id,
                "responseId": self.make_response_id(turn_id, 1),
                "gaTurn": 0,
                "outputs": [],
                "source": "user",
            }
            t = threading.Thread(target=self.run_agent_turn, args=(sess, turn_id, prompt, None), daemon=True, name=f"Turn-{sid}")
            sess.thread = t
            t.start()
            seq = sess.msg_seq
        emit_session_state(sess, "running")
        return {"ok": True, "sessionId": sid, "accepted": True, "userMessageId": user_msg["id"], "seq": seq, "eventSeq": event_seq}

    def run_agent_turn(self, sess: Session, turn_id: str, prompt: str, images: Optional[list] = None):
        full = ""
        ga_turn = 0
        turn_outputs: List[str] = []
        response_id = self.make_response_id(turn_id, 1)
        structured_final_text = ""
        emitted_final_event = False
        emitted_terminal_event = False
        pending_terminal_event: Optional[dict] = None
        saw_structured_output_event = False
        saw_human_intervention = False

        def remember_stream_event(event_type: str) -> None:
            nonlocal emitted_final_event, emitted_terminal_event
            if event_type == "answer.final":
                emitted_final_event = True
            if event_type in {"turn.done", "turn.error"}:
                emitted_terminal_event = True

        def add_stream_event(event: dict) -> None:
            nonlocal pending_terminal_event
            event_type = str(event.get("type") or "")
            if event_type == "turn.done" and not emitted_final_event:
                pending_terminal_event = dict(event)
                return
            self.add_event(sess, event)
            remember_stream_event(event_type)

        def flush_pending_terminal_event() -> None:
            nonlocal pending_terminal_event
            if pending_terminal_event is None or emitted_terminal_event:
                return
            event = pending_terminal_event
            pending_terminal_event = None
            self.add_event(sess, event)
            remember_stream_event(str(event.get("type") or ""))

        def add_final_event_if_missing(text: str) -> None:
            if emitted_final_event:
                return
            clean_text = str(text or "").strip()
            if not clean_text:
                return
            add_stream_event(
                {
                    "type": "answer.final",
                    "turn_id": turn_id,
                    "session_id": sess.id,
                    "data": {
                        "text": clean_text,
                        "response_id": response_id,
                        "created_at": to_iso_timestamp(time.time()),
                    },
                }
            )
            flush_pending_terminal_event()

        def add_terminal_event_if_missing(event_type: str, data: Optional[dict] = None) -> None:
            if emitted_terminal_event:
                return
            event = {
                "type": event_type,
                "turn_id": turn_id,
                "session_id": sess.id,
                "data": data or {},
            }
            if event_type == "turn.error":
                self.add_event(sess, event)
                remember_stream_event(event_type)
                return
            add_stream_event(event)

        try:
            if sess.agent is None:
                sess.agent = self.make_agent(sess)
            agent = sess.agent
            if hasattr(agent, "put_task"):
                display_q = agent.put_task(prompt, images=images or [])
                pieces = []
                import queue as _queue
                while True:
                    if sess.cancel_requested:
                        break
                    try:
                        item = display_q.get(timeout=1.0)
                    except _queue.Empty:
                        continue
                    if isinstance(item, dict):
                        if isinstance(item.get("event"), dict):
                            raw_event = item["event"]
                            event_type = str(raw_event.get("type") or "")
                            result = raw_event.get("result")
                            if event_type == "tool.end" and (
                                str(raw_event.get("tool_name") or "") == "ask_user"
                                or (isinstance(result, dict) and result.get("intent") == "HUMAN_INTERVENTION")
                            ):
                                saw_human_intervention = True
                            if event_type == "agent.final":
                                if saw_human_intervention:
                                    continue
                                structured_final_text = str(raw_event.get("text") or "")
                            converted = self.convert_agent_event(sess, turn_id, response_id, raw_event)
                            if converted:
                                with self.lock:
                                    if converted.get("type") == "timeline.step":
                                        data = converted.get("data") or {}
                                        retract_response_id = str(data.pop("retract_response_id", "") or "")
                                        if retract_response_id:
                                            self.add_event(
                                                sess,
                                                {
                                                    "type": "answer.retract",
                                                    "turn_id": turn_id,
                                                    "session_id": sess.id,
                                                    "data": {"response_id": retract_response_id},
                                                },
                                            )
                                    if converted.get("type") in {"timeline.step", "answer.delta", "answer.final"}:
                                        saw_structured_output_event = True
                                    add_stream_event(converted)
                                    sess.updated_at = time.time()
                            continue
                        if isinstance(item.get("turn"), int):
                            ga_turn = int(item.get("turn") or 0)
                        if isinstance(item.get("outputs"), list):
                            turn_outputs = [str(output) for output in item.get("outputs") if output is not None]
                        if item.get("next"):
                            text = str(item["next"])
                            pieces.append(text)
                            with self.lock:
                                if sess.partial is not None:
                                    if not getattr(agent, "structured_events", False):
                                        sess.partial["content"] = "".join(pieces) if getattr(agent, "inc_out", False) else text
                                        sess.partial["outputs"] = list(turn_outputs)
                                    sess.partial["ts"] = time.time()
                                    sess.partial["turn_id"] = turn_id
                                    sess.partial["responseId"] = response_id
                                    sess.partial["gaTurn"] = ga_turn
                                    sess.updated_at = time.time()
                        if "done" in item:
                            full = str(item.get("done") or "")
                            if isinstance(item.get("turn"), int):
                                ga_turn = int(item.get("turn") or ga_turn)
                            if isinstance(item.get("outputs"), list):
                                turn_outputs = [str(output) for output in item.get("outputs") if output is not None]
                            break
                    else:
                        pieces.append(str(item))
                if not full and pieces:
                    full = pieces[-1] if not getattr(agent, "inc_out", False) else "".join(pieces)
            elif hasattr(agent, "run"):
                ret = agent.run(prompt)
                if isinstance(ret, str):
                    full = ret
            else:
                full = "GenericAgent object has no put_task/run method"
            if not full:
                full = "(completed)"
            if sess.cancel_requested:
                with self.lock:
                    sess.partial = None
                    add_terminal_event_if_missing("turn.error", {"message": "任务已取消"})
                    # Ensure status stays cancelled (don't overwrite)
                    if sess.status != "cancelled":
                        sess.status = "cancelled"
                    sess.updated_at = time.time()
                    self._persist_session(sess)
                emit_session_state(sess, "cancelled")
                return
            with self.lock:
                sess.partial = None
                # Strip trailing [Info] Final response to user. marker
                import re as _re
                full = _re.sub(r'\n*`{5}\n*\[Info\] Final response to user\.\n*`{5}\s*$', '', full)
                if getattr(agent, "structured_events", False):
                    if saw_human_intervention or (saw_structured_output_event and not structured_final_text.strip()):
                        assistant_content = ""
                    else:
                        assistant_content = structured_final_text.strip() if structured_final_text.strip() else full
                else:
                    assistant_content = full
                add_final_event_if_missing(assistant_content)
                add_terminal_event_if_missing("turn.done", {"ok": True})
                flush_pending_terminal_event()
                if assistant_content.strip():
                    self.add_message(
                        sess,
                        "assistant",
                        assistant_content,
                        turn_id=turn_id,
                        responseId=response_id,
                        response_id=response_id,
                        gaTurn=ga_turn,
                        outputs=turn_outputs,
                        source="assistant",
                    )
                sess.status = "idle"
                sess.last_error = ""
                self._persist_session(sess)
            emit_session_state(sess, "idle")
        except Exception as e:
            tb = traceback.format_exc()
            with self.lock:
                sess.partial = None
                sess.status = "error"
                sess.last_error = str(e)
                add_terminal_event_if_missing("turn.error", {"message": str(e) or "请求失败"})
                self.add_message(
                    sess,
                    "error",
                    str(e),
                    turn_id=turn_id,
                    responseId=response_id,
                    response_id=response_id,
                    gaTurn=ga_turn,
                    outputs=turn_outputs,
                    source="error",
                )
                self._persist_session(sess)
            print(tb, file=sys.stderr)
            emit_session_state(sess, "error")

    def messages(self, sid: str, after: int = 0, limit: int = 200, after_event: int = 0) -> dict:
        with self.lock:
            sess = self.sessions.get(sid)
            if not sess:
                raise web.HTTPNotFound(text=json.dumps({"error": f"session not found: {sid}"}, ensure_ascii=False), content_type="application/json")
            msgs = [m for m in sess.messages if int(m.get("id", 0)) > after]
            if limit > 0:
                msgs = msgs[-limit:]
            events = [e for e in sess.events if int(e.get("seq", 0)) > after_event]
            return {
                "sessionId": sid,
                "status": sess.status,
                "messages": msgs,
                "events": events,
                "eventSeq": sess.event_seq,
                "partial": dict(sess.partial) if sess.partial else None,
                "msgSeq": sess.msg_seq,
                "updatedAt": sess.updated_at,
                "lastError": sess.last_error,
            }

    def cancel(self, sid: str) -> dict:
        with self.lock:
            sess = self.sessions.get(sid)
            if not sess:
                raise web.HTTPNotFound(text=json.dumps({"error": f"session not found: {sid}"}, ensure_ascii=False), content_type="application/json")
            sess.cancel_requested = True
            if sess.agent and hasattr(sess.agent, "abort"):
                with contextlib.suppress(Exception):
                    sess.agent.abort()
            sess.status = "cancelled"
            sess.partial = None
            sess.updated_at = time.time()
            self._persist_session(sess)
        emit_session_state(sess, "cancelled")
        return {"ok": True, "sessionId": sid}


import base64
import tempfile

# Shared temp dir for image uploads (persists for process lifetime)
_UPLOAD_DIR = Path(tempfile.gettempdir()) / "ga_web2_uploads"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _save_image_data(data_url: str, img_id: str) -> str:
    """Save a data URL to disk, return absolute path."""
    # data:image/png;base64,xxxxx
    if "," in data_url:
        header, b64 = data_url.split(",", 1)
    else:
        b64 = data_url
        header = ""
    ext = "png"
    if "jpeg" in header or "jpg" in header:
        ext = "jpg"
    elif "webp" in header:
        ext = "webp"
    elif "gif" in header:
        ext = "gif"
    fpath = _UPLOAD_DIR / f"{img_id}.{ext}"
    fpath.write_bytes(base64.b64decode(b64))
    return str(fpath)


def normalize_prompt(prompt: Any, images: Optional[list] = None):
    """Normalize prompt and images.

    images: list of dicts {"id": "img-xxx", "dataUrl": "data:..."} or plain data URLs.
    Returns: (prompt_text_with_image_tags, image_ids_list)
    """
    images = list(images or [])
    if isinstance(prompt, list):
        text_parts = []
        for part in prompt:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict):
                if part.get("type") in ("text", "input_text"):
                    text_parts.append(str(part.get("text") or part.get("content") or ""))
                elif part.get("type") in ("image", "input_image"):
                    url = part.get("image_url") or part.get("url") or part.get("data")
                    if isinstance(url, dict):
                        url = url.get("url")
                    if url:
                        images.append(url)
        prompt = "\n".join([p for p in text_parts if p])

    # Process images: save to disk, build [image:path] tags
    image_ids = []
    image_tags = []
    for img in images:
        if isinstance(img, dict):
            img_id = img.get("id") or f"img-{uuid.uuid4().hex[:8]}"
            data_url = img.get("dataUrl") or img.get("data_url") or ""
        else:
            # Plain data URL string
            img_id = f"img-{uuid.uuid4().hex[:8]}"
            data_url = str(img)
        if data_url:
            path = _save_image_data(data_url, img_id)
            image_tags.append(f"[image:{path}]")
            image_ids.append(img_id)

    # Append image tags to prompt
    final_prompt = str(prompt or "")
    if image_tags:
        final_prompt = final_prompt + "\n" + "\n".join(image_tags)

    return final_prompt, image_ids


manager = AgentManager()


# ---------------------------------------------------------------------------
# Transport layer: WS notification only
# ---------------------------------------------------------------------------

class WsHub:
    def __init__(self):
        self.websockets: Set[web.WebSocketResponse] = set()
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def emit(self, obj: dict):
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self._broadcast(obj), self.loop)

    async def _broadcast(self, obj: dict):
        data = json.dumps(obj, ensure_ascii=False, default=str)
        dead = set()
        for ws in list(self.websockets):
            try:
                await ws.send_str(data)
            except Exception:
                dead.add(ws)
        self.websockets.difference_update(dead)


hub = WsHub()


class EventStreamHub:
    def __init__(self):
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.subscribers: Dict[asyncio.Queue, tuple[str, str]] = {}

    def subscribe(self, session_id: str, turn_id: str = "") -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.subscribers[queue] = (str(session_id or ""), str(turn_id or ""))
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.subscribers.pop(queue, None)

    def publish(self, event: dict) -> None:
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self._publish(dict(event)), self.loop)

    async def _publish(self, event: dict) -> None:
        dead = set()
        for queue, (session_id, turn_id) in list(self.subscribers.items()):
            if str(event.get("session_id") or "") != session_id:
                continue
            if turn_id and event.get("turn_id") != turn_id:
                continue
            try:
                if queue.full():
                    with contextlib.suppress(asyncio.QueueEmpty):
                        queue.get_nowait()
                queue.put_nowait(event)
            except Exception:
                dead.add(queue)
        for queue in dead:
            self.unsubscribe(queue)


event_hub = EventStreamHub()


def emit_session_state(sess: Session, state_name: str):
    hub.emit({
        "type": "session-state",
        "sessionId": sess.id,
        "state": state_name,
        "status": sess.status,
        "seq": sess.msg_seq,
        "updatedAt": sess.updated_at,
        "title": sess.title,
    })


async def ws_handler(request):
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)
    hub.websockets.add(ws)
    await ws.send_str(json.dumps({
        "type": "bridge-ready",
        "gaRoot": manager.ga_root,
        "mykeyPath": manager.mykey_path,
        "http": True,
        "wsEventsOnly": True,
    }, ensure_ascii=False))
    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            # WS is intentionally not a data/command channel anymore.
            with contextlib.suppress(Exception):
                data = json.loads(msg.data)
                if data.get("action") == "ping":
                    await ws.send_str(json.dumps({"type": "pong", "ts": time.time()}, ensure_ascii=False))
    hub.websockets.discard(ws)
    return ws


# ---------------------------------------------------------------------------
# Transport layer: HTTP command/data API
# ---------------------------------------------------------------------------

def cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }


@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        return web.Response(status=204, headers=cors_headers())
    resp = await handler(request)
    for k, v in cors_headers().items():
        resp.headers[k] = v
    return resp


def json_ok(data: dict, status: int = 200):
    return web.json_response(data, status=status, headers=cors_headers(), dumps=lambda x: json.dumps(x, ensure_ascii=False, default=str))


def sse_format_event(event: dict) -> bytes:
    data = json.dumps(event, ensure_ascii=False, default=str)
    return f'id: {event["seq"]}\nevent: message\ndata: {data}\n\n'.encode("utf-8")


async def sse_write_event(response: web.StreamResponse, event: dict) -> None:
    await response.write(sse_format_event(event))
    with contextlib.suppress(Exception):
        await response.drain()


def parse_event_cursor(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def parse_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value or default)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


async def read_json(request) -> dict:
    if request.can_read_body:
        try:
            data = await request.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


async def status_handler(request):
    return json_ok({
        "ok": True,
        "running": True,
        "ready": True,
        "gaRoot": manager.ga_root,
        "mykeyPath": manager.mykey_path,
        "sessionCount": len(manager.sessions),
        "activeSessionId": manager.active_session_id,
        "ws": "/ws",
        "transport": {"http": True, "wsEventsOnly": True},
    })


async def get_config_handler(request):
    return json_ok({"gaRoot": manager.ga_root, "mykeyPath": manager.mykey_path, "config": manager.config})


async def save_config_handler(request):
    data = await read_json(request)
    cfg = data.get("config", data)
    if isinstance(cfg, dict):
        manager.config.update(cfg)
    return json_ok({"ok": True, "gaRoot": manager.ga_root, "mykeyPath": manager.mykey_path, "config": manager.config})


async def model_profiles_handler(request):
    return json_ok({"profiles": manager.list_model_profiles(), "activeProfileId": manager.config.get("activeProfileId")})


async def switch_model_profile_handler(request):
    data = await read_json(request)
    profile_id = data.get("profileId", data.get("id"))
    session_id = data.get("sessionId")
    return json_ok(manager.switch_model_profile(profile_id, session_id if isinstance(session_id, str) and session_id else None))


async def list_sessions_handler(request):
    with manager.lock:
        sessions = sorted(
            (manager.snapshot(s, include_messages=False) for s in manager.sessions.values()),
            key=lambda session: session["updatedAt"],
            reverse=True,
        )
    return json_ok({"sessions": sessions, "activeSessionId": manager.active_session_id})


async def new_session_handler(request):
    data = await read_json(request)
    title = data.get("title") if isinstance(data.get("title"), str) else "New chat"
    sess = manager.create_session(cwd=data.get("cwd") or data.get("path"), title=title)
    return json_ok({"ok": True, "sessionId": sess.id, "session": manager.snapshot(sess)}, status=201)


async def get_session_handler(request):
    sid = request.match_info["sid"]
    sess = manager.get_session(sid)
    return json_ok({
        "sessionId": sid,
        "session": manager.snapshot(sess),
        "messages": list(sess.messages),
        "events": list(sess.events),
        "eventSeq": sess.event_seq,
        "partial": sess.partial,
    })


async def delete_session_handler(request):
    sid = request.match_info["sid"]
    return json_ok(manager.delete_session(sid))


async def prompt_handler(request):
    sid = request.match_info["sid"]
    data = await read_json(request)
    prompt = data.get("prompt", data.get("content", data.get("message", "")))
    images = data.get("images") or []
    return json_ok(manager.submit_prompt(sid, prompt, images))


async def messages_handler(request):
    sid = request.match_info["sid"]
    after = parse_event_cursor(request.query.get("after") or request.query.get("afterId"))
    limit = parse_positive_int(request.query.get("limit"), 200)
    after_event = parse_event_cursor(request.query.get("after_event") or request.query.get("afterEvent"))
    return json_ok(manager.messages(sid, after=after, limit=limit, after_event=after_event))


async def events_handler(request):
    sid = request.match_info["sid"]
    turn_id = str(request.query.get("turn_id") or "")
    query_after = parse_event_cursor(request.query.get("after_event") or request.query.get("afterEvent"))
    header_after = parse_event_cursor(request.headers.get("Last-Event-ID"))
    after_event = max(query_after, header_after)
    queue = event_hub.subscribe(sid, turn_id)
    try:
        with manager.lock:
            sess = manager.sessions.get(sid)
            if not sess:
                raise web.HTTPNotFound(text=json.dumps({"error": f"session not found: {sid}"}, ensure_ascii=False), content_type="application/json")
            replay_events = [
                event
                for event in sess.events
                if int(event.get("seq", 0)) > after_event and (not turn_id or event.get("turn_id") == turn_id)
            ]

        response = web.StreamResponse(
            status=200,
            headers={
                **cors_headers(),
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
        await response.prepare(request)

        cursor = after_event
        for event in replay_events:
            cursor = max(cursor, int(event.get("seq", 0)))
            await sse_write_event(response, event)
            if turn_id and event.get("type") in {"turn.done", "turn.error"}:
                return response

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
            except asyncio.TimeoutError:
                await response.write(b": keep-alive\n\n")
                continue
            if str(event.get("session_id") or "") != sid:
                continue
            if turn_id and event.get("turn_id") != turn_id:
                continue
            event_seq = parse_event_cursor(event.get("seq"))
            if event_seq <= cursor:
                continue
            cursor = event_seq
            await sse_write_event(response, event)
            if turn_id and event.get("type") in {"turn.done", "turn.error"}:
                return response
    except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
        raise
    finally:
        event_hub.unsubscribe(queue)


async def cancel_handler(request):
    sid = request.match_info["sid"]
    return json_ok(manager.cancel(sid))


async def path_open_handler(request):
    data = await read_json(request)
    kind = data.get("kind", "")
    if kind == "mykey":
        target = Path(manager.ga_root) / "mykey.py"
    else:
        target = Path(data.get("path") or data.get("target") or manager.ga_root)
    target = target.resolve()
    if not target.exists():
        return json_ok({"ok": False, "error": f"File not found: {target}"})
    # Actually open the file with the system default editor
    import subprocess, platform
    if platform.system() == "Windows":
        os.startfile(str(target))
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])
    return json_ok({"ok": True, "path": str(target)})


def create_app():
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/status", status_handler)
    app.router.add_get("/config", get_config_handler)
    app.router.add_post("/config", save_config_handler)
    app.router.add_get("/model-profiles", model_profiles_handler)
    app.router.add_post("/model-profile", switch_model_profile_handler)
    app.router.add_get("/sessions", list_sessions_handler)
    app.router.add_post("/session/new", new_session_handler)
    app.router.add_get("/session/{sid}", get_session_handler)
    app.router.add_delete("/session/{sid}", delete_session_handler)
    app.router.add_post("/session/{sid}/prompt", prompt_handler)
    app.router.add_get("/session/{sid}/messages", messages_handler)
    app.router.add_get("/session/{sid}/events", events_handler)
    app.router.add_post("/session/{sid}/cancel", cancel_handler)
    app.router.add_post("/path/open", path_open_handler)

    # Serve the built HeroUI frontend.
    static_dir = APP_DIR / "dist"

    async def index_handler(request):
        return web.FileResponse(static_dir / "index.html")

    app.router.add_get("/", index_handler)
    app.router.add_static("/", static_dir, show_index=False)

    async def on_startup(app):
        hub.loop = asyncio.get_running_loop()
        event_hub.loop = asyncio.get_running_loop()

    app.on_startup.append(on_startup)
    return app


if __name__ == "__main__":
    host = os.environ.get("BRIDGE_HOST", "127.0.0.1")
    port = int(os.environ.get("HEROUI_BRIDGE_PORT", os.environ.get("BRIDGE_PORT", "14169")))
    print(f"GenericAgent HeroUI bridge: http://{host}:{port}  ws://{host}:{port}/ws", file=sys.stderr)
    web.run_app(create_app(), host=host, port=port, print=None)
