import json
import tempfile
import time
import unittest
from pathlib import Path

from reflect import goal_mode


class GoalModeTests(unittest.TestCase):
    def test_default_max_turns_is_100(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "goal_state.json"
            state_file.write_text(
                json.dumps(
                    {
                        "status": "running",
                        "objective": "keep going",
                        "start_time": time.time(),
                        "budget_seconds": 3600,
                        "turns_used": 99,
                    }
                ),
                encoding="utf-8",
            )
            goal_mode.init({"goal_state": str(state_file)})

            prompt = goal_mode.check()
            state = json.loads(state_file.read_text(encoding="utf-8"))

            self.assertIn("第 100 次唤醒", prompt)
            self.assertEqual(state["status"], "running")
            self.assertEqual(state["turns_used"], 100)


if __name__ == "__main__":
    unittest.main()
