from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_LOG_ROOT = PACKAGE_DIR / "log"
FALSE_VALUES = {"0", "false", "no", "off"}
TRUE_VALUES = {"1", "true", "yes", "on"}
PLAIN_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
LOG_FILE_RE = re.compile(r"^audit-(\d{14})\.log$")
MAX_LOG_FILE_BYTES = 1_048_576
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


def _log_file_timestamp(path: Path) -> str | None:
    match = LOG_FILE_RE.match(path.name)
    if not match:
        return None
    return match.group(1)


def _timestamped_log_path(directory: Path, now: datetime) -> Path:
    return directory / f"audit-{now.strftime('%Y%m%d%H%M%S')}.log"


def _next_log_path(directory: Path, now: datetime, *, after_timestamp: str | None = None) -> Path:
    next_time = now
    if after_timestamp and now.strftime("%Y%m%d%H%M%S") <= after_timestamp:
        next_time = datetime.strptime(after_timestamp, "%Y%m%d%H%M%S") + timedelta(seconds=1)

    path = _timestamped_log_path(directory, next_time)
    while path.exists():
        next_time += timedelta(seconds=1)
        path = _timestamped_log_path(directory, next_time)
    return path


def _active_log_path(directory: Path, *, now: datetime, entry_bytes: int) -> Path:
    existing: list[tuple[str, Path]] = []
    for path in directory.glob("audit*.log"):
        timestamp = _log_file_timestamp(path)
        if timestamp is not None:
            existing.append((timestamp, path))
    if not existing:
        return _next_log_path(directory, now)

    timestamp, path = max(existing, key=lambda item: item[0])
    try:
        current_size = path.stat().st_size
    except OSError:
        current_size = 0
    if current_size + entry_bytes <= MAX_LOG_FILE_BYTES:
        return path
    return _next_log_path(directory, now, after_timestamp=timestamp)


def _log_path(now: datetime | None = None, *, entry_bytes: int = 0) -> Path:
    current = now or datetime.now()
    return _active_log_path(_log_root() / current.strftime("%Y-%m-%d"), now=current, entry_bytes=entry_bytes)


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


def _format_scalar(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\r", "\\r").replace("\n", "\\n")
    if text.startswith("[REDACTED"):
        return text
    if len(text) > 240:
        text = f"{text[:237]}..."
    if PLAIN_TOKEN_RE.match(text):
        return text
    return json.dumps(text, ensure_ascii=False)


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _element_label(element: dict[str, Any]) -> str:
    parts = [
        f"index={_format_scalar(element.get('index'))}",
        f"role={_format_scalar(element.get('role'))}",
        f"control={_format_scalar(element.get('control_kind'))}",
        f"layer={_format_scalar(element.get('layer'))}",
        f"visible={_format_scalar(element.get('visible'))}",
        f"disabled={_format_scalar(element.get('disabled'))}",
    ]
    for key in ("text", "value", "selector_hint"):
        value = element.get(key)
        if value not in (None, ""):
            parts.append(f"{key}={_format_scalar(value)}")
    field_context = element.get("field_context") if isinstance(element.get("field_context"), dict) else {}
    for key in ("field_id", "field_name", "row_label", "nearby_text"):
        value = field_context.get(key)
        if value:
            parts.append(f"{key}={_format_scalar(value)}")
    scan_anchor = element.get("scan_anchor") if isinstance(element.get("scan_anchor"), dict) else {}
    for key in ("field_label", "near_text", "row_text", "column_text"):
        value = scan_anchor.get(key)
        if value:
            parts.append(f"{key}={_format_scalar(value)}")
    frame_path = element.get("frame_path")
    if frame_path:
        parts.append(f"frame_path={_format_scalar(frame_path)}")
    return " ".join(parts)


def _match_label(match: dict[str, Any]) -> str:
    parts = [
        f"index={_format_scalar(match.get('index'))}",
        f"score={_format_scalar(match.get('score'))}",
    ]
    if match.get("reason"):
        parts.append(f"reason={_format_scalar(match.get('reason'))}")
    element = match.get("element")
    if isinstance(element, dict):
        for key in ("text", "value", "role", "control_kind", "layer"):
            value = element.get(key)
            if value not in (None, ""):
                parts.append(f"{key}={_format_scalar(value)}")
    return " ".join(parts)


def _step_label(index: int, step: dict[str, Any]) -> str:
    tool = str(step.get("tool") or "-")
    parts = [f"{index}.", tool, f"status={_format_scalar(step.get('status'))}"]
    if step.get("stage"):
        parts.append(f"stage={_format_scalar(step.get('stage'))}")
    if step.get("action"):
        parts.append(f"action={_format_scalar(step.get('action'))}")
    if step.get("recipe"):
        parts.append(f"recipe={_format_scalar(step.get('recipe'))}")
    if step.get("index") is not None:
        parts.append(f"index={_format_scalar(step.get('index'))}")
    matches = step.get("matches")
    if isinstance(matches, list):
        parts.append(f"matches={len(matches)}")
    if step.get("ambiguous") is not None:
        parts.append(f"ambiguous={_format_scalar(step.get('ambiguous'))}")
    if step.get("error"):
        parts.append(f"error={_format_scalar(step.get('error'))}")
    return " ".join(parts)


def _format_elements(elements: list[Any], *, indent: str) -> list[str]:
    lines = [f"{indent}elements_preview:"]
    max_items = 12
    for element in elements[:max_items]:
        if isinstance(element, dict):
            lines.append(f"{indent}  - {_element_label(element)}")
        else:
            lines.append(f"{indent}  - {_format_scalar(element)}")
    omitted = len(elements) - max_items
    if omitted > 0:
        lines.append(f"{indent}  - ... {omitted} more elements omitted")
    if not elements:
        lines.append(f"{indent}  - []")
    return lines


def _format_matches(matches: list[Any], *, indent: str) -> list[str]:
    lines = [f"{indent}matches:"]
    for match in matches:
        if isinstance(match, dict):
            lines.append(f"{indent}  - {_match_label(match)}")
        else:
            lines.append(f"{indent}  - {_format_scalar(match)}")
    if not matches:
        lines.append(f"{indent}  - []")
    return lines


def _format_steps(steps: list[Any], *, indent: str) -> list[str]:
    lines = [f"{indent}steps:"]
    for index, step in enumerate(steps, start=1):
        if isinstance(step, dict):
            lines.append(f"{indent}  - {_step_label(index, step)}")
        else:
            lines.append(f"{indent}  - {index}. {_format_scalar(step)}")
    if not steps:
        lines.append(f"{indent}  - []")
    return lines


def _format_mapping(mapping: dict[str, Any], *, indent: str = "  ") -> list[str]:
    lines: list[str] = []
    for key, value in mapping.items():
        key_text = str(key)
        if key_text == "elements" and isinstance(value, list):
            lines.extend(_format_elements(value, indent=indent))
            continue
        if key_text == "matches" and isinstance(value, list):
            lines.extend(_format_matches(value, indent=indent))
            continue
        if key_text == "steps" and isinstance(value, list):
            lines.extend(_format_steps(value, indent=indent))
            continue
        if _is_scalar(value):
            lines.append(f"{indent}{key_text}: {_format_scalar(value)}")
        elif isinstance(value, dict):
            if not value:
                lines.append(f"{indent}{key_text}: {{}}")
                continue
            lines.append(f"{indent}{key_text}:")
            lines.extend(_format_mapping(value, indent=f"{indent}  "))
        elif isinstance(value, list):
            if not value:
                lines.append(f"{indent}{key_text}: []")
                continue
            lines.append(f"{indent}{key_text}:")
            for item in value:
                if _is_scalar(item):
                    lines.append(f"{indent}  - {_format_scalar(item)}")
                else:
                    lines.append(f"{indent}  -")
                    if isinstance(item, dict):
                        lines.extend(_format_mapping(item, indent=f"{indent}    "))
                    else:
                        lines.append(f"{indent}    {_format_scalar(item)}")
        else:
            lines.append(f"{indent}{key_text}: {_format_scalar(value)}")
    if not lines:
        lines.append(f"{indent}{{}}")
    return lines


def _header(tool: str, phase: str, payload: dict[str, Any], timestamp: str) -> str:
    parts = [f"[{timestamp}]", tool, str(phase or "").upper()]
    for key, label in (("status", "status"), ("stage", "stage"), ("duration_ms", "duration"), ("action", "action"), ("recipe", "recipe"), ("index", "index")):
        value = payload.get(key)
        if value in (None, ""):
            continue
        suffix = "ms" if key == "duration_ms" else ""
        parts.append(f"{label}={value}{suffix}")
    return " ".join(parts)


def _format_event(tool: str, phase: str, payload: dict[str, Any], *, now: datetime | None = None) -> str:
    timestamp = (now or datetime.now()).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    section = "request" if phase == "start" else "result"
    lines = [_header(tool, phase, payload, timestamp), f"{section}:"]
    lines.extend(_format_mapping(payload))
    lines.append("")
    return "\n".join(lines) + "\n"


def log_event(
    tool: str,
    phase: str,
    *,
    fields: dict[str, Any] | None = None,
    sensitive: dict[str, Any] | None = None,
) -> None:
    """Append one browser-use runtime event as readable audit text.

    Sensitive values are logged unless GA_BROWSER_USE_LOG_SENSITIVE is false.
    Logging failures must never affect browser operation results.
    """

    if not _enabled():
        return
    include_sensitive = _include_sensitive()
    payload: dict[str, Any] = {}
    if fields:
        payload.update(_sanitize(fields, allow_sensitive=include_sensitive))
    if sensitive:
        payload.update(_sanitize(sensitive, allow_sensitive=include_sensitive))

    try:
        now = datetime.now()
        event_text = _format_event(tool, phase, payload, now=now)
        path = _log_path(now, entry_bytes=len(event_text.encode("utf-8")))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(event_text)
    except Exception:
        return
