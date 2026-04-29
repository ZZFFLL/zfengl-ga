"""Read-only bridge from GenericAgent history logs to LibreChat session data."""

import hashlib
import os
import time

from frontends import continue_cmd

from .events import strip_summary_blocks


class AdapterSessionNotFound(LookupError):
    """Raised when an opaque adapter session id cannot be resolved."""


def _session_id(path, mtime):
    return hashlib.sha256((str(path) + str(mtime)).encode("utf-8")).hexdigest()


def _relative_time(mtime):
    delta = int(time.time() - float(mtime))
    if delta < 60:
        return f"{delta}秒前"
    if delta < 3600:
        return f"{delta // 60}分前"
    if delta < 86400:
        return f"{delta // 3600}小时前"
    return f"{delta // 86400}天前"


def _clean_ui_messages(messages):
    cleaned = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        item = dict(message)
        if item.get("role") == "assistant" and isinstance(item.get("content"), str):
            item["content"] = strip_summary_blocks(item["content"])
        cleaned.append(item)
    return cleaned


class GASessionBridge:
    def _raw_sessions(self):
        return continue_cmd.list_sessions(exclude_pid=os.getpid())

    def _public_session(self, raw_session):
        path, mtime, preview, rounds = raw_session
        return {
            "id": _session_id(path, mtime),
            "updated_at": mtime,
            "relative_time": _relative_time(mtime),
            "rounds": rounds,
            "preview": preview or "",
            "source": "model_responses",
            "restorable": True,
            "native_history_available": True,
        }

    def list_sessions(self, limit=20):
        limit = int(limit if limit is not None else 20)
        if limit < 0:
            limit = 0
        return [self._public_session(raw) for raw in self._raw_sessions()[:limit]]

    def read_session(self, session_id):
        for raw in self._raw_sessions():
            path, mtime, preview, rounds = raw
            opaque_id = _session_id(path, mtime)
            if opaque_id != session_id:
                continue
            messages = _clean_ui_messages(continue_cmd.extract_ui_messages(path))
            return {
                "id": opaque_id,
                "object": "ga.session",
                "updated_at": mtime,
                "relative_time": _relative_time(mtime),
                "rounds": rounds,
                "preview": preview or "",
                "messages": messages,
                "source": "model_responses",
                "restorable": True,
                "native_history_available": True,
            }
        raise AdapterSessionNotFound(session_id)
