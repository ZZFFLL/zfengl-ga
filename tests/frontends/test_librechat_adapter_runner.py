import queue
import unittest
from dataclasses import dataclass

from frontends.librechat_adapter import runner as runner_module
from frontends.librechat_adapter.runner import LibreChatAdapterRunner
from frontends.librechat_adapter.sessions import InMemoryConversationManager


@dataclass
class SimpleRequest:
    messages: list
    model: str = "generic-agent"
    stream: bool = False
    request_id: str = "chatcmpl-test"


class FakeAgent:
    def __init__(self, responses=None, is_running=False):
        self.responses = list(responses or [[{"done": "ok"}]])
        self.is_running = is_running
        self.put_calls = []
        self.abort_calls = 0

    def put_task(self, prompt, source="user", images=None):
        self.put_calls.append(
            {"prompt": prompt, "source": source, "images": list(images or [])}
        )
        output = queue.Queue()
        for event in self.responses.pop(0):
            output.put(event)
        return output

    def abort(self):
        self.abort_calls += 1


class LibreChatAdapterRunnerTest(unittest.TestCase):
    def setUp(self):
        self.original_builder = runner_module.build_prompt_from_messages
        self.original_reset = runner_module.reset_conversation
        runner_module.build_prompt_from_messages = self._build_prompt
        self.reset_calls = []
        runner_module.reset_conversation = (
            lambda agent, message=None: self.reset_calls.append((agent, message))
        )

    def tearDown(self):
        runner_module.build_prompt_from_messages = self.original_builder
        runner_module.reset_conversation = self.original_reset

    def _build_prompt(self, messages, include_history):
        self.last_include_history = include_history
        selected = messages if include_history else self._latest_user(messages)
        return "\n".join(
            f"{message.get('role', 'user')}:{message.get('content', '')}"
            for message in selected
        )

    @staticmethod
    def _latest_user(messages):
        for message in reversed(messages):
            if message.get("role") == "user":
                return [message]
        return messages[-1:] if messages else []

    def test_first_conversation_includes_history(self):
        manager = InMemoryConversationManager()

        include = manager.should_include_history("conv-a", "parent-a", 2)

        self.assertTrue(include)

    def test_same_conversation_only_sends_latest_user_message(self):
        agent = FakeAgent(
            [
                [{"done": "first"}],
                [{"done": "second"}],
            ]
        )
        runner = LibreChatAdapterRunner(agent)
        meta = {"conversation_id": "conv-a", "parent_message_id": "parent-a"}
        first = SimpleRequest(
            messages=[
                {"role": "user", "content": "old question"},
                {"role": "assistant", "content": "old answer"},
                {"role": "user", "content": "first question"},
            ]
        )
        second = SimpleRequest(
            messages=[
                {"role": "user", "content": "old question"},
                {"role": "assistant", "content": "old answer"},
                {"role": "user", "content": "latest question"},
            ]
        )

        runner.chat(first, meta)
        runner.chat(second, meta)

        self.assertEqual(agent.put_calls[1]["prompt"], "user:latest question")

    def test_switching_conversation_resets_runtime(self):
        agent = FakeAgent(
            [
                [{"done": "first"}],
                [{"done": "second"}],
            ]
        )
        runner = LibreChatAdapterRunner(agent)

        runner.chat(
            SimpleRequest(messages=[{"role": "user", "content": "first"}]),
            {"conversation_id": "conv-a", "parent_message_id": "parent-a"},
        )
        runner.chat(
            SimpleRequest(
                messages=[
                    {"role": "user", "content": "history"},
                    {"role": "assistant", "content": "answer"},
                    {"role": "user", "content": "new"},
                ]
            ),
            {"conversation_id": "conv-b", "parent_message_id": "parent-b"},
        )

        self.assertEqual(self.reset_calls, [(agent, None)])
        self.assertEqual(
            agent.put_calls[1]["prompt"],
            "user:history\nassistant:answer\nuser:new",
        )

    def test_busy_does_not_put_task(self):
        agent = FakeAgent(is_running=True)
        runner = LibreChatAdapterRunner(agent)

        with self.assertRaisesRegex(RuntimeError, "busy"):
            runner.chat(
                SimpleRequest(messages=[{"role": "user", "content": "hello"}]),
                {"conversation_id": "conv-a"},
            )

        self.assertEqual(agent.put_calls, [])

    def test_stream_chat_emits_deltas_for_next_and_done(self):
        agent = FakeAgent(
            [
                [
                    {"next": "hello"},
                    {"next": "hello world"},
                    {"done": "hello world!"},
                ]
            ]
        )
        runner = LibreChatAdapterRunner(agent)

        events = list(
            runner.stream_chat(
                SimpleRequest(
                    messages=[{"role": "user", "content": "hello"}],
                    stream=True,
                ),
                {"conversation_id": "conv-a"},
            )
        )

        content_deltas = [
            event["delta"]["content"]
            for event in events
            if event.get("delta", {}).get("content")
        ]
        self.assertEqual(content_deltas, ["hello", " world", "!"])
        self.assertEqual(events[-1]["finish_reason"], "stop")
        self.assertEqual(agent.put_calls[0]["source"], "librechat")
        self.assertEqual(agent.put_calls[0]["images"], [])

    def test_stream_chat_does_not_append_process_summary_on_done(self):
        agent = FakeAgent(
            [
                [
                    {
                        "done": (
                            "**LLM Running (Turn 1) ...**\n"
                            "<summary>Checked available sessions</summary>\n"
                            "Final answer"
                        )
                    },
                ]
            ]
        )
        runner = LibreChatAdapterRunner(agent)

        events = list(
            runner.stream_chat(
                SimpleRequest(
                    messages=[{"role": "user", "content": "hello"}],
                    stream=True,
                ),
                {"conversation_id": "conv-a"},
            )
        )

        joined = "".join(
            event["delta"].get("content", "")
            for event in events
            if isinstance(event.get("delta"), dict)
        )
        self.assertIn("Final answer", joined)
        self.assertNotIn("## 思考过程", joined)
        self.assertNotIn("### Turn 1", joined)
        self.assertNotIn("LLM Running", joined)
        self.assertNotIn("Checked available sessions", joined)
        self.assertNotIn("<summary>", joined)

    def test_chat_does_not_append_process_summary(self):
        agent = FakeAgent(
            [
                [
                    {
                        "done": (
                            "**LLM Running (Turn 2) ...**\n"
                            "<summary>已读取tavily_search_sop，准备用tavily搜索长沙明天天气</summary>\n"
                            "长沙明天多云。"
                        )
                    },
                ]
            ]
        )
        runner = LibreChatAdapterRunner(agent)

        response = runner.chat(
            SimpleRequest(messages=[{"role": "user", "content": "长沙明天天气怎么样"}]),
            {"conversation_id": "conv-a"},
        )

        content = response["choices"][0]["message"]["content"]
        self.assertIn("长沙明天多云。", content)
        self.assertNotIn("## 思考过程", content)
        self.assertNotIn("### Turn 2", content)
        self.assertNotIn("LLM Running", content)
        self.assertNotIn("已读取tavily_search_sop", content)
        self.assertNotIn("<summary>", content)

    def test_stream_chat_shows_compact_execution_process_and_final_answer(self):
        agent = FakeAgent(
            [
                [
                    {
                        "next": (
                            "**LLM Running (Turn 1) ...**\n"
                            "<summary>准备搜索长沙天气</summary>\n\n"
                            "🛠️ Tool: `code_run`  📥 args:\n"
                            "````text\nimport requests\n````\n"
                            "`````\n[Status] ✅ Exit Code: 0\n[Stdout]\nraw weather output"
                        )
                    },
                    {
                        "next": (
                            "**LLM Running (Turn 1) ...**\n"
                            "<summary>准备搜索长沙天气</summary>\n\n"
                            "🛠️ Tool: `code_run`  📥 args:\n"
                            "````text\nimport requests\n````\n"
                            "`````\n[Status] ✅ Exit Code: 0\n[Stdout]\nraw weather output\n"
                            "`````\n**LLM Running (Turn 2) ...**\n"
                            "<summary>整理天气结果并回答</summary>\n\n"
                            "长沙明天多云。"
                        )
                    },
                    {
                        "done": (
                            "**LLM Running (Turn 1) ...**\n"
                            "<summary>准备搜索长沙天气</summary>\n\n"
                            "🛠️ Tool: `code_run`  📥 args:\n"
                            "````text\nimport requests\n````\n"
                            "`````\n[Status] ✅ Exit Code: 0\n[Stdout]\nraw weather output\n"
                            "`````\n**LLM Running (Turn 2) ...**\n"
                            "<summary>整理天气结果并回答</summary>\n\n"
                            "长沙明天多云。\n\n"
                            "`````\n[Info] Final response to user.\n`````"
                        )
                    },
                ]
            ]
        )
        runner = LibreChatAdapterRunner(agent)

        events = list(
            runner.stream_chat(
                SimpleRequest(
                    messages=[{"role": "user", "content": "长沙明天天气怎么样"}],
                    stream=True,
                ),
                {"conversation_id": "conv-a"},
            )
        )

        joined = "".join(
            event["delta"].get("content", "")
            for event in events
            if isinstance(event.get("delta"), dict)
        )
        self.assertIn("### 执行过程", joined)
        self.assertIn("调用工具 `code_run`", joined)
        self.assertIn("工具 `code_run` 返回", joined)
        self.assertIn("输出预览", joined)
        self.assertIn("### 最终回答", joined)
        self.assertIn("长沙明天多云。", joined)
        self.assertNotIn("LLM Running", joined)
        self.assertNotIn("准备搜索长沙天气", joined)
        self.assertNotIn("Final response to user", joined)
        self.assertNotIn("<summary>", joined)

    def test_chat_shows_compact_execution_process_and_final_answer(self):
        agent = FakeAgent(
            [
                [
                    {
                        "done": (
                            "**LLM Running (Turn 1) ...**\n"
                            "<summary>准备搜索长沙天气</summary>\n\n"
                            "🛠️ Tool: `code_run`  📥 args:\n"
                            "````text\nimport requests\n````\n"
                            "`````\n[Status] ✅ Exit Code: 0\n[Stdout]\nraw weather output\n"
                            "`````\n**LLM Running (Turn 2) ...**\n"
                            "<summary>整理天气结果并回答</summary>\n\n"
                            "长沙明天多云。\n\n"
                            "`````\n[Info] Final response to user.\n`````"
                        )
                    },
                ]
            ]
        )
        runner = LibreChatAdapterRunner(agent)

        response = runner.chat(
            SimpleRequest(messages=[{"role": "user", "content": "长沙明天天气怎么样"}]),
            {"conversation_id": "conv-a"},
        )

        content = response["choices"][0]["message"]["content"]
        self.assertIn("### 执行过程", content)
        self.assertIn("调用工具 `code_run`", content)
        self.assertIn("工具 `code_run` 返回", content)
        self.assertIn("输出预览", content)
        self.assertIn("### 最终回答", content)
        self.assertIn("长沙明天多云。", content)
        self.assertNotIn("LLM Running", content)
        self.assertNotIn("准备搜索长沙天气", content)
        self.assertNotIn("Final response to user", content)
        self.assertNotIn("<summary>", content)

    def test_stream_chat_includes_tool_output_preview_when_final_answer_is_missing(self):
        agent = FakeAgent(
            [
                [
                    {
                        "done": (
                            "**LLM Running (Turn 1) ...**\n"
                            "<summary>查询天气</summary>\n\n"
                            "🛠️ Tool: `code_run`  📥 args:\n"
                            "````text\n{\"script\": \"weather lookup\"}\n````\n"
                            "`````\n[Status] ✅ Exit Code: 0\n[Stdout]\n"
                            "答案摘要: 长沙明天多云，19到25度。\n"
                            "更多原始结果若干行\n`````"
                        )
                    },
                ]
            ]
        )
        runner = LibreChatAdapterRunner(agent)

        events = list(
            runner.stream_chat(
                SimpleRequest(
                    messages=[{"role": "user", "content": "长沙明天天气怎么样"}],
                    stream=True,
                ),
                {"conversation_id": "conv-a"},
            )
        )

        joined = "".join(
            event["delta"].get("content", "")
            for event in events
            if isinstance(event.get("delta"), dict)
        )
        self.assertIn("### 执行过程", joined)
        self.assertIn("调用工具 `code_run`", joined)
        self.assertIn("输出预览", joined)
        self.assertIn("长沙明天多云", joined)
        self.assertNotIn("### 最终回答", joined)
        self.assertNotIn("<summary>", joined)

    def test_chat_strips_dangling_final_info_fence(self):
        agent = FakeAgent(
            [
                [
                    {
                        "done": (
                            "**LLM Running (Turn 1) ...**\n\n"
                            "Final answer\n\n"
                            "[Info] Final response to user.\n`````"
                        )
                    },
                ]
            ]
        )
        runner = LibreChatAdapterRunner(agent)

        response = runner.chat(
            SimpleRequest(messages=[{"role": "user", "content": "hello"}]),
            {"conversation_id": "conv-a"},
        )

        content = response["choices"][0]["message"]["content"]
        self.assertEqual(content, "Final answer")
        self.assertNotIn("`````", content)
        self.assertNotIn("Final response to user", content)

    def test_stream_chat_does_not_append_empty_process_section(self):
        agent = FakeAgent(
            [
                [
                    {"done": "**LLM Running (Turn 1) ...**\n\nFinal answer"},
                ]
            ]
        )
        runner = LibreChatAdapterRunner(agent)

        events = list(
            runner.stream_chat(
                SimpleRequest(
                    messages=[{"role": "user", "content": "hello"}],
                    stream=True,
                ),
                {"conversation_id": "conv-a"},
            )
        )

        joined = "".join(
            event["delta"].get("content", "")
            for event in events
            if isinstance(event.get("delta"), dict)
        )
        self.assertIn("Final answer", joined)
        self.assertNotIn("## 思考过程", joined)
        self.assertNotIn("LLM Running", joined)
        self.assertNotIn("### Turn 1", joined)

    def test_stream_chat_does_not_leak_unclosed_summary_snapshot(self):
        agent = FakeAgent(
            [
                [
                    {"next": "<summary>secret partial"},
                    {"done": "<summary>safe public summary</summary>\nFinal answer"},
                ]
            ]
        )
        runner = LibreChatAdapterRunner(agent)

        events = list(
            runner.stream_chat(
                SimpleRequest(
                    messages=[{"role": "user", "content": "hello"}],
                    stream=True,
                ),
                {"conversation_id": "conv-a"},
            )
        )

        joined = "".join(
            event["delta"].get("content", "")
            for event in events
            if isinstance(event.get("delta"), dict)
        )
        self.assertIn("Final answer", joined)
        self.assertNotIn("safe public summary", joined)
        self.assertNotIn("secret partial", joined)
        self.assertNotIn("<summary>", joined)

    def test_abort_current_calls_agent_abort(self):
        agent = FakeAgent()
        runner = LibreChatAdapterRunner(agent)

        runner.abort_current()

        self.assertEqual(agent.abort_calls, 1)


if __name__ == "__main__":
    unittest.main()
