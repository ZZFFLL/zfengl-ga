from dataclasses import dataclass
from uuid import uuid4


# 中文注释：这些请求头来自云居 OpenWebUI 转发链路，用于把外部会话映射回 GA 本地会话。
OPENWEBUI_CHAT_HEADER = "x-openwebui-chat-id"
OPENWEBUI_CONVERSATION_HEADER = "x-openwebui-conversation-id"
OPENWEBUI_MESSAGE_HEADER = "x-openwebui-message-id"
OPENWEBUI_USER_HEADER = "x-openwebui-user-id"


@dataclass
class YunjuRequestMeta:
    chat_id: str
    message_id: str
    user_id: str
    request_id: str
    source: str


def extract_request_meta(body: dict, headers) -> YunjuRequestMeta:
    body = body if isinstance(body, dict) else {}
    metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}

    body_chat_id = _first_value(metadata, "chat_id", "conversation_id", "conversationId")
    header_chat_id = _header_value(headers, OPENWEBUI_CHAT_HEADER) or _header_value(
        headers,
        OPENWEBUI_CONVERSATION_HEADER,
    )
    chat_id = body_chat_id or header_chat_id or _first_value(body, "conversation_id", "conversationId")

    message_id = (
        _first_value(metadata, "message_id", "parent_message_id", "parentMessageId")
        or _first_value(body, "parent_message_id", "parentMessageId")
        or _header_value(headers, OPENWEBUI_MESSAGE_HEADER)
        or ""
    )
    user_id = (
        _first_value(metadata, "user_id", "userId")
        or _body_user_id(body)
        or _header_value(headers, OPENWEBUI_USER_HEADER)
        or "local-openwebui-user"
    )
    request_id = (
        _first_value(body, "request_id", "requestId")
        or _header_value(headers, "x-request-id")
        or _header_value(headers, "x-client-request-id")
        or f"req_{uuid4().hex}"
    )
    source = "metadata" if body_chat_id else "header" if header_chat_id else "fallback"
    return YunjuRequestMeta(
        chat_id=chat_id or "default-openwebui-chat",
        message_id=message_id,
        user_id=user_id,
        request_id=request_id,
        source=source,
    )


def conversation_key(meta: YunjuRequestMeta) -> str:
    return f"{meta.user_id}:{meta.chat_id}"


def _first_value(source: dict, *keys: str):
    for key in keys:
        value = _clean_value(source.get(key))
        if value:
            return value
    return None


def _body_user_id(body: dict):
    user = body.get("user")
    if isinstance(user, dict):
        return _first_value(user, "id", "_id", "email", "name")
    return _clean_value(user)


def _header_value(headers, name: str):
    if headers is None:
        return None
    if hasattr(headers, "get"):
        value = _clean_value(headers.get(name))
        if value:
            return value
    if isinstance(headers, dict):
        lowered = {str(key).lower(): value for key, value in headers.items()}
        return _clean_value(lowered.get(name.lower()))
    return None


def _clean_value(value):
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if not value or value.lower() in {"undefined", "null"}:
        return None
    if value.startswith("{{") and value.endswith("}}"):
        return None
    return value
