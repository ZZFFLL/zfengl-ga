from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional


APP_DIR = Path(__file__).resolve().parents[1]


def find_default_ga_root() -> Path:
    candidates = [
        APP_DIR / "..",
        APP_DIR / ".." / "..",
    ]
    for p in candidates:
        root = p.resolve()
        if (root / "agentmain.py").exists():
            return root
    return APP_DIR.parent.parent.resolve()


DEFAULT_GA_ROOT = find_default_ga_root()
DEFAULT_HEROUI_DB_PATH = APP_DIR / ".data" / "sessions.sqlite3"


# Bridge 会话运行态模型：仅描述内存状态，不直接执行 Agent 或持久化。
@dataclass
class Session:
    id: str
    title: str = "New chat"
    cwd: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    messages: List[dict] = field(default_factory=list)
    events: List[dict] = field(default_factory=list)
    msg_seq: int = 0
    event_seq: int = 0
    partial: Optional[dict] = None
    status: str = "idle"  # idle|running|error|cancelled
    agent: Any = None
    thread: Optional[threading.Thread] = None
    cancel_requested: bool = False
    last_error: str = ""
