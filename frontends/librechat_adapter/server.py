"""HTTP entry point for the LibreChat adapter."""

import argparse
import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTENDS_DIR = ROOT_DIR / "frontends"
MODEL_ID = "generic-agent"
SERVICE_NAME = "generic-agent-librechat-adapter"
LOGGER_NAME = "generic_agent.librechat_adapter"
DEFAULT_LOG_PATH = ROOT_DIR / "temp" / "librechat_adapter.log"

from .ga_sessions import GASessionBridge
from .runner import LibreChatAdapterRunner


@dataclass
class AdapterRuntime:
    runner: object = None
    session_bridge: object = None
    api_key: str = ""
    init_error: str = ""


def _json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def configure_file_logging(log_path=None):
    path = Path(
        log_path
        or os.environ.get("GA_LIBRECHAT_ADAPTER_LOG")
        or DEFAULT_LOG_PATH
    )
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


def _log_event(event, **fields):
    payload = {"event": event, **fields}
    LOGGER.info(json.dumps(payload, ensure_ascii=False, default=str))


def _error_payload(code, message, type_="ga_error"):
    try:
        from .protocol import make_error_payload

        return make_error_payload(code, message)
    except Exception:
        return {"error": {"message": message, "type": type_, "code": code}}


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
        return False
    return headers.get("Authorization", "") == f"Bearer {api_key}"


def _coerce_event(event):
    if isinstance(event, str):
        return {"delta": {"content": event}, "finish_reason": None}
    return event or {}


def _parse_limit(raw_value):
    try:
        value = int(raw_value or 20)
    except (TypeError, ValueError):
        raise ValueError("invalid_limit")
    return max(0, min(value, 100))


def _meta_value(meta, *names, default=None):
    if meta is None:
        return default
    if isinstance(meta, dict):
        for name in names:
            value = meta.get(name)
            if value not in (None, ""):
                return value
        return default
    for name in names:
        value = getattr(meta, name, None)
        if value not in (None, ""):
            return value
    return default


def make_handler(runtime):
    class LibreChatAdapterRequestHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            message = f"{self.address_string()} - {fmt % args}"
            print(f"[LibreChatAdapter] {message}")
            _log_event(
                "http_access",
                client_ip=self.address_string(),
                message=message,
            )

        def _send_json(self, payload, status=HTTPStatus.OK):
            data = _json_bytes(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)

        def _send_error(self, status, code, message=None):
            self._send_json(
                _error_payload(code, message or code),
                status,
            )

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
                "Content-Type, Authorization, x-ga-librechat-conversation-id, "
                "x-ga-librechat-parent-message-id, x-ga-librechat-user-id",
            )
            self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
            self.end_headers()

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/health":
                self._send_health()
                return
            if not self._require_auth():
                return
            if path == "/v1/models":
                self._send_models()
                return
            if path == "/v1/ga/sessions":
                query = parse_qs(parsed.query)
                try:
                    limit = _parse_limit((query.get("limit") or ["20"])[0])
                except ValueError:
                    self._send_error(
                        HTTPStatus.BAD_REQUEST,
                        "bad_request",
                        "invalid_limit",
                    )
                    return
                self._send_sessions(limit)
                return
            match = path.removeprefix("/v1/ga/sessions/")
            if match != path and match:
                self._send_session(match)
                return
            self._send_error(HTTPStatus.NOT_FOUND, "not_found")

        def do_POST(self):
            parsed = urlparse(self.path)
            path = parsed.path
            if not self._require_auth():
                return
            try:
                body = _read_json(self)
            except ValueError:
                _log_event(
                    "bad_request",
                    method="POST",
                    path=path,
                    client_ip=self.address_string(),
                    error_code="invalid_json",
                )
                self._send_error(HTTPStatus.BAD_REQUEST, "bad_request", "invalid_json")
                return
            if path == "/v1/chat/completions":
                self._handle_chat(body)
                return
            self._send_error(HTTPStatus.NOT_FOUND, "not_found")

        def _send_health(self):
            current_model = None
            running = False
            if runtime.runner is not None:
                if hasattr(runtime.runner, "current_model"):
                    current_model = runtime.runner.current_model()
                if hasattr(runtime.runner, "is_running"):
                    running = bool(runtime.runner.is_running())
            self._send_json(
                {
                    "ok": runtime.runner is not None and not runtime.init_error,
                    "service": SERVICE_NAME,
                    "version": "0.1.0",
                    "configured": runtime.runner is not None and not runtime.init_error,
                    "running": running,
                    "current_model": current_model,
                    "error": runtime.init_error or None,
                }
            )

        def _send_models(self):
            created = int(time.time())
            self._send_json(
                {
                    "object": "list",
                    "data": [
                        {
                            "id": MODEL_ID,
                            "object": "model",
                            "created": created,
                            "owned_by": "generic-agent",
                        }
                    ],
                }
            )

        def _send_sessions(self, limit):
            if runtime.session_bridge is None:
                self._send_json({"object": "list", "data": []})
                return
            sessions = runtime.session_bridge.list_sessions(limit=limit)
            self._send_json({"object": "list", "data": sessions})

        def _send_session(self, session_id):
            if runtime.session_bridge is None:
                self._send_error(HTTPStatus.NOT_FOUND, "not_found")
                return
            try:
                payload = runtime.session_bridge.read_session(session_id)
            except Exception:
                self._send_error(HTTPStatus.NOT_FOUND, "not_found")
                return
            self._send_json(payload)

        def _handle_chat(self, body):
            if runtime.runner is None:
                self._send_error(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "agent_not_configured",
                )
                return
            try:
                from .metadata import extract_request_meta
                from .protocol import AdapterError, parse_chat_request
            except Exception as exc:
                self._send_error(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "internal_error",
                    str(exc),
                )
                return

            try:
                request = parse_chat_request(body)
                meta = extract_request_meta(body, self.headers)
                request_id = (
                    getattr(request, "request_id", None)
                    or _meta_value(meta, "request_id", "requestId", default=None)
                    or "chatcmpl-ga"
                )
                _log_event(
                    "chat_request",
                    request_id=request_id,
                    model=getattr(request, "model", MODEL_ID),
                    stream=bool(getattr(request, "stream", False)),
                    message_count=len(getattr(request, "messages", []) or []),
                    conversation_id=_meta_value(meta, "conversation_id", "conversationId"),
                    parent_message_id=_meta_value(meta, "parent_message_id", "parentMessageId"),
                    user_id=_meta_value(meta, "user_id", "user"),
                )
                if request.stream:
                    self._send_chat_stream(request, meta)
                else:
                    started = time.time()
                    payload = runtime.runner.chat(request, meta)
                    _log_event(
                        "chat_response",
                        request_id=request_id,
                        duration_ms=int((time.time() - started) * 1000),
                        status=200,
                    )
                    self._send_json(payload)
            except AdapterError as exc:
                _log_event(
                    "chat_error",
                    error_type=type(exc).__name__,
                    error_code=exc.code,
                    error_message=exc.message,
                )
                self._send_error(HTTPStatus(exc.status), exc.code, exc.message)
            except RuntimeError as exc:
                code = str(exc) or "internal_error"
                status = HTTPStatus.TOO_MANY_REQUESTS if code == "busy" else HTTPStatus.INTERNAL_SERVER_ERROR
                _log_event(
                    "chat_error",
                    error_type=type(exc).__name__,
                    error_code=code,
                    status=int(status),
                )
                self._send_error(status, code)
            except Exception as exc:
                _log_event(
                    "chat_error",
                    error_type=type(exc).__name__,
                    error_code="internal_error",
                    error_message=str(exc),
                )
                self._send_error(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "internal_error",
                    str(exc),
                )

        def _send_chat_stream(self, request, meta):
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                from .protocol import make_sse_chunk

                request_id = (
                    getattr(request, "request_id", None)
                    or getattr(meta, "request_id", None)
                    or "chatcmpl-ga-stream"
                )
                _log_event(
                    "chat_stream_start",
                    request_id=request_id,
                    model=getattr(request, "model", MODEL_ID),
                )
                chunks = 0
                emitted_chars = 0
                finish_reason = None
                for event in runtime.runner.stream_chat(request, meta):
                    event = _coerce_event(event)
                    chunks += 1
                    delta = event.get("delta", {})
                    if isinstance(delta, dict):
                        emitted_chars += len(str(delta.get("content") or ""))
                    finish_reason = event.get("finish_reason")
                    chunk = make_sse_chunk(
                        request_id,
                        getattr(request, "model", MODEL_ID),
                        event.get("delta", {}),
                        finish_reason,
                    )
                    if isinstance(chunk, dict):
                        chunk = f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                    self.wfile.write(chunk.encode("utf-8"))
                    self.wfile.flush()
                    if finish_reason is not None:
                        break
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
                self.close_connection = True
                _log_event(
                    "chat_stream_done",
                    request_id=request_id,
                    chunks=chunks,
                    emitted_chars=emitted_chars,
                    finish_reason=finish_reason,
                )
            except (BrokenPipeError, ConnectionResetError):
                _log_event(
                    "chat_stream_client_disconnect",
                    request_id=locals().get("request_id", "chatcmpl-ga-stream"),
                )
                if hasattr(runtime.runner, "abort_current"):
                    runtime.runner.abort_current()

    return LibreChatAdapterRequestHandler


def create_runtime(api_key=None):
    api_key = api_key if api_key is not None else os.environ.get("GA_API_KEY", "")
    try:
        for path in (str(ROOT_DIR), str(FRONTENDS_DIR)):
            if path not in sys.path:
                sys.path.insert(0, path)
        from agentmain import GeneraticAgent
        import chatapp_common  # noqa: F401 - activates shared frontend command patches

        agent = GeneraticAgent()
        thread = threading.Thread(target=agent.run, daemon=True)
        thread.start()
        _log_event("runtime_started", model=getattr(agent, "get_llm_name", lambda **_: None)(model=True))
        return AdapterRuntime(
            runner=LibreChatAdapterRunner(agent),
            session_bridge=GASessionBridge(),
            api_key=api_key,
        )
    except Exception as exc:
        _log_event(
            "runtime_init_error",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        return AdapterRuntime(api_key=api_key, init_error=str(exc))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run GenericAgent LibreChat adapter.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18601)
    args = parser.parse_args(argv)

    runtime = create_runtime()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(runtime))
    print(f"[LibreChatAdapter] listening on http://{args.host}:{args.port}")
    _log_event("server_listening", host=args.host, port=args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
