import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class FakeSearchBridge:
    def __init__(self, score):
        self.score = score
        self.queries = []

    def search(self, text, n_results=1, session_id=None):
        self.queries.append((text, n_results, session_id))
        if self.score is None:
            return []
        return [{"score": self.score, "text": "existing", "metadata": {"session_id": session_id}}]


class FakeResultBridge:
    def __init__(self, result):
        self.result = result
        self.queries = []

    def search(self, text, n_results=1, session_id=None):
        self.queries.append((text, n_results, session_id))
        return [self.result]


class MemPalaceDedupTests(unittest.TestCase):
    def test_guard_write_accepts_injected_bridge_and_blocks_duplicate(self):
        from memory.dedup import guard_write

        stored = []
        bridge = FakeSearchBridge(score=0.99)

        result = guard_write(
            "用户重复说了一段足够长的话，用来触发相似度检查",
            lambda: stored.append("stored") or "doc-id",
            threshold=0.85,
            session_id="session-a",
            bridge=bridge,
        )

        self.assertIsNone(result)
        self.assertEqual(stored, [])
        self.assertEqual(bridge.queries[0][2], "session-a")

    def test_guard_write_allows_unique_text(self):
        from memory.dedup import guard_write

        stored = []
        bridge = FakeSearchBridge(score=0.2)

        result = guard_write(
            "这是一段足够长的新内容，应当被写入 MemPalace",
            lambda: stored.append("stored") or "doc-id",
            threshold=0.85,
            session_id="session-b",
            bridge=bridge,
        )

        self.assertEqual(result, "doc-id")
        self.assertEqual(stored, ["stored"])

    def test_guard_write_does_not_query_for_short_text(self):
        from memory.dedup import guard_write

        stored = []
        bridge = FakeSearchBridge(score=0.99)

        result = guard_write(
            "短句",
            lambda: stored.append("stored") or "doc-id",
            threshold=0.85,
            session_id="session-c",
            bridge=bridge,
        )

        self.assertEqual(result, "doc-id")
        self.assertEqual(stored, ["stored"])
        self.assertEqual(bridge.queries, [])

    def test_guard_write_allows_none_without_querying(self):
        from memory.dedup import guard_write

        stored = []
        bridge = FakeSearchBridge(score=0.99)

        result = guard_write(
            None,
            lambda: stored.append("stored") or "doc-id",
            threshold=0.85,
            session_id="session-d",
            bridge=bridge,
        )

        self.assertEqual(result, "doc-id")
        self.assertEqual(stored, ["stored"])
        self.assertEqual(bridge.queries, [])

    def test_guard_write_allows_malformed_search_result(self):
        from memory.dedup import guard_write

        malformed_results = [
            "bad row",
            {"score": None},
            {"score": "not-a-number"},
            {"score": float("nan")},
        ]

        for result_row in malformed_results:
            with self.subTest(result=result_row):
                stored = []
                bridge = FakeResultBridge(result_row)

                result = guard_write(
                    "这是一段足够长的文本，用来触发搜索但允许坏结果",
                    lambda: stored.append("stored") or "doc-id",
                    threshold=0.85,
                    session_id="session-e",
                    bridge=bridge,
                )

                self.assertEqual(result, "doc-id")
                self.assertEqual(stored, ["stored"])


class MemPalaceFactQualityTests(unittest.TestCase):
    def test_fact_object_quality_gate_rejects_markdown_noise(self):
        from memory.palace_bridge import PalaceBridge

        self.assertFalse(PalaceBridge._is_clean_fact_object("级）\n\n### ⭐⭐⭐ 高价值\n\n#### 1."))
        self.assertFalse(PalaceBridge._is_clean_fact_object("人/项目 | entity_detector.py | 无 |"))
        self.assertFalse(PalaceBridge._is_clean_fact_object("<file_content>secret</file_content>"))
        self.assertTrue(PalaceBridge._is_clean_fact_object("用rg搜索文件"))

    def test_extract_conversation_facts_does_not_store_noisy_user_preference(self):
        from memory.palace_bridge import PalaceBridge

        bridge = PalaceBridge(palace_path="unused", kg_path="unused")
        captured = []
        bridge.add_fact = lambda subject, predicate, obj, **kwargs: captured.append((subject, predicate, obj))

        bridge.extract_conversation_facts(
            "session-noise",
            "这个表格里写了优先级 | 模块 | 说明 |，不是用户偏好。",
            "assistant response",
        )

        self.assertNotIn(("user", "prefers", "级 | 模块 | 说明"), captured)
        self.assertNotIn(("user", "prefers", "| 模块 | 说明 |，不是用户偏好。"), captured)


class MemPalaceKGMaintenanceTests(unittest.TestCase):
    def _create_temp_kg(self):
        tmp = tempfile.TemporaryDirectory()
        db_path = Path(tmp.name) / "kg.sqlite3"
        con = sqlite3.connect(str(db_path))
        con.execute(
            "create table triples ("
            "id text primary key, subject text, predicate text, object text, "
            "valid_from text, valid_to text, confidence real, source_closet text, "
            "source_file text, extracted_at text)"
        )
        con.execute(
            "insert into triples values "
            "('bad-1','user','prefers','级）\n\n### ⭐⭐⭐ 高价值\n\n#### 1.',null,null,0.7,null,null,null)"
        )
        con.execute(
            "insert into triples values "
            "('bad-2','user','dislikes','人/项目 | entity_detector.py | 无 |',null,null,0.7,null,null,null)"
        )
        con.execute(
            "insert into triples values "
            "('good-1','user','prefers','用rg搜索文件',null,null,0.7,null,null,null)"
        )
        con.commit()
        con.close()
        return tmp, db_path

    def test_clean_noisy_triples_dry_run_does_not_delete(self):
        from memory.kg_maintenance import clean_noisy_triples

        tmp, db_path = self._create_temp_kg()
        self.addCleanup(tmp.cleanup)

        result = clean_noisy_triples(db_path, dry_run=True)
        self.assertEqual(result["matched"], 2)
        self.assertEqual(result["deleted"], 0)

        con = sqlite3.connect(str(db_path))
        try:
            count = con.execute("select count(*) from triples").fetchone()[0]
        finally:
            con.close()
        self.assertEqual(count, 3)

    def test_list_noisy_triples_respects_zero_limit(self):
        from memory.kg_maintenance import list_noisy_triples

        tmp, db_path = self._create_temp_kg()
        self.addCleanup(tmp.cleanup)

        self.assertEqual(list_noisy_triples(db_path, limit=0), [])

    def test_clean_noisy_triples_deletes_only_noisy_rows(self):
        from memory.kg_maintenance import clean_noisy_triples

        tmp, db_path = self._create_temp_kg()
        self.addCleanup(tmp.cleanup)

        result = clean_noisy_triples(db_path, dry_run=False)
        self.assertEqual(result["matched"], 2)
        self.assertEqual(result["deleted"], 2)

        con = sqlite3.connect(str(db_path))
        try:
            rows = con.execute("select id, object from triples order by id").fetchall()
        finally:
            con.close()
        self.assertEqual(rows, [("good-1", "用rg搜索文件")])


class MemPalacePromptGuidanceTests(unittest.TestCase):
    def test_sys_prompt_describes_actual_mempalace_behavior(self):
        text = Path("assets/sys_prompt.txt").read_text(encoding="utf-8")

        self.assertIn("MemPalace 集成能力", text)
        self.assertIn("历史对话语义检索", text)
        self.assertIn("MemPalace 对话写入路径会进行去重检查", text)
        self.assertNotIn("dedup 模块会自动拦截重复内容", text)


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
