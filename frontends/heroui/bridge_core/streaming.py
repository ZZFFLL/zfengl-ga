from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any, Dict, Optional, Set
from aiohttp import web


# Bridge 流式传输工具：只负责 WS 广播、SSE 编码与事件订阅队列。
class WsHub:
    def __init__(self):
        self.websockets: Set[web.WebSocketResponse] = set()
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def emit(self, obj: dict):
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self._broadcast(obj), self.loop)

    async def _broadcast(self, obj: dict):
        data = json.dumps(obj, ensure_ascii=False, default=str)
        dead = set()
        for ws in list(self.websockets):
            try:
                await ws.send_str(data)
            except Exception:
                dead.add(ws)
        self.websockets.difference_update(dead)


class EventStreamHub:
    def __init__(self):
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.subscribers: Dict[asyncio.Queue, tuple[str, str]] = {}

    def subscribe(self, session_id: str, turn_id: str = "") -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.subscribers[queue] = (str(session_id or ""), str(turn_id or ""))
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.subscribers.pop(queue, None)

    def publish(self, event: dict) -> None:
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self._publish(dict(event)), self.loop)

    async def _publish(self, event: dict) -> None:
        dead = set()
        for queue, (session_id, turn_id) in list(self.subscribers.items()):
            if str(event.get("session_id") or "") != session_id:
                continue
            if turn_id and event.get("turn_id") != turn_id:
                continue
            try:
                if queue.full():
                    with contextlib.suppress(asyncio.QueueEmpty):
                        queue.get_nowait()
                queue.put_nowait(event)
            except Exception:
                dead.add(queue)
        for queue in dead:
            self.unsubscribe(queue)


def sse_format_event(event: dict) -> bytes:
    data = json.dumps(event, ensure_ascii=False, default=str)
    return f'id: {event["seq"]}\nevent: message\ndata: {data}\n\n'.encode("utf-8")


async def sse_write_event(response: web.StreamResponse, event: dict) -> None:
    await response.write(sse_format_event(event))
    with contextlib.suppress(Exception):
        await response.drain()


def parse_event_cursor(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
