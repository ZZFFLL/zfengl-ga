import argparse
import json
import mimetypes
import os
import queue
import re
import sqlite3
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


ROOT_DIR = Path(__file__).resolve().parent.parent
WEBUI_DIST = Path(__file__).resolve().parent / "webui" / "dist"
DEFAULT_DB_PATH = ROOT_DIR / "temp" / "webui_state.sqlite3"
DEFAULT_GROUP_NAME = "未分组"

# 中文注释：用于从 GA 原始输出中拆出执行轮次和 summary。
_TURN_RE = re.compile(r"\**LLM Running \(Turn (\d+)\) \.\.\.\**")
_SUMMARY_RE = re.compile(r"<summary>\s*(.*?)\s*</summary>", re.DOTALL)
_SUMMARY_BLOCK_RE = re.compile(r"\n*<summary>\s*.*?\s*</summary>\n*", re.DOTALL)
_FINAL_INFO_BLOCK_RE = re.compile(
    r"\n*`{3,}\s*\n?\[Info\]\s*Final response to user\.\s*\n?`{3,}\s*$",
    re.IGNORECASE,
)
_FINAL_INFO_LINE_RE = re.compile(
    r"\n*\[Info\]\s*Final response to user\.\s*$",
    re.IGNORECASE,
)
_FINAL_INFO_TRAIL_RE = re.compile(
    r"\n*\[Info\]\s*Final response to user\.\s*(?:`{3,}\s*)*\Z",
    re.IGNORECASE,
)
_TOOL_START_RE = re.compile(r"🛠️ Tool:\s*`(?P<tool>[^`]+)`\s*📥 args:\s*", re.DOTALL)


def _consume_fenced_block(text):
    """提取 markdown fenced block 正文，并返回剩余文本。"""
    match = re.match(r"\s*(?P<fence>`{3,})(?P<info>[^\n]*)\n", text or "")
    if not match:
        return "", text
    fence = match.group("fence")
    start = match.end()
    end_marker = f"\n{fence}"
    end = (text or "").find(end_marker, start)
    if end < 0:
        return "", text
    body = (text or "")[start:end].strip()
    remainder = (text or "")[end + len(end_marker):]
    return body, remainder


def _strip_tool_trace_blocks(text):
    """移除 GA 渲染给前端的工具调用块，避免正文被过程日志淹没。"""
    source = text or ""
    result_parts = []
    cursor = 0
    while True:
        match = _TOOL_START_RE.search(source, cursor)
        if match is None:
            result_parts.append(source[cursor:])
            break
        result_parts.append(source[cursor:match.start()])
        cursor = match.end()

        # 中文注释：工具参数通常是第一个 fenced block。
        _, remainder = _consume_fenced_block(source[cursor:])
        if remainder != source[cursor:]:
            cursor = len(source) - len(remainder)

        # 中文注释：工具结果可能跟着 1 个或多个 fenced block，一并吞掉。
        while True:
            stripped = source[cursor:].lstrip()
            cursor += len(source[cursor:]) - len(stripped)
            _, next_remainder = _consume_fenced_block(stripped)
            if next_remainder == stripped:
                if stripped.startswith("`") and (
                    "[Action]" in stripped
                    or "[Status]" in stripped
                    or "[Stdout]" in stripped
                    or "[Stderr]" in stripped
                ):
                    cursor = len(source)
                break
            cursor += len(stripped) - len(next_remainder)

        while cursor < len(source) and source[cursor] in "\r\n":
            cursor += 1

    return "".join(result_parts)


def _parse_tool_calls(text):
    """从单轮原始文本里提取工具调用、参数和结果。"""
    tool_calls = []
    for chunk in re.split(r"(?=🛠️ Tool:\s*`)", text or ""):
        if not chunk.strip().startswith("🛠️ Tool:"):
            continue
        tool_match = _TOOL_START_RE.match(chunk.strip())
        if not tool_match:
            continue
        tool_name = tool_match.group("tool").strip()
        remainder = chunk.strip()[tool_match.end():]
        args_text, remainder = _consume_fenced_block(remainder)
        result_text = ""
        if remainder.strip().startswith("`"):
            result_text, remainder = _consume_fenced_block(remainder)
        action_line = next(
            (
                line.replace("[Action]", "").strip()
                for line in (result_text or "").splitlines()
                if line.strip().startswith("[Action]")
            ),
            "",
        )
        status_line = next(
            (
                line.replace("[Status]", "").strip()
                for line in (result_text or "").splitlines()
                if line.strip().startswith("[Status]")
            ),
            "",
        )
        tool_calls.append(
            {
                "tool": tool_name,
                "args": args_text,
                "result": result_text.strip(),
                "action": action_line,
                "status": status_line,
            }
        )
    return tool_calls


def strip_summary_blocks(text):
    """移除聊天展示里不应直接显示的 summary 规划块。"""
    cleaned = _SUMMARY_BLOCK_RE.sub("\n", text or "")
    cleaned = re.sub(r"\n*<summary>[\s\S]*\Z", "\n", cleaned)
    cleaned = _TURN_RE.sub("", cleaned)
    cleaned = _strip_tool_trace_blocks(cleaned)
    cleaned = _FINAL_INFO_BLOCK_RE.sub("", cleaned)
    cleaned = _FINAL_INFO_TRAIL_RE.sub("", cleaned)
    cleaned = _FINAL_INFO_LINE_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def extract_visible_reply_text(text):
    """提取真正应该渲染到聊天主区的最终答复正文。"""
    return strip_summary_blocks(text)


def parse_execution_log(text):
    """从 GA 响应中提取按轮次展示的执行摘要。"""
    parts = list(_TURN_RE.finditer(text or ""))
    turns = []
    for idx, match in enumerate(parts):
        turn = int(match.group(1))
        start = match.end()
        end = parts[idx + 1].start() if idx + 1 < len(parts) else len(text or "")
        content = (text or "")[start:end].strip()
        summary_match = _SUMMARY_RE.search(content)
        title = f"LLM Running (Turn {turn})"
        summary = ""
        tool_calls = _parse_tool_calls(content)
        if summary_match:
            summary = summary_match.group(1).strip()
            first_line = next((line.strip() for line in summary.splitlines() if line.strip()), "")
            if first_line:
                title = first_line[:80]
        turns.append(
            {
                "turn": turn,
                "title": title,
                "content": summary,
                "tool_calls": tool_calls,
            }
        )
    return turns


def _now_ts():
    return int(time.time())


def _now_iso():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def _title_from_user_text(text, limit=28):
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return "新对话"
    return text[:limit]


def _preview_from_text(text, limit=80):
    text = re.sub(r"\s+", " ", (text or "").strip())
    return text[:limit]


def _conversation_history_prompt(messages, prompt):
    history_lines = []
    for message in messages or []:
        role = message.get("role", "user")
        content = (message.get("content") or "").strip()
        if content:
            history_lines.append(f"{role}: {content}")
    history_text = "\n".join(history_lines)
    if history_text:
        return f"Conversation History:\n{history_text}\n\nCurrent User Message:\n{prompt}"
    return f"Current User Message:\n{prompt}"


@dataclass
class GroupMoveRequest:
    group_id: Optional[str]


@dataclass
class ChatStartRequest:
    conversation_id: str
    prompt: str


@dataclass
class TaskRecord:
    task_id: str
    output_queue: queue.Queue
    prompt: str
    conversation_id: str
    status: str = "running"
    current_response: str = ""
    created_at: float = 0.0
    completed_at: float = 0.0
    execution_log: Optional[list] = None


class SQLiteConversationStore:
    """WebUI 会话真相层，独立于 GA 原生日志。"""

    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _fetchall(self, sql, params=()):
        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def _fetchone(self, sql, params=()):
        conn = self._connect()
        try:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row is not None else None
        finally:
            conn.close()

    def _init_db(self):
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversation_groups (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    group_id TEXT,
                    title TEXT NOT NULL,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    archived INTEGER NOT NULL DEFAULT 0,
                    deleted_at TEXT,
                    preview TEXT NOT NULL DEFAULT '',
                    last_message_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(group_id) REFERENCES conversation_groups(id)
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL,
                    execution_log TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id)
                );

                CREATE TABLE IF NOT EXISTS runtime_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(messages)").fetchall()
            }
            if "execution_log" not in columns:
                conn.execute(
                    "ALTER TABLE messages ADD COLUMN execution_log TEXT NOT NULL DEFAULT '[]'"
                )
            conn.commit()
        finally:
            conn.close()

    def create_group(self, name):
        now = _now_iso()
        group_id = uuid.uuid4().hex
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order FROM conversation_groups"
                ).fetchone()
                conn.execute(
                    """
                    INSERT INTO conversation_groups (id, name, sort_order, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (group_id, name.strip() or DEFAULT_GROUP_NAME, int(row["next_order"]), now, now),
                )
                conn.commit()
            finally:
                conn.close()
        return self.get_group(group_id)

    def list_groups(self):
        return self._fetchall(
            """
            SELECT id, name, sort_order, created_at, updated_at
            FROM conversation_groups
            ORDER BY sort_order ASC, updated_at DESC
            """
        )

    def get_group(self, group_id):
        return self._fetchone(
            """
            SELECT id, name, sort_order, created_at, updated_at
            FROM conversation_groups
            WHERE id = ?
            """,
            (group_id,),
        )

    def update_group(self, group_id, name):
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE conversation_groups SET name = ?, updated_at = ? WHERE id = ?",
                    (name.strip() or DEFAULT_GROUP_NAME, _now_iso(), group_id),
                )
                conn.commit()
            finally:
                conn.close()
        return self.get_group(group_id)

    def delete_group(self, group_id):
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE conversations SET group_id = NULL, updated_at = ? WHERE group_id = ?",
                    (_now_iso(), group_id),
                )
                conn.execute("DELETE FROM conversation_groups WHERE id = ?", (group_id,))
                conn.commit()
            finally:
                conn.close()
        return {"ok": True}

    def create_conversation(self, initial_user_text="", group_id=None):
        now = _now_iso()
        conversation_id = uuid.uuid4().hex
        title = _title_from_user_text(initial_user_text)
        preview = _preview_from_text(initial_user_text)
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO conversations (
                        id, group_id, title, pinned, archived, deleted_at, preview,
                        last_message_at, created_at, updated_at
                    )
                    VALUES (?, ?, ?, 0, 0, NULL, ?, ?, ?, ?)
                    """,
                    (conversation_id, group_id, title, preview, now, now, now),
                )
                conn.commit()
            finally:
                conn.close()
        return self.get_conversation_summary(conversation_id)

    def list_conversations(self):
        items = self._fetchall(
            """
            SELECT id, title, group_id, pinned, archived, preview,
                   last_message_at, created_at, updated_at
            FROM conversations
            WHERE deleted_at IS NULL AND archived = 0
            ORDER BY pinned DESC, last_message_at DESC, updated_at DESC
            """
        )
        for row in items:
            row["pinned"] = bool(row["pinned"])
            row["archived"] = bool(row["archived"])
        return items

    def get_conversation_summary(self, conversation_id):
        row = self._fetchone(
            """
            SELECT id, title, group_id, pinned, archived, preview,
                   last_message_at, created_at, updated_at
            FROM conversations
            WHERE id = ? AND deleted_at IS NULL
            """,
            (conversation_id,),
        )
        if row is None:
            return None
        row["pinned"] = bool(row["pinned"])
        row["archived"] = bool(row["archived"])
        return row

    def get_conversation_detail(self, conversation_id):
        summary = self.get_conversation_summary(conversation_id)
        if summary is None:
            return None
        rows = self._fetchall(
            """
            SELECT id, conversation_id, role, content, source, execution_log, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC, rowid ASC
            """,
            (conversation_id,),
        )
        for row in rows:
            try:
                row["execution_log"] = json.loads(row.get("execution_log") or "[]")
            except json.JSONDecodeError:
                row["execution_log"] = []
        return {
            "summary": summary,
            "messages": rows,
            "execution_log": next(
                (
                    row["execution_log"]
                    for row in reversed(rows)
                    if row.get("execution_log")
                ),
                [],
            ),
        }

    def update_conversation(self, conversation_id, title=None):
        summary = self.get_conversation_summary(conversation_id)
        if summary is None:
            return None
        title = (title or "").strip() or summary["title"]
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                    (title, _now_iso(), conversation_id),
                )
                conn.commit()
            finally:
                conn.close()
        return self.get_conversation_summary(conversation_id)

    def delete_conversation(self, conversation_id):
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE conversations SET deleted_at = ?, updated_at = ? WHERE id = ?",
                    (_now_iso(), _now_iso(), conversation_id),
                )
                conn.commit()
            finally:
                conn.close()
        return {"ok": True}

    def pin_conversation(self, conversation_id, pinned):
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE conversations SET pinned = ?, updated_at = ? WHERE id = ?",
                    (1 if pinned else 0, _now_iso(), conversation_id),
                )
                conn.commit()
            finally:
                conn.close()
        return self.get_conversation_summary(conversation_id)

    def move_conversation(self, conversation_id, request: GroupMoveRequest):
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE conversations SET group_id = ?, updated_at = ? WHERE id = ?",
                    (request.group_id, _now_iso(), conversation_id),
                )
                conn.commit()
            finally:
                conn.close()
        return self.get_conversation_summary(conversation_id)

    def add_message(self, conversation_id, role, content, source, execution_log=None):
        now = _now_iso()
        message_id = uuid.uuid4().hex
        preview = _preview_from_text(content)
        execution_payload = json.dumps(execution_log or [], ensure_ascii=False)
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO messages (id, conversation_id, role, content, source, execution_log, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (message_id, conversation_id, role, content, source, execution_payload, now),
                )
                conn.execute(
                    """
                    UPDATE conversations
                    SET preview = ?, last_message_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (preview, now, now, conversation_id),
                )
                conn.commit()
            finally:
                conn.close()
        return self.get_conversation_detail(conversation_id)["messages"][-1]

    def set_runtime_state(self, key, value):
        payload = json.dumps(value, ensure_ascii=False)
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO runtime_state (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (key, payload),
                )
                conn.commit()
            finally:
                conn.close()

    def get_runtime_state(self, key, default=None):
        row = self._fetchone(
            "SELECT value FROM runtime_state WHERE key = ?",
            (key,),
        )
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return default


def _llms(agent):
    if agent is None:
        return []
    try:
        items = agent.list_llms()
    except Exception:
        return []
    return [{"index": idx, "name": name, "current": current} for idx, name, current in items]


def build_state(agent, manager):
    llms = _llms(agent)
    current = next((item for item in llms if item["current"]), None)
    if current is None and agent is not None:
        try:
            current = {
                "index": getattr(agent, "llm_no", 0),
                "name": agent.get_llm_name(),
                "current": True,
            }
        except Exception:
            current = None
    running = False
    execution_log = []
    if manager is not None:
        running = any(task.status == "running" for task in manager.tasks.values())
        active_task = manager.active_task()
        if active_task and active_task.execution_log:
            execution_log = active_task.execution_log
        elif getattr(manager, "active_conversation_id", None):
            detail = manager.store.get_conversation_detail(manager.active_conversation_id)
            if detail is not None:
                execution_log = detail.get("execution_log", [])
    return {
        "configured": agent is not None and bool(llms or current),
        "current_llm": current,
        "llms": llms,
        "running": running or bool(getattr(agent, "is_running", False)),
        "autonomous_enabled": bool(getattr(manager, "autonomous_enabled", False)),
        "last_reply_time": int(getattr(manager, "last_reply_time", 0) or 0),
        "active_conversation_id": getattr(manager, "active_conversation_id", None),
        "execution_log": execution_log,
    }


class WebUITaskManager:
    """WebUI 会话主控层：以中间层会话真相驱动 GA。"""

    def __init__(self, agent, store):
        self.agent = agent
        self.store = store
        self.tasks = {}
        self.autonomous_enabled = False
        self.last_reply_time = 0
        self.active_conversation_id = store.get_runtime_state("active_conversation_id")
        self.ga_bound_conversation_id = store.get_runtime_state("ga_bound_conversation_id")
        if self.active_conversation_id is None:
            conversation = self.store.create_conversation()
            self.active_conversation_id = conversation["id"]
            self.store.set_runtime_state("active_conversation_id", self.active_conversation_id)

    def active_task(self):
        for task in reversed(list(self.tasks.values())):
            if task.status == "running":
                return task
        return None

    def list_conversations(self):
        return self.store.list_conversations()

    def create_conversation(self, initial_user_text="", group_id=None):
        conversation = self.store.create_conversation(
            initial_user_text=initial_user_text,
            group_id=group_id,
        )
        self.activate_conversation(conversation["id"])
        return conversation

    def get_conversation(self, conversation_id):
        detail = self.store.get_conversation_detail(conversation_id)
        if detail is None:
            raise KeyError("conversation_not_found")
        return detail

    def rename_conversation(self, conversation_id, title):
        updated = self.store.update_conversation(conversation_id, title=title)
        if updated is None:
            raise KeyError("conversation_not_found")
        return updated

    def delete_conversation(self, conversation_id):
        self.store.delete_conversation(conversation_id)
        if self.active_conversation_id == conversation_id:
            remaining = self.store.list_conversations()
            if remaining:
                self.activate_conversation(remaining[0]["id"])
            else:
                conversation = self.store.create_conversation()
                self.activate_conversation(conversation["id"])
        return {"ok": True}

    def pin_conversation(self, conversation_id, pinned):
        updated = self.store.pin_conversation(conversation_id, pinned)
        if updated is None:
            raise KeyError("conversation_not_found")
        return updated

    def move_conversation(self, conversation_id, group_id):
        updated = self.store.move_conversation(
            conversation_id,
            GroupMoveRequest(group_id),
        )
        if updated is None:
            raise KeyError("conversation_not_found")
        return updated

    def list_groups(self):
        return self.store.list_groups()

    def create_group(self, name):
        return self.store.create_group(name)

    def update_group(self, group_id, name):
        updated = self.store.update_group(group_id, name)
        if updated is None:
            raise KeyError("group_not_found")
        return updated

    def delete_group(self, group_id):
        return self.store.delete_group(group_id)

    def activate_conversation(self, conversation_id):
        detail = self.store.get_conversation_detail(conversation_id)
        if detail is None:
            raise KeyError("conversation_not_found")
        self.active_conversation_id = conversation_id
        self.store.set_runtime_state("active_conversation_id", conversation_id)
        return detail

    def start_chat(self, request: ChatStartRequest):
        if self.agent is None:
            raise RuntimeError("agent_not_configured")
        prompt = (request.prompt or "").strip()
        if not prompt:
            raise ValueError("empty_prompt")
        detail = self.store.get_conversation_detail(request.conversation_id)
        if detail is None:
            raise KeyError("conversation_not_found")
        if self.active_task() is not None:
            raise RuntimeError("task_running")

        if self.active_conversation_id != request.conversation_id:
            self.activate_conversation(request.conversation_id)

        # 中文注释：只有当目标会话与当前绑定到 GA 的会话不一致时，才重置并重放上下文。
        if self.ga_bound_conversation_id != request.conversation_id:
            self._reset_agent_runtime()
            self.ga_bound_conversation_id = request.conversation_id
            self.store.set_runtime_state("ga_bound_conversation_id", request.conversation_id)

        history_messages = detail["messages"]
        ga_prompt = _conversation_history_prompt(history_messages, prompt)
        output_queue = self.agent.put_task(ga_prompt, source="user")
        task_id = uuid.uuid4().hex
        self.store.add_message(request.conversation_id, "user", prompt, "ui")
        self.tasks[task_id] = TaskRecord(
            task_id=task_id,
            output_queue=output_queue,
            prompt=prompt,
            conversation_id=request.conversation_id,
            created_at=time.time(),
            execution_log=[],
        )
        return {"task_id": task_id}

    def drain_task(self, task_id, timeout=10.0):
        task = self.tasks.get(task_id)
        if task is None:
            yield {"event": "app_error", "error": "task_not_found"}
            return
        while task.status == "running":
            try:
                item = task.output_queue.get(timeout=timeout)
            except queue.Empty:
                yield {"event": "heartbeat", "status": task.status}
                continue
            if "next" in item:
                task.current_response = item["next"]
                task.execution_log = parse_execution_log(task.current_response)
                cleaned = extract_visible_reply_text(task.current_response)
                # 中文注释：message_delta 只传真正的聊天正文；若当前只有执行过程则不发正文事件。
                if cleaned:
                    yield {
                        "event": "message_delta",
                        "content": cleaned,
                        "conversation_id": task.conversation_id,
                    }
                yield {
                    "event": "execution_update",
                    "execution_log": task.execution_log,
                    "conversation_id": task.conversation_id,
                }
            if "done" in item:
                task.current_response = item["done"]
                task.status = "done"
                task.completed_at = time.time()
                self.last_reply_time = int(task.completed_at)
                task.execution_log = parse_execution_log(task.current_response)
                cleaned = extract_visible_reply_text(task.current_response)
                self.store.add_message(
                    task.conversation_id,
                    "assistant",
                    cleaned,
                    "ga",
                    execution_log=task.execution_log,
                )
                yield {
                    "event": "message_done",
                    "content": cleaned,
                    "conversation_id": task.conversation_id,
                }
                yield {
                    "event": "execution_update",
                    "execution_log": task.execution_log,
                    "conversation_id": task.conversation_id,
                }

    def abort(self):
        if self.agent is not None:
            self.agent.abort()
        for task in self.tasks.values():
            if task.status == "running":
                task.status = "aborted"
                task.completed_at = time.time()
        return {"ok": True}

    def switch_llm(self, index):
        if self.agent is None:
            raise RuntimeError("agent_not_configured")
        self.agent.next_llm(int(index))
        self.ga_bound_conversation_id = None
        self.store.set_runtime_state("ga_bound_conversation_id", None)
        return build_state(self.agent, self)

    def reinject(self):
        client = getattr(self.agent, "llmclient", None)
        if client is not None and hasattr(client, "last_tools"):
            client.last_tools = ""
        self.ga_bound_conversation_id = None
        self.store.set_runtime_state("ga_bound_conversation_id", None)
        return {"ok": True}

    def reset_conversation(self):
        self._reset_agent_runtime()
        conversation = self.store.create_conversation()
        self.activate_conversation(conversation["id"])
        self.ga_bound_conversation_id = None
        self.store.set_runtime_state("ga_bound_conversation_id", None)
        self.last_reply_time = _now_ts()
        return {
            "message": "New conversation started",
            "conversation": conversation,
        }

    def continue_conversation(self, command):
        """兼容旧命令，但不再作为新会话体系主数据源。"""
        from frontends.continue_cmd import (
            extract_ui_messages,
            handle_frontend_command,
            list_sessions,
        )

        command = (command or "").strip()
        target = None
        match = re.match(r"/continue\s+(\d+)\s*$", command)
        sessions = list_sessions(exclude_pid=os.getpid()) if match else []
        if match:
            idx = int(match.group(1)) - 1
            if 0 <= idx < len(sessions):
                target = sessions[idx][0]
        message = handle_frontend_command(self.agent, command)
        history = extract_ui_messages(target) if target and message.startswith("✅") else None
        if history:
            history = [
                {
                    **item,
                    "content": strip_summary_blocks(item.get("content", "")),
                }
                if item.get("role") != "user"
                else item
                for item in history
            ]
        self.ga_bound_conversation_id = None
        self.store.set_runtime_state("ga_bound_conversation_id", None)
        self.last_reply_time = _now_ts()
        return {"message": strip_summary_blocks(message), "history": history or []}

    def set_autonomous(self, enabled):
        self.autonomous_enabled = bool(enabled)
        return {"autonomous_enabled": self.autonomous_enabled}

    def _reset_agent_runtime(self):
        from frontends.continue_cmd import reset_conversation

        reset_conversation(self.agent, message=None)


class WebUIRuntime:
    def __init__(self, agent=None, manager=None, init_error=None, dev_url=None):
        self.agent = agent
        self.manager = manager
        self.init_error = init_error
        self.dev_url = dev_url


def _json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _read_json(handler):
    length = int(handler.headers.get("Content-Length", "0") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        raise ValueError("invalid_json")


def _static_path(path):
    if path in ("", "/"):
        path = "/index.html"
    requested = (WEBUI_DIST / path.lstrip("/")).resolve()
    dist_root = WEBUI_DIST.resolve()
    if not str(requested).startswith(str(dist_root)):
        return None
    if requested.is_file():
        return requested
    fallback = WEBUI_DIST / "index.html"
    return fallback if fallback.is_file() else None


class WebUIRequestHandler(BaseHTTPRequestHandler):
    runtime = WebUIRuntime()

    def log_message(self, fmt, *args):
        print(f"[WebUI] {self.address_string()} - {fmt % args}")

    def _send_json(self, payload, status=HTTPStatus.OK):
        data = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _send_error_json(self, status, error, message=None):
        payload = {"error": error}
        if message:
            payload["message"] = message
        self._send_json(payload, status)

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,DELETE,OPTIONS")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/state":
            payload = build_state(self.runtime.agent, self.runtime.manager)
            if self.runtime.manager is not None:
                payload["conversations"] = self.runtime.manager.list_conversations()
                payload["groups"] = self.runtime.manager.list_groups()
            if self.runtime.init_error:
                payload["configured"] = False
                payload["error"] = self.runtime.init_error
            self._send_json(payload)
            return
        if path == "/api/conversations":
            self._send_json({"items": self.runtime.manager.list_conversations()})
            return
        if path == "/api/groups":
            self._send_json({"items": self.runtime.manager.list_groups()})
            return
        conversation_match = re.match(r"^/api/conversations/([^/]+)$", path)
        if conversation_match:
            try:
                self._send_json(self.runtime.manager.get_conversation(conversation_match.group(1)))
            except KeyError:
                self._send_error_json(HTTPStatus.NOT_FOUND, "conversation_not_found")
            return
        stream_match = re.match(r"^/api/chat/([^/]+)/stream$", path)
        if stream_match:
            self._send_stream(stream_match.group(1))
            return
        self._send_static(path)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            body = _read_json(self)
        except ValueError:
            self._send_error_json(HTTPStatus.BAD_REQUEST, "invalid_json")
            return
        try:
            if self.runtime.manager is None:
                raise RuntimeError("agent_not_configured")
            if path == "/api/chat":
                request = ChatStartRequest(
                    conversation_id=str(body.get("conversation_id") or self.runtime.manager.active_conversation_id or ""),
                    prompt=str(body.get("prompt", "")).strip(),
                )
                if not request.conversation_id:
                    raise KeyError("conversation_not_found")
                self._send_json(self.runtime.manager.start_chat(request))
                return
            if path == "/api/abort":
                self._send_json(self.runtime.manager.abort())
                return
            if path == "/api/llm":
                self._send_json(self.runtime.manager.switch_llm(body.get("index", 0)))
                return
            if path == "/api/reinject":
                self._send_json(self.runtime.manager.reinject())
                return
            if path == "/api/new":
                self._send_json(self.runtime.manager.reset_conversation())
                return
            if path == "/api/continue":
                self._send_json(self.runtime.manager.continue_conversation(body.get("command", "")))
                return
            if path == "/api/autonomous":
                self._send_json(self.runtime.manager.set_autonomous(body.get("enabled", False)))
                return
            if path == "/api/conversations":
                conversation = self.runtime.manager.create_conversation(
                    initial_user_text=str(body.get("title_hint", "") or ""),
                    group_id=body.get("group_id"),
                )
                self._send_json(conversation, HTTPStatus.CREATED)
                return
            if path == "/api/groups":
                group = self.runtime.manager.create_group(str(body.get("name", "") or DEFAULT_GROUP_NAME))
                self._send_json(group, HTTPStatus.CREATED)
                return
            activate_match = re.match(r"^/api/conversations/([^/]+)/activate$", path)
            if activate_match:
                self._send_json(self.runtime.manager.activate_conversation(activate_match.group(1)))
                return
            pin_match = re.match(r"^/api/conversations/([^/]+)/pin$", path)
            if pin_match:
                self._send_json(
                    self.runtime.manager.pin_conversation(
                        pin_match.group(1),
                        bool(body.get("pinned", True)),
                    )
                )
                return
            move_match = re.match(r"^/api/conversations/([^/]+)/move$", path)
            if move_match:
                self._send_json(
                    self.runtime.manager.move_conversation(
                        move_match.group(1),
                        body.get("group_id"),
                    )
                )
                return
        except KeyError as exc:
            self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
            return
        except ValueError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except Exception as exc:
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "server_error", str(exc))
            return
        self._send_error_json(HTTPStatus.NOT_FOUND, "not_found")

    def do_PATCH(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            body = _read_json(self)
        except ValueError:
            self._send_error_json(HTTPStatus.BAD_REQUEST, "invalid_json")
            return
        try:
            conversation_match = re.match(r"^/api/conversations/([^/]+)$", path)
            if conversation_match:
                self._send_json(
                    self.runtime.manager.rename_conversation(
                        conversation_match.group(1),
                        body.get("title", ""),
                    )
                )
                return
            group_match = re.match(r"^/api/groups/([^/]+)$", path)
            if group_match:
                self._send_json(
                    self.runtime.manager.update_group(
                        group_match.group(1),
                        body.get("name", ""),
                    )
                )
                return
        except KeyError as exc:
            self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
            return
        self._send_error_json(HTTPStatus.NOT_FOUND, "not_found")

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            conversation_match = re.match(r"^/api/conversations/([^/]+)$", path)
            if conversation_match:
                self._send_json(self.runtime.manager.delete_conversation(conversation_match.group(1)))
                return
            group_match = re.match(r"^/api/groups/([^/]+)$", path)
            if group_match:
                self._send_json(self.runtime.manager.delete_group(group_match.group(1)))
                return
        except KeyError as exc:
            self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
            return
        self._send_error_json(HTTPStatus.NOT_FOUND, "not_found")

    def _send_stream(self, task_id):
        if self.runtime.manager is None:
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "agent_not_configured")
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        for event in self.runtime.manager.drain_task(task_id):
            name = event.get("event", "message")
            data = json.dumps(event, ensure_ascii=False)
            self.wfile.write(f"event: {name}\n".encode("utf-8"))
            self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
            self.wfile.flush()
            if name in {"message_done", "app_error"}:
                break

    def _send_static(self, path):
        static_file = _static_path(path)
        if static_file is None:
            self._send_error_json(
                HTTPStatus.NOT_FOUND,
                "webui_not_built",
                "Run npm run build --prefix frontends/webui first.",
            )
            return
        data = static_file.read_bytes()
        content_type = mimetypes.guess_type(str(static_file))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def create_runtime(dev_url=None, db_path=None):
    try:
        sys.path.insert(0, str(ROOT_DIR))
        from agentmain import GeneraticAgent
        from frontends.continue_cmd import install as install_continue_patch

        # 中文注释：continue_cmd patch 只在新 WebUI 的 server 里安装，避免改动共享前端模块。
        install_continue_patch(GeneraticAgent)
        agent = GeneraticAgent()
        thread = threading.Thread(target=agent.run, daemon=True)
        thread.start()
        store = SQLiteConversationStore(db_path or DEFAULT_DB_PATH)
        manager = WebUITaskManager(agent, store)
        return WebUIRuntime(agent=agent, manager=manager, dev_url=dev_url)
    except Exception as exc:
        return WebUIRuntime(init_error=str(exc), dev_url=dev_url)


def create_server(host, port, runtime):
    class Handler(WebUIRequestHandler):
        pass

    Handler.runtime = runtime
    return ThreadingHTTPServer((host, port), Handler)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18601)
    parser.add_argument("--dev-url", default="")
    parser.add_argument("--db-path", default="")
    args = parser.parse_args(argv)

    runtime = create_runtime(
        dev_url=args.dev_url or None,
        db_path=args.db_path or None,
    )
    server = create_server(args.host, args.port, runtime)
    print(f"[WebUI] serving on http://{args.host}:{server.server_port}")
    if runtime.init_error:
        print(f"[WebUI] agent init error: {runtime.init_error}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
