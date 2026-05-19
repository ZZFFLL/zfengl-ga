"""云居 OpenWebUI 使用的 GenericAgent OpenAI-compatible HTTP 入口。"""

import argparse
import json
import logging
import os
import sys
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlparse


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_LOG_PATH = ROOT_DIR / "temp" / "yunju_openwebui_adapter.log"
DEFAULT_DB_PATH = ROOT_DIR / "temp" / "yunju_openwebui_adapter.sqlite3"
SERVICE_NAME = "generic-agent-yunju-openwebui-adapter"
LOGGER_NAME = "generic_agent.yunju_openwebui_adapter"

from .metadata import extract_request_meta
from .protocol import (
    AdapterError,
    MODEL_ID,
    make_completion_response,
    make_error_payload,
    make_models_payload,
    make_sse_chunk,
    parse_chat_request,
)
from .runner import YunjuOpenWebUIRunner


@dataclass
class AdapterRuntime:
    runner: object = None
    api_key: str = ""
    model_id: str = MODEL_ID
    init_error: str = ""


def configure_file_logging(log_path=None):
    path = Path(log_path or os.environ.get("GA_YUNJU_OPENWEBUI_ADAPTER_LOG") or DEFAULT_LOG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    target = str(path.resolve())
    for handler in logger.handlers:
        if getattr(handler, "baseFilename", None) == target:
            return logger
    handler = RotatingFileHandler(
        target,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


LOGGER = configure_file_logging()


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


def _authorized(headers, api_key):
    if not api_key:
        return True
    return headers.get("Authorization", "") == f"Bearer {api_key}"


def _coerce_event(event):
    if isinstance(event, str):
        return {"delta": {"content": event}, "finish_reason": None}
    return event or {}


def _clean_text(value):
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _log_event(event, **fields):
    LOGGER.info(json.dumps({"event": event, **fields}, ensure_ascii=False, default=str))


def make_handler(runtime):
    class YunjuOpenWebUIAdapterRequestHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            message = f"{self.address_string()} - {fmt % args}"
            print(f"[YunjuOpenWebUIAdapter] {message}")
            _log_event("http_access", client_ip=self.address_string(), message=message)

        def _send_json(self, payload, status=HTTPStatus.OK):
            data = _json_bytes(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)

        def _send_error(self, status, code, message=None):
            self._send_json(make_error_payload(code, message or code), status)

        def _require_auth(self):
            if _authorized(self.headers, runtime.api_key):
                return True
            self._send_error(HTTPStatus.UNAUTHORIZED, "unauthorized")
            return False

        def do_OPTIONS(self):
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header(
                "Access-Control-Allow-Headers",
                "Content-Type, Authorization, x-openwebui-chat-id, "
                "x-openwebui-conversation-id, x-openwebui-message-id, x-openwebui-user-id",
            )
            self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
            self.end_headers()

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/health":
                self._send_health()
                return
            if not self._require_auth():
                return
            if path in {"/v1/models", "/models"}:
                self._send_models()
                return
            self._send_error(HTTPStatus.NOT_FOUND, "not_found")

        def do_POST(self):
            if not self._require_auth():
                return
            path = urlparse(self.path).path
            try:
                body = _read_json(self)
            except ValueError:
                self._send_error(HTTPStatus.BAD_REQUEST, "bad_request", "invalid_json")
                return
            if path in {"/v1/chat/completions", "/chat/completions"}:
                self._handle_chat(body)
                return
            if path in {"/provision", "/v1/provision", "/v1/openclaw/provision"}:
                self._handle_provision(body)
                return
            if path == "/v1/ga/abort":
                self._handle_abort()
                return
            self._send_error(HTTPStatus.NOT_FOUND, "not_found")

        def _send_health(self):
            running = False
            current_model = None
            if runtime.runner is not None:
                if hasattr(runtime.runner, "is_running"):
                    running = bool(runtime.runner.is_running())
                if hasattr(runtime.runner, "current_model"):
                    current_model = runtime.runner.current_model()
            self._send_json(
                {
                    "ok": runtime.runner is not None and not runtime.init_error,
                    "service": SERVICE_NAME,
                    "version": "0.1.0",
                    "configured": runtime.runner is not None and not runtime.init_error,
                    "running": running,
                    "model_id": runtime.model_id,
                    "current_model": current_model,
                    "error": runtime.init_error or None,
                }
            )

        def _send_models(self):
            self._send_json(make_models_payload(runtime.model_id, "GenericAgent"))

        def _handle_chat(self, body):
            if runtime.runner is None:
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "agent_not_configured")
                return
            try:
                request = parse_chat_request(body, allowed_models={runtime.model_id})
                meta = extract_request_meta(body, self.headers)
                _log_event(
                    "chat_request",
                    request_id=meta.request_id,
                    chat_id=meta.chat_id,
                    user_id=meta.user_id,
                    stream=request.stream,
                )
                if request.stream:
                    self._send_chat_stream(request, meta)
                    return
                content = runtime.runner.chat(request, meta)
                self._send_json(make_completion_response(content, request.model, meta.request_id))
            except AdapterError as exc:
                self._send_error(HTTPStatus(exc.status), exc.code, exc.message)
            except RuntimeError as exc:
                status = HTTPStatus.TOO_MANY_REQUESTS if str(exc) == "task_running" else HTTPStatus.INTERNAL_SERVER_ERROR
                self._send_error(status, str(exc) or "runtime_error")
            except Exception as exc:
                _log_event("chat_error", error_type=type(exc).__name__, error_message=str(exc))
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", str(exc))

        def _handle_provision(self, body):
            agent_id = _clean_text(body.get("agentId") or body.get("agent_id")).strip()
            model = _clean_text(body.get("model") or runtime.model_id).strip()
            user_id = _clean_text(body.get("userId") or body.get("user_id")).strip()
            if not agent_id:
                self._send_error(HTTPStatus.BAD_REQUEST, "invalid_provision", "agentId is required.")
                return
            _log_event("provision_request", agent_id=agent_id, model=model, user_id=user_id)
            # 中文注释：OpenWebUI 只需要确认外部 Agent 已可用，GA 会在聊天请求到达时再创建本地会话。
            self._send_json(
                {
                    "ok": True,
                    "agent_id": agent_id,
                    "model": model,
                    "user_id": user_id,
                    "service": SERVICE_NAME,
                }
            )

        def _send_chat_stream(self, request, meta):
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                role_chunk = make_sse_chunk(meta.request_id, request.model, {"role": "assistant"})
                self.wfile.write(f"data: {json.dumps(role_chunk, ensure_ascii=False)}\n\n".encode("utf-8"))
                self.wfile.flush()
                for event in runtime.runner.stream_chat(request, meta):
                    event = _coerce_event(event)
                    chunk = make_sse_chunk(
                        meta.request_id,
                        request.model,
                        event.get("delta", {}),
                        event.get("finish_reason"),
                    )
                    self.wfile.write(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    if event.get("finish_reason") is not None:
                        break
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
                self.close_connection = True
            except (BrokenPipeError, ConnectionResetError):
                if hasattr(runtime.runner, "abort_current"):
                    runtime.runner.abort_current()

        def _handle_abort(self):
            if runtime.runner is None or not hasattr(runtime.runner, "abort_current"):
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "agent_not_configured")
                return
            self._send_json(runtime.runner.abort_current())

    YunjuOpenWebUIAdapterRequestHandler.runtime = runtime
    return YunjuOpenWebUIAdapterRequestHandler


def create_runtime(api_key=None, model_id=None, db_path=None):
    api_key = api_key if api_key is not None else os.environ.get("GA_YUNJU_OPENWEBUI_API_KEY", "")
    model_id = model_id or os.environ.get("GA_YUNJU_OPENWEBUI_MODEL_ID", MODEL_ID)
    try:
        if str(ROOT_DIR) not in sys.path:
            sys.path.insert(0, str(ROOT_DIR))
        from agentmain import GeneraticAgent
        from frontends.webui_server import SQLiteConversationStore, WebUITaskManager

        agent = GeneraticAgent()
        thread = threading.Thread(target=agent.run, daemon=True)
        thread.start()
        store = SQLiteConversationStore(db_path or DEFAULT_DB_PATH)
        manager = WebUITaskManager(agent, store)
        return AdapterRuntime(
            runner=YunjuOpenWebUIRunner(manager, model_id=model_id),
            api_key=api_key,
            model_id=model_id,
        )
    except Exception as exc:
        _log_event("runtime_init_error", error_type=type(exc).__name__, error_message=str(exc))
        return AdapterRuntime(api_key=api_key, model_id=model_id, init_error=str(exc))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run GenericAgent Yunju OpenWebUI adapter.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18602)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--model-id", default=None)
    parser.add_argument("--db-path", default="")
    args = parser.parse_args(argv)

    runtime = create_runtime(
        api_key=args.api_key,
        model_id=args.model_id,
        db_path=args.db_path or None,
    )
    server = ThreadingHTTPServer((args.host, args.port), make_handler(runtime))
    print(f"[YunjuOpenWebUIAdapter] listening on http://{args.host}:{args.port}")
    if runtime.init_error:
        print(f"[YunjuOpenWebUIAdapter] agent init error: {runtime.init_error}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
