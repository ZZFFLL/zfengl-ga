"""Process-event helpers for the LibreChat adapter."""

from dataclasses import dataclass
import re


_SUMMARY_BLOCK_RE = re.compile(
    r"<summary\b[^>]*>(.*?)</summary>",
    re.IGNORECASE | re.DOTALL,
)
_UNCLOSED_SUMMARY_RE = re.compile(
    r"<summary\b[^>]*>.*\Z",
    re.IGNORECASE | re.DOTALL,
)
_PROCESS_TOKEN_RE = re.compile(
    r"(?P<summary><summary\b[^>]*>.*?</summary>)|"
    r"(?P<turn>(?:\*\*)?\s*LLM Running\s*\(Turn\s+(?P<turn_num>\d+)\)[^\n]*(?:\*\*)?)",
    re.IGNORECASE | re.DOTALL,
)
_BLANK_LINES_RE = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)+")
_MAX_SUMMARY_CHARS = 240


@dataclass
class GAProcessEvent:
    type: str
    turn: int | None = None
    tool_name: str = ""
    summary: str = ""
    content_delta: str = ""


def _compact_blank_lines(text):
    lines = [line.rstrip() for line in (text or "").splitlines()]
    return _BLANK_LINES_RE.sub("\n\n", "\n".join(lines)).strip()


def strip_summary_blocks(text):
    """Remove hidden summary blocks and normalize extra vertical whitespace."""
    without_summaries = _SUMMARY_BLOCK_RE.sub("", text or "")
    without_summaries = _UNCLOSED_SUMMARY_RE.sub("", without_summaries)
    return _compact_blank_lines(without_summaries)


def _summary_text(summary_block):
    match = _SUMMARY_BLOCK_RE.fullmatch((summary_block or "").strip())
    if not match:
        return ""
    return _compact_blank_lines(match.group(1))


def parse_process_events(text):
    """Parse visible process markers into structured events."""
    events = []
    current_turn = None
    for match in _PROCESS_TOKEN_RE.finditer(text or ""):
        turn_num = match.group("turn_num")
        if turn_num is not None:
            current_turn = int(turn_num)
            events.append(GAProcessEvent(type="turn_start", turn=current_turn))
            continue

        summary = _summary_text(match.group("summary"))
        if summary:
            events.append(
                GAProcessEvent(
                    type="reasoning_summary",
                    turn=current_turn,
                    summary=summary,
                )
            )
    return events


def _truncate_summary(summary):
    summary = _compact_blank_lines(strip_summary_blocks(summary))
    if len(summary) <= _MAX_SUMMARY_CHARS:
        return summary
    return summary[: _MAX_SUMMARY_CHARS - 3].rstrip() + "..."


def render_process_markdown(events):
    """Render safe process summaries without exposing raw hidden reasoning."""
    summary_events = []
    for event in events or []:
        if event.type != "reasoning_summary":
            continue
        summary = _truncate_summary(event.summary)
        if summary:
            summary_events.append((event.turn, summary))
    if not summary_events:
        return ""

    lines = ["## 思考过程"]
    active_turn = None
    for turn, summary in summary_events:
        if turn != active_turn:
            active_turn = turn
            label = f"Turn {active_turn}" if active_turn is not None else "Turn"
            lines.extend(["", f"### {label}"])
        lines.append(f"- {summary}")
    return "\n".join(lines).strip()
