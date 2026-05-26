import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_STATE_PATH = ROOT / "frontends" / "heroui" / "agent_state.py"


class FakeBackend:
    def __init__(self):
        self.history = []


class FakeLlmClient:
    def __init__(self):
        self.backend = FakeBackend()


class FakeHandler:
    def __init__(self):
        self.working = {}


class FakeAgent:
    def __init__(self):
        self.history = []
        self.llmclient = FakeLlmClient()
        self.handler = FakeHandler()
        self.llm_no = 0
        self.restored_llm = None

    def next_llm(self, llm_no):
        self.restored_llm = llm_no
        self.llm_no = llm_no


def load_agent_state():
    spec = importlib.util.spec_from_file_location("heroui_agent_state_under_test", AGENT_STATE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_capture_agent_state_reads_existing_ga_runtime_fields():
    module = load_agent_state()
    agent = FakeAgent()
    agent.history = ["[USER]: one", "[Agent] two"]
    agent.llmclient.backend.history = [{"role": "user", "content": [{"type": "text", "text": "one"}]}]
    agent.handler.working = {"key_info": "important"}
    agent.llm_no = 2

    captured = module.capture_agent_state(agent)

    assert captured == {
        "ga_history": ["[USER]: one", "[Agent] two"],
        "backend_history": [{"role": "user", "content": [{"type": "text", "text": "one"}]}],
        "working": {"key_info": "important"},
        "llm_no": 2,
    }


def test_restore_agent_state_sets_runtime_before_prompt_submission():
    module = load_agent_state()
    agent = FakeAgent()
    state = {
        "ga_history": ["[USER]: restored", "[Agent] restored summary"],
        "backend_history": [{"role": "assistant", "content": [{"type": "text", "text": "restored"}]}],
        "working": {"passed_sessions": 3},
        "llm_no": 4,
    }

    module.restore_agent_state(agent, state)

    assert agent.history == state["ga_history"]
    assert agent.llmclient.backend.history == state["backend_history"]
    assert agent.handler.working == state["working"]
    assert agent.restored_llm == 4


def test_restore_agent_state_primes_working_when_handler_is_created_later():
    module = load_agent_state()
    agent = FakeAgent()
    agent.handler = None
    state = {
        "ga_history": [],
        "backend_history": [],
        "working": {"key_info": "restore before put_task"},
        "llm_no": None,
    }

    module.restore_agent_state(agent, state)

    assert agent.handler.working == {"key_info": "restore before put_task"}


def test_restore_agent_state_clears_working_when_sqlite_state_is_authoritative_empty():
    module = load_agent_state()
    agent = FakeAgent()
    agent.handler.working = {"key_info": "future"}
    state = {
        "ga_history": [],
        "backend_history": [],
        "working": {},
        "llm_no": None,
        "state_version": 1,
    }

    module.restore_agent_state(agent, state)

    assert agent.handler.working == {}


def test_build_state_from_messages_uses_sqlite_messages_only():
    module = load_agent_state()
    messages = [
        {"role": "user", "content": "第一轮问题"},
        {"role": "assistant", "content": "第一轮回答"},
        {"role": "user", "content": "第二轮问题"},
    ]

    state = module.build_state_from_messages(messages, llm_no=0)

    assert state["ga_history"] == [
        "[USER]: 第一轮问题",
        "[Agent] 第一轮回答",
        "[USER]: 第二轮问题",
    ]
    assert state["backend_history"] == []
    assert state["working"] == {}
    assert state["llm_no"] == 0


def test_build_state_from_messages_can_exclude_current_turn():
    module = load_agent_state()
    messages = [
        {"role": "user", "content": "旧问题", "turn_id": "ga|sess|1"},
        {"role": "assistant", "content": "旧回答", "turn_id": "ga|sess|1"},
        {"role": "user", "content": "当前问题", "turn_id": "ga|sess|2"},
    ]

    state = module.build_state_from_messages(messages, llm_no=0, exclude_turn_id="ga|sess|2")

    assert state["ga_history"] == ["[USER]: 旧问题", "[Agent] 旧回答"]


def test_restore_handler_working_merges_missing_saved_keys():
    module = load_agent_state()
    handler = FakeHandler()
    handler.working = {"key_info": "fresh key info", "passed_sessions": 2}
    state = {
        "working": {
            "key_info": "saved key info",
            "passed_sessions": 1,
            "related_sop": "saved sop",
            "custom_note": "saved note",
        }
    }

    module.restore_handler_working(handler, state)

    assert handler.working == {
        "key_info": "fresh key info",
        "passed_sessions": 2,
        "related_sop": "saved sop",
        "custom_note": "saved note",
    }
