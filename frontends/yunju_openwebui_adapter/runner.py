import threading

from frontends.webui_server import ChatStartRequest

from .metadata import conversation_key
from .protocol import latest_user_text


class YunjuOpenWebUIRunner:
    def __init__(self, manager, model_id="ga-yunju"):
        self.manager = manager
        self.model_id = model_id
        self._lock = threading.Lock()
        self._conversation_ids = {}

    def is_running(self):
        active_task = getattr(self.manager, "active_task", lambda: None)()
        return active_task is not None

    def current_model(self):
        agent = getattr(self.manager, "agent", None)
        getter = getattr(agent, "get_llm_name", None)
        if getter is None:
            return self.model_id
        try:
            return getter()
        except Exception:
            return self.model_id

    def chat(self, request, meta):
        task_id = self.start(request, meta)
        content = ""
        for event in self.manager.drain_task(task_id):
            if event.get("event") in {"message_delta", "message_done"}:
                content = event.get("content") or content
            if event.get("event") == "message_done":
                return content
            if event.get("event") == "app_error":
                raise RuntimeError(event.get("error") or "app_error")
        return content

    def stream_chat(self, request, meta):
        task_id = self.start(request, meta)
        content = ""
        execution_log = []
        reasoning_tracker = _SnapshotDeltaTracker()
        for event in self.manager.drain_task(task_id):
            name = event.get("event")
            if name == "message_delta":
                content = event.get("content") or content
            elif name == "execution_update":
                execution_log = event.get("execution_log") or execution_log
                # 中文注释：OpenWebUI 会在正文开始后关闭思考块，所以这里只流式输出思考，正文延后到结束时再发。
                reasoning_delta = reasoning_tracker.consume(_render_execution_log(execution_log))
                if reasoning_delta:
                    yield {"delta": {"reasoning_content": reasoning_delta}, "finish_reason": None}
            elif name == "message_done":
                content = event.get("content") or content
                reasoning_delta = reasoning_tracker.consume(_render_execution_log(execution_log))
                if reasoning_delta:
                    yield {"delta": {"reasoning_content": reasoning_delta}, "finish_reason": None}
                if content:
                    yield {"delta": {"content": content}, "finish_reason": None}
                yield {"delta": {}, "finish_reason": "stop"}
                return
            elif name == "task_aborted":
                yield {"delta": {"content": "\n\n[任务已中止]"}, "finish_reason": "stop"}
                return
            elif name == "app_error":
                raise RuntimeError(event.get("error") or "app_error")

    def abort_current(self):
        return self.manager.abort()

    def start(self, request, meta):
        prompt = latest_user_text(request.messages).strip()
        if not prompt:
            raise RuntimeError("empty_prompt")
        conversation_id = self._ensure_conversation(meta, prompt)
        result = self.manager.start_chat(ChatStartRequest(conversation_id=conversation_id, prompt=prompt))
        return result["task_id"]

    def _ensure_conversation(self, meta, title_hint):
        key = conversation_key(meta)
        with self._lock:
            conversation_id = self._conversation_ids.get(key)
            if conversation_id:
                self.manager.activate_conversation(conversation_id)
                return conversation_id

            # 中文注释：OpenWebUI 的 chat_id 是外部会话键，GA 仍使用自己的会话 id 保存本地状态。
            conversation = self.manager.create_conversation(initial_user_text=title_hint)
            conversation_id = conversation["id"]
            self._conversation_ids[key] = conversation_id
            return conversation_id


def _render_execution_log(execution_log):
    lines = []
    for turn in execution_log or []:
        if not isinstance(turn, dict):
            continue
        title = _clean_line(turn.get("title")) or f"Turn {turn.get('turn') or len(lines) + 1}"
        turn_no = turn.get("turn") or len(lines) + 1
        lines.append(f"Turn {turn_no} · {title}")
        summary = _clean_line(turn.get("summary") or turn.get("content"))
        if summary:
            lines.append(summary)
        for tool_call in turn.get("tool_calls") or []:
            tool_line = _render_tool_call(tool_call)
            if tool_line:
                lines.append(tool_line)
        lines.append("")
    return "\n".join(lines).strip()


def _render_tool_call(tool_call):
    if not isinstance(tool_call, dict):
        return ""
    tool_name = _clean_line(tool_call.get("tool"))
    if not tool_name:
        return ""
    details = []
    action = _clean_line(tool_call.get("action"))
    status = _clean_line(tool_call.get("status"))
    if action:
        details.append(action)
    if status:
        details.append(status)
    # 中文注释：只把工具名称和状态放入 OpenWebUI 思考流，避免把完整工具输出重复塞进聊天上下文。
    return f"Tool: {tool_name}" + (f" ({'; '.join(details)})" if details else "")


def _clean_line(value):
    text = "" if value is None else str(value)
    return " ".join(text.strip().split())


class _SnapshotDeltaTracker:
    def __init__(self):
        self._last_text = ""

    def consume(self, current_text):
        current_text = "" if current_text is None else str(current_text)
        # 中文注释：WebUITaskManager 发的是完整正文快照，OpenAI SSE 需要真正增量，避免前端重复拼接。
        if current_text.startswith(self._last_text):
            delta = current_text[len(self._last_text) :]
        else:
            delta = current_text
        self._last_text = current_text
        return delta
