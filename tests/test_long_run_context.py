import unittest
from types import SimpleNamespace

from ga import GenericAgentHandler


class LongRunContextTests(unittest.TestCase):
    def make_handler(self):
        parent = SimpleNamespace(verbose=False, task_dir=None)
        return GenericAgentHandler(parent, [], "./temp")

    def make_response(self, summary="继续执行"):
        return SimpleNamespace(content=f"<summary>{summary}</summary>")

    def callback_prompt(self, handler, turn, plan=False):
        if plan:
            handler.working["in_plan_mode"] = "./temp/plan.md"
        return handler.turn_end_callback(
            self.make_response(),
            [{"tool_name": "no_tool", "args": {}}],
            [],
            turn,
            "NEXT",
            {},
        )

    def test_normal_mode_long_run_ask_user_pressure_moves_to_turn_70(self):
        handler = self.make_handler()

        prompt_65 = self.callback_prompt(handler, 65)
        prompt_70 = self.callback_prompt(handler, 70)

        self.assertNotIn("必须总结情况进行ask_user", prompt_65)
        self.assertIn("已连续执行第 70 轮", prompt_70)
        self.assertIn("必须总结情况进行ask_user", prompt_70)

    def test_normal_mode_checkpoint_every_25_turns(self):
        handler = self.make_handler()

        prompt = self.callback_prompt(handler, 25)

        self.assertIn("update_working_checkpoint", prompt)
        self.assertIn("用户补充的关键约束", prompt)
        self.assertIn("已验证结论", prompt)

    def test_plan_mode_max_turns_and_ask_user_pressure_move_up(self):
        handler = self.make_handler()
        handler.enter_plan_mode("./temp/plan.md")

        prompt_90 = self.callback_prompt(handler, 90, plan=True)
        prompt_100 = self.callback_prompt(handler, 100, plan=True)

        self.assertEqual(handler.max_turns, 200)
        self.assertNotIn("Plan模式已运行 90 轮，已达上限", prompt_90)
        self.assertIn("Plan模式已运行 100 轮", prompt_100)
        self.assertIn("必须 ask_user 汇报进度并确认是否继续", prompt_100)

    def test_plan_mode_checkpoint_every_35_turns(self):
        handler = self.make_handler()
        handler.enter_plan_mode("./temp/plan.md")

        prompt = self.callback_prompt(handler, 35, plan=True)

        self.assertIn("update_working_checkpoint", prompt)
        self.assertIn("计划文件之外的用户关键约束", prompt)
        self.assertIn("已验证执行状态", prompt)

    def test_working_memory_keeps_latest_60_lines_directly(self):
        history = [f"[Agent] step {i}" for i in range(70)]
        handler = GenericAgentHandler(SimpleNamespace(verbose=False, task_dir=None), history, "./temp")
        handler.current_turn = 1

        prompt = handler._get_anchor_prompt()

        self.assertIn("[Agent] step 10", prompt)
        self.assertIn("[Agent] step 69", prompt)
        self.assertIn("<earlier_context>", prompt)
        self.assertNotIn("[Agent] step 9\n[Agent] step 10", prompt)


if __name__ == "__main__":
    unittest.main()
