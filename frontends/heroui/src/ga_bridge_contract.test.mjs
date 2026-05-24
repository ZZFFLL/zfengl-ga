import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const herouiRoot = new URL("..", import.meta.url);
const herouiPath = fileURLToPath(herouiRoot);
const apiPath = join(herouiPath, "src", "api.ts");
const bridgePath = join(herouiPath, "bridge.py");
const vitePath = join(herouiPath, "vite.config.ts");

test("HeroUI frontend has a dedicated GenericAgent bridge copy", () => {
  assert.equal(existsSync(bridgePath), true);
  const bridge = readFileSync(bridgePath, "utf8");

  assert.match(bridge, /GenericAgent HeroUI Bridge/);
  assert.match(bridge, /HEROUI_BRIDGE_PORT/);
  assert.match(bridge, /APP_DIR \/ "dist"/);
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
  assert.match(bridge, /events: List\[dict\] = field\(default_factory=list\)/);
  assert.match(bridge, /event_seq: int = 0/);
  assert.match(bridge, /CREATE TABLE IF NOT EXISTS events/);
  assert.match(bridge, /def add_event/);
  assert.match(bridge, /def convert_agent_event/);
  assert.match(bridge, /agent\.structured_events = True/);
  assert.match(bridge, /def _persist_session_and_message/);
  assert.match(bridge, /persist=False/);
  assert.doesNotMatch(bridge, /self\._persist_message\(sess, user_msg\)/);
  assert.match(bridge, /app\.router\.add_post\("\/session\/new", new_session_handler\)/);
  assert.match(bridge, /app\.router\.add_get\("\/session\/\{sid\}\/messages", messages_handler\)/);
  assert.match(bridge, /app\.router\.add_post\("\/model-profile", switch_model_profile_handler\)/);
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
  assert.match(api, /turn_id: message\.turn_id/);
  assert.match(api, /response_id: message\.responseId/);
  assert.match(api, /response_id: message\.responseId \|\| message\.response_id/);
  assert.match(api, /switchModelProfile/);
  assert.match(api, /\/model-profile/);
  assert.doesNotMatch(api, /new EventSource/);
  assert.doesNotMatch(api, /\/api\/turns\/\$\{encodeURIComponent\(turnId\)\}\/events/);
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

test("Vite development server proxies GA bridge endpoints", () => {
  assert.equal(existsSync(vitePath), true);
  const vite = readFileSync(vitePath, "utf8");

  assert.match(vite, /GA_HEROUI_API_TARGET/);
  assert.match(vite, /14169/);
  assert.match(vite, /"\/session"/);
  assert.match(vite, /"\/sessions"/);
  assert.match(vite, /"\/status"/);
  assert.match(vite, /"\/model-profile"/);
});
