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
