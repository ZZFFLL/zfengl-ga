"""GenericAgent runner facade used by the LibreChat adapter."""

import json
import logging
import re
import threading
import time
import uuid

from frontends.continue_cmd import reset_conversation

from .sessions import InMemoryConversationManager

try:
    from .protocol import build_prompt_from_messages
except Exception:
    def build_prompt_from_messages(messages):
        lines = []
        for message in messages or []:
            role = _message_value(message, "role", "user")
            content = _content_text(_message_value(message, "content", ""))
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

try:
    from .metadata import conversation_key
except Exception:
    def conversation_key(meta):
        return _meta_value(
            meta,
            "conversation_key",
            "conversation_id",
            "conversationId",
            "chat_id",
            "user_id",
            default="local",
        )

try:
    from .streaming import DeltaTracker
except Exception:
    class DeltaTracker:
        def __init__(self):
            self._text = ""

        def update(self, text):
            text = text or ""
            if text.startswith(self._text):
                delta = text[len(self._text):]
            else:
                delta = text
            self._text = text
            return delta

try:
    from .events import strip_summary_blocks
except Exception:
    _SUMMARY_RE = re.compile(r"<summary>\s*.*?\s*</summary>\s*", re.DOTALL)

    def strip_summary_blocks(text):
        return _SUMMARY_RE.sub("", text or "")


MODEL_ID = "generic-agent"
LOGGER_NAME = "generic_agent.librechat_adapter"
_TURN_MARKER_RE = re.compile(
    r"(?:\*\*)?\s*LLM Running\s*\(Turn\s+\d+\)\s*\.\.\.\s*(?:\*\*)?",
    re.IGNORECASE,
)
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
_DANGLING_FENCE_RE = re.compile(r"\n*`{3,}\s*\Z")
_TOOL_CALL_RE = re.compile(
    r"(?:^|\n)\s*(?:\U0001f6e0\ufe0f?\s*)?Tool:\s*`?(?P<name>[^`\s]+)`?.*?"
    r"args:\s*\n(?P<fence>`{3,})[^\n]*\n(?P<args>[\s\S]*?)\n(?P=fence)",
    re.IGNORECASE,
)
_STATUS_RE = re.compile(r"\[Status\]\s*(?P<status>[^\r\n]*)", re.IGNORECASE)
_STDOUT_RE = re.compile(
    r"\[Stdout\]\s*(?P<stdout>[\s\S]*?)(?:\n\[Stderr\]|\Z)",
    re.IGNORECASE,
)
_CODE_BLOCK_RE = re.compile(r"`{3,}[\s\S]*?`{3,}")
_logger = logging.getLogger(LOGGER_NAME)


class LibreChatAdapterRunner:
    def __init__(self, agent, conversation_manager=None):
        self.agent = agent
        self.conversation_manager = (
            conversation_manager or InMemoryConversationManager()
        )
        self._lock = threading.Lock()
        self._active = False

    def is_running(self):
        return self._active or bool(getattr(self.agent, "is_running", False))

    def current_model(self):
        getter = getattr(self.agent, "get_llm_name", None)
        if getter is None:
            return MODEL_ID
        try:
            return getter(model=True)
        except TypeError:
            return getter()
        except Exception:
            return MODEL_ID

    def chat(self, request, meta):
        output_queue, state = self._start_task(request, meta)
        try:
            content = self._read_final_content(output_queue)
            self.conversation_manager.mark_seen(*state)
            return self._completion_payload(request, meta, content)
        finally:
            self._release()

    def stream_chat(self, request, meta):
        output_queue, state = self._start_task(request, meta)
        tracker = DeltaTracker()
        try:
            yield {"delta": {"role": "assistant"}, "finish_reason": None}
            while True:
                item = output_queue.get()
                if isinstance(item, str):
                    delta = _text_delta(tracker, _visible_chat_content(item))
                    if delta:
                        yield _content_event(delta)
                    continue
                if not isinstance(item, dict):
                    continue
                if "next" in item:
                    delta = _text_delta(
                        tracker,
                        _visible_chat_content(str(item.get("next") or "")),
                    )
                    if delta:
                        yield _content_event(delta)
                if "done" in item:
                    raw_done = str(item.get("done") or "")
                    delta = _text_delta(
                        tracker,
                        _visible_chat_content(raw_done),
                    )
                    if delta:
                        yield _content_event(delta)
                    self.conversation_manager.mark_seen(*state)
                    yield {"delta": {}, "finish_reason": "stop"}
                    return
        finally:
            self._release()

    def abort_current(self):
        return self.agent.abort()

    def _start_task(self, request, meta):
        self._reserve()
        try:
            messages = list(getattr(request, "messages", []) or [])
            key = _safe_conversation_key(meta)
            parent_message_id = _meta_value(
                meta,
                "parent_message_id",
                "parentMessageId",
                "parent_id",
                default=None,
            )
            message_count = len(messages)
            switching = self.conversation_manager.is_switching_conversation(key)
            include_history = self.conversation_manager.should_include_history(
                key,
                parent_message_id,
                message_count,
            )
            if switching:
                reset_conversation(self.agent, message=None)
            prompt = _build_prompt(messages, include_history)
            _log_event(
                "runner_start_task",
                conversation_key=key,
                switching=switching,
                include_history=include_history,
                message_count=message_count,
                prompt_chars=len(prompt or ""),
            )
            output_queue = self.agent.put_task(
                prompt,
                source="librechat",
                images=[],
            )
            return output_queue, (key, parent_message_id, message_count)
        except Exception:
            self._release()
            raise

    def _reserve(self):
        with self._lock:
            if self._active or bool(getattr(self.agent, "is_running", False)):
                _log_event(
                    "runner_busy",
                    active=self._active,
                    agent_is_running=bool(getattr(self.agent, "is_running", False)),
                )
                raise RuntimeError("busy")
            self._active = True

    def _release(self):
        with self._lock:
            self._active = False

    @staticmethod
    def _read_final_content(output_queue):
        content = ""
        while True:
            item = output_queue.get()
            if isinstance(item, str):
                content = item
                continue
            if not isinstance(item, dict):
                continue
            if "next" in item:
                content = str(item.get("next") or "")
            if "done" in item:
                raw_done = str(item.get("done") or content)
                return _compose_final_content(raw_done)

    @staticmethod
    def _completion_payload(request, meta, content):
        return {
            "id": (
                getattr(request, "request_id", None)
                or _meta_value(meta, "request_id", "requestId", default=None)
                or f"chatcmpl-{uuid.uuid4().hex}"
            ),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": getattr(request, "model", MODEL_ID) or MODEL_ID,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
        }


def _safe_conversation_key(meta):
    try:
        return str(conversation_key(meta) or "local")
    except Exception:
        return str(_meta_value(meta, "conversation_id", default="local") or "local")


def _latest_user_message(messages):
    for message in reversed(messages):
        if _message_value(message, "role", "") == "user":
            return [message]
    return messages[-1:] if messages else []


def _build_prompt(messages, include_history):
    try:
        return build_prompt_from_messages(messages, include_history)
    except TypeError:
        selected = messages if include_history else _latest_user_message(messages)
        return build_prompt_from_messages(selected)


def _content_event(content):
    return {"delta": {"content": content}, "finish_reason": None}


def _compose_final_content(raw_text):
    return _visible_chat_content(raw_text)


def _visible_chat_content(raw_text):
    text = strip_summary_blocks(str(raw_text or ""))
    process_lines = _execution_process_lines(text)
    final_answer = _final_answer_text(text)
    if not process_lines:
        return final_answer

    parts = ["### 执行过程", *process_lines]
    if final_answer:
        parts.extend(["", "### 最终回答", final_answer])
    return "\n".join(parts).strip()


def _execution_process_lines(text):
    lines = []
    for segment in _turn_segments(text):
        tool_matches = list(_TOOL_CALL_RE.finditer(segment))
        for index, match in enumerate(tool_matches):
            tool_name = (match.group("name") or "tool").strip()
            args_preview = _compact_snippet(match.group("args"), 120)
            line = f"- 调用工具 `{tool_name}`"
            if args_preview:
                line += f"：`{_escape_inline_code(args_preview)}`"
            lines.append(line)

            end = tool_matches[index + 1].start() if index + 1 < len(tool_matches) else len(segment)
            result_text = segment[match.end() : end]
            status_match = _STATUS_RE.search(result_text)
            if status_match:
                status = _compact_snippet(status_match.group("status"), 80)
                suffix = f"：{status}" if status else ""
                lines.append(f"- 工具 `{tool_name}` 返回{suffix}")
            output_preview = _tool_output_preview(result_text)
            if output_preview:
                lines.append(f"- 工具 `{tool_name}` 输出预览：{output_preview}")
    return lines


def _final_answer_text(text):
    segments = _turn_segments(text)
    candidate = segments[-1] if segments else text
    first_tool = _TOOL_CALL_RE.search(candidate)
    if first_tool:
        candidate = candidate[: first_tool.start()]
    candidate = _FINAL_INFO_BLOCK_RE.sub("", candidate)
    candidate = _FINAL_INFO_TRAIL_RE.sub("", candidate)
    candidate = _FINAL_INFO_LINE_RE.sub("", candidate)
    candidate = _CODE_BLOCK_RE.sub("", candidate)
    candidate = _DANGLING_FENCE_RE.sub("", candidate)
    return candidate.strip()


def _turn_segments(text):
    matches = list(_TURN_MARKER_RE.finditer(text or ""))
    if not matches:
        return [text or ""]
    segments = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text or "")
        segments.append((text or "")[match.end() : end])
    return segments


def _compact_snippet(text, limit):
    snippet = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(snippet) <= limit:
        return snippet
    return snippet[: limit - 3].rstrip() + "..."


def _tool_output_preview(text):
    match = _STDOUT_RE.search(text or "")
    if not match:
        return ""
    stdout = re.sub(r"\n`{3,}[\s\S]*\Z", "", match.group("stdout") or "")
    return _compact_snippet(stdout, 220)


def _escape_inline_code(text):
    return str(text or "").replace("`", "'")


def _log_event(event, **fields):
    if not _logger.handlers:
        return
    payload = {"event": event, **fields}
    _logger.info(json.dumps(payload, ensure_ascii=False, default=str))


def _text_delta(tracker, text):
    for method_name in ("consume_snapshot", "delta", "next_delta", "update"):
        method = getattr(tracker, method_name, None)
        if callable(method):
            return _delta_result_text(method(text))
    previous = getattr(tracker, "_ga_last_text", "")
    text = text or ""
    delta = text[len(previous):] if text.startswith(previous) else text
    tracker._ga_last_text = text
    return delta


def _delta_result_text(result):
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        if "content" in result:
            return str(result.get("content") or "")
        delta = result.get("delta")
        if isinstance(delta, str):
            return delta
        if isinstance(delta, dict):
            return str(delta.get("content") or "")
    return str(result)


def _meta_value(meta, *names, default=None):
    if meta is None:
        return default
    if isinstance(meta, dict):
        for name in names:
            if name in meta and meta[name] not in (None, ""):
                return meta[name]
        return default
    for name in names:
        value = getattr(meta, name, None)
        if value not in (None, ""):
            return value
    return default


def _message_value(message, name, default=None):
    if isinstance(message, dict):
        return message.get(name, default)
    return getattr(message, name, default)


def _content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text") or part.get("content") or ""))
            else:
                parts.append(str(part))
        return "\n".join(part for part in parts if part)
    return "" if content is None else str(content)
