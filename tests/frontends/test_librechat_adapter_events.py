import unittest

from frontends.librechat_adapter.events import (
    GAProcessEvent,
    parse_process_events,
    render_process_markdown,
    strip_summary_blocks,
)


class LibreChatAdapterEventsTestCase(unittest.TestCase):
    def test_strip_summary_blocks_removes_hidden_summaries_and_compacts_blanks(self):
        text = (
            "Visible before\n\n"
            "<summary>\nsecret chain\n\nmore hidden text\n</summary>\n\n\n"
            "Visible after\n\n\n"
            "Final line"
        )

        cleaned = strip_summary_blocks(text)

        self.assertEqual(cleaned, "Visible before\n\nVisible after\n\nFinal line")
        self.assertNotIn("secret chain", cleaned)
        self.assertNotIn("<summary>", cleaned)

    def test_strip_summary_blocks_removes_unclosed_summary_tail(self):
        text = "Visible before\n<summary>secret partial"

        cleaned = strip_summary_blocks(text)

        self.assertEqual(cleaned, "Visible before")
        self.assertNotIn("secret partial", cleaned)
        self.assertNotIn("<summary>", cleaned)

    def test_parse_process_events_extracts_turns_and_reasoning_summaries(self):
        text = (
            "**LLM Running (Turn 1) ...**\n\n"
            "<summary>Checked current adapter shape.</summary>\n"
            "Visible answer text.\n\n"
            "LLM Running (Turn 2)\n"
            "<summary>\nCalled one read-only helper.\n</summary>"
        )

        events = parse_process_events(text)

        self.assertEqual(
            events,
            [
                GAProcessEvent(type="turn_start", turn=1),
                GAProcessEvent(
                    type="reasoning_summary",
                    turn=1,
                    summary="Checked current adapter shape.",
                ),
                GAProcessEvent(type="turn_start", turn=2),
                GAProcessEvent(
                    type="reasoning_summary",
                    turn=2,
                    summary="Called one read-only helper.",
                ),
            ],
        )

    def test_render_process_markdown_has_thinking_section_and_truncates_long_summary(self):
        long_summary = "A" * 420
        markdown = render_process_markdown(
            [
                GAProcessEvent(type="turn_start", turn=1),
                GAProcessEvent(
                    type="reasoning_summary",
                    turn=1,
                    summary=long_summary,
                ),
            ]
        )

        self.assertIn("思考过程", markdown)
        self.assertIn("Turn 1", markdown)
        self.assertNotIn(long_summary, markdown)
        self.assertIn("...", markdown)
        self.assertLess(len(markdown), 360)

    def test_render_process_markdown_returns_empty_without_useful_summary(self):
        markdown = render_process_markdown(
            [
                GAProcessEvent(type="turn_start", turn=1),
            ]
        )

        self.assertEqual(markdown, "")


if __name__ == "__main__":
    unittest.main()
