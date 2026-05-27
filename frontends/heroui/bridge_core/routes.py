from __future__ import annotations

import asyncio
import contextlib
import json
import os
import platform
import re
import subprocess
import time
from pathlib import Path
from typing import Callable
from aiohttp import web, WSMsgType

from .http_utils import cors_headers, cors_middleware, json_ok, parse_positive_int, read_json
from .streaming import parse_event_cursor, sse_write_event


def _plain_sop_text(text: str) -> str:
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
    text = re.sub(r"[*#>|]+", "", text)
    return " ".join(text.split())


# aiohttp 路由层：只做请求解析和响应组装，业务逻辑仍交给 AgentManager。
class BridgeRoutes:
    def __init__(self, get_manager: Callable[[], object], hub: object, event_hub: object, app_dir: Path):
        self.get_manager = get_manager
        self.hub = hub
        self.event_hub = event_hub
        self.app_dir = Path(app_dir)

    @property
    def manager(self):
        return self.get_manager()

    async def ws_handler(self, request):
        manager = self.manager
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        self.hub.websockets.add(ws)
        await ws.send_str(json.dumps({
            "type": "bridge-ready",
            "gaRoot": manager.ga_root,
            "mykeyPath": manager.mykey_path,
            "http": True,
            "wsEventsOnly": True,
        }, ensure_ascii=False))
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                # WS 只保留轻量通知，命令和数据统一走 HTTP/SSE。
                with contextlib.suppress(Exception):
                    data = json.loads(msg.data)
                    if data.get("action") == "ping":
                        await ws.send_str(json.dumps({"type": "pong", "ts": time.time()}, ensure_ascii=False))
        self.hub.websockets.discard(ws)
        return ws

    async def status_handler(self, request):
        manager = self.manager
        return json_ok({
            "ok": True,
            "running": True,
            "ready": True,
            "gaRoot": manager.ga_root,
            "mykeyPath": manager.mykey_path,
            "sessionCount": len(manager.sessions),
            "activeSessionId": manager.active_session_id,
            "ws": "/ws",
            "transport": {"http": True, "wsEventsOnly": True},
        })

    async def get_config_handler(self, request):
        manager = self.manager
        return json_ok({"gaRoot": manager.ga_root, "mykeyPath": manager.mykey_path, "config": manager.config})

    async def save_config_handler(self, request):
        manager = self.manager
        data = await read_json(request)
        cfg = data.get("config", data)
        if isinstance(cfg, dict):
            manager.config.update(cfg)
        return json_ok({"ok": True, "gaRoot": manager.ga_root, "mykeyPath": manager.mykey_path, "config": manager.config})

    async def model_profiles_handler(self, request):
        manager = self.manager
        return json_ok({"profiles": manager.list_model_profiles(), "activeProfileId": manager.config.get("activeProfileId")})

    def _memory_dir(self) -> Path:
        return Path(self.manager.ga_root).resolve() / "memory"

    def _sop_item_from_path(self, path: Path) -> dict:
        content = path.read_text(encoding="utf-8", errors="replace")
        lines = [line.strip() for line in content.splitlines()]
        title = next((_plain_sop_text(line.lstrip("#").strip()) for line in lines if line.startswith("#")), path.name)
        summary = next((_plain_sop_text(line) for line in lines if line and not line.startswith("#")), "")
        # 只返回相对 memory 路径，避免把本机绝对路径暴露给前端输入模板。
        return {
            "id": path.stem,
            "name": path.name,
            "title": title or path.name,
            "path": f"memory/{path.name}",
            "size": path.stat().st_size,
            "summary": summary,
        }

    def _list_sop_items(self) -> list[dict]:
        memory_dir = self._memory_dir()
        if not memory_dir.exists():
            return []
        items = []
        for path in sorted(memory_dir.glob("*.md"), key=lambda item: item.name.lower()):
            if path.is_file():
                items.append(self._sop_item_from_path(path))
        return items

    async def sops_handler(self, request):
        return json_ok({"items": self._list_sop_items()})

    async def sop_detail_handler(self, request):
        sop_id = str(request.match_info.get("sop_id") or "")
        target = self._memory_dir() / f"{sop_id}.md"
        memory_dir = self._memory_dir()
        try:
            resolved = target.resolve()
            resolved.relative_to(memory_dir.resolve())
        except ValueError:
            raise web.HTTPNotFound(text=json.dumps({"error": f"SOP not found: {sop_id}"}, ensure_ascii=False), content_type="application/json")
        if not resolved.is_file():
            raise web.HTTPNotFound(text=json.dumps({"error": f"SOP not found: {sop_id}"}, ensure_ascii=False), content_type="application/json")
        return json_ok({"item": self._sop_item_from_path(resolved), "content": resolved.read_text(encoding="utf-8", errors="replace")})

    async def sop_save_handler(self, request):
        sop_id = str(request.match_info.get("sop_id") or "")
        target = self._memory_dir() / f"{sop_id}.md"
        memory_dir = self._memory_dir()
        try:
            resolved = target.resolve()
            resolved.relative_to(memory_dir.resolve())
        except ValueError:
            raise web.HTTPNotFound(text=json.dumps({"error": f"SOP not found: {sop_id}"}, ensure_ascii=False), content_type="application/json")
        if not resolved.is_file():
            raise web.HTTPNotFound(text=json.dumps({"error": f"SOP not found: {sop_id}"}, ensure_ascii=False), content_type="application/json")
        data = await read_json(request)
        content = data.get("content")
        if not isinstance(content, str):
            raise web.HTTPBadRequest(text=json.dumps({"error": "content must be a string"}, ensure_ascii=False), content_type="application/json")
        # SOP 在线编辑只覆盖 memory 下已有 Markdown 文件，避免把页面输入扩展成任意文件写入能力。
        resolved.write_text(content, encoding="utf-8")
        return json_ok({"item": self._sop_item_from_path(resolved), "content": resolved.read_text(encoding="utf-8", errors="replace")})

    async def switch_model_profile_handler(self, request):
        manager = self.manager
        data = await read_json(request)
        profile_id = data.get("profileId", data.get("id"))
        session_id = data.get("sessionId")
        return json_ok(manager.switch_model_profile(profile_id, session_id if isinstance(session_id, str) and session_id else None))

    async def list_sessions_handler(self, request):
        manager = self.manager
        with manager.lock:
            sessions = sorted(
                (manager.snapshot(s, include_messages=False) for s in manager.sessions.values()),
                key=lambda session: session["updatedAt"],
                reverse=True,
            )
        return json_ok({"sessions": sessions, "activeSessionId": manager.active_session_id})

    async def new_session_handler(self, request):
        manager = self.manager
        data = await read_json(request)
        title = data.get("title") if isinstance(data.get("title"), str) else "New chat"
        sess = manager.create_session(cwd=data.get("cwd") or data.get("path"), title=title)
        return json_ok({"ok": True, "sessionId": sess.id, "session": manager.snapshot(sess)}, status=201)

    async def get_session_handler(self, request):
        manager = self.manager
        sid = request.match_info["sid"]
        sess = manager.get_session(sid)
        return json_ok({
            "sessionId": sid,
            "session": manager.snapshot(sess),
            "messages": list(sess.messages),
            "events": list(sess.events),
            "eventSeq": sess.event_seq,
            "partial": sess.partial,
        })

    async def delete_session_handler(self, request):
        manager = self.manager
        sid = request.match_info["sid"]
        return json_ok(manager.delete_session(sid))

    async def regenerate_session_title_handler(self, request):
        manager = self.manager
        sid = request.match_info["sid"]
        return json_ok(manager.regenerate_session_title(sid))

    async def replay_turn_handler(self, request):
        manager = self.manager
        sid = request.match_info["sid"]
        data = await read_json(request)
        turn_id = str(data.get("turnId") or data.get("turn_id") or "")
        return json_ok(manager.replay_turn(sid, turn_id))

    async def prompt_handler(self, request):
        manager = self.manager
        sid = request.match_info["sid"]
        data = await read_json(request)
        prompt = data.get("prompt", data.get("content", data.get("message", "")))
        display_prompt = data.get("displayPrompt", data.get("display_prompt"))
        images = data.get("images") or []
        return json_ok(manager.submit_prompt(sid, prompt, images, display_prompt if isinstance(display_prompt, str) else None))

    async def messages_handler(self, request):
        manager = self.manager
        sid = request.match_info["sid"]
        after = parse_event_cursor(request.query.get("after") or request.query.get("afterId"))
        limit = parse_positive_int(request.query.get("limit"), 200)
        after_event = parse_event_cursor(request.query.get("after_event") or request.query.get("afterEvent"))
        return json_ok(manager.messages(sid, after=after, limit=limit, after_event=after_event))

    async def events_handler(self, request):
        manager = self.manager
        sid = request.match_info["sid"]
        turn_id = str(request.query.get("turn_id") or "")
        query_after = parse_event_cursor(request.query.get("after_event") or request.query.get("afterEvent"))
        header_after = parse_event_cursor(request.headers.get("Last-Event-ID"))
        after_event = max(query_after, header_after)
        queue = self.event_hub.subscribe(sid, turn_id)
        try:
            with manager.lock:
                sess = manager.sessions.get(sid)
                if not sess:
                    raise web.HTTPNotFound(text=json.dumps({"error": f"session not found: {sid}"}, ensure_ascii=False), content_type="application/json")
                replay_events = [
                    event
                    for event in sess.events
                    if int(event.get("seq", 0)) > after_event and (not turn_id or event.get("turn_id") == turn_id)
                ]

            response = web.StreamResponse(
                status=200,
                headers={
                    **cors_headers(),
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
            await response.prepare(request)

            cursor = after_event
            for event in replay_events:
                cursor = max(cursor, int(event.get("seq", 0)))
                await sse_write_event(response, event)
                if turn_id and event.get("type") in {"turn.done", "turn.error"}:
                    return response

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    await response.write(b": keep-alive\n\n")
                    continue
                if str(event.get("session_id") or "") != sid:
                    continue
                if turn_id and event.get("turn_id") != turn_id:
                    continue
                event_seq = parse_event_cursor(event.get("seq"))
                if event_seq <= cursor:
                    continue
                cursor = event_seq
                await sse_write_event(response, event)
                if turn_id and event.get("type") in {"turn.done", "turn.error"}:
                    return response
        except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
            raise
        finally:
            self.event_hub.unsubscribe(queue)

    async def cancel_handler(self, request):
        manager = self.manager
        sid = request.match_info["sid"]
        return json_ok(manager.cancel(sid))

    async def path_open_handler(self, request):
        manager = self.manager
        data = await read_json(request)
        kind = data.get("kind", "")
        if kind == "mykey":
            target = Path(manager.ga_root) / "mykey.py"
        else:
            target = Path(data.get("path") or data.get("target") or manager.ga_root)
        target = target.resolve()
        if not target.exists():
            return json_ok({"ok": False, "error": f"File not found: {target}"})
        # 用系统默认程序打开文件，保持桌面端的本机体验。
        if platform.system() == "Windows":
            os.startfile(str(target))
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
        return json_ok({"ok": True, "path": str(target)})

    def create_app(self):
        app = web.Application(middlewares=[cors_middleware])
        app.router.add_get("/ws", self.ws_handler)
        app.router.add_get("/status", self.status_handler)
        app.router.add_get("/config", self.get_config_handler)
        app.router.add_post("/config", self.save_config_handler)
        app.router.add_get("/model-profiles", self.model_profiles_handler)
        app.router.add_get("/sops", self.sops_handler)
        app.router.add_get("/sops/{sop_id}", self.sop_detail_handler)
        app.router.add_put("/sops/{sop_id}", self.sop_save_handler)
        app.router.add_post("/model-profile", self.switch_model_profile_handler)
        app.router.add_get("/sessions", self.list_sessions_handler)
        app.router.add_post("/session/new", self.new_session_handler)
        app.router.add_get("/session/{sid}", self.get_session_handler)
        app.router.add_delete("/session/{sid}", self.delete_session_handler)
        app.router.add_post("/session/{sid}/title/regenerate", self.regenerate_session_title_handler)
        app.router.add_post("/session/{sid}/turn/replay", self.replay_turn_handler)
        app.router.add_post("/session/{sid}/prompt", self.prompt_handler)
        app.router.add_get("/session/{sid}/messages", self.messages_handler)
        app.router.add_get("/session/{sid}/events", self.events_handler)
        app.router.add_post("/session/{sid}/cancel", self.cancel_handler)
        app.router.add_post("/path/open", self.path_open_handler)

        static_dir = self.app_dir / "dist"

        async def index_handler(request):
            return web.FileResponse(static_dir / "index.html")

        app.router.add_get("/", index_handler)
        app.router.add_static("/", static_dir, show_index=False)

        async def on_startup(app):
            self.hub.loop = asyncio.get_running_loop()
            self.event_hub.loop = asyncio.get_running_loop()

        app.on_startup.append(on_startup)
        return app
