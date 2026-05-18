from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_LOG_ROOT = PACKAGE_DIR / "log"
FALSE_VALUES = {"0", "false", "no", "off"}
TRUE_VALUES = {"1", "true", "yes", "on"}
SENSITIVE_KEYS = {
    "confirm_text",
    "column_text",
    "header_text",
    "option_text",
    "password",
    "query",
    "row_text",
    "text",
    "value",
    "verify_text",
    "verify_value",
}


def _env_flag(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES or normalized == "":
        return False
    return default


def _enabled() -> bool:
    return _env_flag("GA_BROWSER_USE_LOG_ENABLED", default=True)


def _include_sensitive() -> bool:
    return _env_flag("GA_BROWSER_USE_LOG_SENSITIVE", default=True)


def _log_root() -> Path:
    configured = os.environ.get("GA_BROWSER_USE_LOG_ROOT")
    if configured:
        return Path(configured)
    return DEFAULT_LOG_ROOT


def _log_path(now: datetime | None = None) -> Path:
    current = now or datetime.now()
    return _log_root() / current.strftime("%Y-%m-%d") / "runtime.log"


def _redacted(value: Any) -> str:
    try:
        length = len(str(value))
    except Exception:
        length = 0
    return f"[REDACTED len={length}]"


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()
    return (
        normalized in SENSITIVE_KEYS
        or "password" in normalized
        or "passwd" in normalized
        or normalized == "pwd"
        or "cookie" in normalized
        or "secret" in normalized
    )


def _safe_url(value: Any, *, allow_sensitive: bool) -> Any:
    if allow_sensitive:
        return value
    try:
        parsed = urlsplit(str(value))
    except Exception:
        return value
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _sanitize(value: Any, *, key: str = "", allow_sensitive: bool = False) -> Any:
    if key.lower() in {"url", "href", "page_url"}:
        return _safe_url(value, allow_sensitive=allow_sensitive)
    if key and _is_sensitive_key(key) and not allow_sensitive:
        return _redacted(value)
    if isinstance(value, dict):
        return {str(child_key): _sanitize(child_value, key=str(child_key), allow_sensitive=allow_sensitive) for child_key, child_value in value.items()}
    if isinstance(value, list):
        return [_sanitize(item, allow_sensitive=allow_sensitive) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item, allow_sensitive=allow_sensitive) for item in value]
    return value


def log_event(
    tool: str,
    phase: str,
    *,
    fields: dict[str, Any] | None = None,
    sensitive: dict[str, Any] | None = None,
) -> None:
    """Append one browser-use runtime event as JSONL.

    Sensitive values are logged unless GA_BROWSER_USE_LOG_SENSITIVE is false.
    Logging failures must never affect browser operation results.
    """

    if not _enabled():
        return
    include_sensitive = _include_sensitive()
    event: dict[str, Any] = {
        "ts": datetime.now().isoformat(timespec="milliseconds"),
        "tool": tool,
        "phase": phase,
    }
    if fields:
        event.update(_sanitize(fields, allow_sensitive=include_sensitive))
    if sensitive:
        event.update(_sanitize(sensitive, allow_sensitive=include_sensitive))

    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    except Exception:
        return
