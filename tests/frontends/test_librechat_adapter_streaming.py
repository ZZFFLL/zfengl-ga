import unittest


class StreamingTestCase(unittest.TestCase):
    def streaming_module(self):
        try:
            from frontends.librechat_adapter import streaming
        except ImportError as exc:
            self.fail(f"streaming module should be importable: {exc}")
        return streaming

    def test_consume_snapshot_returns_only_new_suffix(self):
        streaming = self.streaming_module()
        tracker = streaming.DeltaTracker()

        self.assertEqual(tracker.consume_snapshot("hel"), "hel")
        self.assertEqual(tracker.consume_snapshot("hello"), "lo")
        self.assertFalse(tracker.regressed)

    def test_repeated_snapshot_returns_empty_delta(self):
        streaming = self.streaming_module()
        tracker = streaming.DeltaTracker()

        self.assertEqual(tracker.consume_snapshot("hello"), "hello")
        self.assertEqual(tracker.consume_snapshot("hello"), "")
        self.assertFalse(tracker.regressed)

    def test_regressed_snapshot_does_not_repeat_old_text(self):
        streaming = self.streaming_module()
        tracker = streaming.DeltaTracker()

        self.assertEqual(tracker.consume_snapshot("hello world"), "hello world")
        self.assertEqual(tracker.consume_snapshot("hello"), "")
        self.assertTrue(tracker.regressed)
        self.assertEqual(tracker.consume_snapshot("hello again"), " again")


if __name__ == "__main__":
    unittest.main()
