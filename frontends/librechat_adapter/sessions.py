"""In-process conversation state for the LibreChat adapter."""

import time
from dataclasses import dataclass


@dataclass
class RuntimeConversationState:
    key: str
    last_parent_message_id: str
    seen_message_count: int
    updated_at: float


class InMemoryConversationManager:
    def __init__(self):
        self._states = {}
        self._current_key = None

    @property
    def current_key(self):
        return self._current_key

    def should_include_history(self, key, parent_message_id=None, message_count=0):
        key = self._normalize_key(key)
        if self._current_key is None:
            return True
        if key != self._current_key:
            return True
        return key not in self._states

    def is_switching_conversation(self, key):
        key = self._normalize_key(key)
        return self._current_key is not None and key != self._current_key

    def mark_seen(self, key, parent_message_id=None, message_count=0):
        key = self._normalize_key(key)
        state = RuntimeConversationState(
            key=key,
            last_parent_message_id=parent_message_id,
            seen_message_count=int(message_count or 0),
            updated_at=time.time(),
        )
        self._states[key] = state
        self._current_key = key
        return state

    def state_for(self, key):
        return self._states.get(self._normalize_key(key))

    @staticmethod
    def _normalize_key(key):
        return str(key or "local")
