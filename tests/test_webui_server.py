import queue
import unittest

from frontends.webui_server import (
    WebUITaskManager,
    build_state,
    parse_execution_log,
    strip_summary_blocks,
)


class FakeBackend:
    def __init__(self):
        self.history = ["existing"]


class FakeClient:
    def __init__(self, name):
        self.backend = FakeBackend()
        self.last_tools = "cached"
        self.name = name


class FakeAgent:
    def __init__(self):
        self.llm_no = 0
        self.llmclients = [FakeClient("primary"), FakeClient("backup")]
        self.llmclient = self.llmclients[0]
        self.history = ["old"]
        self.handler = object()
        self.is_running = False
        self.aborted = False
        self.tasks = []

    def list_llms(self):
        return [
            (i, f"Fake/{client.name}", i == self.llm_no)
            for i, client in enumerate(self.llmclients)
        ]

    def get_llm_name(self):
        return f"Fake/{self.llmclients[self.llm_no].name}"

    def next_llm(self, n=-1):
        self.llm_no = ((self.llm_no + 1) if n < 0 else n) % len(self.llmclients)
        self.llmclient = self.llmclients[self.llm_no]
        self.llmclient.last_tools = ""

    def abort(self):
        self.aborted = True
        self.is_running = False

    def put_task(self, query, source="user", images=None):
        output = queue.Queue()
        self.tasks.append((query, source, images or [], output))
        return output


class WebUILogParserTests(unittest.TestCase):
    def test_parse_execution_log_returns_summary_only(self):
        text = (
            "Opening answer\n\n"
            "**LLM Running (Turn 1) ...**\n"
            "<summary>\nInspect files\nThen decide\n</summary>\n"
            "Tool output\n\n"
            "**LLM Running (Turn 2) ...**\n"
            "No summary here"
        )

        turns = parse_execution_log(text)

        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]["turn"], 1)
        self.assertEqual(turns[0]["title"], "Inspect files")
        self.assertEqual(turns[0]["content"], "Inspect files\nThen decide")
        self.assertEqual(turns[1]["turn"], 2)
        self.assertEqual(turns[1]["title"], "LLM Running (Turn 2)")
        self.assertEqual(turns[1]["content"], "")

    def test_strip_summary_blocks_keeps_non_summary_content(self):
        text = (
            "Before\n"
            "<summary>\nHidden planning\n</summary>\n"
            "After\n"
            "<summary>Second hidden</summary>\n"
            "Done"
        )

        cleaned = strip_summary_blocks(text)

        self.assertIn("Before", cleaned)
        self.assertIn("After", cleaned)
        self.assertIn("Done", cleaned)
        self.assertNotIn("Hidden planning", cleaned)
        self.assertNotIn("<summary>", cleaned)


class WebUITaskManagerTests(unittest.TestCase):
    def test_start_chat_creates_running_task_and_streams_to_done(self):
        agent = FakeAgent()
        manager = WebUITaskManager(agent)

        task = manager.start_chat("hello")
        task_id = task["task_id"]
        self.assertEqual(agent.tasks[0][0], "hello")
        self.assertEqual(agent.tasks[0][1], "user")
        self.assertEqual(manager.tasks[task_id].status, "running")

        output = agent.tasks[0][3]
        output.put(
            {
                "next": (
                    "**LLM Running (Turn 1) ...**\n"
                    "<summary>\nPlan the response\n</summary>\n"
                    "partial"
                ),
                "source": "user",
            }
        )
        output.put(
            {
                "done": (
                    "**LLM Running (Turn 1) ...**\n"
                    "<summary>\nPlan the response\n</summary>\n"
                    "final"
                ),
                "source": "user",
            }
        )

        events = list(manager.drain_task(task_id, timeout=0.01))

        self.assertEqual(events[0]["event"], "next")
        self.assertNotIn("<summary>", events[0]["content"])
        self.assertNotIn("Plan the response", events[0]["content"])
        self.assertIn("partial", events[0]["content"])
        self.assertEqual(events[0]["execution_log"][0]["content"], "Plan the response")
        self.assertEqual(events[1]["event"], "done")
        self.assertNotIn("<summary>", events[1]["content"])
        self.assertNotIn("Plan the response", events[1]["content"])
        self.assertIn("final", events[1]["content"])
        self.assertEqual(manager.tasks[task_id].status, "done")
        self.assertGreater(manager.last_reply_time, 0)

    def test_build_state_reports_runtime_state(self):
        agent = FakeAgent()
        manager = WebUITaskManager(agent)
        manager.autonomous_enabled = True
        manager.last_reply_time = 123

        state = build_state(agent, manager)

        self.assertTrue(state["configured"])
        self.assertEqual(state["current_llm"]["index"], 0)
        self.assertEqual(state["current_llm"]["name"], "Fake/primary")
        self.assertEqual(len(state["llms"]), 2)
        self.assertTrue(state["autonomous_enabled"])
        self.assertEqual(state["last_reply_time"], 123)

    def test_controls_delegate_to_agent(self):
        agent = FakeAgent()
        manager = WebUITaskManager(agent)

        manager.switch_llm(1)
        self.assertEqual(agent.llm_no, 1)

        manager.abort()
        self.assertTrue(agent.aborted)

        manager.reinject()
        self.assertEqual(agent.llmclient.last_tools, "")

        manager.set_autonomous(True)
        self.assertTrue(manager.autonomous_enabled)

    def test_reset_conversation_clears_visible_state(self):
        agent = FakeAgent()
        manager = WebUITaskManager(agent)
        result = manager.reset_conversation()

        self.assertIn("new conversation", result["message"].lower())
        self.assertEqual(agent.history, [])
        self.assertIsNone(agent.handler)
        self.assertEqual(agent.llmclients[0].backend.history, [])
        self.assertEqual(agent.llmclients[0].last_tools, "")


if __name__ == "__main__":
    unittest.main()
