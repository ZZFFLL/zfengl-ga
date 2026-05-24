import json
from dataclasses import dataclass

from agent_loop import (
    BaseHandler,
    StepOutcome,
    _tool_result_error,
    _tool_result_output,
    _tool_result_status,
    agent_runner_loop,
)


@dataclass
class FakeFunction:
    name: str
    arguments: str


@dataclass
class FakeToolCall:
    id: str
    function: FakeFunction


class FakeResponse:
    def __init__(self, content="", tool_calls=None, thinking=""):
        self.content = content
        self.thinking = thinking
        self.tool_calls = tool_calls or []


class FakeClient:
    def __init__(self):
        self.last_tools = ""
        self.calls = 0

    def chat(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            yield "I will run a command."
            return FakeResponse(
                content="I will run a command.",
                tool_calls=[
                    FakeToolCall(
                        id="call-1",
                        function=FakeFunction(
                            name="code_run",
                            arguments=json.dumps({"type": "python", "code": "print('ok')"}),
                        ),
                    )
                ],
            )
        yield "Done."
        return FakeResponse(content="Done.", tool_calls=[])


class StreamingProtocolClient:
    def __init__(self):
        self.last_tools = ""

    def chat(self, messages, tools):
        yield "Visible "
        yield "<thinking>private reasoning</thinking>"
        yield "<summary>准备调用命令</summary>"
        yield "text"
        return FakeResponse(
            content="<summary>准备调用命令</summary>Visible text",
            thinking="private reasoning",
            tool_calls=[
                FakeToolCall(
                    id="call-1",
                    function=FakeFunction(
                        name="code_run",
                        arguments=json.dumps({"type": "python", "code": "print('ok')"}),
                    ),
                )
            ],
        )


class NoToolProtocolClient:
    def __init__(self):
        self.last_tools = ""

    def chat(self, messages, tools):
        yield "Visible answer"
        return FakeResponse(
            content="Visible answer <thinking>private reasoning</thinking><tool_use>{}</tool_use><file_content>secret</file_content>",
            thinking="private reasoning",
            tool_calls=[],
        )


class NoToolEmptyContentStreamingClient:
    def __init__(self):
        self.last_tools = ""

    def chat(self, messages, tools):
        yield "Visible final "
        yield "<thinking>private reasoning</thinking>"
        yield "answer"
        return FakeResponse(content="", thinking="private reasoning", tool_calls=[])


class NoToolProtocolOnlyContentClient:
    def __init__(self):
        self.last_tools = ""

    def chat(self, messages, tools):
        yield "Visible "
        yield "<thinking>private reasoning</thinking>"
        yield "answer"
        return FakeResponse(content="<thinking>private reasoning</thinking>", thinking="private reasoning", tool_calls=[])


class FakeParent:
    task_dir = None


class EventHandler(BaseHandler):
    def __init__(self):
        self.parent = FakeParent()
        self._done_hooks = []
        self.current_turn = 0

    def do_code_run(self, args, response):
        yield "[stdout]\nok\n"
        return StepOutcome("ok", next_prompt="continue")

    def do_no_tool(self, args, response):
        yield "[Info] Final response to user.\n"
        return StepOutcome(response, next_prompt=None)


class FileFailureHandler(EventHandler):
    def do_file_read(self, args, response):
        yield "[Action] Reading file: E:\\missing.txt\n"
        return StepOutcome("Error: [Errno 2] No such file or directory", next_prompt="\n")

    def do_file_write(self, args, response):
        yield "[Status] ❌ 失败: 未在回复中找到<file_content>代码块内容\n"
        return StepOutcome({"status": "error", "msg": "No content found"}, next_prompt="\n")


class FileReadContentHandler(EventHandler):
    def do_file_read(self, args, response):
        yield "[Action] Reading file: E:\\zfengl-ai-project\\GenericAgent\\agent_loop.py\n"
        return StepOutcome(
            '由于设置了show_linenos，以下返回信息为：(行号|)内容 。\n'
            '[FILE] 268 lines | PARTIAL showing 69; assess need for more\n'
            '202| failed = isinstance(getattr(outcome, "data", None), str) and "[Error]" in outcome.data\n',
            next_prompt="\n",
        )


class FileFailureClient:
    def __init__(self, tool_name):
        self.last_tools = ""
        self.tool_name = tool_name

    def chat(self, messages, tools):
        yield f"I will call {self.tool_name}."
        return FakeResponse(
            content=f"I will call {self.tool_name}.",
            tool_calls=[
                FakeToolCall(
                    id=f"call-{self.tool_name}",
                    function=FakeFunction(
                        name=self.tool_name,
                        arguments=json.dumps({"path": "E:\\missing.txt"}),
                    ),
                )
            ],
        )


def test_agent_runner_loop_emits_ordered_structured_events():
    events = []
    handler = EventHandler()
    chunks = list(
        agent_runner_loop(
            FakeClient(),
            "system",
            "run it",
            handler,
            tools_schema=[],
            verbose=True,
            yield_info=True,
            event_sink=events.append,
        )
    )

    event_types = [event["type"] for event in events]

    assert "LLM Running" in "".join(str(chunk) for chunk in chunks)
    assert event_types == [
        "turn.start",
        "llm.start",
        "llm.visible_delta",
        "llm.end",
        "tool.start",
        "tool.delta",
        "tool.end",
        "turn.end",
        "turn.start",
        "llm.start",
        "llm.visible_delta",
        "llm.end",
        "agent.final",
        "turn.end",
        "agent.done",
    ]
    tool_start = events[event_types.index("tool.start")]
    tool_delta = events[event_types.index("tool.delta")]
    tool_end = events[event_types.index("tool.end")]
    llm_end = events[event_types.index("llm.end")]
    final_event = events[event_types.index("agent.final")]

    assert isinstance(llm_end["elapsed_ms"], int)
    assert llm_end["elapsed_ms"] >= 0
    assert tool_start["tool_name"] == "code_run"
    assert tool_start["args"] == {"type": "python", "code": "print('ok')"}
    assert tool_delta["tool_kind"] == "command"
    assert tool_delta["delta"] == "[stdout]\nok\n"
    assert tool_end["tool_kind"] == "command"
    assert tool_end["status"] == "done"
    assert tool_end["result"] == "ok"
    assert final_event["text"] == "Done."


def test_agent_runner_loop_without_event_sink_keeps_legacy_chunks_only():
    handler = EventHandler()
    chunks = list(
        agent_runner_loop(
            FakeClient(),
            "system",
            "run it",
            handler,
            tools_schema=[],
            verbose=True,
            yield_info=True,
        )
    )

    assert any(isinstance(chunk, dict) and chunk.get("turn") == 1 for chunk in chunks)
    assert not any(isinstance(chunk, dict) and chunk.get("type") == "tool.start" for chunk in chunks)


def test_agent_runner_loop_marks_file_read_error_result_as_failed_card_output():
    events = []

    list(
        agent_runner_loop(
            FileFailureClient("file_read"),
            "system",
            "read missing",
            FileFailureHandler(),
            tools_schema=[],
            verbose=True,
            yield_info=True,
            max_turns=1,
            event_sink=events.append,
        )
    )

    tool_end = next(event for event in events if event["type"] == "tool.end")

    assert tool_end["status"] == "failed"
    assert "[Action] Reading file:" in tool_end["detail"]
    assert tool_end["output"] == ""
    assert "Error: [Errno 2]" in tool_end["error"]


def test_agent_runner_loop_keeps_file_read_content_with_error_marker_successful():
    events = []

    list(
        agent_runner_loop(
            FileFailureClient("file_read"),
            "system",
            "read source",
            FileReadContentHandler(),
            tools_schema=[],
            verbose=True,
            yield_info=True,
            max_turns=1,
            event_sink=events.append,
        )
    )

    tool_end = next(event for event in events if event["type"] == "tool.end")

    assert tool_end["status"] == "done"
    assert "[Action] Reading file:" in tool_end["detail"]
    assert "PARTIAL showing 69" in tool_end["output"]
    assert '"[Error]" in outcome.data' in tool_end["output"]
    assert tool_end["error"] == ""


def test_agent_runner_loop_marks_file_write_error_dict_as_failed_card_output():
    events = []

    list(
        agent_runner_loop(
            FileFailureClient("file_write"),
            "system",
            "write missing content",
            FileFailureHandler(),
            tools_schema=[],
            verbose=True,
            yield_info=True,
            max_turns=1,
            event_sink=events.append,
        )
    )

    tool_end = next(event for event in events if event["type"] == "tool.end")

    assert tool_end["status"] == "failed"
    assert "未在回复中找到<file_content>" in tool_end["detail"]
    assert tool_end["output"] == ""
    assert "No content found" in tool_end["error"]


def test_builtin_tool_result_contracts_do_not_guess_from_success_content():
    assert _tool_result_status("file_read", '202| literal "[Error]" in source') == "done"
    assert _tool_result_status("file_read", "Error: File not found: missing.py") == "failed"
    assert _tool_result_status("file_write", {"status": "success", "writed_bytes": 10}) == "done"
    assert _tool_result_status("file_write", {"status": "error", "msg": "No content found"}) == "failed"
    assert _tool_result_status("file_patch", {"status": "success", "msg": "文件局部修改成功"}) == "done"
    assert _tool_result_status("file_patch", {"status": "error", "msg": "未找到匹配"}) == "failed"
    assert _tool_result_status("code_run", {"status": "success", "stdout": "[Error] as data", "exit_code": 0}) == "done"
    assert _tool_result_status("code_run", {"status": "error", "stdout": "Traceback", "exit_code": 1}) == "failed"
    assert _tool_result_status("web_scan", {"status": "success", "content": "visible [Error] page text"}) == "done"
    assert _tool_result_status("web_scan", {"status": "error", "msg": "没有可用的浏览器标签页"}) == "failed"
    assert _tool_result_status("web_execute_js", '{"status": "error", "msg": "没有可用的浏览器标签页"}') == "failed"
    assert _tool_result_status("ask_user", {"status": "INTERRUPT", "intent": "HUMAN_INTERVENTION"}) == "done"
    assert _tool_result_status("update_working_checkpoint", {"result": "working key_info updated"}) == "done"
    assert _tool_result_status("start_long_term_update", "Memory Management SOP not found. Do not update memory.") == "done"

    assert _tool_result_output("code_run", {"status": "success", "stdout": "ok\n", "exit_code": 0}, "done") == "ok\n"
    assert _tool_result_error({"status": "error", "msg": "No content found"}, "failed") == "No content found"


def test_agent_runner_loop_emits_clean_model_delta_and_thinking_summary():
    events = []
    handler = EventHandler()

    list(
        agent_runner_loop(
            StreamingProtocolClient(),
            "system",
            "run it",
            handler,
            tools_schema=[],
            verbose=True,
            yield_info=True,
            max_turns=1,
            event_sink=events.append,
        )
    )

    event_types = [event["type"] for event in events]
    deltas = [
        event["delta"]
        for event in events
        if event["type"] == "llm.visible_delta" and event["turn"] == 1
    ]
    llm_end = next(event for event in events if event["type"] == "llm.end")

    assert "llm.visible_delta" in event_types
    assert "".join(deltas) == "Visible text"
    assert "private reasoning" not in "".join(deltas)
    assert llm_end["summary"] == "准备调用命令"
    assert llm_end["thinking_summary"] == "准备调用命令"


def test_agent_runner_loop_sanitizes_agent_final_text_for_no_tool_response():
    events = []
    handler = EventHandler()

    list(
        agent_runner_loop(
            NoToolProtocolClient(),
            "system",
            "run it",
            handler,
            tools_schema=[],
            verbose=True,
            yield_info=True,
            max_turns=1,
            event_sink=events.append,
        )
    )

    final_event = next(event for event in events if event["type"] == "agent.final")

    assert final_event["text"] == "Visible answer"
    assert "<thinking>" not in final_event["text"]
    assert "<tool_use>" not in final_event["text"]
    assert "<file_content>" not in final_event["text"]


def test_agent_runner_loop_uses_visible_stream_fallback_for_empty_final_content():
    events = []
    handler = EventHandler()

    list(
        agent_runner_loop(
            NoToolEmptyContentStreamingClient(),
            "system",
            "run it",
            handler,
            tools_schema=[],
            verbose=True,
            yield_info=True,
            max_turns=1,
            event_sink=events.append,
        )
    )

    final_event = next(event for event in events if event["type"] == "agent.final")
    deltas = [event["delta"] for event in events if event["type"] == "llm.visible_delta"]

    assert "".join(deltas) == "Visible final answer"
    assert final_event["text"] == "Visible final answer"


def test_agent_runner_loop_uses_visible_stream_fallback_when_final_content_sanitizes_empty():
    events = []
    handler = EventHandler()

    list(
        agent_runner_loop(
            NoToolProtocolOnlyContentClient(),
            "system",
            "run it",
            handler,
            tools_schema=[],
            verbose=True,
            yield_info=True,
            max_turns=1,
            event_sink=events.append,
        )
    )

    final_event = next(event for event in events if event["type"] == "agent.final")

    assert final_event["text"] == "Visible answer"


def test_structured_event_path_yields_sanitized_model_chunks_but_legacy_path_remains_raw():
    structured_handler = EventHandler()
    structured_chunks = list(
        agent_runner_loop(
            NoToolProtocolOnlyContentClient(),
            "system",
            "run it",
            structured_handler,
            tools_schema=[],
            verbose=True,
            yield_info=True,
            max_turns=1,
            event_sink=lambda event: None,
        )
    )

    legacy_handler = EventHandler()
    legacy_chunks = list(
        agent_runner_loop(
            NoToolProtocolOnlyContentClient(),
            "system",
            "run it",
            legacy_handler,
            tools_schema=[],
            verbose=True,
            yield_info=True,
            max_turns=1,
        )
    )

    structured_text = "".join(str(chunk) for chunk in structured_chunks)
    legacy_text = "".join(str(chunk) for chunk in legacy_chunks)

    assert "private reasoning" not in structured_text
    assert "<thinking>" not in structured_text
    assert "private reasoning" in legacy_text
    assert "<thinking>" in legacy_text


def test_generic_agent_structured_events_default_disabled():
    from agentmain import GenericAgent

    agent = GenericAgent.__new__(GenericAgent)

    assert not getattr(agent, "structured_events", False)
