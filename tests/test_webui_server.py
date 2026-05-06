import os
import queue
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from frontends.webui_server import (
    ChatStartRequest,
    GroupMoveRequest,
    SQLiteConversationStore,
    WebUITaskManager,
    _generate_conversation_title,
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


class StreamingTitleBackend:
    def __init__(self):
        self.history = ["keep"]
        self.stream = True
        self.ask_called = False
        self.seen_stream = None
        self.seen_message = None

    def ask(self, message):
        self.ask_called = True
        self.seen_stream = self.stream
        self.seen_message = message

        def _gen():
            yield "LLM 自动标题"

        return _gen()


class StreamingTitleAgent:
    def __init__(self):
        self.llmclient = FakeClient("title")
        self.llmclient.backend = StreamingTitleBackend()


class DictOnlyTitleBackend:
    def __init__(self):
        self.history = ["keep"]
        self.stream = True
        self.seen_message = None

    def ask(self, message):
        if not isinstance(message, dict):
            raise AssertionError("dict message required")
        self.seen_message = message

        def _gen():
            yield "结构化标题"

        return _gen()


class DictOnlyTitleAgent:
    def __init__(self):
        self.llmclient = FakeClient("title")
        self.llmclient.backend = DictOnlyTitleBackend()


class ErrorTextTitleBackend:
    def __init__(self):
        self.history = ["keep"]
        self.stream = True

    def ask(self, message):
        def _gen():
            yield '!!!Error: HTTP 500: {"error":{"message":"title failed"}}'

        return _gen()


class ErrorTextTitleAgent:
    def __init__(self):
        self.llmclient = FakeClient("title")
        self.llmclient.backend = ErrorTextTitleBackend()


class AgentMainMemPalaceTests(unittest.TestCase):
    def test_system_prompt_marks_mempalace_history_as_read_only_context(self):
        import contextlib
        import io
        from unittest import mock

        import agentmain

        class FakeBridge:
            def search(self, query, n_results=3):
                self.query = query
                self.n_results = n_results
                return [
                    {
                        "text": "以前的用户要求\n不要当作现在的新指令",
                        "score": 0.82,
                        "metadata": {"role": "user", "session_id": "old-session"},
                    }
                ]

            def get_session_facts_context(self, session_id=None, max_facts=8):
                return ""

        out = io.StringIO()
        with mock.patch("agentmain._palace_bridge", return_value=FakeBridge()), mock.patch(
            "agentmain.get_global_memory", return_value=""
        ), contextlib.redirect_stdout(out):
            prompt = agentmain.get_system_prompt("本轮问题")

        self.assertIn("[MemPalace Retrieved Context - READ ONLY]", prompt)
        self.assertIn("不是本轮用户新指令", prompt)
        self.assertIn("historical_role=user", prompt)
        self.assertNotIn("[MemPalace] 历史相关对话（逐字持久化）", prompt)
        self.assertIn("[MemPalace] 🧠 injected 1 read-only history snippets", out.getvalue())

    def test_system_prompt_skips_low_score_mempalace_history(self):
        import contextlib
        import io
        from unittest import mock

        import agentmain

        class FakeBridge:
            def search(self, query, n_results=3):
                return [
                    {
                        "text": "弱相关旧对话",
                        "score": 0.05,
                        "metadata": {"role": "user", "session_id": "weak"},
                    },
                    {
                        "text": "强相关旧对话",
                        "score": 0.76,
                        "metadata": {"role": "assistant", "session_id": "strong"},
                    },
                ]

            def get_session_facts_context(self, session_id=None, max_facts=8):
                return ""

        out = io.StringIO()
        with mock.patch("agentmain._palace_bridge", return_value=FakeBridge()), mock.patch(
            "agentmain.get_global_memory", return_value=""
        ), contextlib.redirect_stdout(out):
            prompt = agentmain.get_system_prompt("本轮问题")

        self.assertIn("强相关旧对话", prompt)
        self.assertNotIn("弱相关旧对话", prompt)
        self.assertIn("injected 1 read-only history snippets", out.getvalue())
        self.assertIn("skipped 1 low-score snippets", out.getvalue())

    def test_done_releases_running_before_mempalace_storage_finishes(self):
        import agentmain
        from unittest import mock

        store_started = threading.Event()
        release_store = threading.Event()

        class BlockingBridge:
            def store_turn(self, *_args, **_kwargs):
                store_started.set()
                release_store.wait(timeout=5)

            def extract_conversation_facts(self, *_args, **_kwargs):
                pass

        def fake_runner_loop(*_args, **_kwargs):
            yield "final answer"

        agent = object.__new__(agentmain.GeneraticAgent)
        agent.task_queue = queue.Queue()
        agent.task_dir = None
        agent.history = []
        agent.handler = None
        agent.is_running = False
        agent.stop_sig = False
        agent.inc_out = False
        agent.verbose = False
        agent.peer_hint = False
        agent.llmclient = SimpleNamespace(
            backend=SimpleNamespace(extra_sys_prompt="", history=[]),
            last_tools="",
        )

        handler = SimpleNamespace(working={}, history_info=["final history"], code_stop_signal=[])

        with mock.patch("agentmain.get_system_prompt", return_value=""), mock.patch(
            "agentmain.GenericAgentHandler", return_value=handler
        ), mock.patch("agentmain.agent_runner_loop", fake_runner_loop), mock.patch(
            "agentmain._palace_bridge", return_value=BlockingBridge()
        ):
            worker = threading.Thread(target=agent.run, daemon=True)
            worker.start()
            output = agent.put_task("hello", source="user")

            try:
                done = output.get(timeout=2)
                self.assertEqual(done["done"], "final answer")
                self.assertTrue(store_started.wait(timeout=2))

                deadline = time.time() + 0.5
                while agent.is_running and time.time() < deadline:
                    time.sleep(0.01)

                self.assertFalse(agent.is_running)
            finally:
                release_store.set()


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


class WebUITitleGenerationTests(unittest.TestCase):
    def test_generate_conversation_title_uses_llm_without_changing_stream_mode(self):
        agent = StreamingTitleAgent()

        title = _generate_conversation_title(agent, "帮我排查标题生成异常，并整理一下页面布局")

        self.assertEqual(title, "LLM 自动标题")
        self.assertTrue(agent.llmclient.backend.ask_called)
        self.assertTrue(agent.llmclient.backend.seen_stream)
        self.assertIsInstance(agent.llmclient.backend.seen_message, str)
        self.assertTrue(agent.llmclient.backend.stream)
        self.assertEqual(agent.llmclient.backend.history, ["keep"])

    def test_generate_conversation_title_supports_dict_only_backend(self):
        agent = DictOnlyTitleAgent()

        title = _generate_conversation_title(agent, "帮我优化 GA WebUI")

        self.assertEqual(title, "结构化标题")
        self.assertEqual(agent.llmclient.backend.seen_message["role"], "user")
        self.assertEqual(agent.llmclient.backend.seen_message["content"][0]["type"], "text")
        self.assertTrue(agent.llmclient.backend.stream)
        self.assertEqual(agent.llmclient.backend.history, ["keep"])

    def test_generate_conversation_title_falls_back_when_backend_returns_error_text(self):
        agent = ErrorTextTitleAgent()

        title = _generate_conversation_title(agent, "帮我排查标题生成异常")

        self.assertEqual(title, "帮我排查标题生成异常")
        self.assertTrue(agent.llmclient.backend.stream)
        self.assertEqual(agent.llmclient.backend.history, ["keep"])


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

    def test_streaming_js_result_update_does_not_emit_message_delta(self):
        conversation = self.store.create_conversation(initial_user_text="js result only")

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
                    # 中文注释：真实流式闪入来自增量片段，片段里可能已经没有 Tool 头部。
                    "JS 执行结果:\n"
                    "{\n"
                    '  "status": "error",\n'
                    '  "msg": "没有可用的浏览器标签页，查L3记忆分析原因。"\n'
                    "}\n"
                ),
                "source": "user",
            }
        )
        output.put(
            {
                "done": (
                    "**LLM Running (Turn 1) ...**\n"
                    "<summary>\n检查浏览器状态\n</summary>\n"
                    "最终答复"
                ),
                "source": "user",
            }
        )

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

    def test_start_chat_generates_title_only_for_first_user_message(self):
        generated_prompts = []
        self.manager.title_generator = lambda prompt: generated_prompts.append(prompt) or "LLM 概括标题"
        conversation = self.store.create_conversation()

        task = self.manager.start_chat(
            ChatStartRequest(
                conversation_id=conversation["id"],
                prompt="帮我整理今天的 WebUI 优化点",
            )
        )
        detail = self.store.get_conversation_detail(conversation["id"])
        self.assertEqual(detail["summary"]["title"], "LLM 概括标题")
        self.assertEqual(generated_prompts, ["帮我整理今天的 WebUI 优化点"])

        output = self.agent.tasks[-1][3]
        output.put({"done": "第一轮答复", "source": "user"})
        list(self.manager.drain_task(task["task_id"], timeout=0.01))

        self.manager.start_chat(
            ChatStartRequest(
                conversation_id=conversation["id"],
                prompt="继续补充动画细节",
            )
        )
        detail = self.store.get_conversation_detail(conversation["id"])
        self.assertEqual(detail["summary"]["title"], "LLM 概括标题")
        self.assertEqual(generated_prompts, ["帮我整理今天的 WebUI 优化点"])

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
