import unittest
from types import SimpleNamespace

import agentmain
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

    def test_normal_mode_soft_reviews_at_120_and_asks_user_from_180(self):
        handler = self.make_handler()

        prompt_70 = self.callback_prompt(handler, 70)
        prompt_120 = self.callback_prompt(handler, 120)
        prompt_121 = self.callback_prompt(handler, 121)
        prompt_180 = self.callback_prompt(handler, 180)
        prompt_181 = self.callback_prompt(handler, 181)

        self.assertNotIn("必须总结情况进行ask_user", prompt_70)
        self.assertIn("已连续执行第 120 轮", prompt_120)
        self.assertIn("不要仅因为轮次达到该值就停止", prompt_120)
        self.assertNotIn("必须总结情况进行ask_user", prompt_120)
        self.assertNotIn("必须总结情况进行ask_user", prompt_121)
        self.assertIn("已连续执行第 180 轮", prompt_180)
        self.assertIn("必须总结情况进行ask_user", prompt_180)
        self.assertNotIn("必须总结情况进行ask_user", prompt_181)

    def test_normal_mode_max_turns_is_240(self):
        self.assertEqual(agentmain.NORMAL_RUNNER_MAX_TURNS, 240)

    def test_normal_mode_checkpoint_every_30_turns(self):
        handler = self.make_handler()

        prompt = self.callback_prompt(handler, 30)

        self.assertIn("update_working_checkpoint", prompt)
        self.assertIn("用户补充的关键约束", prompt)
        self.assertIn("已验证结论", prompt)

    def test_normal_mode_stall_warning_and_global_memory_refresh_every_30_turns(self):
        handler = self.make_handler()

        prompt_20 = self.callback_prompt(handler, 20)
        prompt_30 = self.callback_prompt(handler, 30)

        self.assertNotIn("[Memory]", prompt_20)
        self.assertNotIn("禁止无效重试", prompt_20)
        self.assertIn("[Memory]", prompt_30)
        self.assertIn("防止无效重试", prompt_30)

    def test_plan_mode_soft_reviews_at_180_and_asks_user_from_270(self):
        handler = self.make_handler()
        handler.enter_plan_mode("./temp/plan.md")

        prompt_100 = self.callback_prompt(handler, 100, plan=True)
        prompt_180 = self.callback_prompt(handler, 180, plan=True)
        prompt_181 = self.callback_prompt(handler, 181, plan=True)
        prompt_270 = self.callback_prompt(handler, 270, plan=True)
        prompt_271 = self.callback_prompt(handler, 271, plan=True)

        self.assertEqual(handler.max_turns, 480)
        self.assertNotIn("必须 ask_user 汇报进度并确认是否继续", prompt_100)
        self.assertIn("Plan模式已运行 180 轮", prompt_180)
        self.assertIn("不要仅因为轮次达到该值就停止", prompt_180)
        self.assertNotIn("必须 ask_user 汇报进度并确认是否继续", prompt_180)
        self.assertNotIn("必须 ask_user 汇报进度并确认是否继续", prompt_181)
        self.assertIn("Plan模式已运行 270 轮", prompt_270)
        self.assertIn("必须 ask_user 汇报进度并确认是否继续", prompt_270)
        self.assertNotIn("必须 ask_user 汇报进度并确认是否继续", prompt_271)

    def test_plan_mode_stall_warning_every_60_turns(self):
        handler = self.make_handler()
        handler.enter_plan_mode("./temp/plan.md")

        prompt_30 = self.callback_prompt(handler, 30, plan=True)
        prompt_60 = self.callback_prompt(handler, 60, plan=True)

        self.assertNotIn("防止计划空转", prompt_30)
        self.assertIn("防止计划空转", prompt_60)

    def test_plan_mode_checkpoint_every_30_turns(self):
        handler = self.make_handler()
        handler.enter_plan_mode("./temp/plan.md")

        prompt = self.callback_prompt(handler, 30, plan=True)

        self.assertIn("update_working_checkpoint", prompt)
        self.assertIn("计划文件之外的用户关键约束", prompt)
        self.assertIn("已验证执行状态", prompt)

    def test_normal_working_memory_keeps_latest_80_lines_directly(self):
        history = [f"[Agent] step {i}" for i in range(90)]
        handler = GenericAgentHandler(SimpleNamespace(verbose=False, task_dir=None), history, "./temp")
        handler.current_turn = 1

        prompt = handler._get_anchor_prompt()

        self.assertIn("[Agent] step 10", prompt)
        self.assertIn("[Agent] step 89", prompt)
        self.assertIn("<earlier_context>", prompt)
        self.assertNotIn("[Agent] step 9\n[Agent] step 10", prompt)

    def test_plan_working_memory_keeps_latest_120_lines_directly(self):
        history = [f"[Agent] step {i}" for i in range(130)]
        handler = GenericAgentHandler(SimpleNamespace(verbose=False, task_dir=None), history, "./temp")
        handler.current_turn = 1
        handler.working["in_plan_mode"] = "./temp/plan.md"

        prompt = handler._get_anchor_prompt()

        self.assertIn("[Agent] step 10", prompt)
        self.assertIn("[Agent] step 129", prompt)
        self.assertIn("<earlier_context>", prompt)
        self.assertNotIn("[Agent] step 9\n[Agent] step 10", prompt)


if __name__ == "__main__":
    unittest.main()
