from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional


def to_iso_timestamp(value: Any) -> str:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        seconds = time.time()
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def extract_summary_text(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    match = re.search(r"<summary>\s*([\s\S]*?)\s*</(?:summary|parameter)>", raw, flags=re.IGNORECASE)
    if match:
        return " ".join(match.group(1).split())
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[0]


def round_label(turn_no: int) -> str:
    return f"第{turn_no}轮"


def ask_user_interaction_payload(raw: dict) -> Optional[dict]:
    result = raw.get("result")
    if not isinstance(result, dict):
        return None
    intent = str(result.get("intent") or "")
    status = str(result.get("status") or "")
    if intent != "HUMAN_INTERVENTION":
        return None
    data = result.get("data")
    payload = data if isinstance(data, dict) else {}
    candidates = payload.get("candidates") or []
    if not isinstance(candidates, list):
        candidates = []
    candidate_texts = [str(candidate) for candidate in candidates if str(candidate).strip()]
    if not candidate_texts:
        return None
    return {
        "status": status,
        "intent": intent,
        "question": str(payload.get("question") or ""),
        "candidates": candidate_texts,
    }


def convert_agent_event(session_id: str, turn_id: str, response_id: str, raw: dict) -> Optional[dict]:
    event_type = str(raw.get("type") or "")
    ga_turn = int(raw.get("turn") or 0)
    created_at = to_iso_timestamp(raw.get("ts") or time.time())
    tool_name = str(raw.get("tool_name") or "tool")
    tool_kind = str(raw.get("tool_kind") or "tool")
    index = int(raw.get("index") or 0) + 1
    step_id = f"{response_id}:tool:{ga_turn}:{index}"
    label = round_label(ga_turn) if ga_turn else "GA"
    tool_title = f"{label} 调用了 {tool_name}"

    if event_type == "turn.start":
        return None
    if event_type == "llm.start":
        return {
            "type": "phase.update",
            "turn_id": turn_id,
            "session_id": session_id,
            "data": {"phase": "understanding", "label": "正在思考"},
        }
    if event_type == "llm.visible_delta":
        return {
            "type": "answer.delta",
            "turn_id": turn_id,
            "session_id": session_id,
            "data": {
                "delta": str(raw.get("delta") or ""),
                "response_id": response_id,
                "created_at": created_at,
            },
        }
    if event_type == "llm.end":
        if not raw.get("has_tools"):
            return None
        text = str(raw.get("text") or "")
        summary = str(raw.get("summary") or "") or extract_summary_text(text) or "模型输出"
        thinking_summary = str(raw.get("thinking_summary") or "")
        detail = thinking_summary if thinking_summary and thinking_summary != summary else ""
        return {
            "type": "timeline.step",
            "turn_id": turn_id,
            "session_id": session_id,
            "data": {
                "id": f"{response_id}:phase:{ga_turn}:llm",
                "turn_id": turn_id,
                "response_id": response_id,
                "kind": "phase",
                "title": summary,
                "status": "done",
                "summary": summary,
                "detail": detail,
                "elapsed_ms": raw.get("elapsed_ms"),
                "default_open": False,
                "created_at": created_at,
                "retract_response_id": response_id,
            },
        }
    if event_type == "tool.start":
        data = {
            "id": step_id,
            "turn_id": turn_id,
            "response_id": response_id,
            "kind": tool_kind,
            "title": tool_title,
            "status": "running",
            "summary": tool_title,
            "detail": "",
            "input": json.dumps(raw.get("args") or {}, ensure_ascii=False, indent=2),
            "tool_name": tool_name,
            "tool_label": label,
            "created_at": created_at,
        }
        interaction = ask_user_interaction_payload(raw)
        if interaction is not None:
            data["interaction"] = interaction
        return {
            "type": "timeline.step",
            "turn_id": turn_id,
            "session_id": session_id,
            "data": data,
        }
    if event_type == "tool.delta":
        return {
            "type": "timeline.step",
            "turn_id": turn_id,
            "session_id": session_id,
            "data": {
                "id": step_id,
                "turn_id": turn_id,
                "response_id": response_id,
                "kind": tool_kind,
                "title": tool_title,
                "status": "running",
                "summary": tool_title,
                "detail": "",
                "detail_delta": str(raw.get("delta") or ""),
                "tool_name": tool_name,
                "tool_label": label,
                "created_at": created_at,
            },
        }
    if event_type == "tool.end":
        status = str(raw.get("status") or "done")
        error = str(raw.get("error") or "")
        if status == "failed" and not error:
            error = str(raw.get("result") or "")
        data = {
            "id": step_id,
            "turn_id": turn_id,
            "response_id": response_id,
            "kind": tool_kind,
            "title": tool_title,
            "status": "failed" if status == "failed" else "done",
            "summary": tool_title,
            "detail": str(raw.get("detail") or ""),
            "output": str(raw.get("output") or ""),
            "error": error if status == "failed" else "",
            "elapsed_ms": raw.get("elapsed_ms"),
            "tool_name": tool_name,
            "tool_label": label,
            "created_at": created_at,
        }
        interaction = ask_user_interaction_payload(raw)
        if tool_name == "ask_user":
            data["default_open"] = interaction is None
        if interaction is not None:
            data["interaction"] = interaction
        return {
            "type": "timeline.step",
            "turn_id": turn_id,
            "session_id": session_id,
            "data": data,
        }
    if event_type == "turn.end":
        return None
    if event_type == "agent.final":
        return {
            "type": "answer.final",
            "turn_id": turn_id,
            "session_id": session_id,
            "data": {
                "text": str(raw.get("text") or ""),
                "response_id": response_id,
                "created_at": created_at,
            },
        }
    if event_type == "agent.done":
        return {
            "type": "turn.done",
            "turn_id": turn_id,
            "session_id": session_id,
            "data": {"ok": True},
        }
    return None
