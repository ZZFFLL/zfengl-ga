import importlib.util
import re
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STORE_PATH = ROOT / "frontends" / "heroui" / "session_store.py"


def load_store():
    spec = importlib.util.spec_from_file_location("heroui_session_store_under_test", STORE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_init_store_creates_agent_state_without_log_restore(tmp_path):
    store_mod = load_store()
    db_path = tmp_path / "sessions.sqlite3"

    store = store_mod.SessionStore(db_path)

    with sqlite3.connect(db_path) as conn:
        names = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }

    source = STORE_PATH.read_text(encoding="utf-8").lower()

    assert {"sessions", "messages", "events", "agent_state"}.issubset(names)
    assert not hasattr(store, "import_model_responses")
    assert "import_model_responses" not in source
    assert "temp/model_responses" not in source.replace("\\", "/")
    assert not re.search(r"(restore|import|load|read).*model_responses", source)
    assert not re.search(r"model_responses.*(restore|import|load|read)", source)


def test_session_message_event_and_agent_state_round_trip(tmp_path):
    store_mod = load_store()
    store = store_mod.SessionStore(tmp_path / "sessions.sqlite3")

    session = {
        "id": "sess-1",
        "title": "SQLite test",
        "cwd": "E:/tmp/ga",
        "created_at": 100.0,
        "updated_at": 101.0,
        "status": "idle",
        "msg_seq": 2,
        "last_error": "",
    }
    user_message = {
        "id": 1,
        "role": "user",
        "content": "之前我们讨论了什么？",
        "ts": 102.0,
        "turn_id": "ga|sess-1|1",
        "source": "user",
    }
    event = {
        "seq": 1,
        "turn_id": "ga|sess-1|1",
        "type": "timeline.step",
        "ts": 103.0,
        "session_id": "sess-1",
        "data": {"id": "tool-1", "tool_name": "file_read", "status": "done"},
    }
    state = {
        "ga_history": ["[USER]: 之前我们讨论了什么？", "[Agent] 讨论了 SQLite 持久化"],
        "backend_history": [{"role": "user", "content": [{"type": "text", "text": "之前我们讨论了什么？"}]}],
        "working": {"key_info": "Bridge-owned state"},
        "llm_no": 1,
    }

    store.upsert_session(session)
    store.upsert_message("sess-1", user_message)
    store.upsert_event("sess-1", event)
    store.upsert_agent_state("sess-1", state)

    loaded = store.load_all_sessions()
    assert list(loaded) == ["sess-1"]
    assert loaded["sess-1"].messages[0]["content"] == "之前我们讨论了什么？"
    assert loaded["sess-1"].events[0]["data"]["tool_name"] == "file_read"
    assert store.load_agent_state("sess-1")["ga_history"] == state["ga_history"]
    assert store.load_agent_state("sess-1")["backend_history"] == state["backend_history"]
    assert store.load_agent_state("sess-1")["working"] == state["working"]
    assert store.load_agent_state("sess-1")["llm_no"] == 1


def test_delete_session_removes_messages_events_and_agent_state(tmp_path):
    store_mod = load_store()
    store = store_mod.SessionStore(tmp_path / "sessions.sqlite3")
    store.upsert_session({
        "id": "sess-delete",
        "title": "Delete",
        "cwd": "E:/tmp/ga",
        "created_at": 100.0,
        "updated_at": 101.0,
        "status": "idle",
        "msg_seq": 1,
        "last_error": "",
    })
    store.upsert_message("sess-delete", {"id": 1, "role": "user", "content": "x", "ts": 102.0})
    store.upsert_event("sess-delete", {"seq": 1, "turn_id": "ga|sess-delete|1", "type": "turn.done", "ts": 103.0})
    store.upsert_agent_state("sess-delete", {"ga_history": ["[USER]: x"], "backend_history": [], "working": {}, "llm_no": 0})

    store.delete_session("sess-delete")

    assert store.load_all_sessions() == {}
    assert store.load_agent_state("sess-delete") is None


def test_delete_agent_state_preserves_session_messages_and_events(tmp_path):
    store_mod = load_store()
    store = store_mod.SessionStore(tmp_path / "sessions.sqlite3")
    store.upsert_session({
        "id": "sess-state",
        "title": "State",
        "cwd": "E:/tmp/ga",
        "created_at": 100.0,
        "updated_at": 101.0,
        "status": "idle",
        "msg_seq": 1,
        "last_error": "",
    })
    store.upsert_message("sess-state", {"id": 1, "role": "user", "content": "x", "ts": 102.0})
    store.upsert_event("sess-state", {"seq": 1, "turn_id": "ga|sess-state|1", "type": "turn.done", "ts": 103.0})
    store.upsert_agent_state("sess-state", {"ga_history": ["future"], "backend_history": [], "working": {}, "llm_no": 0})

    store.delete_agent_state("sess-state")

    loaded = store.load_all_sessions()
    assert list(loaded) == ["sess-state"]
    assert loaded["sess-state"].messages[0]["content"] == "x"
    assert loaded["sess-state"].events[0]["type"] == "turn.done"
    assert store.load_agent_state("sess-state") is None


def test_corrupt_agent_state_json_returns_none_for_message_fallback(tmp_path):
    store_mod = load_store()
    store = store_mod.SessionStore(tmp_path / "sessions.sqlite3")
    store.upsert_session({
        "id": "sess-corrupt",
        "title": "Corrupt",
        "cwd": "E:/tmp/ga",
        "created_at": 100.0,
        "updated_at": 101.0,
        "status": "idle",
        "msg_seq": 1,
        "last_error": "",
    })
    with sqlite3.connect(tmp_path / "sessions.sqlite3") as conn:
        conn.execute(
            """
            INSERT INTO agent_state (
                session_id, ga_history_json, backend_history_json, working_json,
                llm_no, state_version, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("sess-corrupt", "{bad json", "[]", "{}", 1, store_mod.STATE_VERSION, 102.0),
        )
        conn.commit()

    assert store.load_agent_state("sess-corrupt") is None
