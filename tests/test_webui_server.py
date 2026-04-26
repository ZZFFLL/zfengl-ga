import queue
import unittest

from frontends.webui_server import WebUITaskManager, build_state, parse_execution_log


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
        self.pet_requests = []
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
    def test_parse_execution_log_uses_summary_first_line_as_title(self):
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
        self.assertIn("Tool output", turns[0]["content"])
        self.assertEqual(turns[1]["turn"], 2)
        self.assertEqual(turns[1]["title"], "LLM Running (Turn 2)")
        self.assertIn("No summary here", turns[1]["content"])


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
        output.put({"next": "partial", "source": "user"})
        output.put({"done": "final", "source": "user"})

        events = list(manager.drain_task(task_id, timeout=0.01))

        self.assertEqual(events[0]["event"], "next")
        self.assertEqual(events[0]["content"], "partial")
        self.assertEqual(events[1]["event"], "done")
        self.assertEqual(events[1]["content"], "final")
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
        agent._pet_req = agent.pet_requests.append

        manager.switch_llm(1)
        self.assertEqual(agent.llm_no, 1)

        manager.abort()
        self.assertTrue(agent.aborted)

        manager.reinject()
        self.assertEqual(agent.llmclient.last_tools, "")

        manager.set_autonomous(True)
        self.assertTrue(manager.autonomous_enabled)

        manager.send_pet_request("state=walk")
        self.assertEqual(agent.pet_requests, ["state=walk"])

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
