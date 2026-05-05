import os
import queue
import sqlite3
import tempfile
import unittest
from pathlib import Path

from frontends.webui_server import (
    ChatStartRequest,
    GroupMoveRequest,
    SQLiteConversationStore,
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
        self.assertEqual(turns[0]["tool_calls"], [])
        self.assertEqual(turns[1]["turn"], 2)
        self.assertEqual(turns[1]["title"], "LLM Running (Turn 2)")
        self.assertEqual(turns[1]["content"], "")
        self.assertEqual(turns[1]["tool_calls"], [])

    def test_parse_execution_log_extracts_tool_calls_without_final_answer(self):
        text = (
            "**LLM Running (Turn 1) ...**\n"
            "<summary>\n先检查目录内容\n</summary>\n"
            "🛠️ Tool: `code_run`  📥 args:\n"
            "````text\n"
            "{\n"
            '  "script": "ls -la temp/model_responses/ 2>/dev/null | tail -10",\n'
            '  "type": "powershell"\n'
            "}\n"
            "````\n"
            "`````\n"
            "[Action] Running powershell in temp: ls -la temp/model_responses/ 2>/dev/null | tail -10\n"
            "[Status] ❌ Exit Code: 1\n"
            "[Stdout]\n"
            "out-file : 未能找到路径“E:\\dev\\null”的一部分。\n"
            "`````\n\n"
            "你好！请问有什么需要帮忙的吗？"
        )

        turns = parse_execution_log(text)

        self.assertEqual(turns[0]["content"], "先检查目录内容")
        self.assertEqual(len(turns[0]["tool_calls"]), 1)
        self.assertEqual(turns[0]["tool_calls"][0]["tool"], "code_run")
        self.assertIn('"type": "powershell"', turns[0]["tool_calls"][0]["args"])
        self.assertIn("[Status] ❌ Exit Code: 1", turns[0]["tool_calls"][0]["result"])
        self.assertEqual(
            turns[0]["tool_calls"][0]["action"],
            "Running powershell in temp: ls -la temp/model_responses/ 2>/dev/null | tail -10",
        )
        self.assertEqual(turns[0]["tool_calls"][0]["status"], "❌ Exit Code: 1")

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

    def test_strip_summary_blocks_removes_final_info_marker(self):
        text = (
            "最终回答正文\n\n"
            "`````\n"
            "[Info] Final response to user.\n"
            "`````"
        )

        cleaned = strip_summary_blocks(text)

        self.assertEqual(cleaned, "最终回答正文")

    def test_strip_summary_blocks_removes_tool_trace_and_keeps_final_answer(self):
        text = (
            "🛠️ Tool: `code_run`  📥 args:\n"
            "````text\n"
            "{\n"
            '  "script": "ls -la temp/model_responses/ 2>/dev/null | tail -10"\n'
            "}\n"
            "````\n"
            "`````\n"
            "[Action] Running powershell in temp: ls -la temp/model_responses/ 2>/dev/null | tail -10\n"
            "[Status] ❌ Exit Code: 1\n"
            "[Stdout]\n"
            "out-file : 未能找到路径“E:\\dev\\null”的一部分。\n"
            "`````\n\n"
            "你好！请问有什么需要帮忙的吗？"
        )

        cleaned = strip_summary_blocks(text)

        self.assertEqual(cleaned, "你好！请问有什么需要帮忙的吗？")

    def test_strip_summary_blocks_drops_incomplete_streaming_tool_output(self):
        text = (
            "🛠️ Tool: `code_run`  📥 args:\n"
            "````text\n"
            "{\n"
            '  "script": "Start-Sleep -Seconds 5; Write-Host \\"等待完成\\""\n'
            "}\n"
            "````\n"
            "`````\n"
            "[Action] Running powershell in temp: Start-Sleep -Seconds 5; Write-Host \"等待完成\"\n"
        )

        cleaned = strip_summary_blocks(text)

        self.assertEqual(cleaned, "")


class SQLiteConversationStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "webui.sqlite3"
        self.store = SQLiteConversationStore(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_conversation_persists_default_title_and_message(self):
        conversation = self.store.create_conversation(
            initial_user_text="这是一个很长的首条消息标题，需要被裁剪到合适长度以便展示",
        )

        detail = self.store.get_conversation_detail(conversation["id"])
        self.assertEqual(detail["summary"]["id"], conversation["id"])
        self.assertTrue(detail["summary"]["title"].startswith("这是一个很长的首条消息标题"))
        self.assertEqual(detail["messages"], [])

    def test_group_and_pin_operations_update_list_sort(self):
        alpha = self.store.create_conversation(initial_user_text="alpha")
        beta = self.store.create_conversation(initial_user_text="beta")
        group = self.store.create_group("重要分组")

        self.store.pin_conversation(beta["id"], True)
        self.store.move_conversation(beta["id"], GroupMoveRequest(group["id"]))

        conversations = self.store.list_conversations()
        self.assertEqual(conversations[0]["id"], beta["id"])
        self.assertTrue(conversations[0]["pinned"])
        self.assertEqual(conversations[0]["group_id"], group["id"])

    def test_soft_delete_hides_conversation(self):
        conversation = self.store.create_conversation(initial_user_text="to delete")
        self.store.delete_conversation(conversation["id"])

        conversations = self.store.list_conversations()
        self.assertEqual(conversations, [])


class WebUITaskManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "webui.sqlite3"
        self.store = SQLiteConversationStore(self.db_path)
        self.agent = FakeAgent()
        self.manager = WebUITaskManager(self.agent, self.store)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_start_chat_creates_conversation_and_streams_to_done(self):
        conversation = self.store.create_conversation(initial_user_text="旧会话")

        task = self.manager.start_chat(
            ChatStartRequest(
                conversation_id=conversation["id"],
                prompt="hello world",
            )
        )
        task_id = task["task_id"]
        self.assertEqual(self.manager.active_conversation_id, conversation["id"])
        self.assertIn("Current User Message", self.agent.tasks[0][0])
        self.assertIn("hello world", self.agent.tasks[0][0])
        self.assertEqual(self.manager.tasks[task_id].status, "running")

        output = self.agent.tasks[0][3]
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

        events = list(self.manager.drain_task(task_id, timeout=0.01))

        self.assertEqual(events[0]["event"], "message_delta")
        self.assertNotIn("<summary>", events[0]["content"])
        self.assertNotIn("Plan the response", events[0]["content"])
        self.assertIn("partial", events[0]["content"])
        self.assertEqual(events[1]["event"], "execution_update")
        self.assertEqual(events[2]["event"], "message_done")
        self.assertNotIn("<summary>", events[2]["content"])
        self.assertIn("final", events[2]["content"])
        self.assertEqual(self.manager.tasks[task_id].status, "done")
        self.assertGreater(self.manager.last_reply_time, 0)

        detail = self.store.get_conversation_detail(conversation["id"])
        self.assertEqual(len(detail["messages"]), 2)
        self.assertEqual(detail["messages"][0]["role"], "user")
        self.assertEqual(detail["messages"][1]["role"], "assistant")
        self.assertEqual(detail["messages"][1]["content"], "final")
        self.assertEqual(detail["execution_log"][0]["content"], "Plan the response")

    def test_streaming_tool_only_update_does_not_emit_message_delta(self):
        conversation = self.store.create_conversation(initial_user_text="tool only")

        task = self.manager.start_chat(
            ChatStartRequest(
                conversation_id=conversation["id"],
                prompt="hello world",
            )
        )
        task_id = task["task_id"]

        output = self.agent.tasks[0][3]
        output.put(
            {
                "next": (
                    "**LLM Running (Turn 1) ...**\n"
                    "🛠️ Tool: `code_run`  📥 args:\n"
                    "````text\n"
                    '{"script": "Start-Sleep -Seconds 5; Write-Host \\"等待完成\\""}\n'
                    "````\n"
                    "`````\n"
                    "[Action] Running powershell in temp: Start-Sleep -Seconds 5; Write-Host \"等待完成\"\n"
                ),
                "source": "user",
            }
        )
        output.put({"done": "最终答复", "source": "user"})

        events = list(self.manager.drain_task(task_id, timeout=0.01))

        self.assertEqual(events[0]["event"], "execution_update")
        self.assertEqual(events[1]["event"], "message_done")
        self.assertEqual(events[1]["content"], "最终答复")

    def test_streaming_partial_summary_does_not_emit_message_delta(self):
        conversation = self.store.create_conversation(initial_user_text="partial summary")

        task = self.manager.start_chat(
            ChatStartRequest(
                conversation_id=conversation["id"],
                prompt="hello world",
            )
        )
        task_id = task["task_id"]

        output = self.agent.tasks[0][3]
        output.put(
            {
                "next": (
                    "**LLM Running (Turn 1) ...**\n"
                    "<summary>\n用户想让我在chrome浏览器打开B站"
                ),
                "source": "user",
            }
        )
        output.put({"done": "最终答复", "source": "user"})

        events = list(self.manager.drain_task(task_id, timeout=0.01))

        self.assertEqual(events[0]["event"], "execution_update")
        self.assertEqual(events[1]["event"], "message_done")
        self.assertEqual(events[1]["content"], "最终答复")

    def test_switching_conversation_resets_agent_before_next_send(self):
        first = self.store.create_conversation(initial_user_text="first")
        second = self.store.create_conversation(initial_user_text="second")
        self.store.add_message(first["id"], "user", "alpha question", "ui")
        self.store.add_message(first["id"], "assistant", "alpha answer", "ga")
        self.store.add_message(second["id"], "user", "beta question", "ui")
        self.store.add_message(second["id"], "assistant", "beta answer", "ga")

        self.manager.activate_conversation(first["id"])
        self.agent.aborted = False
        self.manager.activate_conversation(second["id"])

        task = self.manager.start_chat(
            ChatStartRequest(
                conversation_id=second["id"],
                prompt="new beta followup",
            )
        )

        self.assertTrue(self.agent.aborted)
        self.assertEqual(self.manager.active_conversation_id, second["id"])
        prompt_text = self.agent.tasks[-1][0]
        self.assertIn("beta question", prompt_text)
        self.assertIn("beta answer", prompt_text)
        self.assertIn("new beta followup", prompt_text)
        self.assertNotIn("alpha question", prompt_text)
        self.assertIsNotNone(task["task_id"])

    def test_build_state_reports_runtime_state_and_active_conversation(self):
        conversation = self.store.create_conversation(initial_user_text="stateful")
        self.manager.activate_conversation(conversation["id"])
        self.manager.autonomous_enabled = True
        self.manager.last_reply_time = 123

        state = build_state(self.agent, self.manager)

        self.assertTrue(state["configured"])
        self.assertEqual(state["current_llm"]["index"], 0)
        self.assertEqual(state["current_llm"]["name"], "Fake/primary")
        self.assertEqual(len(state["llms"]), 2)
        self.assertTrue(state["autonomous_enabled"])
        self.assertEqual(state["last_reply_time"], 123)
        self.assertEqual(state["active_conversation_id"], conversation["id"])
        self.assertEqual(state["execution_log"], [])

    def test_build_state_returns_persisted_execution_log_when_idle(self):
        conversation = self.store.create_conversation(initial_user_text="stateful")
        self.manager.activate_conversation(conversation["id"])
        self.store.add_message(
            conversation["id"],
            "assistant",
            "final",
            "ga",
            execution_log=[{"turn": 1, "title": "Inspect files", "content": "Inspect files"}],
        )

        state = build_state(self.agent, self.manager)

        self.assertEqual(state["execution_log"][0]["title"], "Inspect files")

    def test_conversation_detail_messages_include_execution_log(self):
        conversation = self.store.create_conversation(initial_user_text="stateful")
        execution_log = [
            {"turn": 1, "title": "Inspect files", "content": "Inspect files"},
            {"turn": 2, "title": "Draft reply", "content": "Draft reply"},
        ]
        self.store.add_message(conversation["id"], "user", "hello", "ui")
        self.store.add_message(
            conversation["id"],
            "assistant",
            "final",
            "ga",
            execution_log=execution_log,
        )

        detail = self.manager.get_conversation(conversation["id"])

        self.assertEqual(detail["messages"][0]["execution_log"], [])
        self.assertEqual(detail["messages"][1]["execution_log"], execution_log)
        self.assertEqual(detail["execution_log"], execution_log)

    def test_controls_delegate_to_agent(self):
        self.manager.switch_llm(1)
        self.assertEqual(self.agent.llm_no, 1)

        self.manager.abort()
        self.assertTrue(self.agent.aborted)

        self.manager.reinject()
        self.assertEqual(self.agent.llmclient.last_tools, "")

        self.manager.set_autonomous(True)
        self.assertTrue(self.manager.autonomous_enabled)

    def test_reset_conversation_clears_visible_state_and_creates_new_active_conversation(self):
        self.store.create_conversation(initial_user_text="old")
        result = self.manager.reset_conversation()

        self.assertIn("new conversation", result["message"].lower())
        self.assertEqual(self.agent.history, [])
        self.assertIsNone(self.agent.handler)
        self.assertEqual(self.agent.llmclients[0].backend.history, [])
        self.assertEqual(self.agent.llmclients[0].last_tools, "")
        self.assertTrue(result["conversation"]["id"])
        self.assertEqual(self.manager.active_conversation_id, result["conversation"]["id"])

    def test_continue_conversation_returns_clean_compatible_payload(self):
        import frontends.webui_server as webui_server

        original_extract = webui_server.WebUITaskManager.continue_conversation.__globals__["extract_ui_messages"] if "extract_ui_messages" in webui_server.WebUITaskManager.continue_conversation.__globals__ else None
        original_handle = webui_server.WebUITaskManager.continue_conversation.__globals__["handle_frontend_command"] if "handle_frontend_command" in webui_server.WebUITaskManager.continue_conversation.__globals__ else None
        original_list = webui_server.WebUITaskManager.continue_conversation.__globals__["list_sessions"] if "list_sessions" in webui_server.WebUITaskManager.continue_conversation.__globals__ else None

        def fake_extract_ui_messages(_target):
            return [
                {"role": "user", "content": "hello"},
                {
                    "role": "assistant",
                    "content": (
                        "**LLM Running (Turn 1) ...**\n"
                        "<summary>\nHidden planning\n</summary>\n"
                        "final answer\n"
                        "[Info] Final response to user.\n"
                    ),
                },
            ]

        def fake_handle_frontend_command(_agent, _command):
            return (
                "✅ restored\n"
                "<summary>\nshould hide\n</summary>\n"
                "usable text\n"
                "[Info] Final response to user.\n"
            )

        def fake_list_sessions(**_kwargs):
            return [("session-1", "demo")]

        from unittest import mock

        with mock.patch("frontends.continue_cmd.extract_ui_messages", fake_extract_ui_messages), mock.patch(
            "frontends.continue_cmd.handle_frontend_command", fake_handle_frontend_command
        ), mock.patch("frontends.continue_cmd.list_sessions", fake_list_sessions):
            result = self.manager.continue_conversation("/continue 1")

        self.assertEqual(result["message"], "✅ restored\nusable text")
        self.assertEqual(len(result["history"]), 2)
        self.assertEqual(result["history"][0]["content"], "hello")
        self.assertEqual(result["history"][1]["content"], "final answer")

    def test_store_path_is_real_sqlite_file(self):
        self.assertTrue(os.path.exists(self.db_path))
        conn = sqlite3.connect(self.db_path)
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        finally:
            conn.close()
        self.assertIn("conversations", tables)
        self.assertIn("messages", tables)
        self.assertIn("conversation_groups", tables)


if __name__ == "__main__":
    unittest.main()
