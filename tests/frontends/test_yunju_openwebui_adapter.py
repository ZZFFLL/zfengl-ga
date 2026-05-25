import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from tempfile import TemporaryDirectory
from pathlib import Path

from frontends.yunju_openwebui_adapter.metadata import extract_request_meta, conversation_key
from frontends.yunju_openwebui_adapter.runner import YunjuOpenWebUIRunner
from frontends.yunju_openwebui_adapter.server import AdapterRuntime, make_handler


# 中文注释：这些测试只覆盖 GA 侧适配器行为，OpenWebUI 项目仅作为只读协议参考。
class FakeManager:
    def __init__(self):
        self.created = []
        self.activated = []
        self.started = []
        self.aborted = False
        self.conversations = {}
        self.stream_events = {}
        self.next_stream_events = None
        self.switch_llm_calls = []

    def list_conversations(self):
        return list(self.conversations.values())

    def create_conversation(self, initial_user_text="", group_id=None):
        conversation_id = f"conv-{len(self.conversations) + 1}"
        conversation = {
            "id": conversation_id,
            "title": initial_user_text or "新对话",
            "group_id": group_id,
        }
        self.conversations[conversation_id] = conversation
        self.created.append((initial_user_text, group_id))
        return conversation

    def activate_conversation(self, conversation_id):
        if conversation_id not in self.conversations:
            raise KeyError("conversation_not_found")
        self.activated.append(conversation_id)
        return {"summary": self.conversations[conversation_id], "messages": []}

    def start_chat(self, request):
        self.started.append(request)
        task_id = f"task-{len(self.started)}"
        if self.next_stream_events is not None:
            self.stream_events[task_id] = self.next_stream_events
            self.next_stream_events = None
        else:
            self.stream_events[task_id] = [
                {"event": "message_delta", "content": "pong", "conversation_id": request.conversation_id},
                {"event": "message_done", "content": "pong", "conversation_id": request.conversation_id},
            ]
        return {"task_id": task_id}

    def drain_task(self, task_id):
        yield from self.stream_events.get(task_id, [{"event": "app_error", "error": "missing"}])

    def abort(self):
        self.aborted = True
        return {"ok": True}

    def switch_llm(self, index):
        self.switch_llm_calls.append(index)
        return {"current_llm": {"index": int(index), "name": "Fake/GA"}}


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        runtime = AdapterRuntime(
            runner=YunjuOpenWebUIRunner(FakeManager(), model_id="ga-yunju"),
            api_key="test-key",
        )
        handler = make_handler(runtime)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method, path, body=None, headers=None, auth=True):
        conn = HTTPConnection(self.host, self.port, timeout=5)
        request_headers = dict(headers or {})
        if auth:
            request_headers["Authorization"] = "Bearer test-key"
        if body is not None:
            request_headers["Content-Type"] = "application/json"
            body = json.dumps(body).encode("utf-8")
        conn.request(method, path, body=body, headers=request_headers)
        response = conn.getresponse()
        payload = response.read()
        conn.close()
        return response.status, response.getheaders(), payload

    def test_health_without_auth_reports_yunju_adapter(self):
        status, _, payload = self.request("GET", "/health", auth=False)

        self.assertEqual(status, 200)
        data = json.loads(payload.decode("utf-8"))
        self.assertEqual(data["service"], "generic-agent-yunju-openwebui-adapter")
        self.assertTrue(data["ok"])

    def test_models_returns_openai_compatible_model(self):
        status, _, payload = self.request("GET", "/v1/models")

        self.assertEqual(status, 200)
        data = json.loads(payload.decode("utf-8"))
        self.assertEqual(data["object"], "list")
        self.assertEqual(data["data"][0]["id"], "ga-yunju")
        self.assertEqual(data["data"][0]["owned_by"], "generic-agent")

    def test_chat_non_stream_uses_metadata_chat_id_for_ga_conversation(self):
        status, _, payload = self.request(
            "POST",
            "/v1/chat/completions",
            {
                "model": "ga-yunju",
                "stream": False,
                "metadata": {"chat_id": "owui-chat-1", "user_id": "user-a"},
                "messages": [{"role": "user", "content": "ping"}],
            },
        )

        self.assertEqual(status, 200)
        data = json.loads(payload.decode("utf-8"))
        self.assertEqual(data["choices"][0]["message"]["content"], "pong")
        manager = self.server.RequestHandlerClass.runtime.runner.manager
        self.assertEqual(len(manager.created), 1)
        self.assertEqual(manager.started[0].prompt, "ping")
        self.assertEqual(manager.started[0].conversation_id, "conv-1")

    def test_chat_accepts_openclaw_user_model_from_openwebui(self):
        status, _, payload = self.request(
            "POST",
            "/v1/chat/completions",
            {
                "model": "openclaw/alice",
                "stream": False,
                "metadata": {"chat_id": "owui-openclaw-chat", "user_id": "user-a"},
                "messages": [{"role": "user", "content": "ping"}],
            },
        )

        self.assertEqual(status, 200)
        data = json.loads(payload.decode("utf-8"))
        self.assertEqual(data["model"], "openclaw/alice")
        self.assertEqual(data["choices"][0]["message"]["content"], "pong")
        manager = self.server.RequestHandlerClass.runtime.runner.manager
        self.assertEqual(manager.started[-1].prompt, "ping")

    def test_provision_accepts_openclaw_payload(self):
        status, _, payload = self.request(
            "POST",
            "/provision",
            {
                "agentId": "openclaw-user-a",
                "model": "openclaw/user-a",
                "userId": "user-a",
                "userName": "Alice",
                "userEmail": "alice@example.test",
            },
        )

        self.assertEqual(status, 200)
        data = json.loads(payload.decode("utf-8"))
        self.assertTrue(data["ok"])
        self.assertEqual(data["agent_id"], "openclaw-user-a")
        self.assertEqual(data["model"], "openclaw/user-a")

    def test_chat_stream_returns_openai_sse_chunks(self):
        status, headers, payload = self.request(
            "POST",
            "/v1/chat/completions",
            {
                "model": "ga-yunju",
                "stream": True,
                "metadata": {"chat_id": "owui-chat-stream"},
                "messages": [{"role": "user", "content": "ping"}],
            },
        )

        self.assertEqual(status, 200)
        self.assertIn(("Content-Type", "text/event-stream; charset=utf-8"), headers)
        text = payload.decode("utf-8")
        self.assertIn('"object": "chat.completion.chunk"', text)
        self.assertIn('"content": "pong"', text)
        self.assertIn("data: [DONE]", text)

    def test_chat_stream_sends_final_snapshot_once_without_duplicate_prefix(self):
        manager = self.server.RequestHandlerClass.runtime.runner.manager
        manager.next_stream_events = [
            {"event": "message_delta", "content": "上一轮已经全部列出来了", "conversation_id": "conv-1"},
            {
                "event": "message_delta",
                "content": "上一轮已经全部列出来了，共 30+ 个 SOP/工具模块",
                "conversation_id": "conv-1",
            },
            {
                "event": "message_done",
                "content": "上一轮已经全部列出来了，共 30+ 个 SOP/工具模块",
                "conversation_id": "conv-1",
            },
        ]

        status, _, payload = self.request(
            "POST",
            "/v1/chat/completions",
            {
                "model": "ga-yunju",
                "stream": True,
                "metadata": {"chat_id": "owui-chat-snapshot"},
                "messages": [{"role": "user", "content": "ping"}],
            },
        )

        self.assertEqual(status, 200)
        text = payload.decode("utf-8")
        self.assertIn('"content": "上一轮已经全部列出来了，共 30+ 个 SOP/工具模块"', text)
        self.assertEqual(text.count("上一轮已经全部列出来了"), 1)

    def test_chat_stream_streams_reasoning_before_final_answer(self):
        manager = self.server.RequestHandlerClass.runtime.runner.manager
        first_log = [
            {
                "turn": 1,
                "title": "读取项目结构",
                "content": "先确认适配器入口",
                "state": "active",
                "tool_calls": [],
            }
        ]
        second_log = [
            {
                "turn": 1,
                "title": "读取项目结构",
                "content": "先确认适配器入口",
                "state": "completed",
                "tool_calls": [],
            },
            {
                "turn": 2,
                "title": "实现协议映射",
                "content": "把执行日志映射到 OpenWebUI reasoning_content",
                "state": "active",
                "tool_calls": [],
            },
        ]
        manager.next_stream_events = [
            {"event": "execution_update", "execution_log": first_log, "conversation_id": "conv-1"},
            {"event": "message_delta", "content": "已适配。", "conversation_id": "conv-1"},
            {"event": "execution_update", "execution_log": second_log, "conversation_id": "conv-1"},
            {"event": "message_done", "content": "已适配。完成。", "conversation_id": "conv-1"},
        ]

        status, _, payload = self.request(
            "POST",
            "/v1/chat/completions",
            {
                "model": "ga-yunju",
                "stream": True,
                "metadata": {"chat_id": "owui-chat-reasoning"},
                "messages": [{"role": "user", "content": "ping"}],
            },
        )

        self.assertEqual(status, 200)
        # 中文注释：OpenWebUI 只能稳定渲染正文前的单个 reasoning_content 块。
        text = payload.decode("utf-8")
        self.assertGreaterEqual(text.count('"reasoning_content":'), 2)
        self.assertIn('"reasoning_content":', text)
        self.assertIn("Turn 1 · 读取项目结构", text)
        self.assertIn("Turn 2 · 实现协议映射", text)
        self.assertIn('"content": "已适配。完成。"', text)
        self.assertEqual(text.count("先确认适配器入口"), 1)
        self.assertLess(text.rindex('"reasoning_content":'), text.index('"content": "已适配。完成。"'))

    def test_stream_console_summary_reports_outgoing_delta_kind(self):
        from frontends.yunju_openwebui_adapter.server import _stream_event_summary

        self.assertEqual(
            _stream_event_summary({"delta": {"reasoning_content": "abc"}, "finish_reason": None}),
            "reasoning chars=3",
        )
        self.assertEqual(
            _stream_event_summary({"delta": {"content": "answer"}, "finish_reason": None}),
            "content chars=6",
        )
        self.assertEqual(_stream_event_summary({"delta": {}, "finish_reason": "stop"}), "stop")

    def test_openwebui_title_task_does_not_start_ga_chat(self):
        status, _, payload = self.request(
            "POST",
            "/v1/chat/completions",
            {
                "model": "ga-yunju",
                "stream": False,
                "metadata": {"task": "title_generation", "chat_id": "owui-task-chat"},
                "messages": [{"role": "user", "content": "Generate a concise title for hello world"}],
            },
        )

        self.assertEqual(status, 200)
        data = json.loads(payload.decode("utf-8"))
        self.assertEqual(json.loads(data["choices"][0]["message"]["content"])["title"], "hello world")
        manager = self.server.RequestHandlerClass.runtime.runner.manager
        self.assertEqual(manager.started, [])

    def test_openwebui_follow_up_task_returns_empty_json_without_ga_chat(self):
        status, _, payload = self.request(
            "POST",
            "/v1/chat/completions",
            {
                "model": "ga-yunju",
                "stream": False,
                "metadata": {"task": "follow_up_generation", "chat_id": "owui-task-chat"},
                "messages": [{"role": "user", "content": "Suggest follow ups"}],
            },
        )

        self.assertEqual(status, 200)
        data = json.loads(payload.decode("utf-8"))
        self.assertEqual(json.loads(data["choices"][0]["message"]["content"]), {"follow_ups": []})
        manager = self.server.RequestHandlerClass.runtime.runner.manager
        self.assertEqual(manager.started, [])

    def test_openwebui_follow_up_prompt_without_metadata_does_not_start_ga_chat(self):
        prompt = (
            "### Task:\n"
            "Suggest 3-5 relevant follow-up questions or prompts that the user might naturally ask next "
            "in this conversation as a **user**, based on the chat history, to help continue or deepen "
            "the discussion.\n"
            "### Output:\n"
            'JSON format: { "follow_ups": ["Question 1?", "Question 2?", "Question 3?"] }\n'
            "### Chat History:\n<chat_history>\nUSER: hi\nASSISTANT: hello\n</chat_history>"
        )

        status, _, payload = self.request(
            "POST",
            "/v1/chat/completions",
            {
                "model": "ga-yunju",
                "stream": False,
                "metadata": {"chat_id": "owui-task-chat"},
                "messages": [{"role": "user", "content": prompt}],
            },
        )

        self.assertEqual(status, 200)
        data = json.loads(payload.decode("utf-8"))
        self.assertEqual(json.loads(data["choices"][0]["message"]["content"]), {"follow_ups": []})
        manager = self.server.RequestHandlerClass.runtime.runner.manager
        self.assertEqual(manager.started, [])

    def test_openwebui_function_calling_prompt_without_metadata_does_not_start_ga_chat(self):
        prompt = (
            'History:\nSYSTEM: """Host-controlled workspace publish bridge"""\n'
            'USER: """hi"""\n'
            "Query: 你能帮我做什么？"
        )

        status, _, payload = self.request(
            "POST",
            "/v1/chat/completions",
            {
                "model": "ga-yunju",
                "stream": False,
                "metadata": {"chat_id": "owui-task-chat"},
                "messages": [
                    {
                        "role": "system",
                        "content": 'Available Tools: []\nReturn {"tool_calls": []} if no tools match.',
                    },
                    {"role": "user", "content": prompt},
                ],
            },
        )

        self.assertEqual(status, 200)
        data = json.loads(payload.decode("utf-8"))
        self.assertEqual(json.loads(data["choices"][0]["message"]["content"]), {"tool_calls": []})
        manager = self.server.RequestHandlerClass.runtime.runner.manager
        self.assertEqual(manager.started, [])

    def test_openwebui_headers_are_supported_as_conversation_metadata(self):
        body = {"model": "ga-yunju", "messages": [{"role": "user", "content": "ping"}]}
        headers = {
            "x-openwebui-chat-id": "chat-from-header",
            "x-openwebui-message-id": "msg-from-header",
            "x-openwebui-user-id": "user-from-header",
        }

        meta = extract_request_meta(body, headers)

        self.assertEqual(meta.chat_id, "chat-from-header")
        self.assertEqual(meta.message_id, "msg-from-header")
        self.assertEqual(meta.user_id, "user-from-header")
        self.assertEqual(conversation_key(meta), "user-from-header:chat-from-header")

    def test_reuses_same_ga_conversation_for_same_openwebui_chat(self):
        body = {
            "model": "ga-yunju",
            "stream": False,
            "metadata": {"chat_id": "same-chat", "user_id": "user-a"},
            "messages": [{"role": "user", "content": "ping"}],
        }

        self.request("POST", "/v1/chat/completions", body)
        self.request("POST", "/v1/chat/completions", body)

        manager = self.server.RequestHandlerClass.runtime.runner.manager
        self.assertEqual(len(manager.created), 1)
        self.assertEqual(len(manager.started), 2)
        self.assertEqual(manager.started[0].conversation_id, manager.started[1].conversation_id)

    def test_configure_runtime_can_create_log_file_without_agent_import(self):
        from frontends.yunju_openwebui_adapter.server import configure_file_logging

        with TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "adapter.log"
            logger = configure_file_logging(log_path)
            handlers = [
                handler
                for handler in logger.handlers
                if getattr(handler, "baseFilename", None) == str(log_path.resolve())
            ]
            try:
                logger.info("yunju adapter log smoke")
                for handler in handlers:
                    handler.flush()
                self.assertIn("yunju adapter log smoke", log_path.read_text(encoding="utf-8"))
            finally:
                for handler in handlers:
                    logger.removeHandler(handler)
                    handler.close()


class ProtocolTestCase(unittest.TestCase):
    def test_strips_openwebui_reasoning_details_from_history_messages(self):
        from frontends.yunju_openwebui_adapter.protocol import parse_chat_request

        request = parse_chat_request(
            {
                "model": "ga-yunju",
                "messages": [
                    {
                        "role": "assistant",
                        "content": (
                            '<details type="reasoning" done="true">\n'
                            "<summary>Thought</summary>\n"
                            "> Turn 1 · 内部过程\n"
                            "</details>\n"
                            "最终答复"
                        ),
                    },
                    {"role": "user", "content": "继续"},
                ],
            },
            allowed_models={"ga-yunju"},
        )

        self.assertEqual(request.messages[0].content, "最终答复")
        self.assertEqual(request.messages[1].content, "继续")

    def test_extracts_latest_user_text_from_mixed_content_parts(self):
        from frontends.yunju_openwebui_adapter.protocol import latest_user_text, parse_chat_request

        request = parse_chat_request(
            {
                "model": "ga-yunju",
                "messages": [
                    {"role": "system", "content": "rules"},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "hello"},
                            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                        ],
                    },
                ],
            },
            allowed_models={"ga-yunju"},
        )

        self.assertEqual(latest_user_text(request.messages), "hello\n[Image omitted] data:image/png;base64,abc")


if __name__ == "__main__":
    unittest.main()
