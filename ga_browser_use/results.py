from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _base_recovery(code: str, message: str, *, next_tool: str | None = None, next_args: dict[str, Any] | None = None) -> dict[str, Any]:
    recovery: dict[str, Any] = {
        "code": code,
        "message": message,
        "stop_retry": False,
    }
    if next_tool:
        recovery["next_tool"] = next_tool
    if next_args:
        recovery["next_args"] = next_args
    return recovery


def recovery_for_stage(stage: str, *, action: str | None = None) -> dict[str, Any]:
    stage = str(stage or "").strip()
    action = str(action or "").strip() or None
    if stage == "state_missing":
        if action == "keys":
            return _base_recovery(
                "use_focused_keys",
                "If this follows a successful input, retry keys without index so the key is sent to the focused element.",
                next_tool="browser_action",
                next_args={"action": "keys"},
            )
        return _base_recovery(
            "refresh_state",
            "Run browser_state before retrying indexed browser actions.",
            next_tool="browser_state",
        )
    if stage == "stale_index":
        return _base_recovery(
            "refresh_state_then_find",
            "The cached index is stale. Refresh state and locate the target again before retrying.",
            next_tool="browser_find",
            next_args={"refresh": True, "max_results": 5},
        )
    if stage == "control_unsupported" and action == "select":
        return _base_recovery(
            "use_custom_select_recipe",
            "This target is not a native select. Use the custom select recipe.",
            next_tool="browser_recipe",
            next_args={"recipe": "custom_select"},
        )
    if stage == "verify_failed":
        return _base_recovery(
            "refresh_state_then_find",
            "The action ran but verification failed. Refresh state and inspect the target before retrying.",
            next_tool="browser_find",
            next_args={"refresh": True, "max_results": 5},
        )
    if stage == "repeat_blocked":
        recovery = _base_recovery(
            "stop_repeating",
            "The same action failed repeatedly against the same target. Stop retrying this call.",
        )
        recovery["stop_retry"] = True
        return recovery
    return _base_recovery(
        "fallback_low_level",
        "Use low-level browser inspection when the high-level action cannot classify the recovery path.",
        next_tool="web_execute_js",
    )


def add_recovery(result: dict[str, Any], *, action: str | None = None, index: int | None = None) -> dict[str, Any]:
    updated = dict(result)
    stage = str(updated.get("stage") or "")
    updated.setdefault("status", "failed")
    if action and "action" not in updated:
        updated["action"] = action
    if index is not None and "index" not in updated:
        updated["index"] = index
    updated.setdefault("recovery", recovery_for_stage(stage, action=str(updated.get("action") or action or "")))
    return updated


def failed_result(action: str | None, stage: str, error: str, index: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "failed", "stage": stage, "error": error}
    if action:
        result["action"] = action
    if index is not None:
        result["index"] = index
    return add_recovery(result, action=action, index=index)


@dataclass
class FailureFuse:
    threshold: int = 3
    _counts: dict[tuple[str, ...], int] = field(default_factory=dict)

    def _signature(self, result: dict[str, Any], *, tab_id: str, url: str, target: dict[str, Any] | None) -> tuple[str, ...]:
        target = target or {}
        return (
            str(tab_id or ""),
            str(url or ""),
            str(result.get("action") or ""),
            str(result.get("index") or ""),
            str(result.get("stage") or ""),
            str(target.get("stable_key") or ""),
            str(target.get("selector_hint") or ""),
            str(target.get("text") or target.get("value") or "")[:120],
        )

    def record(self, result: dict[str, Any], *, tab_id: str, url: str, target: dict[str, Any] | None = None) -> dict[str, Any]:
        updated = add_recovery(result, action=result.get("action"), index=result.get("index"))
        signature = self._signature(updated, tab_id=tab_id, url=url, target=target)
        count = self._counts.get(signature, 0) + 1
        self._counts[signature] = count
        if count >= self.threshold:
            blocked = failed_result(
                updated.get("action"),
                "repeat_blocked",
                "The same browser action failed repeatedly against the same target.",
                updated.get("index"),
            )
            blocked["tab_id"] = tab_id
            return blocked
        if count == self.threshold - 1:
            updated["recovery"] = dict(updated["recovery"])
            updated["recovery"]["stop_retry"] = True
        return updated

    def reset(self) -> None:
        self._counts.clear()
