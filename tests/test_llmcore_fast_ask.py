import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import llmcore


class FastAskTests(unittest.TestCase):
    def make_native_claude_session(self):
        return llmcore.NativeClaudeSession(
            {
                "apikey": "sk-test",
                "apibase": "https://example.invalid/v1",
                "model": "claude-test",
                "stream": False,
            }
        )

    def test_fast_ask_accepts_plain_prompt_for_native_claude_sessions(self):
        session = self.make_native_claude_session()
        captured = {}

        def fake_stream_with_retry(sess, url, headers, payload, parse_fn):
            captured["payload"] = payload
            yield "新的标题"
            return [{"type": "text", "text": "新的标题"}]

        stdout = io.StringIO()
        with redirect_stdout(stdout), patch.object(llmcore, "resolve_session", return_value=session), patch.object(
            llmcore, "_stream_with_retry", new=fake_stream_with_retry
        ):
            result = llmcore.fast_ask("请生成一个标题", "native_claude_config")

        self.assertEqual(result, "新的标题")
        self.assertNotIn("No tools provided for this session", stdout.getvalue())
        payload = captured["payload"]
        self.assertNotIn("tools", payload)
        self.assertEqual(payload["messages"][0]["role"], "user")
        self.assertEqual(payload["messages"][0]["content"][0]["text"], "请生成一个标题")
        self.assertEqual(
            payload["messages"][0]["content"][0]["cache_control"],
            {"type": "ephemeral"},
        )


if __name__ == "__main__":
    unittest.main()
