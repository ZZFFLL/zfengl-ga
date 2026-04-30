from dataclasses import dataclass
from uuid import uuid4


CONVERSATION_HEADER = "x-ga-librechat-conversation-id"
PARENT_MESSAGE_HEADER = "x-ga-librechat-parent-message-id"
USER_HEADER = "x-ga-librechat-user-id"


@dataclass
class LibreChatRequestMeta:
    conversation_id: str
    parent_message_id: str
    user_id: str
    request_id: str
    source: str


def extract_request_meta(body: dict, headers) -> LibreChatRequestMeta:
    body = body if isinstance(body, dict) else {}

    body_conversation_id = _first_body_value(body, "conversation_id", "conversationId")
    header_conversation_id = _header_value(headers, CONVERSATION_HEADER)
    conversation_id = body_conversation_id or header_conversation_id or "default-conversation"

    parent_message_id = (
        _first_body_value(body, "parent_message_id", "parentMessageId")
        or _header_value(headers, PARENT_MESSAGE_HEADER)
        or ""
    )
    user_id = (
        _body_user_id(body)
        or _first_body_value(body, "user_id", "userId")
        or _header_value(headers, USER_HEADER)
        or "local-single-user"
    )
    request_id = (
        _first_body_value(body, "request_id", "requestId")
        or _header_value(headers, "x-request-id")
        or _header_value(headers, "x-client-request-id")
        or _fallback_id("req")
    )
    source = "body" if body_conversation_id else "header" if header_conversation_id else "fallback"

    return LibreChatRequestMeta(
        conversation_id=conversation_id,
        parent_message_id=parent_message_id,
        user_id=user_id,
        request_id=request_id,
        source=source,
    )


def conversation_key(meta: LibreChatRequestMeta) -> str:
    return f"{meta.user_id}:{meta.conversation_id}"


def _first_body_value(body: dict, *keys: str):
    for key in keys:
        value = _clean_value(body.get(key))
        if value:
            return value
    metadata = body.get("metadata")
    if isinstance(metadata, dict):
        for key in keys:
            value = _clean_value(metadata.get(key))
            if value:
                return value
    return None


def _body_user_id(body: dict):
    user = body.get("user")
    if isinstance(user, dict):
        return (
            _clean_value(user.get("id"))
            or _clean_value(user.get("_id"))
            or _clean_value(user.get("email"))
        )
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
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        if value.lower() in {"undefined", "null"}:
            return None
        if value.startswith("{{") and value.endswith("}}"):
            return None
        return value
    return str(value)


def _fallback_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"
