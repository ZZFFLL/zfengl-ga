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

import contextlib, importlib, json, os, sqlite3, sys
import threading, time, traceback, uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from aiohttp import web

APP_DIR = Path(__file__).resolve().parent

try:
    from .bridge_core.session import DEFAULT_GA_ROOT, DEFAULT_HEROUI_DB_PATH, Session, find_default_ga_root
except ImportError:
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    from bridge_core.session import DEFAULT_GA_ROOT, DEFAULT_HEROUI_DB_PATH, Session, find_default_ga_root

if str(DEFAULT_GA_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULT_GA_ROOT))

from llmcore import fast_ask, reload_mykeys

try:
    from .session_store import SessionStore, StoredSession
except ImportError:
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    from session_store import SessionStore, StoredSession

try:
    from .agent_state import build_state_from_messages, capture_agent_state, restore_agent_state, restore_handler_working
except ImportError:
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    from agent_state import build_state_from_messages, capture_agent_state, restore_agent_state, restore_handler_working

try:
    from .bridge_core.titles import (
        build_initial_title_prompt,
        build_title_regeneration_prompt,
        generate_title_with_current_model,
        is_untitled_session_title,
        resolve_llm_config_name,
    )
except ImportError:
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    from bridge_core.titles import (
        build_initial_title_prompt,
        build_title_regeneration_prompt,
        generate_title_with_current_model,
        is_untitled_session_title,
        resolve_llm_config_name,
    )

try:
    from .bridge_core.uploads import normalize_prompt
except ImportError:
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    from bridge_core.uploads import normalize_prompt

try:
    from .bridge_core.events import convert_agent_event as map_agent_event, to_iso_timestamp
except ImportError:
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    from bridge_core.events import convert_agent_event as map_agent_event, to_iso_timestamp

try:
    from .bridge_core.streaming import EventStreamHub, WsHub
except ImportError:
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    from bridge_core.streaming import EventStreamHub, WsHub

try:
    from .bridge_core.routes import BridgeRoutes
except ImportError:
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    from bridge_core.routes import BridgeRoutes


for _s in (sys.stdout, sys.stderr):
    with contextlib.suppress(Exception):
        _s.reconfigure(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Agent management layer
# ---------------------------------------------------------------------------

# 单次 turn_outputs 截断阈值：每条 ≤64KB，整个 list ≤256KB。
# 防止把 agent 的 file_read / shell 输出全量塞进 assistant 消息和 SQLite payload。
MAX_OUTPUT_ITEM_BYTES = 64 * 1024
MAX_OUTPUT_TOTAL_BYTES = 256 * 1024

# 单 session 内存里保留的最大事件数。超过后裁掉最旧的，SQLite 同步 DELETE。
# 配合 Phase 1A 的 cap_field，单事件 ≤64KB，上限 5000 ≈ 150MB 上界。
# 客户端的 after_event cursor 仍然按 seq 比较，最旧事件被裁后客户端不会
# 重复消费（seq 是单调递增的）。
MAX_EVENTS_PER_SESSION = 5000


def cap_outputs(items: Optional[List[Any]]) -> List[str]:
    """Trim a list of per-round output chunks to bounded total size."""
    capped: List[str] = []
    total = 0
    for raw in items or []:
        s = str(raw) if raw is not None else ""
        b = s.encode("utf-8")
        if len(b) > MAX_OUTPUT_ITEM_BYTES:
            s = b[:MAX_OUTPUT_ITEM_BYTES].decode("utf-8", errors="replace") + "\n…[truncated]"
            b = s.encode("utf-8")
        if total + len(b) > MAX_OUTPUT_TOTAL_BYTES:
            capped.append(
                f"…[further outputs omitted, total >{MAX_OUTPUT_TOTAL_BYTES // 1024}KB]"
            )
            break
        capped.append(s)
        total += len(b)
    return capped


class AgentManager:
    def __init__(self, db_path: Optional[str] = None):
        self.lock = threading.RLock()
        self.ga_root = str(DEFAULT_GA_ROOT)
        self.config: Dict[str, Any] = {}
        self.selected_llm_no: Optional[int] = None
        self.sessions: Dict[str, Session] = {}
        self.active_session_id: Optional[str] = None
        self.deleted_session_ids: set[str] = set()
        self.db_path = Path(db_path or os.environ.get("HEROUI_BRIDGE_DB") or DEFAULT_HEROUI_DB_PATH)
        self.store = SessionStore(self.db_path)
        self._load_sessions()

    @property
    def mykey_path(self) -> str:
        return str(Path(self.ga_root) / "mykey.txt")

    def ensure_ga_import_path(self) -> Path:
        root = Path(self.ga_root).resolve()
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        return root

    def _normalize_cwd(self, cwd: Optional[str]) -> str:
        """Validate and normalize a cwd path, falling back to ga_root if invalid."""
        if cwd:
            cwd_path = Path(cwd)
            if cwd_path.exists() and cwd_path.is_dir():
                return str(cwd_path.resolve())
        return self.ga_root

    def make_turn_id(self, session_id: str, turn_no: int) -> str:
        return f"ga|{session_id}|{turn_no}"

    def make_response_id(self, turn_id: str, response_no: int) -> str:
        return f"{turn_id}:response:{response_no}"

    def _connect(self) -> sqlite3.Connection:
        return self.store.connect()

    def _init_store(self) -> None:
        self.store.init_schema()

    def _load_sessions(self) -> None:
        loaded = self.store.load_all_sessions()
        sessions: Dict[str, Session] = {}
        for sid, stored in loaded.items():
            sess = Session(
                id=stored.id,
                title=stored.title,
                cwd=self._normalize_cwd(stored.cwd),
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
        self.store.upsert_session_row(conn, self._session_store_payload(sess))

    def _persist_message_row(self, conn: sqlite3.Connection, sess: Session, msg: dict) -> None:
        if sess.id in self.deleted_session_ids:
            return
        self.store.upsert_message_row(conn, sess.id, msg)

    def _persist_event_row(self, conn: sqlite3.Connection, sess: Session, event: dict) -> None:
        if sess.id in self.deleted_session_ids:
            return
        self.store.upsert_event_row(conn, sess.id, event)

    def _session_store_payload(self, sess: Session) -> dict:
        return {
            "id": sess.id,
            "title": sess.title,
            "cwd": sess.cwd,
            "created_at": sess.created_at,
            "updated_at": sess.updated_at,
            "status": sess.status,
            "msg_seq": sess.msg_seq,
            "last_error": sess.last_error,
        }

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
        # Phase 1C：内存里 sess.events 超过上限时裁掉最旧的，SQLite 同步删除。
        if len(sess.events) > MAX_EVENTS_PER_SESSION:
            dropped = len(sess.events) - MAX_EVENTS_PER_SESSION
            cutoff_seq = int(sess.events[dropped].get("seq", 0) or 0)
            sess.events = sess.events[dropped:]
            if persist and sess.id not in self.deleted_session_ids and cutoff_seq > 0:
                with self._connect() as conn:
                    conn.execute(
                        "DELETE FROM events WHERE session_id = ? AND seq < ?",
                        (sess.id, cutoff_seq),
                    )
                    conn.commit()
        if persist:
            with self._connect() as conn:
                self._persist_event_row(conn, sess, stored)
                conn.commit()
            if sess.id not in self.deleted_session_ids:
                event_hub.publish(stored)
        return stored

    def convert_agent_event(self, sess: Session, turn_id: str, response_id: str, raw: dict) -> Optional[dict]:
        return map_agent_event(sess.id, turn_id, response_id, raw)

    def load_continuation_state(self, sess: Session, current_turn_id: Optional[str] = None) -> dict:
        state = self.store.load_agent_state(sess.id)
        if state is not None:
            return state
        excluded_turn_id = current_turn_id or str((sess.partial or {}).get("turn_id") or "")
        return build_state_from_messages(
            sess.messages,
            llm_no=self.selected_llm_no,
            exclude_turn_id=excluded_turn_id or None,
        )

    def persist_continuation_state(self, sess: Session) -> None:
        agent = getattr(sess, "agent", None)
        if agent is None or sess.id in self.deleted_session_ids:
            return
        state = capture_agent_state(agent)
        if state.get("llm_no") is None and self.selected_llm_no is not None:
            state["llm_no"] = self.selected_llm_no
        self.store.upsert_agent_state(sess.id, state)

    def _wait_for_agent_task_completion(self, agent: Any, timeout: float = 30.0) -> None:
        task_queue = getattr(agent, "task_queue", None)
        if task_queue is None:
            return
        if not hasattr(task_queue, "unfinished_tasks"):
            return
        deadline = time.time() + timeout
        while int(getattr(task_queue, "unfinished_tasks", 0) or 0) > 0:
            if time.time() >= deadline:
                return
            time.sleep(0.01)

    def _persist_session_llm_state(self, sess: Session, llm_no: int) -> None:
        if sess.agent is not None:
            self.persist_continuation_state(sess)
            state = self.store.load_agent_state(sess.id) or {}
        else:
            state = self.load_continuation_state(sess)
        state["llm_no"] = int(llm_no)
        self.store.upsert_agent_state(sess.id, state)

    def _install_handler_working_restore_hook(self, agent: Any, state: dict) -> None:
        if agent is None:
            return
        working = dict((state or {}).get("working") or {})
        setattr(agent, "_heroui_restore_working_state", {"working": working})
        module_name = str(getattr(type(agent), "__module__", "") or "")
        agent_module = sys.modules.get(module_name)
        if agent_module is None or not hasattr(agent_module, "GenericAgentHandler"):
            return
        if getattr(agent_module, "_heroui_handler_restore_installed", False):
            return
        original_handler_factory = getattr(agent_module, "GenericAgentHandler")

        def heroui_handler_factory(*args, **kwargs):
            handler = original_handler_factory(*args, **kwargs)
            target_agent = args[0] if args else kwargs.get("agent")
            pending_state = getattr(target_agent, "_heroui_restore_working_state", None)
            if pending_state is not None:
                restore_handler_working(handler, pending_state)
            return handler

        setattr(agent_module, "_heroui_original_GenericAgentHandler", original_handler_factory)
        setattr(agent_module, "_heroui_handler_restore_installed", True)
        setattr(agent_module, "GenericAgentHandler", heroui_handler_factory)

    def make_agent(self, sess: Session):
        root = self.ensure_ga_import_path()
        old_cwd = os.getcwd()
        cwd = sess.cwd if sess.cwd and Path(sess.cwd).exists() else str(root)
        try:
            os.chdir(cwd)
            agentmain = importlib.import_module("agentmain")
            GA = getattr(agentmain, "GenericAgent")
            agent = GA()
            state = self.load_continuation_state(sess)
            restore_agent_state(agent, state)
            self._install_handler_working_restore_hook(agent, state)
            if state.get("llm_no") is None and self.selected_llm_no is not None and hasattr(agent, "next_llm"):
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
            if sess:
                self._persist_session_llm_state(sess, next_llm_no)

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
        if role == "assistant" and content.strip():
            self._assign_initial_summary_title_if_needed(sess)
        if persist:
            self._persist_session_and_message(sess, msg)
        return msg

    def _is_untitled_session_title(self, title: str) -> bool:
        return is_untitled_session_title(title)

    def _assign_initial_summary_title_if_needed(self, sess: Session) -> None:
        if not self._is_untitled_session_title(sess.title):
            return
        first_user_message = next(
            (
                str(message.get("content") or "").strip()
                for message in sess.messages
                if message.get("role") == "user" and str(message.get("content") or "").strip()
            ),
            "",
        )
        first_assistant_message = next(
            (
                str(message.get("content") or "").strip()
                for message in sess.messages
                if message.get("role") == "assistant" and str(message.get("content") or "").strip()
            ),
            "",
        )
        if not first_user_message or not first_assistant_message:
            return
        llm_no = self.selected_llm_no if self.selected_llm_no is not None else 0
        prompt = self._build_initial_title_prompt(first_user_message, first_assistant_message)
        title = self._generate_title_with_current_model(prompt, llm_no)
        if title:
            sess.title = title

    def _build_initial_title_prompt(self, first_user_message: str, first_assistant_message: str) -> str:
        return build_initial_title_prompt(first_user_message, first_assistant_message)

    def regenerate_session_title(self, sid: str) -> dict:
        with self.lock:
            sess = self.sessions.get(sid)
            if not sess:
                raise web.HTTPNotFound(text=json.dumps({"error": f"session not found: {sid}"}, ensure_ascii=False), content_type="application/json")
            recent_user_messages = [
                str(message.get("content") or "").strip()
                for message in sess.messages
                if message.get("role") == "user" and str(message.get("content") or "").strip()
            ][-5:]
            if not recent_user_messages:
                raise web.HTTPBadRequest(text=json.dumps({"error": "no user messages available for title regeneration"}, ensure_ascii=False), content_type="application/json")
            llm_no = self.selected_llm_no if self.selected_llm_no is not None else 0

        prompt = self._build_title_regeneration_prompt(recent_user_messages)
        title = self._generate_title_with_current_model(prompt, llm_no)
        if not title:
            raise web.HTTPBadRequest(text=json.dumps({"error": "title generation returned empty result"}, ensure_ascii=False), content_type="application/json")

        with self.lock:
            sess = self.sessions.get(sid)
            if not sess:
                raise web.HTTPNotFound(text=json.dumps({"error": f"session not found: {sid}"}, ensure_ascii=False), content_type="application/json")
            sess.title = title
            sess.updated_at = time.time()
            self._persist_session(sess)
        emit_session_state(sess, "updated")
        return {"ok": True, "sessionId": sid, "title": title}

    def replay_turn(self, sid: str, turn_id: str) -> dict:
        with self.lock:
            sess = self.sessions.get(sid)
            if not sess:
                raise web.HTTPNotFound(text=json.dumps({"error": f"session not found: {sid}"}, ensure_ascii=False), content_type="application/json")
            if sess.status == "running":
                raise web.HTTPConflict(text=json.dumps({"error": "session is already running"}, ensure_ascii=False), content_type="application/json")

            target_user_message = next(
                (
                    message
                    for message in sess.messages
                    if message.get("role") == "user" and message.get("turn_id") == turn_id and str(message.get("content") or "").strip()
                ),
                None,
            )
            if not target_user_message:
                raise web.HTTPBadRequest(text=json.dumps({"error": f"user message not found for turn: {turn_id}"}, ensure_ascii=False), content_type="application/json")

            replay_prompt = str(target_user_message.get("agent_prompt") or target_user_message.get("content") or "")
            replay_display_prompt = str(target_user_message.get("content") or "")
            replay_images = list(target_user_message.get("image_ids") or [])
            replay_turn_no = int(target_user_message.get("id") or 0)
            truncated_turn_ids = {
                str(message.get("turn_id") or "")
                for message in sess.messages
                if int(message.get("id", 0)) >= replay_turn_no
            }
            truncated_turn_ids.discard("")

            sess.messages = [message for message in sess.messages if int(message.get("id", 0)) < replay_turn_no]
            sess.events = [event for event in sess.events if str(event.get("turn_id") or "") not in truncated_turn_ids]
            sess.msg_seq = replay_turn_no - 1
            sess.event_seq = max((int(event.get("seq", 0)) for event in sess.events), default=0)
            sess.partial = None
            sess.status = "running"
            sess.cancel_requested = False
            sess.last_error = ""
            sess.updated_at = time.time()
            self._persist_session(sess)

            with self._connect() as conn:
                conn.execute("DELETE FROM messages WHERE session_id = ? AND id >= ?", (sid, replay_turn_no))
                if truncated_turn_ids:
                    placeholders = ",".join("?" for _ in truncated_turn_ids)
                    conn.execute(
                        f"DELETE FROM events WHERE session_id = ? AND turn_id IN ({placeholders})",
                        (sid, *sorted(truncated_turn_ids)),
                    )
                conn.commit()
            previous_state = self.store.load_agent_state(sid) or {}
            replay_llm_no = previous_state.get("llm_no") if previous_state.get("llm_no") is not None else self.selected_llm_no
            self.store.upsert_agent_state(
                sid,
                build_state_from_messages(sess.messages, llm_no=replay_llm_no),
            )

            replay_user_message = self.add_message(
                sess,
                "user",
                replay_display_prompt,
                persist=False,
                image_ids=replay_images,
                turn_started_at=time.time(),
                agent_prompt=replay_prompt if replay_prompt != replay_display_prompt else "",
            )
            replay_user_message["turn_id"] = turn_id
            replay_user_message["source"] = "user"
            self._persist_session_and_message(sess, replay_user_message)
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
                "turn_started_at": replay_user_message.get("turn_started_at"),
            }
            thread = threading.Thread(target=self.run_agent_turn, args=(sess, turn_id, replay_prompt, replay_images), daemon=True, name=f"Replay-{sid}")
            sess.thread = thread
            event_seq = sess.event_seq
            seq = sess.msg_seq
            thread.start()

        emit_session_state(sess, "running")
        return {"ok": True, "sessionId": sid, "turnId": turn_id, "seq": seq, "eventSeq": event_seq}

    def _build_title_regeneration_prompt(self, user_messages: List[str]) -> str:
        return build_title_regeneration_prompt(user_messages)

    def _generate_title_with_current_model(self, prompt: str, llm_no: int) -> str:
        return generate_title_with_current_model(
            prompt,
            llm_no,
            self.ensure_ga_import_path,
            fast_ask,
            reload_mykeys,
        )

    def _resolve_llm_config_name(self, agent: Any, llm_no: int) -> str:
        return resolve_llm_config_name(agent, llm_no, reload_mykeys)

    def create_session(self, cwd: Optional[str] = None, title: str = "New chat") -> Session:
        sid = "sess-" + uuid.uuid4().hex[:12]
        effective_cwd = self._normalize_cwd(cwd)
        sess = Session(id=sid, title=title or "New chat", cwd=effective_cwd)
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
        self.store.delete_session(sid)
        emit_session_state(sess, "closed")
        return {"ok": True, "sessionId": sid}

    def submit_prompt(self, sid: str, prompt: Any, images: Optional[list] = None, display_prompt: Optional[str] = None) -> dict:
        prompt, image_ids = normalize_prompt(prompt, images)
        display_prompt = str(display_prompt) if display_prompt is not None else prompt
        with self.lock:
            sess = self.sessions.get(sid)
            if not sess:
                raise web.HTTPNotFound(text=json.dumps({"error": f"session not found: {sid}"}, ensure_ascii=False), content_type="application/json")
            if sess.status == "running":
                raise web.HTTPConflict(text=json.dumps({"error": "session is already running"}, ensure_ascii=False), content_type="application/json")
            extra = {}
            if image_ids:
                extra["image_ids"] = image_ids
            if display_prompt != prompt:
                extra["agent_prompt"] = prompt
            user_msg = self.add_message(sess, "user", display_prompt, persist=False, **extra)
            turn_started_at = float(user_msg.get("ts") or time.time())
            turn_id = self.make_turn_id(sid, user_msg["id"])
            user_msg["turn_id"] = turn_id
            user_msg["source"] = "user"
            user_msg["turn_started_at"] = turn_started_at
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
                "turn_started_at": turn_started_at,
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
        turn_started_at = 0.0
        emitted_final_event = False
        emitted_terminal_event = False
        pending_terminal_event: Optional[dict] = None
        saw_structured_output_event = False
        saw_human_intervention = False
        agent = None

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
            with self.lock:
                # 兼容直接调用 run_agent_turn 的测试场景，此时不一定先落过用户消息。
                turn_started_at = float((sess.partial or {}).get("turn_started_at") or 0.0)
                if turn_started_at <= 0:
                    turn_started_at = float(
                        next(
                            (
                                message.get("turn_started_at") or message.get("ts") or 0
                                for message in reversed(sess.messages)
                                if message.get("turn_id") == turn_id
                            ),
                            0.0,
                        )
                    )
                if turn_started_at <= 0:
                    turn_started_at = time.time()
            created_agent = False
            if sess.agent is None:
                sess.agent = self.make_agent(sess)
                created_agent = True
            agent = sess.agent
            if not created_agent:
                state = self.load_continuation_state(sess, current_turn_id=turn_id)
                restore_agent_state(agent, state)
                if state.get("llm_no") is None and self.selected_llm_no is not None and hasattr(agent, "next_llm"):
                    agent.next_llm(self.selected_llm_no)
            state = self.load_continuation_state(sess, current_turn_id=turn_id)
            self._install_handler_working_restore_hook(agent, state)
            if hasattr(agent, "put_task"):
                display_q = agent.put_task(prompt, images=images or [])
                restore_handler_working(getattr(agent, "handler", None), state)
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
                            turn_outputs = cap_outputs(item.get("outputs"))
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
                                turn_outputs = cap_outputs(item.get("outputs"))
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
            self._wait_for_agent_task_completion(agent)
            if sess.cancel_requested:
                with self.lock:
                    sess.partial = None
                    add_terminal_event_if_missing("turn.error", {"message": "任务已取消"})
                    # Ensure status stays cancelled (don't overwrite)
                    if sess.status != "cancelled":
                        sess.status = "cancelled"
                    sess.updated_at = time.time()
                    self._persist_session(sess)
                    self.persist_continuation_state(sess)
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
                turn_elapsed_ms = int(max(time.time() - (turn_started_at or time.time()), 0) * 1000)
                add_final_event_if_missing(assistant_content)
                add_terminal_event_if_missing("turn.done", {"ok": True, "elapsed_ms": turn_elapsed_ms})
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
                        elapsed_ms=turn_elapsed_ms,
                    )
                sess.status = "idle"
                sess.last_error = ""
                self._persist_session(sess)
                self.persist_continuation_state(sess)
            emit_session_state(sess, "idle")
        except Exception as e:
            tb = traceback.format_exc()
            with contextlib.suppress(Exception):
                self._wait_for_agent_task_completion(agent)
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
                self.persist_continuation_state(sess)
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


manager = AgentManager()


# ---------------------------------------------------------------------------
# Transport layer: WS notification only
# ---------------------------------------------------------------------------

hub = WsHub()


event_hub = EventStreamHub()


def _manager_provider():
    return manager


routes = BridgeRoutes(_manager_provider, hub, event_hub, APP_DIR)


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
    return await routes.ws_handler(request)


# ---------------------------------------------------------------------------
# Transport layer: HTTP command/data API
# ---------------------------------------------------------------------------

async def status_handler(request):
    return await routes.status_handler(request)


async def get_config_handler(request):
    return await routes.get_config_handler(request)


async def save_config_handler(request):
    return await routes.save_config_handler(request)


async def model_profiles_handler(request):
    return await routes.model_profiles_handler(request)


async def sops_handler(request):
    return await routes.sops_handler(request)


async def sop_detail_handler(request):
    return await routes.sop_detail_handler(request)


async def sop_save_handler(request):
    return await routes.sop_save_handler(request)


async def switch_model_profile_handler(request):
    return await routes.switch_model_profile_handler(request)


async def list_sessions_handler(request):
    return await routes.list_sessions_handler(request)


async def new_session_handler(request):
    return await routes.new_session_handler(request)


async def get_session_handler(request):
    return await routes.get_session_handler(request)


async def delete_session_handler(request):
    return await routes.delete_session_handler(request)


async def regenerate_session_title_handler(request):
    return await routes.regenerate_session_title_handler(request)


async def replay_turn_handler(request):
    return await routes.replay_turn_handler(request)


async def prompt_handler(request):
    return await routes.prompt_handler(request)


async def messages_handler(request):
    return await routes.messages_handler(request)


async def events_handler(request):
    return await routes.events_handler(request)


async def cancel_handler(request):
    return await routes.cancel_handler(request)


async def path_open_handler(request):
    return await routes.path_open_handler(request)


def create_app():
    return routes.create_app()


if __name__ == "__main__":
    host = os.environ.get("BRIDGE_HOST", "127.0.0.1")
    port = int(os.environ.get("HEROUI_BRIDGE_PORT", os.environ.get("BRIDGE_PORT", "14169")))
    print(f"GenericAgent HeroUI bridge: http://{host}:{port}  ws://{host}:{port}/ws", file=sys.stderr)
    web.run_app(create_app(), host=host, port=port, print=None)
