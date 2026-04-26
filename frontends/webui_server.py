import argparse
import json
import mimetypes
import os
import queue
import re
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT_DIR = Path(__file__).resolve().parent.parent
WEBUI_DIST = Path(__file__).resolve().parent / "webui" / "dist"

_TURN_RE = re.compile(r"\**LLM Running \(Turn (\d+)\) \.\.\.\**")
_SUMMARY_RE = re.compile(r"<summary>\s*(.*?)\s*</summary>", re.DOTALL)


def parse_execution_log(text):
    """Split assistant output into collapsible LLM turn entries."""
    parts = list(_TURN_RE.finditer(text or ""))
    turns = []
    for idx, match in enumerate(parts):
        turn = int(match.group(1))
        start = match.end()
        end = parts[idx + 1].start() if idx + 1 < len(parts) else len(text or "")
        content = (text or "")[start:end].strip()
        summary_match = _SUMMARY_RE.search(content)
        title = f"LLM Running (Turn {turn})"
        if summary_match:
            first_line = next(
                (line.strip() for line in summary_match.group(1).splitlines() if line.strip()),
                "",
            )
            if first_line:
                title = first_line[:80]
        turns.append({"turn": turn, "title": title, "content": content})
    return turns


@dataclass
class TaskRecord:
    task_id: str
    output_queue: queue.Queue
    prompt: str
    status: str = "running"
    current_response: str = ""
    created_at: float = 0.0
    completed_at: float = 0.0


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
    if manager is not None:
        running = any(task.status == "running" for task in manager.tasks.values())
    return {
        "configured": agent is not None and bool(llms or current),
        "current_llm": current,
        "llms": llms,
        "running": running or bool(getattr(agent, "is_running", False)),
        "autonomous_enabled": bool(getattr(manager, "autonomous_enabled", False)),
        "last_reply_time": int(getattr(manager, "last_reply_time", 0) or 0),
    }


class WebUITaskManager:
    def __init__(self, agent):
        self.agent = agent
        self.tasks = {}
        self.autonomous_enabled = False
        self.last_reply_time = 0

    def start_chat(self, prompt):
        if self.agent is None:
            raise RuntimeError("agent_not_configured")
        output_queue = self.agent.put_task(prompt, source="user")
        task_id = uuid.uuid4().hex
        self.tasks[task_id] = TaskRecord(
            task_id=task_id,
            output_queue=output_queue,
            prompt=prompt,
            created_at=time.time(),
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
                yield {
                    "event": "next",
                    "content": task.current_response,
                    "execution_log": parse_execution_log(task.current_response),
                }
            if "done" in item:
                task.current_response = item["done"]
                task.status = "done"
                task.completed_at = time.time()
                self.last_reply_time = int(task.completed_at)
                yield {
                    "event": "done",
                    "content": task.current_response,
                    "execution_log": parse_execution_log(task.current_response),
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
        return build_state(self.agent, self)

    def reinject(self):
        client = getattr(self.agent, "llmclient", None)
        if client is not None and hasattr(client, "last_tools"):
            client.last_tools = ""
        return {"ok": True}

    def reset_conversation(self):
        try:
            from .continue_cmd import reset_conversation
        except ImportError:
            from continue_cmd import reset_conversation

        message = reset_conversation(self.agent, message="New conversation started")
        self.last_reply_time = int(time.time())
        return {"message": message}

    def continue_conversation(self, command):
        try:
            from .continue_cmd import extract_ui_messages, handle_frontend_command, list_sessions
        except ImportError:
            from continue_cmd import extract_ui_messages, handle_frontend_command, list_sessions

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
        self.last_reply_time = int(time.time())
        return {"message": message, "history": history or []}

    def set_autonomous(self, enabled):
        self.autonomous_enabled = bool(enabled)
        return {"autonomous_enabled": self.autonomous_enabled}

    def send_pet_request(self, query):
        pet_req = getattr(self.agent, "_pet_req", None)
        if callable(pet_req):
            pet_req(query)
            return {"ok": True, "started": False}
        return {"ok": False, "started": False}

    def start_pet(self):
        if self.agent is None:
            raise RuntimeError("agent_not_configured")
        kwargs = {"creationflags": 0x08} if sys.platform == "win32" else {}
        pet_script = Path(__file__).resolve().parent / "desktop_pet_v2.pyw"
        if not pet_script.exists():
            pet_script = Path(__file__).resolve().parent / "desktop_pet.pyw"
        subprocess.Popen([sys.executable, str(pet_script)], **kwargs)

        def _pet_req(query):
            from urllib.request import urlopen

            def _do():
                try:
                    urlopen(f"http://127.0.0.1:41983/?{query}", timeout=2)
                except Exception:
                    pass

            threading.Thread(target=_do, daemon=True).start()

        self.agent._pet_req = _pet_req
        return {"ok": True, "started": True}


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
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/state":
            payload = build_state(self.runtime.agent, self.runtime.manager)
            if self.runtime.init_error:
                payload["configured"] = False
                payload["error"] = self.runtime.init_error
            self._send_json(payload)
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
                prompt = str(body.get("prompt", "")).strip()
                if not prompt:
                    self._send_error_json(HTTPStatus.BAD_REQUEST, "empty_prompt")
                    return
                self._send_json(self.runtime.manager.start_chat(prompt))
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
            if path == "/api/pet":
                result = self.runtime.manager.start_pet()
                self._send_json(result)
                return
        except Exception as exc:
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "server_error", str(exc))
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
            if name in {"done", "app_error"}:
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


def create_runtime(dev_url=None):
    try:
        sys.path.insert(0, str(ROOT_DIR))
        from agentmain import GeneraticAgent
        import chatapp_common  # noqa: F401 - activates shared frontend command patches

        agent = GeneraticAgent()
        thread = threading.Thread(target=agent.run, daemon=True)
        thread.start()
        manager = WebUITaskManager(agent)
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
    args = parser.parse_args(argv)

    runtime = create_runtime(dev_url=args.dev_url or None)
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
