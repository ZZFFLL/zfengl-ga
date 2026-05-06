"""Deterministic experience fact extraction from assistant replies."""

from __future__ import annotations

from dataclasses import dataclass
import re


MAX_FACT_OBJECT_CHARS = 160


@dataclass(frozen=True)
class ExperienceFact:
    subject: str
    predicate: str
    object: str
    confidence: float = 0.75


_PREDICATE_BY_MARKER = {
    "根因": "root_cause",
    "修复": "solution",
    "解决方案": "solution",
    "验证": "verification",
    "测试": "verification",
    "结论": "lesson_learned",
    "经验": "lesson_learned",
    "教训": "lesson_learned",
}

_MARKER_PATTERN = re.compile(r"(?:^|[。；;，,\s])(?:我定位到)?(根因|修复|解决方案|验证|测试|结论|经验|教训)[:：]\s*")

_STEP_PATTERN = re.compile(r"^\s*(?:[-*]\s+|\d+[.)、]\s*)(.+)$")


def extract_experience_facts(session_id: str, user_text: str, assistant_text: str) -> list[ExperienceFact]:
    facts: list[ExperienceFact] = []
    seen: set[tuple[str, str]] = set()

    def add(predicate: str, obj: str) -> None:
        normalized = _normalize_object(obj)
        if not normalized or _is_noise(normalized):
            return
        key = (predicate, normalized)
        if key in seen:
            return
        seen.add(key)
        facts.append(ExperienceFact(subject=session_id, predicate=predicate, object=normalized))

    goal = _normalize_object(user_text)
    if goal and not _is_noise(goal):
        add("task_goal", goal)

    in_steps = False
    for line in _clean_lines(assistant_text):
        stripped = line.strip()
        if stripped in {"步骤：", "步骤:", "操作步骤：", "操作步骤:"}:
            in_steps = True
            continue

        step_match = _STEP_PATTERN.match(stripped)
        if in_steps and step_match:
            add("successful_step", step_match.group(1))
            continue

        if in_steps and not step_match:
            in_steps = False

        for predicate, obj in _extract_marked_segments(stripped):
            add(predicate, obj)

    return facts


def _clean_lines(text: str) -> list[str]:
    lines: list[str] = []
    in_fence = False
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line or _is_noise(line):
            continue
        lines.append(line)
    return lines


def _normalize_object(text: str) -> str:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if len(normalized) > MAX_FACT_OBJECT_CHARS:
        normalized = normalized[:MAX_FACT_OBJECT_CHARS].rstrip()
    return normalized


def _extract_marked_segments(line: str) -> list[tuple[str, str]]:
    matches = list(_MARKER_PATTERN.finditer(line))
    segments: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(line)
        obj = line[match.end() : next_start].strip(" ；;，,")
        segments.append((_PREDICATE_BY_MARKER[match.group(1)], obj))
    return segments


def _is_noise(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if stripped.startswith(("#", "{", "}")):
        return True
    if stripped.startswith(("🛠️ Tool:", "Tool:", "tool:")):
        return True
    if "```" in stripped:
        return True
    if stripped.startswith(("```json", "```python")):
        return True
    if stripped.startswith("{") and stripped.endswith("}"):
        return True
    return False
