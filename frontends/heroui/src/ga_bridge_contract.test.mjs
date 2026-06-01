import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const herouiRoot = new URL("..", import.meta.url);
const herouiPath = fileURLToPath(herouiRoot);
const apiPath = join(herouiPath, "src", "api.ts");
const bridgePath = join(herouiPath, "bridge.py");
const bridgeEventsPath = join(herouiPath, "bridge_core", "events.py");
const bridgeSessionPath = join(herouiPath, "bridge_core", "session.py");
const bridgeRoutesPath = join(herouiPath, "bridge_core", "routes.py");
const bridgeStreamingPath = join(herouiPath, "bridge_core", "streaming.py");
const bridgeHttpUtilsPath = join(herouiPath, "bridge_core", "http_utils.py");
const vitePath = join(herouiPath, "vite.config.ts");

test("HeroUI frontend has a dedicated GenericAgent bridge copy", () => {
  assert.equal(existsSync(bridgePath), true);
  assert.equal(existsSync(bridgeSessionPath), true);
  assert.equal(existsSync(bridgeRoutesPath), true);
  const bridge = readFileSync(bridgePath, "utf8");
  const session = readFileSync(bridgeSessionPath, "utf8");
  const routes = readFileSync(bridgeRoutesPath, "utf8");
  const bridgeAndSession = `${bridge}\n${session}`;
  const bridgeAndRoutes = `${bridge}\n${routes}`;

  assert.match(bridge, /GenericAgent HeroUI Bridge/);
  assert.match(bridge, /HEROUI_BRIDGE_PORT/);
  assert.match(bridgeAndRoutes, /APP_DIR \/ "dist"|app_dir .* "dist"|self\.app_dir \/ "dist"/);
  assert.match(bridge, /make_turn_id/);
  assert.match(bridge, /make_response_id/);
  assert.match(bridge, /"turn_id"/);
  assert.match(bridge, /"responseId"/);
  assert.match(bridge, /"gaTurn"/);
  assert.match(bridge, /"outputs"/);
  assert.match(bridge, /"model"/);
  assert.match(bridge, /get_llm_name\(client, model=True\)/);
  assert.match(bridge, /selected_llm_no/);
  assert.match(bridge, /def switch_model_profile/);
  assert.match(bridge, /def regenerate_session_title/);
  assert.match(bridge, /def replay_turn/);
  assert.match(bridgeAndSession, /events: List\[dict\] = field\(default_factory=list\)/);
  assert.match(bridgeAndSession, /event_seq: int = 0/);
  assert.match(bridge, /SessionStore/);
  assert.match(bridge, /def add_event/);
  assert.match(bridge, /def convert_agent_event/);
  assert.match(bridge, /agent\.structured_events = True/);
  assert.match(bridge, /def _persist_session_and_message/);
  assert.match(bridge, /persist=False/);
  assert.doesNotMatch(bridge, /self\._persist_message\(sess, user_msg\)/);
  assert.match(bridgeAndRoutes, /app\.router\.add_post\("\/session\/new", (self\.)?new_session_handler\)/);
  assert.match(bridgeAndRoutes, /app\.router\.add_get\("\/session\/\{sid\}\/messages", (self\.)?messages_handler\)/);
  assert.match(bridgeAndRoutes, /app\.router\.add_post\("\/model-profile", (self\.)?switch_model_profile_handler\)/);
  assert.match(bridgeAndRoutes, /app\.router\.add_post\("\/session\/\{sid\}\/title\/regenerate", (self\.)?regenerate_session_title_handler\)/);
  assert.match(bridgeAndRoutes, /app\.router\.add_post\("\/session\/\{sid\}\/turn\/replay", (self\.)?replay_turn_handler\)/);
});

test("HeroUI bridge keeps session model and default paths in bridge_core", () => {
  assert.equal(existsSync(bridgePath), true);
  assert.equal(existsSync(bridgeSessionPath), true);
  const bridge = readFileSync(bridgePath, "utf8");
  const session = readFileSync(bridgeSessionPath, "utf8");

  assert.match(bridge, /from .*session import|from bridge_core\.session import/);
  assert.match(session, /class Session/);
  assert.match(session, /def find_default_ga_root/);
  assert.match(session, /DEFAULT_GA_ROOT = find_default_ga_root\(\)/);
  assert.match(session, /DEFAULT_HEROUI_DB_PATH = APP_DIR \/ "\.data" \/ "sessions\.sqlite3"/);
});

test("HeroUI api adapter speaks the GA bridge polling contract", () => {
  assert.equal(existsSync(apiPath), true);
  const api = readFileSync(apiPath, "utf8");

  assert.match(api, /\/session\/new/);
  assert.match(api, /\/session\/\$\{encodeURIComponent\(sessionId\)\}\/prompt/);
  assert.match(api, /\/session\/\$\{encodeURIComponent\(sessionId\)\}\/messages\?after=/);
  assert.match(api, /window\.setTimeout\(poll/);
  assert.match(api, /answer\.delta/);
  assert.match(api, /answer\.final/);
  assert.match(api, /emitBridgeOutputs/);
  assert.match(api, /type: "timeline\.step"/);
  assert.match(api, /parseGenericAgentOutputSteps/);
  assert.match(api, /after_event=/);
  assert.match(api, /payload\.events/);
  assert.doesNotMatch(api, /tool_name: "GenericAgent\.outputs"/);
  assert.match(api, /new EventSource/);
  assert.match(api, /function subscribeTurnPolling/);
  assert.match(api, /turn_id: message\.turn_id/);
  assert.match(api, /response_id: message\.responseId/);
  assert.match(api, /response_id: message\.responseId \|\| message\.response_id/);
  assert.match(api, /switchModelProfile/);
  assert.match(api, /\/model-profile/);
  assert.match(api, /regenerateSessionTitle/);
  assert.match(api, /\/title\/regenerate/);
  assert.match(api, /replayTurn/);
  assert.match(api, /\/turn\/replay/);
  assert.doesNotMatch(api, /\/api\/turns\/\$\{encodeURIComponent\(turnId\)\}\/events/);
});

test("HeroUI bridge replays a turn by trimming that turn and rerunning from the original user prompt", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-bridge-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_replay_turn", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="replay test")

captured = {}

def fake_run_agent_turn(sess, turn_id, prompt, images=None):
    captured["sid"] = sess.id
    captured["turn_id"] = turn_id
    captured["prompt"] = prompt
    captured["images"] = images

manager.run_agent_turn = fake_run_agent_turn

manager.add_message(session, "user", "第一轮问题", turn_id="ga|" + session.id + "|1", source="user")
manager.add_message(session, "assistant", "第一轮回答", turn_id="ga|" + session.id + "|1", responseId="resp-1", response_id="resp-1", source="assistant")
manager.add_event(session, {"type": "timeline.step", "turn_id": "ga|" + session.id + "|1", "data": {"id": "t1", "kind": "tool", "title": "第一轮工具", "status": "done"}})
manager.add_message(session, "user", "第二轮问题", turn_id="ga|" + session.id + "|2", source="user")
manager.add_message(session, "assistant", "第二轮旧回答", turn_id="ga|" + session.id + "|2", responseId="resp-2", response_id="resp-2", source="assistant")
manager.add_event(session, {"type": "timeline.step", "turn_id": "ga|" + session.id + "|2", "data": {"id": "t2", "kind": "tool", "title": "第二轮工具", "status": "done"}})
manager.store.upsert_agent_state(session.id, {
    "ga_history": ["[USER]: 第一轮问题", "[Agent] 第一轮回答", "[USER]: 第二轮问题", "[Agent] 第二轮旧回答"],
    "backend_history": [{"role": "assistant", "content": [{"type": "text", "text": "future"}]}],
    "working": {"key_info": "future state"},
    "llm_no": 0,
})

result = manager.replay_turn(session.id, "ga|" + session.id + "|2")

assert result["ok"] is True
assert captured["sid"] == session.id
assert captured["prompt"] == "第二轮问题"
assert captured["turn_id"] == "ga|" + session.id + "|2"
assert [message["content"] for message in session.messages] == ["第一轮问题", "第一轮回答", "第二轮问题"]
assert [event["data"]["id"] for event in session.events if event["type"] == "timeline.step"] == ["t1"]
assert manager.store.load_agent_state(session.id)["ga_history"] == ["[USER]: 第一轮问题", "[Agent] 第一轮回答"]
assert manager.store.load_agent_state(session.id)["llm_no"] == 0
assert session.status == "running"
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge exposes persisted SSE events with replay cursor", () => {
  assert.equal(existsSync(bridgePath), true);
  assert.equal(existsSync(bridgeRoutesPath), true);
  assert.equal(existsSync(bridgeStreamingPath), true);
  const bridge = readFileSync(bridgePath, "utf8");
  const routes = readFileSync(bridgeRoutesPath, "utf8");
  const streaming = readFileSync(bridgeStreamingPath, "utf8");
  const bridgeAndStreaming = `${bridge}\n${routes}\n${streaming}`;

  assert.match(bridge, /from .*streaming import|from bridge_core\.streaming import/);
  assert.match(bridgeAndStreaming, /class EventStreamHub/);
  assert.match(bridgeAndStreaming, /event_hub = EventStreamHub\(\)/);
  assert.match(bridgeAndStreaming, /async def events_handler\(self, request\):|async def events_handler\(request\):/);
  assert.match(bridgeAndStreaming, /text\/event-stream/);
  assert.match(bridgeAndStreaming, /after_event/);
  assert.match(bridgeAndStreaming, /Last-Event-ID/);
  assert.match(bridgeAndStreaming, /event_hub\.publish\(stored\)/);
  assert.match(bridgeAndStreaming, /app\.router\.add_get\("\/session\/\{sid\}\/events", (self\.)?events_handler\)/);
});

test("HeroUI bridge keeps aiohttp route handlers in bridge_core", () => {
  assert.equal(existsSync(bridgePath), true);
  assert.equal(existsSync(bridgeRoutesPath), true);
  const bridge = readFileSync(bridgePath, "utf8");
  const routes = readFileSync(bridgeRoutesPath, "utf8");

  assert.match(bridge, /from .*routes import|from bridge_core\.routes import/);
  assert.match(routes, /class BridgeRoutes/);
  assert.match(routes, /async def ws_handler\(self, request\)/);
  assert.match(routes, /async def status_handler\(self, request\)/);
  assert.match(routes, /async def path_open_handler\(self, request\)/);
  assert.match(routes, /def create_app\(self\)/);
});

test("HeroUI bridge keeps HTTP utility helpers in bridge_core", () => {
  assert.equal(existsSync(bridgePath), true);
  assert.equal(existsSync(bridgeRoutesPath), true);
  assert.equal(existsSync(bridgeHttpUtilsPath), true);
  const bridge = readFileSync(bridgePath, "utf8");
  const routes = readFileSync(bridgeRoutesPath, "utf8");
  const httpUtils = readFileSync(bridgeHttpUtilsPath, "utf8");
  const bridgeAndRoutes = `${bridge}\n${routes}`;

  assert.match(bridgeAndRoutes, /from .*http_utils import|from bridge_core\.http_utils import/);
  assert.match(httpUtils, /def cors_headers/);
  assert.match(httpUtils, /async def cors_middleware/);
  assert.match(httpUtils, /def json_ok/);
  assert.match(httpUtils, /def parse_positive_int/);
  assert.match(httpUtils, /async def read_json/);
});

test("HeroUI bridge maps model deltas, retracts, and process summaries", () => {
  assert.equal(existsSync(bridgePath), true);
  assert.equal(existsSync(bridgeEventsPath), true);
  const bridge = readFileSync(bridgePath, "utf8");
  const events = readFileSync(bridgeEventsPath, "utf8");
  const bridgeAndEvents = `${bridge}\n${events}`;

  assert.match(bridgeAndEvents, /event_type == "llm\.visible_delta"/);
  assert.match(bridgeAndEvents, /"type": "answer\.delta"/);
  assert.match(bridgeAndEvents, /"type": "answer\.retract"/);
  assert.match(bridgeAndEvents, /thinking_summary/);
  assert.match(bridgeAndEvents, /retract_response_id/);
  assert.match(bridgeAndEvents, /round_label\(ga_turn\)/);
});

test("HeroUI bridge live SSE filters by session before advancing cursor", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-bridge-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import asyncio
import importlib.util
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_sse_live", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class FakeRequest:
    def __init__(self, sid, query=None, headers=None):
        self.match_info = {"sid": sid}
        self.query = query or {}
        self.headers = headers or {}

class FakeStreamResponse:
    last = None

    def __init__(self, *args, **kwargs):
        self.writes = []
        FakeStreamResponse.last = self

    async def prepare(self, request):
        return None

    async def write(self, data):
        self.writes.append(bytes(data).decode("utf-8"))

    async def drain(self):
        return None

async def main():
    bridge.manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
    session = bridge.manager.create_session(cwd="E:/tmp/ga", title="sse live")
    turn_id = bridge.manager.make_turn_id(session.id, 1)
    queue = asyncio.Queue()
    await queue.put({
        "seq": 99,
        "type": "answer.delta",
        "turn_id": "ga|other-session|1",
        "session_id": "other-session",
        "data": {"delta": "leak"},
    })
    await queue.put({
        "seq": 1,
        "type": "turn.done",
        "turn_id": turn_id,
        "session_id": session.id,
        "data": {"ok": True},
    })

    original_stream = bridge.web.StreamResponse
    original_subscribe = bridge.event_hub.subscribe
    original_unsubscribe = bridge.event_hub.unsubscribe
    bridge.web.StreamResponse = FakeStreamResponse
    bridge.event_hub.subscribe = lambda session_id, turn_id="": queue
    bridge.event_hub.unsubscribe = lambda subscribed: None
    try:
        await asyncio.wait_for(
            bridge.events_handler(FakeRequest(session.id, query={"turn_id": turn_id})),
            timeout=1,
        )
    finally:
        bridge.web.StreamResponse = original_stream
        bridge.event_hub.subscribe = original_subscribe
        bridge.event_hub.unsubscribe = original_unsubscribe

    output = "".join(FakeStreamResponse.last.writes)
    assert "leak" not in output
    assert "id: 1" in output
    assert '"session_id": "' + session.id + '"' in output

asyncio.run(main())
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge SSE cursor parsing treats invalid values as zero", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-bridge-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import asyncio
import importlib.util
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_sse_cursor", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class FakeRequest:
    def __init__(self, sid, turn_id):
        self.match_info = {"sid": sid}
        self.query = {"after_event": "not-a-number", "turn_id": turn_id}
        self.headers = {"Last-Event-ID": "also-bad"}

class FakeStreamResponse:
    last = None

    def __init__(self, *args, **kwargs):
        self.writes = []
        FakeStreamResponse.last = self

    async def prepare(self, request):
        return None

    async def write(self, data):
        self.writes.append(bytes(data).decode("utf-8"))

    async def drain(self):
        return None

async def main():
    bridge.manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
    session = bridge.manager.create_session(cwd="E:/tmp/ga", title="sse cursor")
    turn_id = bridge.manager.make_turn_id(session.id, 1)
    bridge.manager.add_event(session, {
        "type": "turn.done",
        "turn_id": turn_id,
        "session_id": session.id,
        "data": {"ok": True},
    })

    original_stream = bridge.web.StreamResponse
    bridge.web.StreamResponse = FakeStreamResponse
    try:
        await bridge.events_handler(FakeRequest(session.id, turn_id))
    finally:
        bridge.web.StreamResponse = original_stream

    output = "".join(FakeStreamResponse.last.writes)
    assert "id: 1" in output
    assert "turn.done" in output

asyncio.run(main())
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge messages endpoint treats malformed cursors as safe defaults", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-bridge-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import asyncio
import importlib.util
import json
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_messages_cursor", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class FakeRequest:
    def __init__(self, sid):
        self.match_info = {"sid": sid}
        self.query = {"after": "bad", "limit": "bad", "after_event": "bad"}

async def main():
    bridge.manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
    session = bridge.manager.create_session(cwd="E:/tmp/ga", title="messages cursor")
    bridge.manager.add_message(session, "user", "hello", turn_id="ga|" + session.id + "|1")
    bridge.manager.add_event(session, {
        "type": "turn.done",
        "turn_id": "ga|" + session.id + "|1",
        "session_id": session.id,
        "data": {"ok": True},
    })

    response = await bridge.messages_handler(FakeRequest(session.id))
    payload = json.loads(response.text)
    assert payload["messages"][0]["content"] == "hello"
    assert payload["events"][0]["type"] == "turn.done"

asyncio.run(main())
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge scoped event subscriptions do not let other sessions evict relevant events", () => {
  const script = `
import asyncio
import importlib.util
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_scoped_hub", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

async def main():
    hub = bridge.EventStreamHub()
    queue = hub.subscribe("sess-target", "ga|sess-target|1")
    for i in range(1100):
        await hub._publish({
            "seq": i + 1,
            "type": "answer.delta",
            "turn_id": "ga|sess-other|1",
            "session_id": "sess-other",
            "data": {"delta": "noise"},
        })
    await hub._publish({
        "seq": 1,
        "type": "turn.done",
        "turn_id": "ga|sess-target|1",
        "session_id": "sess-target",
        "data": {"ok": True},
    })

    assert queue.qsize() == 1
    event = queue.get_nowait()
    assert event["session_id"] == "sess-target"
    assert event["type"] == "turn.done"

asyncio.run(main())
`;

  execFileSync("python", ["-c", script], { stdio: "pipe" });
});

test("HeroUI bridge switches model profile for idle sessions and blocks running sessions", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-bridge-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import sys
import types
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_profile_switch", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class Backend:
    def __init__(self, name, model):
        self.name = name
        self.model = model
        self.history = []

class Client:
    def __init__(self, name, model):
        self.backend = Backend(name, model)
        self.last_tools = ""

class FakeAgent:
    def __init__(self):
        self.llm_no = 0
        self.llmclients = [Client("primary", "gpt-a"), Client("backup", "gpt-b")]
        self.inc_out = False
        self.verbose = False
    def load_llm_sessions(self):
        return None
    def get_llm_name(self, client=None, model=False):
        client = client or self.llmclients[self.llm_no]
        return client.backend.model if model else client.backend.name
    def next_llm(self, n=-1):
        self.llm_no = ((self.llm_no + 1) if n < 0 else n) % len(self.llmclients)
        self.llmclient = self.llmclients[self.llm_no]
    def run(self):
        return None

sys.modules["agentmain"] = types.SimpleNamespace(GenericAgent=FakeAgent)

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd=bridge.DEFAULT_GA_ROOT, title="profile switch")
session.agent = manager.make_agent(session)

assert manager.list_model_profiles()[0]["active"] is True
result = manager.switch_model_profile("1", session.id)
assert result["activeProfileId"] == "1"
assert manager.selected_llm_no == 1
assert session.agent.llm_no == 1
assert result["profiles"][1]["active"] is True

next_session = manager.create_session(cwd=bridge.DEFAULT_GA_ROOT, title="next session")
next_agent = manager.make_agent(next_session)
assert next_agent.llm_no == 1

session.status = "running"
try:
    manager.switch_model_profile("0", session.id)
except bridge.web.HTTPConflict as exc:
    assert "session is running" in exc.text
else:
    raise AssertionError("running session switch should fail")
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge persists sessions and messages across manager restarts", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-bridge-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

db_path = ${JSON.stringify(dbPath)}
manager1 = bridge.AgentManager(db_path=db_path)
session = manager1.create_session(cwd="E:/tmp/ga", title="First chat")
manager1.add_message(session, "user", "hello from ui", turn_id="turn-1", source="user")
manager1.add_message(
    session,
    "assistant",
    "hello from ga",
    turn_id="turn-1",
    responseId="resp-1",
    response_id="resp-1",
    gaTurn=3,
    outputs=["thinking", "done"],
    source="assistant",
)

manager2 = bridge.AgentManager(db_path=db_path)
restored = list(manager2.sessions.values())
assert len(restored) == 1, restored
assert restored[0].id == session.id
assert restored[0].title == "First chat"
assert restored[0].cwd == "E:/tmp/ga"
assert restored[0].msg_seq == 2
assert len(restored[0].messages) == 2
assert restored[0].messages[0]["role"] == "user"
assert restored[0].messages[0]["turn_id"] == "turn-1"
assert restored[0].messages[1]["role"] == "assistant"
assert restored[0].messages[1]["responseId"] == "resp-1"
assert restored[0].messages[1]["response_id"] == "resp-1"
assert restored[0].messages[1]["gaTurn"] == 3
assert restored[0].messages[1]["outputs"] == ["thinking", "done"]
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge derives the first title from the first user message and first assistant reply summary", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-bridge-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import sys
import types
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_title", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

captured = {}

def fake_fast_ask(prompt, cfg_name):
    captured["prompt"] = prompt
    captured["cfg_name"] = cfg_name
    return "OpenAI 封号原因汇总"

fake_agentmain = types.ModuleType("agentmain")

class FakeBackend:
    def __init__(self):
        self.name = "newapi-native"
        self.model = "gpt-5.4"
        self.api_base = "https://example.invalid/v1"

class FakeGenericAgent:
    def __init__(self):
        self.llmclient = types.SimpleNamespace(backend=FakeBackend())

    def next_llm(self, llm_no):
        return None

    def get_llm_name(self, b=None, model=False):
        b = self.llmclient if b is None else b
        if model:
            return b.backend.model.lower()
        return f"{type(b.backend).__name__}/{b.backend.name}"

fake_agentmain.GenericAgent = FakeGenericAgent
sys.modules["agentmain"] = fake_agentmain

def fake_reload_mykeys():
    return (
        {
            "native_oai_config": {
                "name": "newapi-native",
                "model": "gpt-5.4",
                "apibase": "https://example.invalid/v1",
                "apikey": "sk-test",
            }
        },
        False,
    )

bridge.reload_mykeys = fake_reload_mykeys
bridge.fast_ask = fake_fast_ask
manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="新会话")
manager.selected_llm_no = 0
manager.add_message(session, "user", "去X站上找一下关于openai pro账号的封号和警告邮件的内容和原因", turn_id="turn-1", source="user")
manager.add_message(session, "assistant", "我整理了 OpenAI Pro 封号、警告邮件、触发原因与常见申诉路径。", turn_id="turn-1", responseId="resp-1", source="assistant")

assert session.title == "OpenAI 封号原因汇总"
assert "openai pro账号的封号" in captured["prompt"]
assert "警告邮件" in captured["prompt"]
assert "常见申诉路径" in captured["prompt"]

manager.add_message(session, "user", "第二条消息不应覆盖标题", turn_id="turn-2", source="user")
assert session.title == "OpenAI 封号原因汇总"
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge regenerates a session title from the latest user turns", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-bridge-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import sys
import types
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_regen_title", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

captured = {}

def fake_fast_ask(prompt, cfg_name):
    captured["prompt"] = prompt
    captured["cfg_name"] = cfg_name
    return "新的会话标题"

fake_agentmain = types.ModuleType("agentmain")

class FakeBackend:
    def __init__(self):
        self.name = "newapi-native"
        self.model = "gpt-5.4"
        self.api_base = "https://example.invalid/v1"

class FakeGenericAgent:
    def __init__(self):
        self.llmclient = types.SimpleNamespace(backend=FakeBackend())

    def next_llm(self, llm_no):
        return None

    def get_llm_name(self, b=None, model=False):
        b = self.llmclient if b is None else b
        if model:
            return b.backend.model.lower()
        return f"{type(b.backend).__name__}/{b.backend.name}"

fake_agentmain.GenericAgent = FakeGenericAgent
sys.modules["agentmain"] = fake_agentmain

def fake_reload_mykeys():
    return (
        {
            "native_oai_config": {
                "name": "newapi-native",
                "model": "gpt-5.4",
                "apibase": "https://example.invalid/v1",
                "apikey": "sk-test",
            }
        },
        False,
    )

bridge.reload_mykeys = fake_reload_mykeys
bridge.fast_ask = fake_fast_ask
manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
manager.selected_llm_no = 0
session = manager.create_session(cwd="E:/tmp/ga", title="旧标题")
manager.add_message(session, "user", "第一轮：讨论项目目标", persist=False)
manager.add_message(session, "assistant", "第一轮回复", persist=False)
manager.add_message(session, "user", "第二轮：确认页面布局", persist=False)
manager.add_message(session, "assistant", "第二轮回复", persist=False)
manager.add_message(session, "user", "第三轮：调整模型切换交互", persist=False)
manager.add_message(session, "assistant", "第三轮回复", persist=False)
manager.add_message(session, "user", "第四轮：收紧按钮样式", persist=False)
manager.add_message(session, "assistant", "第四轮回复", persist=False)
manager.add_message(session, "user", "第五轮：处理会话标题逻辑", persist=False)
manager.add_message(session, "assistant", "第五轮回复", persist=False)
manager.add_message(session, "user", "第六轮：把删除放进更多菜单", persist=False)

result = manager.regenerate_session_title(session.id)
assert result["ok"] is True
assert result["title"] == "新的会话标题"
assert session.title == "新的会话标题"
assert captured["cfg_name"] == "native_oai_config"
assert "第一轮" not in captured["prompt"]
assert "第二轮" in captured["prompt"]
assert "第六轮" in captured["prompt"]
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge route handlers restore persisted sessions and message detail", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-bridge-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import asyncio
import importlib.util
import json
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_routes", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

db_path = ${JSON.stringify(dbPath)}
bridge.manager = bridge.AgentManager(db_path=db_path)
session = bridge.manager.create_session(cwd="E:/tmp/ga", title="route restore")
bridge.manager.add_message(session, "user", "hello route", turn_id="turn-1", source="user")
bridge.manager.add_message(session, "assistant", "hello detail", turn_id="turn-1", responseId="resp-1")

bridge.manager = bridge.AgentManager(db_path=db_path)

class Request:
    def __init__(self, sid=None):
        self.match_info = {"sid": sid} if sid else {}

async def main():
    list_response = await bridge.list_sessions_handler(Request())
    listed = json.loads(list_response.text)
    assert listed["sessions"][0]["id"] == session.id
    assert listed["sessions"][0]["title"] == "route restore"

    detail_response = await bridge.get_session_handler(Request(session.id))
    detail = json.loads(detail_response.text)
    assert detail["session"]["id"] == session.id
    assert len(detail["messages"]) == 2
    assert detail["messages"][0]["content"] == "hello route"
    assert detail["messages"][1]["responseId"] == "resp-1"

asyncio.run(main())
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge exposes SOP metadata and on-demand SOP detail", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-sops-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const memoryDir = join(tempDir, "memory");
  mkdirSync(memoryDir, { recursive: true });
  writeFileSync(join(memoryDir, "plan_sop.md"), "# Plan Mode SOP\n\n用于**复杂任务**的 `auto_reports` 探索、计划、执行和验证。\n\n第二段不应丢失。", "utf8");
  writeFileSync(join(memoryDir, "notes.txt"), "not a SOP", "utf8");
  const script = `
import asyncio
import importlib.util
import json
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_sops", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

bridge.manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
bridge.manager.ga_root = ${JSON.stringify(tempDir)}

class Request:
    def __init__(self, sop_id=None):
        self.match_info = {"sop_id": sop_id} if sop_id else {}

async def main():
    list_response = await bridge.sops_handler(Request())
    listed = json.loads(list_response.text)
    assert len(listed["items"]) == 1
    item = listed["items"][0]
    assert item["id"] == "plan_sop"
    assert item["name"] == "plan_sop.md"
    assert item["title"] == "Plan Mode SOP"
    assert item["path"] == "memory/plan_sop.md"
    assert "用于复杂任务" in item["summary"]
    assert "auto_reports" in item["summary"]
    assert "**" not in item["summary"]
    assert "\`" not in item["summary"]
    assert "content" not in item

    detail_response = await bridge.sop_detail_handler(Request("plan_sop"))
    detail = json.loads(detail_response.text)
    assert detail["item"]["id"] == "plan_sop"
    assert "第二段不应丢失" in detail["content"]

asyncio.run(main())
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge updates an existing SOP inside memory only", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-sop-save-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const memoryDir = join(tempDir, "memory");
  mkdirSync(memoryDir, { recursive: true });
  writeFileSync(join(memoryDir, "plan_sop.md"), "# Old SOP\n\n旧内容", "utf8");
  const script = `
import asyncio
import importlib.util
import json
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_sop_save", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

bridge.manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
bridge.manager.ga_root = ${JSON.stringify(tempDir)}

class Request:
    can_read_body = True
    def __init__(self, sop_id, payload):
        self.match_info = {"sop_id": sop_id}
        self._payload = payload
    async def json(self):
        return self._payload

async def main():
    response = await bridge.sop_save_handler(Request("plan_sop", {"content": "# New SOP\\n\\n新内容"}))
    payload = json.loads(response.text)
    assert payload["item"]["id"] == "plan_sop"
    assert payload["item"]["title"] == "New SOP"
    assert payload["content"] == "# New SOP\\n\\n新内容"
    assert Path(${JSON.stringify(join(memoryDir, "plan_sop.md"))}).read_text(encoding="utf-8") == "# New SOP\\n\\n新内容"

    for bad_id in ["../outside", "missing_sop"]:
        try:
            await bridge.sop_save_handler(Request(bad_id, {"content": "bad"}))
        except bridge.web.HTTPNotFound:
            pass
        else:
            raise AssertionError("unsafe or missing SOP should not be written")

asyncio.run(main())
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge stores display prompt separately from the GA execution prompt", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-display-prompt-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_display_prompt", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="display prompt")

class FakeThread:
    def __init__(self, target, args, daemon=True, name=None):
        self.target = target
        self.args = args
        self.daemon = daemon
        self.name = name
    def start(self):
        pass

old_thread = bridge.threading.Thread
bridge.threading.Thread = FakeThread
try:
    manager.submit_prompt(
        session.id,
        "用户引用了以下 SOP：\\n- memory/plan_sop.md\\n\\n请先读取这些 SOP",
        display_prompt="@plan_sop\\n\\n这个适合什么时候用？",
    )
finally:
    bridge.threading.Thread = old_thread

message = session.messages[-1]
assert message["content"] == "@plan_sop\\n\\n这个适合什么时候用？"
assert "用户引用了以下 SOP" not in message["content"]
assert "用户引用了以下 SOP" in message["agent_prompt"]
assert session.thread.args[2] == message["agent_prompt"]
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge suppresses turn boundary phases and exposes model output content", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-bridge-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_events", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="event mapping")
turn_id = manager.make_turn_id(session.id, 1)
response_id = manager.make_response_id(turn_id, 1)

assert manager.convert_agent_event(session, turn_id, response_id, {"type": "turn.start", "turn": 1}) is None
assert manager.convert_agent_event(session, turn_id, response_id, {"type": "turn.end", "turn": 1}) is None

assert manager.convert_agent_event(session, turn_id, response_id, {"type": "llm.end", "turn": 1, "text": "最终回复正文", "has_tools": False}) is None

delta = manager.convert_agent_event(session, turn_id, response_id, {"type": "llm.visible_delta", "turn": 1, "delta": "我先查一下。"})
assert delta["type"] == "answer.delta"
assert delta["data"]["delta"] == "我先查一下。"
assert delta["data"]["response_id"] == response_id

event = manager.convert_agent_event(
    session,
    turn_id,
    response_id,
    {
        "type": "llm.end",
        "turn": 1,
        "text": "<summary>用户请求今日AI新闻，调用搜索获取</summary>我需要先搜索。",
        "has_tools": True,
        "elapsed_ms": 1234,
        "summary": "用户请求今日AI新闻，调用搜索获取",
        "thinking_summary": "用户请求今日AI新闻，调用搜索获取",
    },
)
assert event["type"] == "timeline.step"
assert event["data"]["title"] == "用户请求今日AI新闻，调用搜索获取"
assert event["data"]["summary"] == "用户请求今日AI新闻，调用搜索获取"
assert event["data"]["detail"] == ""
assert event["data"]["elapsed_ms"] == 1234
assert event["data"]["default_open"] is False
assert event["data"]["retract_response_id"] == response_id

tool = manager.convert_agent_event(session, turn_id, response_id, {"type": "tool.start", "turn": 1, "tool_name": "web_scan", "tool_kind": "search"})
assert tool["data"]["title"] == "第1轮 调用了 web_scan"
assert tool["data"]["tool_label"] == "第1轮"
assert "default_open" not in tool["data"]

ask_user_start = manager.convert_agent_event(session, turn_id, response_id, {"type": "tool.start", "turn": 1, "index": 1, "tool_name": "ask_user", "tool_kind": "help", "args": {"question": "继续吗？"}})
assert "default_open" not in ask_user_start["data"]

tool_delta = manager.convert_agent_event(session, turn_id, response_id, {"type": "tool.delta", "turn": 2, "index": 0, "tool_name": "file_read", "tool_kind": "read", "delta": "[Action] Reading file\\n"})
assert tool_delta["data"]["detail_delta"] == "[Action] Reading file\\n"
assert "output_delta" not in tool_delta["data"]

tool_done = manager.convert_agent_event(session, turn_id, response_id, {
    "type": "tool.end",
    "turn": 2,
    "index": 0,
    "tool_name": "file_read",
    "tool_kind": "read",
    "status": "done",
    "output": "[FILE] 268 lines\\n202| literal [Error] text",
    "detail": "[Action] Reading file\\n",
    "error": "",
    "elapsed_ms": 12,
})
assert tool_done["data"]["status"] == "done"
assert tool_done["data"]["output"].startswith("[FILE] 268 lines")
assert tool_done["data"]["detail"] == "[Action] Reading file\\n"
assert tool_done["data"]["error"] == ""

tool_failed = manager.convert_agent_event(session, turn_id, response_id, {
    "type": "tool.end",
    "turn": 2,
    "index": 1,
    "tool_name": "file_write",
    "tool_kind": "file",
    "status": "failed",
    "output": "",
    "detail": "[Status] failed\\n",
    "error": "No content found",
})
assert tool_failed["data"]["status"] == "failed"
assert tool_failed["data"]["detail"] == "[Status] failed\\n"
assert tool_failed["data"]["error"] == "No content found"

ask_user_done = manager.convert_agent_event(session, turn_id, response_id, {
    "type": "tool.end",
    "turn": 1,
    "index": 1,
    "tool_name": "ask_user",
    "tool_kind": "help",
    "status": "done",
    "result": {
        "status": "INTERRUPT",
        "intent": "HUMAN_INTERVENTION",
        "data": {
            "question": "请问你想让我做什么？",
            "candidates": ["继续演示工具", "换个话题", "执行实际任务"],
        },
    },
    "output": "用户确认继续",
    "elapsed_ms": 22,
})
assert ask_user_done["data"]["default_open"] is False
assert ask_user_done["data"]["interaction"] == {
    "status": "INTERRUPT",
    "intent": "HUMAN_INTERVENTION",
    "question": "请问你想让我做什么？",
    "candidates": ["继续演示工具", "换个话题", "执行实际任务"],
}

ask_user_unparsed = manager.convert_agent_event(session, turn_id, response_id, {
    "type": "tool.end",
    "turn": 1,
    "index": 2,
    "tool_name": "ask_user",
    "tool_kind": "help",
    "status": "done",
    "result": {
        "status": "INTERRUPT",
        "intent": "HUMAN_INTERVENTION",
        "data": {"question": "继续吗？"},
    },
    "output": '{"status":"INTERRUPT","intent":"HUMAN_INTERVENTION"}',
    "elapsed_ms": 22,
})
assert ask_user_unparsed["data"]["default_open"] is True
assert "interaction" not in ask_user_unparsed["data"]
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge does not resurrect deleted sessions from stale worker writes", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-bridge-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_delete", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="delete race")
manager.add_message(session, "user", "stale prompt", turn_id="turn-1", source="user")
manager.add_event(session, {"type": "timeline.step", "turn_id": "turn-1", "data": {"id": "step-1"}})
manager.delete_session(session.id)

# Simulate a stale background turn still holding the old Session object.
manager.add_message(session, "assistant", "late answer", turn_id="turn-1", responseId="resp-1")
manager.add_event(session, {"type": "turn.done", "turn_id": "turn-1", "data": {"ok": True}})
manager._persist_session(session)

reloaded = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
assert session.id not in reloaded.sessions

import sqlite3
with sqlite3.connect(${JSON.stringify(dbPath)}) as conn:
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge stores structured final text instead of raw verbose output", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-bridge-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import queue
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_structured_final", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class FakeAgent:
    structured_events = True
    inc_out = True

    def put_task(self, prompt, images=None):
        q = queue.Queue()
        q.put({"event": {"type": "agent.final", "turn": 1, "text": "clean final"}})
        q.put({"done": "**LLM Running**\\nraw tool log\\nclean final", "turn": 1, "outputs": ["raw tool log"]})
        return q

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="structured final")
session.agent = FakeAgent()
manager.run_agent_turn(session, "ga|" + session.id + "|1", "prompt")

assert session.messages[-1]["role"] == "assistant"
assert session.messages[-1]["content"] == "clean final"
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge retracts streamed model drafts before tool-turn model cards", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-bridge-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import queue
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_retract", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class FakeAgent:
    structured_events = True
    inc_out = True

    def put_task(self, prompt, images=None):
        q = queue.Queue()
        q.put({"event": {"type": "llm.visible_delta", "turn": 1, "delta": "我先查一下。"}})
        q.put({"event": {"type": "llm.end", "turn": 1, "text": "我先查一下。", "has_tools": True, "summary": "需要调用工具", "thinking_summary": "需要调用工具"}})
        q.put({"event": {"type": "agent.final", "turn": 1, "text": "最终回答"}})
        q.put({"event": {"type": "agent.done", "turn": 1}})
        q.put({"done": "raw log", "turn": 1, "outputs": []})
        return q

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="retract")
session.agent = FakeAgent()
turn_id = "ga|" + session.id + "|1"
manager.run_agent_turn(session, turn_id, "prompt")

types = [event["type"] for event in session.events]
assert types[:4] == ["answer.delta", "answer.retract", "timeline.step", "answer.final"], types
step = next(event for event in session.events if event["type"] == "timeline.step")
assert "retract_response_id" not in step["data"]
assert step["data"]["title"] == "需要调用工具"
assert step["data"]["default_open"] is False
assert session.messages[-1]["content"] == "最终回答"
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge keeps ask_user interruption inside the expanded tool card", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-bridge-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import queue
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_ask_user_card", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class FakeAgent:
    structured_events = True
    inc_out = True

    def put_task(self, prompt, images=None):
        q = queue.Queue()
        q.put({"event": {"type": "tool.start", "turn": 1, "index": 0, "tool_name": "ask_user", "tool_kind": "help", "args": {"question": "继续吗？", "candidates": ["继续", "停止"]}}})
        q.put({"event": {"type": "tool.end", "turn": 1, "index": 0, "tool_name": "ask_user", "tool_kind": "help", "status": "done", "result": {"status": "INTERRUPT", "intent": "HUMAN_INTERVENTION"}, "output": '{"status":"INTERRUPT","intent":"HUMAN_INTERVENTION"}', "detail": "Waiting for your answer ...\\n"}})
        q.put({"event": {"type": "agent.final", "turn": 1, "text": "不应该显示成正文"}})
        q.put({"done": "LLM Running (Turn 1) ...\\nTool: ask_user args:\\nraw legacy output", "turn": 1, "outputs": ["raw legacy output"]})
        return q

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="ask user")
session.agent = FakeAgent()
turn_id = "ga|" + session.id + "|1"
manager.run_agent_turn(session, turn_id, "prompt")

types = [event["type"] for event in session.events]
assert "timeline.step" in types, types
assert "turn.done" in types, types
assert "answer.final" not in types, types
step = [event for event in session.events if event["type"] == "timeline.step" and event["data"].get("tool_name") == "ask_user"][-1]
assert step["data"]["tool_name"] == "ask_user"
assert step["data"]["default_open"] is True
assert not any(message["role"] == "assistant" for message in session.messages), session.messages
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge synthesizes terminal events when a structured turn only emits done", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-bridge-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import queue
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_terminal_done", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class FakeAgent:
    structured_events = True
    inc_out = True

    def put_task(self, prompt, images=None):
        q = queue.Queue()
        q.put({"done": "plain final", "turn": 1, "outputs": []})
        return q

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="terminal done")
session.agent = FakeAgent()
turn_id = "ga|" + session.id + "|1"
manager.run_agent_turn(session, turn_id, "prompt")

types = [event["type"] for event in session.events]
assert "answer.final" in types, types
assert "turn.done" in types, types
assert session.messages[-1]["content"] == "plain final"
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge writes synthesized final answers before earlier agent.done terminal events", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-bridge-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import queue
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_terminal_order", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class FakeAgent:
    structured_events = True
    inc_out = True

    def put_task(self, prompt, images=None):
        q = queue.Queue()
        q.put({"event": {"type": "agent.done", "turn": 1}})
        q.put({"done": "final after terminal", "turn": 1, "outputs": []})
        return q

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="terminal order")
session.agent = FakeAgent()
turn_id = "ga|" + session.id + "|1"
manager.run_agent_turn(session, turn_id, "prompt")

types = [event["type"] for event in session.events]
assert types == ["answer.final", "turn.done"], types
assert session.events[0]["data"]["text"] == "final after terminal"
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge emits a terminal event when a structured turn is cancelled before completion", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-bridge-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import queue
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_terminal_cancel", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class FakeAgent:
    structured_events = True
    inc_out = True

    def put_task(self, prompt, images=None):
        return queue.Queue()

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="terminal cancel")
session.agent = FakeAgent()
session.cancel_requested = True
turn_id = "ga|" + session.id + "|1"
manager.run_agent_turn(session, turn_id, "prompt")

types = [event["type"] for event in session.events]
assert "turn.error" in types, types
assert session.status == "cancelled"
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge emits a terminal event when a structured turn raises after streaming begins", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-bridge-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_terminal_error", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class FailingQueue:
    def __init__(self):
        self.calls = 0

    def get(self, timeout=1.0):
        self.calls += 1
        if self.calls == 1:
            return {"event": {"type": "llm.visible_delta", "turn": 1, "delta": "hello"}}
        raise RuntimeError("boom")

class FakeAgent:
    structured_events = True
    inc_out = True

    def put_task(self, prompt, images=None):
        return FailingQueue()

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="terminal error")
session.agent = FakeAgent()
turn_id = "ga|" + session.id + "|1"
manager.run_agent_turn(session, turn_id, "prompt")

types = [event["type"] for event in session.events]
assert "answer.delta" in types, types
assert "turn.error" in types, types
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge restores sqlite agent state before submitting a restored session prompt", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-state-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_state_restore", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class FakeBackend:
    def __init__(self):
        self.history = []

class FakeClient:
    def __init__(self):
        self.backend = FakeBackend()

class FakeAgent:
    def __init__(self):
        self.history = []
        self.llmclient = FakeClient()
        self.handler = None
        self.llm_no = 0
        self.structured_events = False
        self.inc_out = False
        self.verbose = False
        self.seen_prompt = None

    def next_llm(self, n):
        self.llm_no = n

    def run(self):
        return None

    def put_task(self, prompt, images=None):
        self.seen_prompt = prompt
        import queue
        q = queue.Queue()
        q.put({"done": "restored answer", "turn": 1, "outputs": []})
        return q

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="restore")
manager.add_message(session, "user", "旧问题", turn_id="ga|" + session.id + "|1", source="user")
manager.store.upsert_agent_state(session.id, {
    "ga_history": ["[USER]: 旧问题", "[Agent] 旧回答"],
    "backend_history": [{"role": "user", "content": [{"type": "text", "text": "旧问题"}]}],
    "working": {"key_info": "old context"},
    "llm_no": 3,
})

fake = FakeAgent()
manager.make_agent = lambda sess: (bridge.restore_agent_state(fake, manager.load_continuation_state(sess)) or fake)
manager.run_agent_turn(session, "ga|" + session.id + "|2", "之前聊了什么？")

assert fake.history == ["[USER]: 旧问题", "[Agent] 旧回答"]
assert fake.llmclient.backend.history == [{"role": "user", "content": [{"type": "text", "text": "旧问题"}]}]
assert fake.llm_no == 3
assert fake.seen_prompt == "之前聊了什么？"
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge writes updated agent state after a completed turn", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-state-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_state_capture", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class FakeBackend:
    def __init__(self):
        self.history = []

class FakeClient:
    def __init__(self):
        self.backend = FakeBackend()

class FakeAgent:
    def __init__(self):
        self.history = []
        self.llmclient = FakeClient()
        self.handler = type("Handler", (), {"working": {"key_info": "captured"}})()
        self.llm_no = 2
        self.structured_events = False
        self.inc_out = False

    def put_task(self, prompt, images=None):
        self.history = ["[USER]: " + prompt, "[Agent] captured answer"]
        self.llmclient.backend.history = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        import queue
        q = queue.Queue()
        q.put({"done": "captured answer", "turn": 1, "outputs": []})
        return q

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="capture")
session.agent = FakeAgent()
manager.run_agent_turn(session, "ga|" + session.id + "|1", "保存状态")

state = manager.store.load_agent_state(session.id)
assert state["ga_history"] == ["[USER]: 保存状态", "[Agent] captured answer"]
assert state["backend_history"] == [{"role": "user", "content": [{"type": "text", "text": "保存状态"}]}]
assert state["working"] == {"key_info": "captured"}
assert state["llm_no"] == 2
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge waits for GA task completion before capturing terminal state", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-state-race-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import queue
import sys
import threading
import time
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_state_race", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class FakeBackend:
    def __init__(self):
        self.history = []

class FakeClient:
    def __init__(self):
        self.backend = FakeBackend()

class FakeAgent:
    def __init__(self):
        self.history = []
        self.llmclient = FakeClient()
        self.handler = type("Handler", (), {"working": {"key_info": "captured after task done"}})()
        self.llm_no = 2
        self.structured_events = False
        self.inc_out = False
        self.task_queue = queue.Queue()

    def put_task(self, prompt, images=None):
        self.task_queue.put({"query": prompt})
        display_q = queue.Queue()
        display_q.put({"done": "captured answer", "turn": 1, "outputs": []})

        def finish_after_done():
            time.sleep(0.2)
            self.history = ["[USER]: " + prompt, "[Agent] captured answer"]
            self.llmclient.backend.history = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
            self.task_queue.task_done()

        threading.Thread(target=finish_after_done, daemon=True).start()
        return display_q

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="capture race")
session.agent = FakeAgent()
manager.run_agent_turn(session, "ga|" + session.id + "|1", "保存状态")

state = manager.store.load_agent_state(session.id)
assert state["ga_history"] == ["[USER]: 保存状态", "[Agent] captured answer"]
assert state["backend_history"] == [{"role": "user", "content": [{"type": "text", "text": "保存状态"}]}]
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge fallback state excludes the currently submitted user turn", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-state-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_state_fallback", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="fallback")
manager.add_message(session, "user", "旧问题", turn_id="ga|" + session.id + "|1", source="user")
manager.add_message(session, "assistant", "旧回答", turn_id="ga|" + session.id + "|1", source="assistant")
current = manager.add_message(session, "user", "当前问题", turn_id="ga|" + session.id + "|2", source="user")
session.partial = {"turn_id": current["turn_id"]}

state = manager.load_continuation_state(session)

assert state["ga_history"] == ["[USER]: 旧问题", "[Agent] 旧回答"]
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge falls back to messages when stored agent state is corrupt", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-state-corrupt-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import sqlite3
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_corrupt_state", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="corrupt")
manager.add_message(session, "user", "旧问题", turn_id="ga|" + session.id + "|1", source="user")
manager.add_message(session, "assistant", "旧回答", turn_id="ga|" + session.id + "|1", source="assistant")

with sqlite3.connect(${JSON.stringify(dbPath)}) as conn:
    conn.execute(
        "INSERT OR REPLACE INTO agent_state (session_id, ga_history_json, backend_history_json, working_json, llm_no, state_version, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (session.id, "{bad json", "[]", "{}", 1, 1, 100.0),
    )
    conn.commit()

state = manager.load_continuation_state(session)
assert state["ga_history"] == ["[USER]: 旧问题", "[Agent] 旧回答"]
assert state["llm_no"] is None
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge persists a session model switch into agent state", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-model-state-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_model_state", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
manager.list_model_profiles = lambda: [
    {"id": "0", "name": "default", "active": False},
    {"id": "2", "name": "selected", "active": False},
]
session = manager.create_session(cwd="E:/tmp/ga", title="model")
manager.add_message(session, "user", "旧问题", turn_id="ga|" + session.id + "|1", source="user")

manager.switch_model_profile(2, session.id)

restored_manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
restored_session = restored_manager.get_session(session.id)
state = restored_manager.load_continuation_state(restored_session)
assert state["llm_no"] == 2
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge prefers persisted session model over global selected model on restore", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-model-restore-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import queue
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_model_restore", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class FakeBackend:
    def __init__(self):
        self.history = []

class FakeClient:
    def __init__(self):
        self.backend = FakeBackend()

class FakeAgent:
    def __init__(self):
        self.history = []
        self.llmclient = FakeClient()
        self.handler = type("Handler", (), {"working": {}})()
        self.llm_no = 0
        self.structured_events = False
        self.inc_out = False

    def next_llm(self, llm_no):
        self.llm_no = llm_no

    def put_task(self, prompt, images=None):
        q = queue.Queue()
        q.put({"done": "answer", "turn": 1, "outputs": []})
        return q

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="model restore")
manager.store.upsert_agent_state(session.id, {
    "ga_history": ["[USER]: old", "[Agent] old"],
    "backend_history": [],
    "working": {},
    "llm_no": 2,
})
manager.selected_llm_no = 0

fake = FakeAgent()
session.agent = fake
manager.run_agent_turn(session, "ga|" + session.id + "|2", "继续")

assert fake.llm_no == 2
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge replay preserves persisted session model over global selected model", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-replay-model-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import queue
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_replay_model", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class FakeBackend:
    def __init__(self):
        self.history = []

class FakeClient:
    def __init__(self):
        self.backend = FakeBackend()

class FakeAgent:
    def __init__(self):
        self.history = []
        self.llmclient = FakeClient()
        self.handler = type("Handler", (), {"working": {}})()
        self.llm_no = 0
        self.structured_events = False
        self.inc_out = False

    def next_llm(self, llm_no):
        self.llm_no = llm_no

    def put_task(self, prompt, images=None):
        q = queue.Queue()
        q.put({"done": "replayed", "turn": 1, "outputs": []})
        return q

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="replay model")
manager.add_message(session, "user", "第一轮问题", turn_id="ga|" + session.id + "|1", source="user")
manager.add_message(session, "assistant", "第一轮回答", turn_id="ga|" + session.id + "|1", source="assistant")
manager.add_message(session, "user", "第二轮问题", turn_id="ga|" + session.id + "|2", source="user")
manager.add_message(session, "assistant", "第二轮旧回答", turn_id="ga|" + session.id + "|2", source="assistant")
manager.store.upsert_agent_state(session.id, {
    "ga_history": ["[USER]: 第一轮问题", "[Agent] 第一轮回答", "[USER]: 第二轮问题", "[Agent] 第二轮旧回答"],
    "backend_history": [],
    "working": {},
    "llm_no": 2,
})
manager.selected_llm_no = 0
session.agent = FakeAgent()

manager.replay_turn(session.id, "ga|" + session.id + "|2")
session.thread.join(timeout=5)

assert manager.store.load_agent_state(session.id)["llm_no"] == 2
assert session.agent.llm_no == 2
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge replay truncates future turn events with future messages", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-replay-events-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import queue
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_replay_events", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class FakeBackend:
    def __init__(self):
        self.history = []

class FakeClient:
    def __init__(self):
        self.backend = FakeBackend()

class FakeAgent:
    def __init__(self):
        self.history = []
        self.llmclient = FakeClient()
        self.handler = type("Handler", (), {"working": {}})()
        self.llm_no = 0
        self.structured_events = False
        self.inc_out = False

    def put_task(self, prompt, images=None):
        self.history = ["[USER]: " + prompt, "[Agent] replayed"]
        q = queue.Queue()
        q.put({"done": "replayed", "turn": 1, "outputs": []})
        return q

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="replay events")
for index in range(1, 4):
    turn_id = "ga|" + session.id + "|" + str(index)
    manager.add_message(session, "user", "问题" + str(index), turn_id=turn_id, source="user")
    manager.add_message(session, "assistant", "回答" + str(index), turn_id=turn_id, source="assistant")
    manager.add_event(session, {"type": "timeline.step", "turn_id": turn_id, "session_id": session.id, "data": {"id": "tool-" + str(index)}})

session.agent = FakeAgent()
manager.replay_turn(session.id, "ga|" + session.id + "|2")
session.thread.join(timeout=5)

future_turn_id = "ga|" + session.id + "|3"
assert not any(message.get("turn_id") == future_turn_id for message in session.messages)
assert not any(event.get("turn_id") == future_turn_id for event in session.events)

loaded = manager.store.load_all_sessions()[session.id]
assert not any(message.get("turn_id") == future_turn_id for message in loaded.messages)
assert not any(event.get("turn_id") == future_turn_id for event in loaded.events)
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge clears stale existing-agent working after replay truncates state", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-state-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_replay_working", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class FakeBackend:
    def __init__(self):
        self.history = []

class FakeClient:
    def __init__(self):
        self.backend = FakeBackend()

class FakeAgent:
    def __init__(self):
        self.history = []
        self.llmclient = FakeClient()
        self.handler = type("Handler", (), {"working": {"key_info": "future state"}})()
        self.llm_no = 0
        self.structured_events = False
        self.inc_out = False
        self.seen_working_before_put_task = None

    def put_task(self, prompt, images=None):
        self.seen_working_before_put_task = dict(self.handler.working)
        import queue
        q = queue.Queue()
        q.put({"done": "replayed", "turn": 1, "outputs": []})
        return q

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="replay working")
manager.add_message(session, "user", "第一轮问题", turn_id="ga|" + session.id + "|1", source="user")
manager.add_message(session, "assistant", "第一轮回答", turn_id="ga|" + session.id + "|1", source="assistant")
manager.add_message(session, "user", "第二轮问题", turn_id="ga|" + session.id + "|2", source="user")
manager.add_message(session, "assistant", "第二轮旧回答", turn_id="ga|" + session.id + "|2", source="assistant")
manager.store.upsert_agent_state(session.id, {
    "ga_history": ["[USER]: 第一轮问题", "[Agent] 第一轮回答", "[USER]: 第二轮问题", "[Agent] 第二轮旧回答"],
    "backend_history": [],
    "working": {"key_info": "future state"},
    "llm_no": 3,
})

fake = FakeAgent()
session.agent = fake
manager.replay_turn(session.id, "ga|" + session.id + "|2")
session.thread.join(timeout=5)

assert fake.seen_working_before_put_task == {}
assert manager.store.load_agent_state(session.id)["working"] == {}
assert manager.store.load_agent_state(session.id)["llm_no"] == 3
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge merges saved working into the GA-created handler", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-handler-working-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import queue
import sys
import threading
import types
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_handler_working", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

runtime = types.ModuleType("fake_ga_runtime")

class RuntimeHandler:
    def __init__(self, agent, history, temp_dir):
        self.working = {}

runtime.GenericAgentHandler = RuntimeHandler
sys.modules[runtime.__name__] = runtime

class FakeBackend:
    def __init__(self):
        self.history = []

class FakeClient:
    def __init__(self):
        self.backend = FakeBackend()

class ExistingHandler:
    def __init__(self):
        self.working = {}

class FakeAgent:
    def __init__(self):
        self.history = []
        self.llmclient = FakeClient()
        self.handler = ExistingHandler()
        self.llm_no = 0
        self.structured_events = False
        self.inc_out = False
        self.task_queue = queue.Queue()
        self.seen_new_handler_working = None

    def put_task(self, prompt, images=None):
        self.task_queue.put({"query": prompt})
        display_q = queue.Queue()

        def run_like_ga():
            handler = runtime.GenericAgentHandler(self, self.history, "temp")
            if self.handler and "key_info" in self.handler.working:
                handler.working["key_info"] = self.handler.working["key_info"]
                handler.working["passed_sessions"] = self.handler.working.get("passed_sessions", 0) + 1
            self.handler = handler
            self.seen_new_handler_working = dict(handler.working)
            self.history = ["[USER]: " + prompt, "[Agent] answer"]
            display_q.put({"done": "answer", "turn": 1, "outputs": []})
            self.task_queue.task_done()

        threading.Thread(target=run_like_ga, daemon=True).start()
        return display_q

FakeAgent.__module__ = runtime.__name__

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="handler working")
manager.store.upsert_agent_state(session.id, {
    "ga_history": ["[USER]: old", "[Agent] old"],
    "backend_history": [],
    "working": {"key_info": "saved key", "passed_sessions": 2, "related_sop": "saved sop"},
    "llm_no": 0,
})

fake = FakeAgent()
session.agent = fake
manager.run_agent_turn(session, "ga|" + session.id + "|2", "继续")

assert fake.seen_new_handler_working["key_info"] == "saved key"
assert fake.seen_new_handler_working["passed_sessions"] == 3
assert fake.seen_new_handler_working["related_sop"] == "saved sop"
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("Vite development server proxies GA bridge endpoints", () => {
  assert.equal(existsSync(vitePath), true);
  const vite = readFileSync(vitePath, "utf8");

  assert.match(vite, /GA_HEROUI_API_TARGET/);
  assert.match(vite, /14169/);
  assert.match(vite, /"\/session"/);
  assert.match(vite, /"\/sessions"/);
  assert.match(vite, /"\/status"/);
  assert.match(vite, /"\/model-profile"/);
  assert.match(vite, /"\/sops"/);
});

test("HeroUI bridge persists Bridge-owned agent state without model_responses restore", () => {
  assert.equal(existsSync(bridgePath), true);
  const bridge = readFileSync(bridgePath, "utf8");

  assert.match(bridge, /from session_store import|import session_store/);
  assert.match(bridge, /from agent_state import|import agent_state/);
  assert.match(bridge, /agent_state/);
  assert.match(bridge, /restore_agent_state/);
  assert.match(bridge, /capture_agent_state/);
  assert.match(bridge, /upsert_agent_state/);
  assert.doesNotMatch(bridge, /extract_history/);
  assert.doesNotMatch(bridge, /compress_session/);
  assert.doesNotMatch(bridge, /model_responses.*restore/);
});

test("HeroUI bridge caps oversized tool.end output and detail to 64KB", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-cap-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_cap", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="cap")
turn_id = manager.make_turn_id(session.id, 1)
response_id = manager.make_response_id(turn_id, 1)

big = "x" * (200 * 1024)

# tool.end with huge output/detail should be truncated to ~64KB + marker
event = manager.convert_agent_event(session, turn_id, response_id, {
    "type": "tool.end",
    "turn": 1,
    "index": 0,
    "tool_name": "file_read",
    "tool_kind": "read",
    "status": "done",
    "output": big,
    "detail": big,
})
encoded_output = event["data"]["output"].encode("utf-8")
encoded_detail = event["data"]["detail"].encode("utf-8")
assert len(encoded_output) <= 64 * 1024 + 200, len(encoded_output)
assert len(encoded_detail) <= 64 * 1024 + 200, len(encoded_detail)
assert "truncated" in event["data"]["output"]
assert "truncated" in event["data"]["detail"]

# llm.end with huge detail should be truncated
llm = manager.convert_agent_event(session, turn_id, response_id, {
    "type": "llm.end",
    "turn": 1,
    "text": "summary text",
    "has_tools": True,
    "summary": "summary text",
    "thinking_summary": big,
})
encoded = llm["data"]["detail"].encode("utf-8")
assert len(encoded) <= 64 * 1024 + 200, len(encoded)
assert "truncated" in llm["data"]["detail"]

# small output/detail should pass through unchanged
small = "small output"
event_small = manager.convert_agent_event(session, turn_id, response_id, {
    "type": "tool.end",
    "turn": 1,
    "index": 0,
    "tool_name": "file_read",
    "tool_kind": "read",
    "status": "done",
    "output": small,
    "detail": small,
})
assert event_small["data"]["output"] == small
assert event_small["data"]["detail"] == small
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge caps oversized turn_outputs list to 256KB and item to 64KB", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-cap-outputs-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import queue
import sys
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_cap_outputs", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class FakeAgent:
    structured_events = True
    inc_out = True

    def put_task(self, prompt, images=None):
        q = queue.Queue()
        # one huge item (>64KB) and many small items that together exceed 256KB
        huge = "h" * (200 * 1024)
        outputs = [huge] + ["x" * 1024 for _ in range(300)]
        q.put({"done": "answer", "turn": 1, "outputs": outputs})
        return q

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="cap outputs")
session.agent = FakeAgent()
turn_id = "ga|" + session.id + "|1"
manager.run_agent_turn(session, turn_id, "prompt")

assistant = [m for m in session.messages if m["role"] == "assistant"][-1]
assert "outputs" in assistant, assistant
outputs = assistant["outputs"]
total = sum(len(s.encode("utf-8")) for s in outputs)
assert total <= 256 * 1024 + 200, total
# huge item must be truncated
assert any("truncated" in s for s in outputs)
# the chain stops before exhausting all 300 small items
assert len(outputs) < 300
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});

test("HeroUI bridge trims sess.events beyond 5000 entries and prunes the SQLite events table", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "ga-heroui-events-trim-"));
  const dbPath = join(tempDir, "sessions.sqlite3");
  const script = `
import importlib.util
import sys
import sqlite3
from pathlib import Path

bridge_path = Path(${JSON.stringify(bridgePath)})
spec = importlib.util.spec_from_file_location("heroui_bridge_under_test_events_trim", bridge_path)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

manager = bridge.AgentManager(db_path=${JSON.stringify(dbPath)})
session = manager.create_session(cwd="E:/tmp/ga", title="events trim")
for i in range(5050):
    manager.add_event(session, {
        "type": "timeline.step",
        "turn_id": "ga|" + session.id + "|1",
        "session_id": session.id,
        "data": {"id": "step-" + str(i), "kind": "tool", "title": "t", "status": "done"},
    })

assert len(session.events) == 5000, len(session.events)
# the oldest events should be the ones dropped
assert session.events[0]["data"]["id"] == "step-50", session.events[0]["data"]["id"]
assert session.events[-1]["data"]["id"] == "step-5049"

# SQLite events table should also have been pruned
with sqlite3.connect(${JSON.stringify(dbPath)}) as conn:
    count = conn.execute("SELECT COUNT(*) FROM events WHERE session_id = ?", (session.id,)).fetchone()[0]
    assert count == 5000, count
    # the lowest seq in SQLite should be at or above 51 (i.e. step-50's seq)
    min_seq = conn.execute("SELECT MIN(seq) FROM events WHERE session_id = ?", (session.id,)).fetchone()[0]
    assert min_seq >= 51, min_seq
`;

  try {
    execFileSync("python", ["-c", script], { stdio: "pipe" });
  } finally {
    rmSync(tempDir, { force: true, recursive: true });
  }
});
