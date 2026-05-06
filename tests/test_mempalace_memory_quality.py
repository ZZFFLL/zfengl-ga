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
