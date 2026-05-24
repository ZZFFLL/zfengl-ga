import json
from dataclasses import dataclass

from agent_loop import BaseHandler, StepOutcome, agent_runner_loop


@dataclass
class FakeFunction:
    name: str
    arguments: str


@dataclass
class FakeToolCall:
    id: str
    function: FakeFunction


class FakeResponse:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.thinking = ""
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
        "llm.end",
        "tool.start",
        "tool.delta",
        "tool.end",
        "turn.end",
        "turn.start",
        "llm.start",
        "llm.end",
        "agent.final",
        "turn.end",
        "agent.done",
    ]
    tool_start = events[event_types.index("tool.start")]
    tool_delta = events[event_types.index("tool.delta")]
    tool_end = events[event_types.index("tool.end")]
    final_event = events[event_types.index("agent.final")]

    assert tool_start["tool_name"] == "code_run"
    assert tool_start["args"] == {"type": "python", "code": "print('ok')"}
    assert tool_delta["delta"] == "[stdout]\nok\n"
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


def test_generic_agent_structured_events_default_disabled():
    from agentmain import GenericAgent

    agent = GenericAgent.__new__(GenericAgent)

    assert not getattr(agent, "structured_events", False)
