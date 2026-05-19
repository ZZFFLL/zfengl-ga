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
        tracker = _SnapshotDeltaTracker()
        for event in self.manager.drain_task(task_id):
            name = event.get("event")
            if name == "message_delta":
                delta = tracker.consume(event.get("content") or "")
                if delta:
                    yield {"delta": {"content": delta}, "finish_reason": None}
            elif name == "message_done":
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
