import time
from dataclasses import dataclass


@dataclass
class NormalizedMessage:
    role: str
    content: str


@dataclass
class ChatRequest:
    model: str
    messages: list
    stream: bool
    user: str
    conversation_id: str
    parent_message_id: str


class AdapterError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def parse_chat_request(body) -> ChatRequest:
    if not isinstance(body, dict):
        raise AdapterError("invalid_request", "Request body must be a JSON object.")
    if body.get("model") != "generic-agent":
        raise AdapterError("invalid_model", "Only model 'generic-agent' is supported.")

    raw_messages = body.get("messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        raise AdapterError("invalid_messages", "messages must be a non-empty list.")

    return ChatRequest(
        model="generic-agent",
        messages=normalize_messages(raw_messages),
        stream=body.get("stream") is True,
        user=_string_value(body.get("user")),
        conversation_id=_string_value(
            body.get("conversation_id", body.get("conversationId"))
        ),
        parent_message_id=_string_value(
            body.get("parent_message_id", body.get("parentMessageId"))
        ),
    )


def normalize_messages(messages) -> list:
    normalized = []
    for message in messages:
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
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return ""


def build_prompt_from_messages(
    messages, include_history: bool, max_context_chars: int = 32000
) -> str:
    current_index = _latest_user_index(messages)
    current = messages[current_index].content if current_index is not None else ""
    if not include_history:
        return current

    history_messages = messages[:current_index] if current_index is not None else messages
    history = "\n".join(
        f"{message.role}: {message.content}"
        for message in history_messages
        if message.content
    )
    if history:
        prompt = (
            f"Conversation History:\n{history}\n\n"
            f"Current User Message:\n{current}"
        )
    else:
        prompt = f"Current User Message:\n{current}"

    return _trim_prompt(prompt, current, max_context_chars)


def make_completion_response(
    content: str, model: str, request_id: str, created: int = None
) -> dict:
    created = int(time.time()) if created is None else created
    return {
        "id": request_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


def make_sse_chunk(
    request_id: str,
    model: str,
    delta: dict,
    finish_reason,
    created: int = None,
) -> dict:
    created = int(time.time()) if created is None else created
    return {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": created,
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


def _normalize_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and "text" in part:
                text = _string_value(part.get("text"))
                if text:
                    parts.append(text)
        return "\n".join(parts)
    return _string_value(content)


def _latest_user_index(messages):
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].role == "user":
            return index
    return None


def _trim_prompt(prompt: str, current: str, max_context_chars: int) -> str:
    if max_context_chars <= 0:
        return ""
    if len(prompt) <= max_context_chars:
        return prompt

    current_section = f"Current User Message:\n{current}"
    if len(current_section) >= max_context_chars:
        return current_section[-max_context_chars:]

    separator = "\n\n"
    history_label = "Conversation History:\n"
    budget = max_context_chars - len(separator) - len(current_section)
    if budget <= len(history_label):
        return current_section

    history_tail = prompt[: -len(separator + current_section)]
    history_tail = history_tail[-budget:]
    return f"{history_tail}{separator}{current_section}"


def _string_value(value) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)
