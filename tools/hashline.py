"""
hashline.py — Line-anchored patch language for GA file tools.
Inspired by @oh-my-pi/hashline (can1357/oh-my-pi).

Core ideas:
  * Every file read mints a 4-hex content tag: xxHash32(normalized_text) & 0xffff.
  * Edits are anchored to ORIGINAL line numbers (never shifted by hunks) and
    validated against the tag before any write hits disk.
  * A stale tag triggers recovery (3-way merge via line diff + anchor context)
    or a mismatch rejection that distinguishes fabricated tags from drift.

DSL (see prompt.md in oh-my-pi for the full spec):
  [path#TAG]
  PUT N.=M:      replace original inclusive lines N..M with body rows
  PUT N*:        replace syntactic block opening at N (indent heuristic)
  PUT <N:        insert body rows before line N  (PUT <1: = file head)
  PUT >N:        insert body rows after line N   (PUT >$: = file tail)
  PUT <N @reg / PUT >N @reg   paste register at gap
  PUT N.=M @reg / PUT N* @reg paste register over range/block
  CUT N.=M / CUT N*           delete + capture (anonymous or @reg)
  REM            delete file
  MV DEST        move/rename file (prior edits apply to source)
Body rows: verbatim `+TEXT` (leading whitespace preserved); `+` = blank.
"""

import difflib
import os
import re
from collections import OrderedDict

# ═══════════════════════════════════════════════════════════════════════════
# xxHash32 (pure Python, verified against xxhash lib on 30+ vectors)
# ═══════════════════════════════════════════════════════════════════════════

PRIME32_1 = 2654435761
PRIME32_2 = 2246822519
PRIME32_3 = 3266489917
PRIME32_4 = 668265263
PRIME32_5 = 374761393
MASK32 = 0xFFFFFFFF


def _rotl(x, r):
    return ((x << r) | (x >> (32 - r))) & MASK32


def _read32(b, i):
    return int.from_bytes(b[i:i + 4], "little")


def xxh32(data: bytes, seed: int = 0) -> int:
    """xxHash32. Tail processing starts at the block-processing end position."""
    n = len(data)
    if n >= 16:
        v1 = (seed + PRIME32_1 + PRIME32_2) & MASK32
        v2 = (seed + PRIME32_2) & MASK32
        v3 = seed & MASK32
        v4 = (seed - PRIME32_1) & MASK32
        i = 0
        limit = n - 16
        while i <= limit:
            v1 = (_rotl((v1 + _read32(data, i) * PRIME32_2) & MASK32, 13) * PRIME32_1) & MASK32
            v2 = (_rotl((v2 + _read32(data, i + 4) * PRIME32_2) & MASK32, 13) * PRIME32_1) & MASK32
            v3 = (_rotl((v3 + _read32(data, i + 8) * PRIME32_2) & MASK32, 13) * PRIME32_1) & MASK32
            v4 = (_rotl((v4 + _read32(data, i + 12) * PRIME32_2) & MASK32, 13) * PRIME32_1) & MASK32
            i += 16
        h = (_rotl(v1, 1) + _rotl(v2, 7) + _rotl(v3, 12) + _rotl(v4, 18)) & MASK32
        block_end = i
    else:
        h = (seed + PRIME32_5) & MASK32
        block_end = 0
    h = (h + n) & MASK32
    # tail: from block_end to end
    i = block_end
    limit = n - 4
    while i <= limit:
        h = (h + _read32(data, i) * PRIME32_3) & MASK32
        h = (_rotl(h, 17) * PRIME32_4) & MASK32
        i += 4
    while i < n:
        h = (h + data[i] * PRIME32_5) & MASK32
        h = (_rotl(h, 11) * PRIME32_1) & MASK32
        i += 1
    h ^= h >> 15
    h = (h * PRIME32_2) & MASK32
    h ^= h >> 13
    h = (h * PRIME32_3) & MASK32
    h ^= h >> 16
    return h & MASK32


# ═══════════════════════════════════════════════════════════════════════════
# Text normalization + file hash
# ═══════════════════════════════════════════════════════════════════════════

def normalize_file_hash_text(text: str) -> str:
    """Trim trailing [ \t\r] from every line (and the final line) in one pass."""
    return re.sub(r"[ \t\r]+(?=\n|$)", "", text)


def compute_file_hash(text: str) -> str:
    """4-hex uppercase fingerprint of the whole file's normalized text."""
    normalized = normalize_file_hash_text(text)
    low16 = xxh32(normalized.encode("utf-8"), 0) & 0xFFFF
    return f"{low16:04X}"


def detect_line_ending(content: str) -> str:
    crlf = content.find("\r\n")
    lf = content.find("\n")
    if lf == -1:
        return "\n"
    if crlf == -1:
        return "\n"
    return "\r\n" if crlf < lf else "\n"


def normalize_to_lf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n") if "\r" in text else text


def restore_line_endings(text: str, ending: str) -> str:
    return text.replace("\n", "\r\n") if ending == "\r\n" else text


def strip_bom(content: str):
    if content.startswith("\ufeff"):
        return "\ufeff", content[1:]
    return "", content


def split_addressable_lines(text: str):
    """Split LF text into lines hashline anchors can address (drop trailing '')."""
    lines = text.split("\n")
    if len(lines) > 1 and lines[-1] == "":
        lines.pop()
    return lines


def join_lines(lines) -> str:
    """Join lines back into file text with a trailing newline (like a normal file)."""
    return "\n".join(lines) + "\n"


# ═══════════════════════════════════════════════════════════════════════════
# Snapshot store
# ═══════════════════════════════════════════════════════════════════════════

class Snapshot:
    __slots__ = ("path", "text", "hash", "recorded_at", "seen_lines")

    def __init__(self, path, text, hash_, seen_lines=None):
        self.path = path
        self.text = text
        self.hash = hash_
        self.recorded_at = 0
        self.seen_lines = set(seen_lines) if seen_lines is not None else None


class SnapshotStore:
    """Per-path ring of full-file versions; tag is a fast index, never identity."""

    def __init__(self, max_versions_per_path=8, max_paths=256):
        self._versions = OrderedDict()  # path -> list[Snapshot] (newest first)
        self._max_versions = max_versions_per_path
        self._max_paths = max_paths

    def _touch(self, path):
        if path in self._versions:
            self._versions.move_to_end(path)
        while len(self._versions) > self._max_paths:
            self._versions.popitem(last=False)

    def head(self, path):
        hist = self._versions.get(path)
        return hist[0] if hist else None

    def by_hash(self, path, hash_):
        hist = self._versions.get(path)
        if hist:
            for v in hist:
                if v.hash == hash_:
                    return v
        return None

    def by_content(self, path, full_text):
        hist = self._versions.get(path)
        if hist:
            for v in hist:
                if v.text == full_text:
                    return v
        return None

    def find_by_hash(self, hash_):
        out = []
        for hist in self._versions.values():
            for v in hist:
                if v.hash == hash_:
                    out.append(v)
        return out

    def record(self, path, full_text, seen_lines=None):
        hash_ = compute_file_hash(full_text)
        self._touch(path)
        hist = self._versions.setdefault(path, [])
        # read fusion: byte-identical content reuses the existing tag
        for v in hist:
            if v.text == full_text:
                if seen_lines:
                    if v.seen_lines is None:
                        v.seen_lines = set()
                    v.seen_lines.update(seen_lines)
                return v.hash
        snap = Snapshot(path, full_text, hash_, seen_lines)
        hist.insert(0, snap)
        del hist[self._max_versions:]
        return hash_


# ═══════════════════════════════════════════════════════════════════════════
# DSL parsing
# ═══════════════════════════════════════════════════════════════════════════

HEADER_RE = re.compile(r"^\[([^#\r\n]+)#([0-9A-F]{4})\]\s*$")
PUT_RE = re.compile(r"^PUT\s+(.+?)\s*:\s*$")
PUT_REG_RE = re.compile(r"^PUT\s+(.+?)\s+@([A-Za-z0-9_-]+)\s*$")
CUT_RE = re.compile(r"^CUT\s+(.+?)(?:\s+@([A-Za-z0-9_-]+))?\s*$")
REM_RE = re.compile(r"^REM\s*$")
MV_RE = re.compile(r"^MV\s+(.+?)\s*$")
RANGE_RE = re.compile(r"^([1-9]\d*)\.=([1-9]\d*)$")
BLOCK_RE = re.compile(r"^([1-9]\d*)\*$")
GAP_RE = re.compile(r"^([<>])([1-9]\d*|\$)(\*)?$")
BODY_RE = re.compile(r"^\+(.*)$")


class ParseError(Exception):
    pass


class Edit:
    __slots__ = ("kind", "line", "end", "block", "gap", "gap_line", "gap_eof",
                 "body", "register", "dest", "src_line")

    def __init__(self, kind, **kw):
        self.kind = kind
        self.line = kw.get("line")
        self.end = kw.get("end")
        self.block = kw.get("block", False)
        self.gap = kw.get("gap")
        self.gap_line = kw.get("gap_line")
        self.gap_eof = kw.get("gap_eof", False)
        self.body = kw.get("body")
        self.register = kw.get("register")
        self.dest = kw.get("dest")
        self.src_line = kw.get("src_line")

    def __repr__(self):
        return f"Edit({self.kind}, line={self.line}, end={self.end}, block={self.block}, gap={self.gap}, body={self.body!r}, reg={self.register})"


def _parse_locator(loc):
    """Parse a locator into (kind, line, end, block, gap, gap_line, gap_eof)."""
    loc = loc.strip()
    m = RANGE_RE.match(loc)
    if m:
        return ("range", int(m.group(1)), int(m.group(2)), False, None, None, False)
    m = BLOCK_RE.match(loc)
    if m:
        return ("block", int(m.group(1)), None, True, None, None, False)
    m = GAP_RE.match(loc)
    if m:
        gap, num, star = m.group(1), m.group(2), m.group(3)
        if num == "$":
            return ("gap", None, None, False, gap, None, True)
        return ("gap", int(num), None, bool(star), gap, int(num), False)
    raise ParseError(f"invalid locator: {loc!r}")


def parse_patch(text):
    """Parse hashline DSL text into a list of sections.

    Returns: [{"path": str, "tag": str, "edits": [Edit...], "mv": str|None, "rem": bool}]
    """
    sections = []
    cur = None
    pending = None  # (edit, header_line) awaiting body rows
    for lineno, raw in enumerate(text.split("\n"), 1):
        line = raw.rstrip("\n")
        if pending is not None:
            m = BODY_RE.match(line)
            if m:
                pending[0].body.append(m.group(1))
                continue
            # header without body rows: commit pending as bodyless
            cur["edits"].append(pending[0])
            pending = None
        if not line.strip():
            continue
        if line.strip().startswith("#"):
            continue
        m = HEADER_RE.match(line)
        if m:
            cur = {"path": m.group(1), "tag": m.group(2), "edits": [], "mv": None, "rem": False}
            sections.append(cur)
            continue
        if cur is None:
            raise ParseError(f"line {lineno}: content before any [path#TAG] header")
        m = PUT_RE.match(line)
        if m:
            loc = m.group(1)
            kind, ln, end, block, gap, gap_line, gap_eof = _parse_locator(loc)
            ed = Edit("put", line=ln, end=end, block=block, gap=gap,
                      gap_line=gap_line, gap_eof=gap_eof, body=[])
            pending = (ed, lineno)
            continue
        m = PUT_REG_RE.match(line)
        if m:
            loc = m.group(1)
            kind, ln, end, block, gap, gap_line, gap_eof = _parse_locator(loc)
            ed = Edit("paste", line=ln, end=end, block=block, gap=gap,
                      gap_line=gap_line, gap_eof=gap_eof, register=m.group(2))
            cur["edits"].append(ed)
            continue
        m = CUT_RE.match(line)
        if m:
            loc = m.group(1)
            kind, ln, end, block, gap, gap_line, gap_eof = _parse_locator(loc)
            ed = Edit("cut", line=ln, end=end, block=block, register=m.group(2))
            cur["edits"].append(ed)
            continue
        m = REM_RE.match(line)
        if m:
            cur["rem"] = True
            continue
        m = MV_RE.match(line)
        if m:
            cur["mv"] = m.group(1).strip().strip('"').strip("'")
            continue
        raise ParseError(f"line {lineno}: unrecognized hashline op: {line!r}")
    if pending is not None:
        cur["edits"].append(pending[0])
    return sections


# ═══════════════════════════════════════════════════════════════════════════
# Block resolution (indent heuristic — no tree-sitter dependency)
# ═══════════════════════════════════════════════════════════════════════════

def resolve_block(lines, start_line):
    """Resolve `N*` to an inclusive end line using indentation heuristics.

    Returns end line (>= start_line). Falls back to start_line when the line
    is a single-line construct or indentation is ambiguous.
    """
    n = len(lines)
    if start_line < 1 or start_line > n:
        raise ParseError(f"block anchor line {start_line} does not exist (file has {n} lines)")
    opener = lines[start_line - 1]
    base_indent = len(opener) - len(opener.lstrip())
    # single-line construct: no trailing opener, no following indented block
    stripped = opener.strip()
    if not stripped:
        return start_line
    # look ahead for the first line at same-or-less indent that closes the block
    end = start_line
    for i in range(start_line, n):
        line = lines[i]
        if i == start_line:
            continue
        indent = len(line) - len(line.lstrip())
        if line.strip() == "":
            end = i + 1
            continue
        if base_indent == 0:
            # top-level opener: block = opener + deeper-indented lines
            if indent > 0:
                end = i + 1
            else:
                break
        else:
            # nested opener: block = opener + same-or-deeper indented lines
            if indent >= base_indent:
                end = i + 1
            else:
                break
    return end


# ═══════════════════════════════════════════════════════════════════════════
# Applier
# ═══════════════════════════════════════════════════════════════════════════

class ApplyError(Exception):
    pass


def _resolve_edit_lines(edit, lines):
    """Return (start, end) 1-indexed inclusive original lines for an edit."""
    if edit.kind in ("put", "paste", "cut"):
        if edit.block:
            end = resolve_block(lines, edit.line)
            return edit.line, end
        if edit.end is not None:
            return edit.line, edit.end
        return edit.line, edit.line
    raise ApplyError(f"cannot resolve lines for {edit.kind}")


def apply_edits(lines, edits, clipboard):
    """Apply edits to original lines; returns new lines list.

    All anchors refer to the ORIGINAL file; edits are applied in order by
    rebuilding the file: unchanged runs are copied, edits splice content.
    """
    n = len(lines)
    out = []
    pos = 1  # next original line to copy

    def sort_key(e):
        # anchor line for ordering; gap_eof sorts last; <N before N.=M before >N
        if e.gap_eof:
            return (n + 1, 2)
        if e.gap is not None:
            prio = 0 if e.gap == "<" else 2
            return (e.gap_line, prio)
        return (e.line, 1)

    ordered = sorted(edits, key=sort_key)
    for ed in ordered:
        if ed.kind == "put":
            if ed.gap is not None:
                if ed.gap_eof:
                    while pos <= n:
                        out.append(lines[pos - 1])
                        pos += 1
                    out.extend(ed.body)
                elif ed.gap == "<":
                    while pos < ed.gap_line:
                        out.append(lines[pos - 1])
                        pos += 1
                    out.extend(ed.body)
                else:  # ">"
                    while pos <= ed.gap_line:
                        out.append(lines[pos - 1])
                        pos += 1
                    out.extend(ed.body)
            else:
                start, end = _resolve_edit_lines(ed, lines)
                while pos < start:
                    out.append(lines[pos - 1])
                    pos += 1
                out.extend(ed.body)
                pos = end + 1
        elif ed.kind == "paste":
            reg = clipboard.get(ed.register) if ed.register else clipboard.get(None)
            if reg is None:
                raise ApplyError(f"register @{ed.register or ''} is empty")
            if ed.gap is not None:
                if ed.gap_eof:
                    while pos <= n:
                        out.append(lines[pos - 1])
                        pos += 1
                    out.extend(reg)
                elif ed.gap == "<":
                    while pos < ed.gap_line:
                        out.append(lines[pos - 1])
                        pos += 1
                    out.extend(reg)
                else:
                    while pos <= ed.gap_line:
                        out.append(lines[pos - 1])
                        pos += 1
                    out.extend(reg)
            else:
                start, end = _resolve_edit_lines(ed, lines)
                while pos < start:
                    out.append(lines[pos - 1])
                    pos += 1
                out.extend(reg)
                pos = end + 1
        elif ed.kind == "cut":
            start, end = _resolve_edit_lines(ed, lines)
            while pos < start:
                out.append(lines[pos - 1])
                pos += 1
            captured = lines[start - 1:end]
            clipboard[ed.register] = captured
            pos = end + 1
        else:
            raise ApplyError(f"unknown edit kind {ed.kind}")
    while pos <= n:
        out.append(lines[pos - 1])
        pos += 1
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Recovery (3-way merge via line diff + anchor context)
# ═══════════════════════════════════════════════════════════════════════════

def _diff_line_runs(a_lines, b_lines):
    """Yield ('equal'|'replace'|'delete'|'insert', count) runs like diffLineRuns."""
    sm = difflib.SequenceMatcher(a=a_lines, b=b_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            yield ("equal", i2 - i1)
        elif tag == "replace":
            yield ("delete", i2 - i1)
            yield ("insert", j2 - j1)
        elif tag == "delete":
            yield ("delete", i2 - i1)
        elif tag == "insert":
            yield ("insert", j2 - j1)


def build_line_map(prev_lines, curr_lines):
    """Map previous 1-indexed line -> current 1-indexed line (only unchanged lines)."""
    mapping = {}
    prev_line = 1
    curr_line = 1
    for change, count in _diff_line_runs(prev_lines, curr_lines):
        if change == "insert":
            curr_line += count
        elif change == "delete":
            prev_line += count
        else:  # equal
            for off in range(count):
                mapping[prev_line + off] = curr_line + off
            prev_line += count
            curr_line += count
    return mapping


def recover_section(snapshot_text, current_text, edits, clipboard):
    """Try to replay edits against drifted current content.

    Strategy: map every anchor line through the line diff; if all anchors map
    to unchanged lines with consistent context, replay edits on current lines.
    Returns (new_lines, warnings) or raises ApplyError.
    """
    prev_lines = split_addressable_lines(snapshot_text)
    curr_lines = split_addressable_lines(current_text)
    mapping = build_line_map(prev_lines, curr_lines)

    # collect anchor lines from edits
    anchors = []
    for ed in edits:
        if ed.kind in ("put", "paste", "cut"):
            if ed.gap is not None:
                if ed.gap_eof:
                    anchors.append(len(prev_lines) + 1)
                else:
                    anchors.append(ed.gap_line)
            else:
                start, end = _resolve_edit_lines(ed, prev_lines)
                anchors.extend(range(start, end + 1))
    # every anchor must map to an unchanged line
    remapped = {}
    for a in anchors:
        if a not in mapping:
            raise ApplyError(
                f"recovery failed: anchor line {a} changed between read and edit; "
                "re-read the file to refresh the tag")
        remapped[a] = mapping[a]

    # rebuild edits with remapped line numbers
    new_edits = []
    for ed in edits:
        ne = Edit(ed.kind, line=ed.line, end=ed.end, block=ed.block, gap=ed.gap,
                  gap_line=ed.gap_line, gap_eof=ed.gap_eof, body=list(ed.body) if ed.body else None,
                  register=ed.register, dest=ed.dest)
        if ne.kind in ("put", "paste", "cut"):
            if ne.gap is not None:
                if ne.gap_eof:
                    ne.gap_line = len(curr_lines) + 1
                else:
                    ne.gap_line = remapped.get(ne.gap_line, ne.gap_line)
            else:
                start, end = _resolve_edit_lines(ed, prev_lines)
                ne.line = remapped[start]
                if ne.end is not None:
                    ne.end = remapped.get(end, ne.end)
        new_edits.append(ne)

    new_lines = apply_edits(curr_lines, new_edits, clipboard)
    return new_lines, ["[recovery] file drifted since read; edits replayed against live content"]


# ═══════════════════════════════════════════════════════════════════════════
# High-level patch application
# ═══════════════════════════════════════════════════════════════════════════

def apply_patch(patch_text, store, cwd=".", allow_recovery=True):
    """Apply a hashline patch. Returns a result dict.

    result: {"status": "success"|"error", "sections": [...], "msg": str}
    """
    try:
        sections = parse_patch(patch_text)
    except ParseError as e:
        return {"status": "error", "msg": f"parse error: {e}"}
    if not sections:
        return {"status": "error", "msg": "no [path#TAG] sections found in patch"}

    clipboard = {}
    results = []
    for sec in sections:
        path = os.path.abspath(os.path.join(cwd, sec["path"]))
        tag = sec["tag"]
        edits = sec["edits"]
        # read live file
        if not os.path.exists(path):
            results.append({"path": sec["path"], "status": "error",
                            "msg": f"file not found: {sec['path']}"})
            continue
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
        bom, text = strip_bom(raw)
        text = normalize_to_lf(text)
        live_hash = compute_file_hash(text)
        live_lines = split_addressable_lines(text)

        if live_hash != tag:
            # mismatch: distinguish fabricated vs drift
            snap = store.by_hash(path, tag)
            if snap is None:
                results.append({"path": sec["path"], "status": "error",
                                "msg": (
                                    f"Edit rejected for {sec['path']}: hash #{tag} is not from this session. "
                                    f"The current file hashes to #{live_hash}. Re-read the file to copy a "
                                    f"current [path#tag] header — never invent the tag."
                                )})
                continue
            # drift: try recovery
            if allow_recovery:
                try:
                    new_lines, warns = recover_section(snap.text, text, edits, clipboard)
                    new_text = join_lines(new_lines)
                    results.append({"path": sec["path"], "status": "success",
                                    "msg": f"recovered after drift; {len(warns)} warning(s)",
                                    "warnings": warns,
                                    "new_hash": compute_file_hash(new_text)})
                    _write_file(path, new_text, bom)
                    store.record(path, new_text)
                    continue
                except ApplyError as e:
                    results.append({"path": sec["path"], "status": "error",
                                    "msg": (
                                        f"Edit rejected for {sec['path']}: file changed between read and edit. "
                                        f"Section bound to #{tag}, current file hashes to #{live_hash}. "
                                        f"Recovery failed: {e}"
                                    )})
                    continue
            results.append({"path": sec["path"], "status": "error",
                            "msg": (
                                f"Edit rejected for {sec['path']}: file changed between read and edit. "
                                f"Section bound to #{tag}, current file hashes to #{live_hash}. "
                                f"Re-read the file to refresh the tag."
                            )})
            continue

        # hash matches: apply edits
        try:
            new_lines = apply_edits(live_lines, edits, clipboard)
        except ApplyError as e:
            results.append({"path": sec["path"], "status": "error", "msg": str(e)})
            continue
        new_text = join_lines(new_lines)
        if sec["rem"]:
            os.remove(path)
            results.append({"path": sec["path"], "status": "success", "msg": "file removed"})
            continue
        dest = sec["mv"]
        if dest:
            dest_path = os.path.abspath(os.path.join(cwd, dest))
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            _write_file(dest_path, new_text, bom)
            if os.path.abspath(dest_path) != path:
                os.remove(path)
            results.append({"path": sec["path"], "status": "success",
                            "msg": f"moved to {dest}", "new_hash": compute_file_hash(new_text)})
            store.record(dest_path, new_text)
            continue
        _write_file(path, new_text, bom)
        new_hash = compute_file_hash(new_text)
        store.record(path, new_text)
        results.append({"path": sec["path"], "status": "success",
                        "msg": "patched", "new_hash": new_hash})

    ok = all(r["status"] == "success" for r in results)
    return {"status": "success" if ok else "error",
            "sections": results,
            "msg": "; ".join(f"{r['path']}: {r['msg']}" for r in results)}


def _write_file(path, text, bom=""):
    ending = detect_line_ending(text)
    out = restore_line_endings(text, ending)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(bom + out)


# ═══════════════════════════════════════════════════════════════════════════
# Read-side helpers (used by file_read to mint tags)
# ═══════════════════════════════════════════════════════════════════════════

def format_header(path, text):
    return f"[{path}#{compute_file_hash(text)}]"


def format_numbered_lines(text, start_line=1):
    lines = split_addressable_lines(text)
    return "\n".join(f"{start_line + i}:{line}" for i, line in enumerate(lines))