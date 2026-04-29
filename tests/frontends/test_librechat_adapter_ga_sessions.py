import hashlib
import json
import unittest
from unittest.mock import patch

from frontends.librechat_adapter.ga_sessions import (
    AdapterSessionNotFound,
    GASessionBridge,
)


class LibreChatAdapterGASessionsTestCase(unittest.TestCase):
    def test_list_sessions_uses_opaque_ids_and_does_not_expose_paths(self):
        path = r"E:\secret\model_responses_123.txt"
        mtime = 1710000000.5
        expected_id = hashlib.sha256((path + str(mtime)).encode("utf-8")).hexdigest()

        with patch(
            "frontends.librechat_adapter.ga_sessions.continue_cmd.list_sessions",
            return_value=[(path, mtime, "hello preview", 2)],
        ):
            sessions = GASessionBridge().list_sessions(limit=1)

        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["id"], expected_id)
        self.assertEqual(sessions[0]["rounds"], 2)
        self.assertEqual(sessions[0]["preview"], "hello preview")
        self.assertNotIn("path", sessions[0])
        self.assertNotIn(path, json.dumps(sessions, ensure_ascii=False))

    def test_read_session_returns_ui_messages_and_cleans_assistant_summaries(self):
        path = r"E:\secret\model_responses_456.txt"
        mtime = 1710000100.0
        session_id = hashlib.sha256((path + str(mtime)).encode("utf-8")).hexdigest()

        with patch(
            "frontends.librechat_adapter.ga_sessions.continue_cmd.list_sessions",
            return_value=[(path, mtime, "hello preview", 1)],
        ), patch(
            "frontends.librechat_adapter.ga_sessions.continue_cmd.extract_ui_messages",
            return_value=[
                {"role": "user", "content": "hello"},
                {
                    "role": "assistant",
                    "content": "Visible\n\n<summary>hidden chain</summary>\n\nDone",
                },
            ],
        ):
            payload = GASessionBridge().read_session(session_id)

        self.assertEqual(payload["id"], session_id)
        self.assertEqual(payload["object"], "ga.session")
        self.assertEqual(payload["rounds"], 1)
        self.assertEqual(payload["messages"][0]["content"], "hello")
        self.assertEqual(payload["messages"][1]["content"], "Visible\n\nDone")
        self.assertNotIn("path", payload)
        self.assertNotIn(path, json.dumps(payload, ensure_ascii=False))
        self.assertNotIn("<summary>", payload["messages"][1]["content"])
        self.assertNotIn("hidden chain", payload["messages"][1]["content"])

    def test_read_session_raises_not_found_for_unknown_opaque_id(self):
        with patch(
            "frontends.librechat_adapter.ga_sessions.continue_cmd.list_sessions",
            return_value=[(r"E:\secret\model_responses_789.txt", 1710000200.0, "preview", 1)],
        ):
            with self.assertRaises(AdapterSessionNotFound):
                GASessionBridge().read_session("missing")


if __name__ == "__main__":
    unittest.main()
