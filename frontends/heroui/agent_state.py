from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional


def _as_list(value: Any) -> list:
    return list(value) if isinstance(value, list) else []


def _as_dict(value: Any) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def capture_agent_state(agent: Any) -> Dict[str, Any]:
    llmclient = getattr(agent, "llmclient", None)
    backend = getattr(llmclient, "backend", None)
    handler = getattr(agent, "handler", None)
    return {
        "ga_history": _as_list(getattr(agent, "history", [])),
        "backend_history": _as_list(getattr(backend, "history", [])),
        "working": _as_dict(getattr(handler, "working", {})),
        "llm_no": getattr(agent, "llm_no", None),
    }


def restore_agent_state(agent: Any, state: Optional[dict]) -> None:
    if not state:
        return
    agent.history = _as_list(state.get("ga_history"))
    llmclient = getattr(agent, "llmclient", None)
    backend = getattr(llmclient, "backend", None)
    if backend is not None:
        backend.history = _as_list(state.get("backend_history"))
    llm_no = state.get("llm_no")
    if llm_no is not None and hasattr(agent, "next_llm"):
        agent.next_llm(int(llm_no))
    elif llm_no is not None:
        agent.llm_no = int(llm_no)
    handler = getattr(agent, "handler", None)
    working = _as_dict(state.get("working"))
    if handler is not None and working:
        handler.working = working
    elif handler is not None and state.get("state_version") is not None:
        handler.working = {}
    elif working:
        agent.handler = SimpleNamespace(working=working)


def restore_handler_working(handler: Any, state: Optional[dict]) -> None:
    working = _as_dict((state or {}).get("working"))
    existing = _as_dict(getattr(handler, "working", {}))
    if handler is not None and working:
        merged = dict(working)
        merged.update(existing)
        handler.working = merged


def build_state_from_messages(
    messages: List[dict],
    llm_no: Optional[int] = None,
    exclude_turn_id: Optional[str] = None,
) -> Dict[str, Any]:
    ga_history: List[str] = []
    for message in messages:
        if exclude_turn_id and str(message.get("turn_id") or "") == exclude_turn_id:
            continue
        role = str(message.get("role") or "")
        content = " ".join(str(message.get("content") or "").split())
        if not content:
            continue
        if role == "user":
            ga_history.append(f"[USER]: {content}")
        elif role == "assistant":
            ga_history.append(f"[Agent] {content}")
    return {
        "ga_history": ga_history,
        "backend_history": [],
        "working": {},
        "llm_no": llm_no,
    }
