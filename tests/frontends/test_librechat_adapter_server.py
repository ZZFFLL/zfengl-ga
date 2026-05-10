import json
import sys
import threading
import types
import unittest
from pathlib import Path
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from tempfile import TemporaryDirectory
from unittest.mock import patch

from frontends.librechat_adapter import server as server_module
from frontends.librechat_adapter.server import AdapterRuntime, make_handler


class FakeRunner:
    def __init__(self):
        self.chat_requests = []

    def is_running(self):
        return False

    def current_model(self):
        return "Fake/generic-agent"

    def chat(self, request, meta):
        self.chat_requests.append((request, meta))
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 123,
            "model": "generic-agent",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "pong"},
                    "finish_reason": "stop",
                }
            ],
        }

    def stream_chat(self, request, meta):
        yield {"delta": {"role": "assistant"}, "finish_reason": None}
        yield {"delta": {"content": "pong"}, "finish_reason": None}
        yield {"delta": {}, "finish_reason": "stop"}


class FakeSessionBridge:
    def list_sessions(self, limit=20):
        return [
            {
                "id": "ga_sess_fake",
                "updated_at": 123,
                "relative_time": "1秒前",
                "rounds": 1,
                "preview": "hello",
                "native_history_available": True,
            }
        ][:limit]

    def read_session(self, session_id):
        if session_id != "ga_sess_fake":
            raise KeyError(session_id)
        return {
            "id": session_id,
            "object": "ga.session",
            "rounds": 1,
            "messages": [{"role": "user", "content": "hello"}],
            "source": "model_responses",
            "restorable": True,
        }


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        runtime = AdapterRuntime(
            runner=FakeRunner(),
            session_bridge=FakeSessionBridge(),
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

    def request(self, method, path, body=None, auth=True):
        conn = HTTPConnection(self.host, self.port, timeout=5)
        headers = {}
        if auth:
            headers["Authorization"] = "Bearer test-key"
        if body is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(body).encode("utf-8")
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        payload = response.read()
        conn.close()
        return response.status, response.getheaders(), payload

    def test_health_without_auth(self):
        status, _, payload = self.request("GET", "/health", auth=False)

        self.assertEqual(status, 200)
        data = json.loads(payload.decode("utf-8"))
        self.assertTrue(data["ok"])
        self.assertEqual(data["service"], "generic-agent-librechat-adapter")

    def test_models_requires_auth(self):
        status, _, payload = self.request("GET", "/v1/models", auth=False)

        self.assertEqual(status, 401)
        data = json.loads(payload.decode("utf-8"))
        self.assertEqual(data["error"]["code"], "unauthorized")

    def test_models_returns_generic_agent(self):
        status, _, payload = self.request("GET", "/v1/models")

        self.assertEqual(status, 200)
        data = json.loads(payload.decode("utf-8"))
        self.assertEqual(data["object"], "list")
        self.assertEqual(data["data"][0]["id"], "generic-agent")

    def test_chat_non_stream_returns_completion(self):
        status, _, payload = self.request(
            "POST",
            "/v1/chat/completions",
            {
                "model": "generic-agent",
                "stream": False,
                "messages": [{"role": "user", "content": "ping"}],
            },
        )

        self.assertEqual(status, 200)
        data = json.loads(payload.decode("utf-8"))
        self.assertEqual(data["choices"][0]["message"]["content"], "pong")

    def test_chat_stream_returns_openai_sse(self):
        status, headers, payload = self.request(
            "POST",
            "/v1/chat/completions",
            {
                "model": "generic-agent",
                "stream": True,
                "messages": [{"role": "user", "content": "ping"}],
            },
        )

        self.assertEqual(status, 200)
        self.assertIn(("Content-Type", "text/event-stream; charset=utf-8"), headers)
        text = payload.decode("utf-8")
        self.assertIn('"object": "chat.completion.chunk"', text)
        self.assertIn('"id": "req_', text)
        self.assertIn("data: [DONE]", text)

    def test_sessions_requires_auth(self):
        status, _, payload = self.request("GET", "/v1/ga/sessions", auth=False)

        self.assertEqual(status, 401)
        data = json.loads(payload.decode("utf-8"))
        self.assertEqual(data["error"]["code"], "unauthorized")

    def test_sessions_list_and_read(self):
        status, _, payload = self.request("GET", "/v1/ga/sessions?limit=1")

        self.assertEqual(status, 200)
        listed = json.loads(payload.decode("utf-8"))
        self.assertEqual(listed["data"][0]["id"], "ga_sess_fake")

        status, _, payload = self.request("GET", "/v1/ga/sessions/ga_sess_fake")

        self.assertEqual(status, 200)
        data = json.loads(payload.decode("utf-8"))
        self.assertEqual(data["messages"][0]["content"], "hello")

    def test_sessions_bad_limit_returns_bad_request(self):
        status, _, payload = self.request("GET", "/v1/ga/sessions?limit=bad")

        self.assertEqual(status, 400)
        data = json.loads(payload.decode("utf-8"))
        self.assertEqual(data["error"]["code"], "bad_request")

    def test_unknown_route_returns_openai_error(self):
        status, _, payload = self.request("GET", "/v1/missing")

        self.assertEqual(status, 404)
        data = json.loads(payload.decode("utf-8"))
        self.assertEqual(data["error"]["code"], "not_found")

    def test_create_runtime_uses_frontends_import_path(self):
        class FakeAgent:
            def run(self):
                return None

            def _handle_slash_cmd(self, raw_query, display_queue):
                return raw_query

        fake_agentmain = types.SimpleNamespace(GeneraticAgent=FakeAgent)
        original_agentmain = sys.modules.get("agentmain")
        original_chatapp_common = sys.modules.pop("chatapp_common", None)
        sys.modules["agentmain"] = fake_agentmain
        try:
            with patch.object(server_module, "LibreChatAdapterRunner", lambda agent: ("runner", agent)), patch.object(
                server_module, "GASessionBridge", lambda: "bridge"
            ):
                runtime = server_module.create_runtime(api_key="test-key")
        finally:
            if original_agentmain is None:
                sys.modules.pop("agentmain", None)
            else:
                sys.modules["agentmain"] = original_agentmain
            if original_chatapp_common is not None:
                sys.modules["chatapp_common"] = original_chatapp_common
            else:
                sys.modules.pop("chatapp_common", None)

        self.assertFalse(runtime.init_error)
        self.assertEqual(runtime.runner[0], "runner")
        self.assertEqual(runtime.session_bridge, "bridge")

    def test_configure_file_logging_writes_adapter_log_file(self):
        with TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "librechat_adapter.log"

            logger = server_module.configure_file_logging(log_path)
            handlers = [
                handler
                for handler in logger.handlers
                if getattr(handler, "baseFilename", None) == str(log_path.resolve())
            ]
            try:
                logger.info("adapter log smoke")
                for handler in handlers:
                    handler.flush()

                self.assertTrue(log_path.exists())
                self.assertIn(
                    "adapter log smoke",
                    log_path.read_text(encoding="utf-8"),
                )
            finally:
                for handler in handlers:
                    logger.removeHandler(handler)
                    handler.close()


if __name__ == "__main__":
    unittest.main()
