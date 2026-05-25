import re
import time
from dataclasses import dataclass
from uuid import uuid4


MODEL_ID = "ga-yunju"
OPENWEBUI_MODEL_PREFIXES = ("openclaw/", "yunju_openclaw/")
_OPENWEBUI_DETAILS_RE = re.compile(r"<details\b[^>]*>.*?</details>", re.IGNORECASE | re.DOTALL)


@dataclass
class NormalizedMessage:
    role: str
    content: str


@dataclass
class ChatRequest:
    model: str
    messages: list
    stream: bool


class AdapterError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def parse_chat_request(body, allowed_models=None, allowed_prefixes=None) -> ChatRequest:
    if not isinstance(body, dict):
        raise AdapterError("invalid_request", "Request body must be a JSON object.")
    allowed = set(allowed_models or {MODEL_ID})
    prefixes = tuple(allowed_prefixes or OPENWEBUI_MODEL_PREFIXES)
    model = _string_value(body.get("model")) or MODEL_ID
    if model not in allowed and not _has_allowed_prefix(model, prefixes):
        raise AdapterError(
            "invalid_model",
            f"Only model {sorted(allowed)!r} or OpenWebUI OpenClaw models are supported.",
        )

    raw_messages = body.get("messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        raise AdapterError("invalid_messages", "messages must be a non-empty list.")
    return ChatRequest(
        model=model,
        messages=normalize_messages(raw_messages),
        stream=body.get("stream") is True,
    )


def normalize_messages(messages) -> list:
    normalized = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        normalized.append(
            NormalizedMessage(
                role=_string_value(message.get("role")) or "user",
                content=_normalize_content(message.get("content")),
            )
        )
    return normalized


def latest_user_text(messages) -> str:
    for message in reversed(messages or []):
        if message.role == "user":
            return message.content
    return ""


def make_models_payload(model_id=MODEL_ID, name="GenericAgent"):
    created = int(time.time())
    return {
        "object": "list",
        "data": [
            {
                "id": model_id,
                "name": name,
                "object": "model",
                "created": created,
                "owned_by": "generic-agent",
            }
        ],
    }


def make_completion_response(content: str, model: str, request_id: str = "") -> dict:
    return {
        "id": request_id or f"chatcmpl-{uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


def make_sse_chunk(request_id: str, model: str, delta: dict, finish_reason=None) -> dict:
    return {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }


def make_error_payload(code: str, message: str) -> dict:
    return {
        "error": {
            "message": message,
            "type": "invalid_request_error",
            "code": code,
        }
    }


def _has_allowed_prefix(model: str, prefixes: tuple) -> bool:
    # 中文注释：云居 OpenWebUI 会把外部 Agent 请求改写成 openclaw/{user}，这里只做入口兼容。
    return any(model.startswith(prefix) and len(model) > len(prefix) for prefix in prefixes)


def _normalize_content(content) -> str:
    if isinstance(content, str):
        return _strip_openwebui_display_blocks(content)
    if isinstance(content, list):
        parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") in {"text", "input_text"}:
                text = _string_value(item.get("text"))
                if text:
                    parts.append(text)
            elif item.get("type") in {"image_url", "input_image"}:
                uri = item.get("image_url")
                if isinstance(uri, dict):
                    uri = uri.get("url")
                uri = _string_value(uri or item.get("image"))
                if uri:
                    parts.append(f"[Image omitted] {uri}")
        return _strip_openwebui_display_blocks("\n".join(parts))
    return _strip_openwebui_display_blocks(_string_value(content))


def _string_value(value) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _strip_openwebui_display_blocks(text: str) -> str:
    # 中文注释：OpenWebUI 会把 reasoning/tool 展示块写回历史消息，转给 GA 前要去掉显示层 HTML。
    return _OPENWEBUI_DETAILS_RE.sub("", text or "").strip()
