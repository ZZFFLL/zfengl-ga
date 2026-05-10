# MemPalace Experience Memory Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn GA's MemPalace integration from raw conversation archiving into a useful experience memory layer that captures successful steps, conclusions, root causes, verification evidence, and reusable lessons without restructuring GA.

**Architecture:** Keep MemPalace as a parallel capability layer. GA continues storing full turns into ChromaDB, while a new small extractor derives compact high-value experience facts from assistant outputs and writes them into the existing MemPalace SQLite KG. Prompt injection stays bounded and read-only, and only high-value experience facts are added to the prompt; existing GA L0-L4 memory and agent loop behavior are not replaced.

**Tech Stack:** Python 3.13, pytest/unittest, existing `mempalace` ChromaDB drawers via `memory.palace_bridge.PalaceBridge.store_turn()`, existing SQLite KG via `mempalace.knowledge_graph.KnowledgeGraph`, existing tests in `tests/test_webui_server.py` and `tests/test_mempalace_memory_quality.py`.

---

## Current Evidence

- `agentmain._store_mempalace_turn()` writes user and assistant turns into MemPalace and then calls `bridge.extract_conversation_facts(session_id, raw_query, full_resp)`.
- `memory/palace_bridge.py::extract_conversation_facts()` currently extracts only tool usage, user preference/dislike, decision snippets, and `occurred_at` metadata.
- Live KG currently has mostly `occurred_at` and `uses_tool` facts, with only two useful preference facts: `user prefers 用rg搜索文件` and `user dislikes 用python处理`.
- Full successful exploration/process content is stored in ChromaDB as raw assistant text, but it is not summarized into structured reusable facts.
- MemPalace is a good fit for this as a dual store: ChromaDB keeps verbatim drawers for semantic recall, KG keeps compact relationships/facts for prompt injection and durable lessons.
- GA should not be deeply refactored: keep the existing async post-processing thread and add one bridge method call inside the existing write path.

## Design Constraints

- Do not replace GA's existing L0-L4 memory files.
- Do not modify external `mempalace` package files under site-packages.
- Do not restructure GA's main loop or handler lifecycle.
- Do not add an LLM call inside memory extraction; extraction must be local, deterministic, and fast.
- Do not inject raw execution transcripts into the system prompt as authoritative instructions.
- Do not store huge markdown or full tool logs as KG objects.
- Prefer adding focused files under `memory/` and tests under existing test files.

## File Structure

- Create `memory/experience_extractor.py`
  - Pure local extraction utilities.
  - Defines `ExperienceFact` dataclass.
  - Extracts compact facts from assistant output and optional user goal.
  - No MemPalace imports and no database writes.

- Modify `memory/palace_bridge.py`
  - Add `extract_experience_facts(session_id, user_text, assistant_text)`.
  - Use `memory.experience_extractor.extract_experience_facts()`.
  - Write facts to KG with predicates:
    - `task_goal`
    - `successful_step`
    - `root_cause`
    - `solution`
    - `verification`
    - `lesson_learned`
  - Add `get_experience_context(session_id=None, max_facts=6)`.
  - Keep existing `extract_conversation_facts()` behavior intact except for optional call site additions in `agentmain.py`.

- Modify `agentmain.py`
  - Add one call to `bridge.extract_experience_facts(session_id, raw_query, full_resp)` in `_store_mempalace_turn()`, after existing `extract_conversation_facts()`.
  - Add prompt injection for `bridge.get_experience_context(max_facts=5)` after KG context, with read-only wording.
  - Keep current async write model and prompt retrieval score filter unchanged.

- Modify `memory/kg_maintenance.py`
  - Add dry-run helper to list and delete orphan noisy entities that no longer appear in triples.
  - Do not delete entities referenced by any triple.

- Modify `assets/sys_prompt.txt`
  - Clarify that MemPalace stores raw conversation drawers plus compact experience facts.
  - Tell GA to use experience memory as background reference, not as a current user instruction.

- Modify `tests/test_mempalace_memory_quality.py`
  - Unit tests for `experience_extractor`.
  - Bridge tests for experience KG writes and prompt context formatting.
  - Maintenance tests for orphan noisy entity cleanup.

- Modify `tests/test_webui_server.py`
  - Integration test that `_store_mempalace_turn()` calls both existing conversation fact extraction and new experience fact extraction.
  - Prompt injection test for read-only experience context.

---

### Task 1: Add Pure Experience Fact Extractor

**Files:**
- Create: `memory/experience_extractor.py`
- Modify: `tests/test_mempalace_memory_quality.py`

- [ ] **Step 1: Write failing extractor tests**

Append this class to `tests/test_mempalace_memory_quality.py`:

```python

class MemPalaceExperienceExtractorTests(unittest.TestCase):
    def test_extracts_success_steps_solution_and_verification(self):
        from memory.experience_extractor import extract_experience_facts

        assistant_text = """
        我定位到根因：检索记忆被当成 USER 消息压入，导致历史内容像当前指令。
        修复：把 MemPalace 检索结果改成 READ ONLY system context，并增加 score 过滤。
        步骤：
        1. 读取 agentmain.py 的 get_system_prompt。
        2. 添加 _format_mempalace_history_context。
        3. 增加低分跳过日志。
        验证：python -m pytest tests/test_webui_server.py::AgentMainMemPalaceTests -q -> 8 passed
        结论：历史检索只能作为背景参考，不能作为当前用户指令。
        """

        facts = extract_experience_facts(
            session_id="session-a",
            user_text="mempalace 检索内容被压进 USER，帮我修",
            assistant_text=assistant_text,
        )

        pairs = [(f.predicate, f.object) for f in facts]
        self.assertIn(("root_cause", "检索记忆被当成 USER 消息压入，导致历史内容像当前指令。"), pairs)
        self.assertIn(("solution", "把 MemPalace 检索结果改成 READ ONLY system context，并增加 score 过滤。"), pairs)
        self.assertIn(("verification", "python -m pytest tests/test_webui_server.py::AgentMainMemPalaceTests -q -> 8 passed"), pairs)
        self.assertIn(("lesson_learned", "历史检索只能作为背景参考，不能作为当前用户指令。"), pairs)
        self.assertTrue(any(p == "successful_step" and "读取 agentmain.py" in o for p, o in pairs))

    def test_skips_tool_transcript_and_long_markdown_noise(self):
        from memory.experience_extractor import extract_experience_facts

        assistant_text = """
        🛠️ Tool: `file_read`
        ```json
        {"path": "agentmain.py", "count": 200}
        ```
        ## 大段日志
        这个块不应该成为经验事实，因为它是工具流水。
        结论：dedup 写入失败时要有降级日志。
        """

        facts = extract_experience_facts(
            session_id="session-b",
            user_text="记得打日志",
            assistant_text=assistant_text,
        )

        objects = [f.object for f in facts]
        self.assertIn("dedup 写入失败时要有降级日志。", objects)
        self.assertFalse(any("Tool:" in obj or "```json" in obj for obj in objects))
```

- [ ] **Step 2: Run extractor tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_mempalace_memory_quality.py::MemPalaceExperienceExtractorTests -q
```

Expected: `FAIL`, because `memory.experience_extractor` does not exist.

- [ ] **Step 3: Create `memory/experience_extractor.py`**

Create the file with this content:

```python
"""Extract compact reusable experience facts from GA assistant output."""

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


_PREDICATE_MARKERS = (
    ("root_cause", ("根因：", "原因：", "Root cause:", "root cause:")),
    ("solution", ("修复：", "解决方案：", "处理方式：", "Solution:", "Fix:")),
    ("verification", ("验证：", "测试：", "Verification:", "Test:")),
    ("lesson_learned", ("结论：", "经验：", "Lesson:", "Takeaway:")),
)


def _normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", str(line or "").strip())


def _is_noise_line(line: str) -> bool:
    text = str(line or "").strip()
    if not text:
        return True
    noisy_fragments = (
        "🛠️ Tool:",
        "📥 args:",
        "`````",
        "```",
        "{",
        "}",
        "<summary>",
        "</summary>",
        "[Action]",
        "[Info] Final response to user.",
    )
    if any(fragment in text for fragment in noisy_fragments):
        return True
    if text.startswith(("##", "###", "---")):
        return True
    return False


def _clean_object(value: str) -> str:
    text = _normalize_line(value)
    if len(text) > MAX_FACT_OBJECT_CHARS:
        text = text[:MAX_FACT_OBJECT_CHARS].rsplit(" ", 1)[0].strip()
    return text


def _append_fact(facts: list[ExperienceFact], subject: str, predicate: str,
                 value: str, confidence: float = 0.75) -> None:
    obj = _clean_object(value)
    if len(obj) < 4:
        return
    key = (subject, predicate, obj)
    if any((f.subject, f.predicate, f.object) == key for f in facts):
        return
    facts.append(ExperienceFact(subject, predicate, obj, confidence=confidence))


def _extract_step_value(line: str) -> str:
    return re.sub(r"^(?:[-*]\s*|\d+[.)、]\s*)", "", line).strip()


def extract_experience_facts(session_id: str, user_text: str,
                             assistant_text: str) -> list[ExperienceFact]:
    """Extract reusable task experience from assistant output.

    This intentionally stays heuristic and local. Raw transcripts remain in
    ChromaDB; this function only emits compact KG-ready facts.
    """
    facts: list[ExperienceFact] = []
    subject = session_id or "session"

    goal = _clean_object(user_text)
    if goal:
        _append_fact(facts, subject, "task_goal", goal, confidence=0.65)

    in_steps = False
    for raw_line in str(assistant_text or "").splitlines():
        line = raw_line.strip()
        if _is_noise_line(line):
            continue

        if line.rstrip("：:") in ("步骤", "执行步骤", "成功步骤", "Steps"):
            in_steps = True
            continue

        matched_marker = False
        for predicate, markers in _PREDICATE_MARKERS:
            for marker in markers:
                if line.startswith(marker):
                    _append_fact(
                        facts,
                        subject,
                        predicate,
                        line[len(marker):].strip(),
                        confidence=0.85 if predicate in ("verification", "solution") else 0.8,
                    )
                    matched_marker = True
                    in_steps = False
                    break
            if matched_marker:
                break
        if matched_marker:
            continue

        if in_steps and re.match(r"^(?:[-*]\s*|\d+[.)、]\s*)", line):
            _append_fact(
                facts,
                subject,
                "successful_step",
                _extract_step_value(line),
                confidence=0.75,
            )
            continue

        if in_steps and not re.match(r"^(?:[-*]\s*|\d+[.)、]\s*)", line):
            in_steps = False

    return facts
```

- [ ] **Step 4: Run extractor tests**

Run:

```powershell
python -m pytest tests/test_mempalace_memory_quality.py::MemPalaceExperienceExtractorTests -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add memory/experience_extractor.py tests/test_mempalace_memory_quality.py
git commit -m "feat: extract MemPalace experience facts"
```

Expected: commit contains only the new extractor and tests. If `memory/experience_extractor.py` is ignored by `memory/*`, use:

```powershell
git add -f memory/experience_extractor.py
git add tests/test_mempalace_memory_quality.py
git commit -m "feat: extract MemPalace experience facts"
```

---

### Task 2: Write Experience Facts Into MemPalace KG

**Files:**
- Modify: `memory/palace_bridge.py`
- Modify: `agentmain.py`
- Modify: `tests/test_mempalace_memory_quality.py`
- Modify: `tests/test_webui_server.py`

- [ ] **Step 1: Add failing bridge tests**

Append this class to `tests/test_mempalace_memory_quality.py`:

```python

class MemPalaceExperienceBridgeTests(unittest.TestCase):
    def test_extract_experience_facts_writes_compact_kg_facts(self):
        from memory.palace_bridge import PalaceBridge

        bridge = PalaceBridge(palace_path="unused", kg_path="unused")
        captured = []
        bridge.add_fact = lambda subject, predicate, obj, **kwargs: captured.append(
            (subject, predicate, obj, kwargs.get("confidence"))
        )

        bridge.extract_experience_facts(
            "session-exp",
            "修复 MemPalace 记忆质量",
            "根因：只存原文，没有结构化经验。\n"
            "修复：新增经验抽取层。\n"
            "验证：python -m pytest tests/test_mempalace_memory_quality.py -q -> passed\n"
            "结论：原文归档和经验事实应该分层存储。",
        )

        predicates = [row[1] for row in captured]
        self.assertIn("task_goal", predicates)
        self.assertIn("root_cause", predicates)
        self.assertIn("solution", predicates)
        self.assertIn("verification", predicates)
        self.assertIn("lesson_learned", predicates)
        self.assertTrue(all(len(row[2]) <= 160 for row in captured))

    def test_experience_context_includes_only_experience_predicates(self):
        from memory.palace_bridge import PalaceBridge

        bridge = PalaceBridge(palace_path="unused", kg_path="unused")

        class FakeKG:
            def timeline(self):
                return [
                    {"subject": "s1", "predicate": "occurred_at", "object": "2026-05-06 10:00:00"},
                    {"subject": "s1", "predicate": "uses_tool", "object": "file_read"},
                    {"subject": "s1", "predicate": "solution", "object": "新增经验抽取层"},
                    {"subject": "s1", "predicate": "verification", "object": "pytest -> passed"},
                ]

        bridge._kg = FakeKG()
        context = bridge.get_experience_context(max_facts=5)

        self.assertIn("[MemPalace Experience - READ ONLY]", context)
        self.assertIn("solution: 新增经验抽取层", context)
        self.assertIn("verification: pytest -> passed", context)
        self.assertNotIn("occurred_at", context)
        self.assertNotIn("uses_tool", context)
```

- [ ] **Step 2: Run bridge tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_mempalace_memory_quality.py::MemPalaceExperienceBridgeTests -q
```

Expected: `FAIL`, because `PalaceBridge.extract_experience_facts()` and `get_experience_context()` do not exist.

- [ ] **Step 3: Add experience methods to `memory/palace_bridge.py`**

Add this constant near the other config constants:

```python
EXPERIENCE_PREDICATES = {
    "task_goal",
    "successful_step",
    "root_cause",
    "solution",
    "verification",
    "lesson_learned",
}
```

Add this method below `extract_conversation_facts()` and above `_is_clean_fact_object()`:

```python
    def extract_experience_facts(self, session_id: str,
                                 user_text: str, assistant_text: str):
        """Extract reusable task experience facts into the KG."""
        try:
            from memory.experience_extractor import extract_experience_facts

            facts = extract_experience_facts(session_id, user_text, assistant_text)
            for fact in facts:
                if fact.predicate not in EXPERIENCE_PREDICATES:
                    continue
                if not self._is_clean_experience_object(fact.object):
                    continue
                try:
                    self.add_fact(
                        fact.subject,
                        fact.predicate,
                        fact.object,
                        valid_from=time.strftime('%Y-%m-%d %H:%M:%S'),
                        confidence=fact.confidence,
                    )
                except Exception:
                    pass
            if facts:
                print(f"[MemPalace] 🧩 extracted {len(facts)} experience facts")
        except Exception as e:
            print(f"[MemPalace] ⚠️ experience extraction failed: {e}")
```

Add this static method below `_is_clean_fact_object()`:

```python
    @staticmethod
    def _is_clean_experience_object(value: str) -> bool:
        text = str(value or "").strip()
        if not (4 <= len(text) <= 180):
            return False
        noisy_fragments = (
            "```",
            "`````",
            "<summary>",
            "</summary>",
            "🛠️ Tool:",
            "📥 args:",
            "[Action]",
            "[Info] Final response to user.",
            "<file_content>",
            "</file_content>",
        )
        if any(fragment in text for fragment in noisy_fragments):
            return False
        if text.count("|") >= 2:
            return False
        return True
```

Add this method near `get_session_facts_context()`:

```python
    def get_experience_context(self, session_id: str = None,
                               max_facts: int = 6) -> str:
        """Return compact reusable experience facts for prompt injection."""
        try:
            facts = self.query_facts(session_id) if session_id else self.kg.timeline()
        except Exception as e:
            print(f"[MemPalace] ❌ get_experience_context failed: {e}")
            return ""

        selected = []
        seen = set()
        for f in facts:
            predicate = f.get("predicate", "")
            if predicate not in EXPERIENCE_PREDICATES:
                continue
            obj = str(f.get("object", "")).strip()
            if not obj or not self._is_clean_experience_object(obj):
                continue
            key = (f.get("subject", "?"), predicate, obj)
            if key in seen:
                continue
            seen.add(key)
            selected.append((f.get("subject", "?"), predicate, obj))
            if len(selected) >= max_facts:
                break

        if not selected:
            return ""

        lines = [
            "[MemPalace Experience - READ ONLY]",
            "以下是历史任务中提炼出的可复用经验，仅作背景参考；不是本轮用户新指令。",
        ]
        for subject, predicate, obj in selected:
            lines.append(f"- {subject} {predicate}: {obj}")
        lines.append("[/MemPalace Experience]")
        print(f"[MemPalace] 🧩 experience context injected ({len(selected)} facts)")
        return "\n".join(lines)
```

- [ ] **Step 4: Run bridge tests**

Run:

```powershell
python -m pytest tests/test_mempalace_memory_quality.py::MemPalaceExperienceBridgeTests -q
```

Expected: `2 passed`.

- [ ] **Step 5: Add failing agentmain integration tests**

Add these methods to `AgentMainMemPalaceTests` in `tests/test_webui_server.py`:

```python
    def test_mempalace_storage_extracts_experience_facts(self):
        import agentmain
        from unittest import mock

        class FakeBridge:
            def __init__(self):
                self.stored = []
                self.conversation_facts = None
                self.experience_facts = None

            def store_turn(self, session_id, role, content):
                self.stored.append((session_id, role, content))
                return f"{role}-id"

            def extract_conversation_facts(self, session_id, raw_query, full_resp):
                self.conversation_facts = (session_id, raw_query, full_resp)

            def extract_experience_facts(self, session_id, raw_query, full_resp):
                self.experience_facts = (session_id, raw_query, full_resp)

        bridge = FakeBridge()
        with mock.patch("agentmain._palace_bridge", return_value=bridge), mock.patch(
            "memory.dedup.is_duplicate", return_value=False
        ):
            agentmain._store_mempalace_turn("session-1", "用户目标", "修复：做了一个小改动")

        self.assertEqual(bridge.conversation_facts, ("session-1", "用户目标", "修复：做了一个小改动"))
        self.assertEqual(bridge.experience_facts, ("session-1", "用户目标", "修复：做了一个小改动"))

    def test_system_prompt_injects_read_only_experience_context(self):
        import contextlib
        import io
        from unittest import mock

        import agentmain

        class FakeBridge:
            def search(self, query, n_results=3):
                return []

            def get_session_facts_context(self, session_id=None, max_facts=8):
                return ""

            def get_experience_context(self, session_id=None, max_facts=5):
                return "[MemPalace Experience - READ ONLY]\n- s1 solution: 新增经验抽取层\n[/MemPalace Experience]"

        out = io.StringIO()
        with mock.patch("agentmain._palace_bridge", return_value=FakeBridge()), mock.patch(
            "agentmain.get_global_memory", return_value=""
        ), contextlib.redirect_stdout(out):
            prompt = agentmain.get_system_prompt("怎么优化记忆")

        self.assertIn("[MemPalace Experience - READ ONLY]", prompt)
        self.assertIn("solution: 新增经验抽取层", prompt)
```

- [ ] **Step 6: Run agentmain tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_webui_server.py::AgentMainMemPalaceTests::test_mempalace_storage_extracts_experience_facts tests/test_webui_server.py::AgentMainMemPalaceTests::test_system_prompt_injects_read_only_experience_context -q
```

Expected: `FAIL`, because `agentmain.py` does not call `extract_experience_facts()` or `get_experience_context()` yet.

- [ ] **Step 7: Wire experience extraction and prompt context in `agentmain.py`**

In `_store_mempalace_turn()`, after:

```python
            bridge.extract_conversation_facts(session_id, raw_query, full_resp)
```

add:

```python
            if hasattr(bridge, "extract_experience_facts"):
                bridge.extract_experience_facts(session_id, raw_query, full_resp)
```

In `get_system_prompt()`, after KG context injection:

```python
                if hasattr(bridge, "get_experience_context"):
                    exp_ctx = bridge.get_experience_context(session_id=None, max_facts=5)
                    if exp_ctx:
                        prompt += "\n" + exp_ctx
```

- [ ] **Step 8: Run integration tests**

Run:

```powershell
python -m pytest tests/test_webui_server.py::AgentMainMemPalaceTests::test_mempalace_storage_extracts_experience_facts tests/test_webui_server.py::AgentMainMemPalaceTests::test_system_prompt_injects_read_only_experience_context -q
```

Expected: `2 passed`.

- [ ] **Step 9: Run focused suites**

Run:

```powershell
python -m pytest tests/test_mempalace_memory_quality.py::MemPalaceExperienceBridgeTests tests/test_webui_server.py::AgentMainMemPalaceTests -q
```

Expected: all selected tests pass.

- [ ] **Step 10: Commit Task 2**

Run:

```powershell
git add agentmain.py memory/palace_bridge.py tests/test_mempalace_memory_quality.py tests/test_webui_server.py
git commit -m "feat: write MemPalace experience facts"
```

Expected: commit contains only the bridge, agentmain integration, and tests.

---

### Task 3: Reduce Low-Value KG Context Injection

**Files:**
- Modify: `memory/palace_bridge.py`
- Modify: `tests/test_mempalace_memory_quality.py`

- [ ] **Step 1: Add failing KG context filtering tests**

Append this test method to `MemPalaceExperienceBridgeTests`:

```python
    def test_session_facts_context_skips_occurred_at_noise(self):
        from memory.palace_bridge import PalaceBridge

        bridge = PalaceBridge(palace_path="unused", kg_path="unused")

        class FakeKG:
            def timeline(self):
                return [
                    {"subject": "s1", "predicate": "occurred_at", "object": "2026-05-06 10:00:00"},
                    {"subject": "s1", "predicate": "uses_tool", "object": "file_read"},
                    {"subject": "user", "predicate": "prefers", "object": "用rg搜索文件"},
                ]

        bridge._kg = FakeKG()
        context = bridge.get_session_facts_context(max_facts=8)

        self.assertIn("user prefers 用rg搜索文件", context)
        self.assertIn("s1 uses_tool file_read", context)
        self.assertNotIn("occurred_at", context)
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
python -m pytest tests/test_mempalace_memory_quality.py::MemPalaceExperienceBridgeTests::test_session_facts_context_skips_occurred_at_noise -q
```

Expected: `FAIL`, because current `get_session_facts_context()` includes earliest timeline facts and can include `occurred_at`.

- [ ] **Step 3: Filter low-value KG predicates in `get_session_facts_context()`**

In `memory/palace_bridge.py`, add this constant near `EXPERIENCE_PREDICATES`:

```python
PROMPT_KG_PREDICATES = {"prefers", "dislikes", "uses_tool", "decided"}
```

In `get_session_facts_context()`, change the loop:

```python
        for f in facts[:max_facts]:
```

to:

```python
        for f in facts:
```

and after reading `s, p, o`, add:

```python
            if p not in PROMPT_KG_PREDICATES:
                continue
```

Move the max limit check after appending:

```python
            if len(seen) >= max_facts:
                break
```

The final loop body should be:

```python
        for f in facts:
            s, p, o = (f.get('subject','?'), f.get('predicate','?'),
                       f.get('object','?'))
            if p not in PROMPT_KG_PREDICATES:
                continue
            key = (s, p, o)
            if key in seen:
                continue
            seen.add(key)
            valid = f.get('valid_from', '')
            lines.append(f"- {s} {p} {o}" + (f" (since {valid})" if valid else ""))
            if len(seen) >= max_facts:
                break
```

After the loop, if only the header exists, return empty:

```python
        if not seen:
            return ""
```

- [ ] **Step 4: Run KG context filtering test**

Run:

```powershell
python -m pytest tests/test_mempalace_memory_quality.py::MemPalaceExperienceBridgeTests::test_session_facts_context_skips_occurred_at_noise -q
```

Expected: `1 passed`.

- [ ] **Step 5: Run focused memory quality tests**

Run:

```powershell
python -m pytest tests/test_mempalace_memory_quality.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 3**

Run:

```powershell
git add memory/palace_bridge.py tests/test_mempalace_memory_quality.py
git commit -m "fix: keep low-value KG metadata out of prompt"
```

Expected: commit contains only `memory/palace_bridge.py` and tests.

---

### Task 4: Add Dry-Run Cleanup For Orphan Noisy Entities

**Files:**
- Modify: `memory/kg_maintenance.py`
- Modify: `tests/test_mempalace_memory_quality.py`

- [ ] **Step 1: Add failing orphan entity cleanup tests**

Append this class to `tests/test_mempalace_memory_quality.py`:

```python

class MemPalaceEntityMaintenanceTests(unittest.TestCase):
    def _create_temp_kg_with_entities(self):
        tmp = tempfile.TemporaryDirectory()
        db_path = Path(tmp.name) / "kg.sqlite3"
        con = sqlite3.connect(str(db_path))
        con.execute(
            "create table entities ("
            "id text primary key, name text not null, type text default 'unknown', "
            "properties text default '{}', created_at text default CURRENT_TIMESTAMP)"
        )
        con.execute(
            "create table triples ("
            "id text primary key, subject text, predicate text, object text, "
            "valid_from text, valid_to text, confidence real, source_closet text, "
            "source_file text, extracted_at text)"
        )
        con.execute("insert into entities values ('noise','人/项目 | entity_detector.py | 无 |','unknown','{}',null)")
        con.execute("insert into entities values ('good','用rg搜索文件','unknown','{}',null)")
        con.execute("insert into entities values ('referenced-noise','级）\n\n### ⭐⭐⭐ 高价值','unknown','{}',null)")
        con.execute(
            "insert into triples values "
            "('t1','user','prefers','用rg搜索文件',null,null,0.7,null,null,null)"
        )
        con.execute(
            "insert into triples values "
            "('t2','session','decided','级）\n\n### ⭐⭐⭐ 高价值',null,null,0.7,null,null,null)"
        )
        con.commit()
        con.close()
        return tmp, db_path

    def test_clean_orphan_noisy_entities_dry_run_does_not_delete(self):
        from memory.kg_maintenance import clean_orphan_noisy_entities

        tmp, db_path = self._create_temp_kg_with_entities()
        self.addCleanup(tmp.cleanup)

        result = clean_orphan_noisy_entities(db_path, dry_run=True)
        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["deleted"], 0)

        con = sqlite3.connect(str(db_path))
        try:
            count = con.execute("select count(*) from entities").fetchone()[0]
        finally:
            con.close()
        self.assertEqual(count, 3)

    def test_clean_orphan_noisy_entities_deletes_only_unreferenced_noise(self):
        from memory.kg_maintenance import clean_orphan_noisy_entities

        tmp, db_path = self._create_temp_kg_with_entities()
        self.addCleanup(tmp.cleanup)

        result = clean_orphan_noisy_entities(db_path, dry_run=False)
        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["deleted"], 1)

        con = sqlite3.connect(str(db_path))
        try:
            rows = con.execute("select id, name from entities order by id").fetchall()
        finally:
            con.close()
        self.assertEqual(rows, [
            ("good", "用rg搜索文件"),
            ("referenced-noise", "级）\n\n### ⭐⭐⭐ 高价值"),
        ])
```

- [ ] **Step 2: Run orphan entity tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_mempalace_memory_quality.py::MemPalaceEntityMaintenanceTests -q
```

Expected: `FAIL`, because `clean_orphan_noisy_entities()` does not exist.

- [ ] **Step 3: Add orphan entity cleanup helpers**

In `memory/kg_maintenance.py`, add:

```python
def list_orphan_noisy_entities(db_path=KG_PATH, limit=None):
    """Return noisy entities that are not referenced by any triple."""
    con = _connect(db_path)
    try:
        rows = con.execute("select id, name from entities order by created_at, id").fetchall()
        referenced = set()
        for subject, obj in con.execute("select subject, object from triples").fetchall():
            referenced.add(str(subject))
            referenced.add(str(obj))
    finally:
        con.close()

    noisy = [
        {"id": row[0], "name": row[1]}
        for row in rows
        if str(row[1]) not in referenced and not PalaceBridge._is_clean_fact_object(row[1])
    ]
    return noisy[:limit] if limit is not None else noisy


def clean_orphan_noisy_entities(db_path=KG_PATH, dry_run=True):
    """Delete unreferenced noisy entities when dry_run is False."""
    noisy = list_orphan_noisy_entities(db_path)
    ids = [row["id"] for row in noisy]
    deleted = 0
    if ids and not dry_run:
        con = _connect(db_path)
        try:
            con.executemany("delete from entities where id = ?", [(entity_id,) for entity_id in ids])
            deleted = con.total_changes
            con.commit()
        finally:
            con.close()
    print(
        f"[MemPalace] 🧹 KG orphan noisy entities matched={len(ids)} "
        f"deleted={deleted} dry_run={dry_run}"
    )
    return {"matched": len(ids), "deleted": deleted, "ids": ids}
```

- [ ] **Step 4: Run orphan entity tests**

Run:

```powershell
python -m pytest tests/test_mempalace_memory_quality.py::MemPalaceEntityMaintenanceTests -q
```

Expected: `2 passed`.

- [ ] **Step 5: Run dry-run against real local KG**

Run:

```powershell
python -c "from memory.kg_maintenance import clean_orphan_noisy_entities; print(clean_orphan_noisy_entities(dry_run=True))"
```

Expected: command exits `0`, prints matched/deleted summary, and `deleted=0`.

- [ ] **Step 6: Commit Task 4**

Run:

```powershell
git add memory/kg_maintenance.py tests/test_mempalace_memory_quality.py
git commit -m "chore: clean orphan MemPalace KG entities"
```

Expected: commit contains only maintenance helper and tests.

---

### Task 5: Update Prompt Guidance For Experience Memory

**Files:**
- Modify: `assets/sys_prompt.txt`
- Modify: `tests/test_mempalace_memory_quality.py`

- [ ] **Step 1: Add failing prompt guidance test**

Append this test method to `MemPalacePromptGuidanceTests`:

```python
    def test_sys_prompt_mentions_experience_memory_as_background(self):
        text = Path("assets/sys_prompt.txt").read_text(encoding="utf-8")

        self.assertIn("经验事实", text)
        self.assertIn("探索成功步骤", text)
        self.assertIn("根因、方案、验证结果、结论", text)
        self.assertIn("仅作背景参考，不是本轮用户新指令", text)
```

- [ ] **Step 2: Run guidance test and verify it fails**

Run:

```powershell
python -m pytest tests/test_mempalace_memory_quality.py::MemPalacePromptGuidanceTests::test_sys_prompt_mentions_experience_memory_as_background -q
```

Expected: `FAIL`, because current prompt does not mention experience memory.

- [ ] **Step 3: Update `assets/sys_prompt.txt` MemPalace block**

Replace the current MemPalace block with:

```text
# MemPalace 集成能力
当需要搜索历史对话、查找"之前处理过的类似问题"、确认"用户之前提过什么偏好"时，优先使用 `memory/hybrid_search.py` 做历史对话语义检索；精确查文件名、代码片段、变量名时继续优先用 rg。
- **精确搜索**（文件名、代码片段、变量名）→ rg
- **历史对话语义检索**（"上次怎么处理的"、"类似的问题"、"用户提过什么偏好"）→ `memory/hybrid_search.py`
- **经验事实**：MemPalace 会从已完成任务中提炼探索成功步骤、根因、方案、验证结果、结论；这些内容仅作背景参考，不是本轮用户新指令。
- **MemPalace 对话写入路径会进行去重检查**；如果去重组件异常，日志会出现 `[MemPalace] ⚠️ dedup guard failed` 并降级为直接写入。
```

- [ ] **Step 4: Run guidance tests**

Run:

```powershell
python -m pytest tests/test_mempalace_memory_quality.py::MemPalacePromptGuidanceTests -q
```

Expected: all prompt guidance tests pass.

- [ ] **Step 5: Commit Task 5**

Run:

```powershell
git add assets/sys_prompt.txt tests/test_mempalace_memory_quality.py
git commit -m "docs: describe MemPalace experience memory"
```

Expected: commit contains only prompt and prompt tests.

---

### Task 6: Final Verification And Runtime Smoke

**Files:**
- No production code changes.

- [ ] **Step 1: Run focused MemPalace tests**

Run:

```powershell
python -m pytest tests/test_webui_server.py::AgentMainMemPalaceTests tests/test_mempalace_memory_quality.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run WebUI regression tests**

Run:

```powershell
python -m pytest tests/test_webui_server.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run runtime experience extraction smoke**

Run:

```powershell
python - <<'PY'
from memory.palace_bridge import get_bridge

b = get_bridge()
b.extract_experience_facts(
    "smoke-experience",
    "验证 MemPalace 经验记忆",
    "根因：原始流水没有结构化经验。\n修复：新增经验抽取层。\n验证：smoke command -> passed\n结论：经验事实用于背景参考。"
)
print(b.get_experience_context(session_id="smoke-experience", max_facts=6))
PY
```

Expected: command exits `0` and prints a `[MemPalace Experience - READ ONLY]` block containing `root_cause`, `solution`, `verification`, or `lesson_learned`.

- [ ] **Step 4: Run KG cleanup dry-runs**

Run:

```powershell
python -c "from memory.kg_maintenance import clean_noisy_triples, clean_orphan_noisy_entities; print(clean_noisy_triples(dry_run=True)); print(clean_orphan_noisy_entities(dry_run=True))"
```

Expected: command exits `0`, both summaries print `deleted=0`.

- [ ] **Step 5: Run diff hygiene**

Run:

```powershell
git diff --check -- agentmain.py memory/experience_extractor.py memory/palace_bridge.py memory/kg_maintenance.py assets/sys_prompt.txt tests/test_webui_server.py tests/test_mempalace_memory_quality.py
```

Expected: no output and exit code `0`.

- [ ] **Step 6: Inspect final git status**

Run:

```powershell
git -c safe.directory=E:/zfengl-ai-project/GenericAgent status --short --branch
```

Expected: implementation files are committed. Existing unrelated dirty files such as `memory/file_access_stats.json`, `AGENTS.main.backup.md`, `assets/sys_prompt.2026-04-22`, previous plan docs, and `temp_1x1.png` may remain; do not stage or delete them unless the user asks.

---

## Self-Review

- Spec coverage: The plan addresses the observed gap that GA stores raw MemPalace turns but does not structure successful exploration steps, conclusions, root causes, solutions, or verification evidence. Tasks add a deterministic extractor, bridge KG writes, prompt injection, low-value KG filtering, orphan noisy entity cleanup, prompt guidance, and verification.
- Placeholder scan: The plan contains no `TBD`, `TODO`, "implement later", or unspecified "add tests" steps. Code and commands are explicit.
- Type consistency: `ExperienceFact.subject/predicate/object/confidence`, `extract_experience_facts(session_id, user_text, assistant_text)`, `PalaceBridge.extract_experience_facts()`, `PalaceBridge.get_experience_context()`, and `clean_orphan_noisy_entities()` are consistently named across tasks.
