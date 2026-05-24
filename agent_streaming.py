import re


_BLOCK_TAGS = ("thinking", "think", "summary", "tool_use", "tool_call", "file_content")
_SUMMARY_RE = re.compile(r"<summary>\s*([\s\S]*?)\s*</(?:summary|parameter)>", re.IGNORECASE)
_TAG_RE = re.compile(r"</?([a-zA-Z_][a-zA-Z0-9_]*)[^>]*>")


class ModelDisplayStreamFilter:
    """Remove GA protocol/private blocks from model text before UI streaming."""

    def __init__(self):
        self._buffer = ""
        self._blocked_tag = ""

    def feed(self, chunk):
        self._buffer += str(chunk or "")
        return self._drain(final=False)

    def finish(self):
        return self._drain(final=True)

    def _drain(self, final):
        visible = []
        while self._buffer:
            if self._blocked_tag:
                close_match = _blocked_close_match(self._buffer, self._blocked_tag)
                if close_match is None:
                    if final:
                        self._buffer = ""
                        self._blocked_tag = ""
                    else:
                        self._buffer = self._buffer[-64:]
                    break
                self._buffer = self._buffer[close_match.end():]
                self._blocked_tag = ""
                continue

            tag_match = _TAG_RE.search(self._buffer)
            if not tag_match:
                if final:
                    blocked_start = _possible_blocked_opening_start(self._buffer)
                    if blocked_start >= 0:
                        visible.append(self._buffer[:blocked_start])
                    else:
                        visible.append(self._buffer)
                    self._buffer = ""
                else:
                    last_open = self._buffer.rfind("<")
                    if last_open >= 0:
                        visible.append(self._buffer[:last_open])
                        self._buffer = self._buffer[last_open:]
                        break
                    keep = min(len(self._buffer), 64)
                    emit_len = max(0, len(self._buffer) - keep)
                    visible.append(self._buffer[:emit_len])
                    self._buffer = self._buffer[emit_len:]
                break

            start, end = tag_match.span()
            tag_name = tag_match.group(1).lower()
            is_close = self._buffer[start + 1:start + 2] == "/"
            if tag_name not in _BLOCK_TAGS:
                visible.append(self._buffer[:end])
                self._buffer = self._buffer[end:]
                continue

            visible.append(self._buffer[:start])
            self._buffer = self._buffer[end:]
            if not is_close:
                self._blocked_tag = tag_name

        return "".join(visible)


def extract_model_process_summary(text, thinking="", limit=90):
    raw_text = str(text or "").strip()
    match = _SUMMARY_RE.search(raw_text)
    if match:
        return _single_line(match.group(1), limit)

    raw_thinking = str(thinking or "").strip()
    if raw_thinking:
        return _single_line(raw_thinking.splitlines()[0], limit)

    for line in raw_text.splitlines():
        line = _strip_protocol_tags(line).strip()
        if line:
            return _single_line(line, limit)
    return ""


def sanitize_model_visible_text(text):
    stream_filter = ModelDisplayStreamFilter()
    return (stream_filter.feed(text) + stream_filter.finish()).strip()


def _single_line(text, limit):
    line = " ".join(str(text or "").split())
    if len(line) <= limit:
        return line
    return line[: limit - 1].rstrip() + "…"


def _strip_protocol_tags(text):
    out = str(text or "")
    for tag in _BLOCK_TAGS:
        out = re.sub(rf"<{tag}[^>]*>[\s\S]*?</{tag}>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"<summary[^>]*>[\s\S]*?</parameter>", "", out, flags=re.IGNORECASE)
    return out


def _blocked_close_match(text, tag):
    if tag == "summary":
        return re.search(r"</(?:summary|parameter)>", text, flags=re.IGNORECASE)
    return re.search(rf"</{re.escape(tag)}>", text, flags=re.IGNORECASE)


def _possible_blocked_opening_start(text):
    start = str(text or "").rfind("<")
    if start < 0:
        return -1
    suffix = text[start + 1:].lower()
    if not suffix or suffix.startswith("/"):
        return -1
    name_match = re.match(r"[a-zA-Z_][a-zA-Z0-9_]*", suffix)
    if not name_match:
        return -1
    name = name_match.group(0)
    for tag in _BLOCK_TAGS:
        if tag.startswith(name) or name.startswith(tag):
            return start
    return -1
