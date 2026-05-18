import json
from pathlib import Path

from ga_browser_use.actions import BrowserActionLayer
from ga_browser_use.runtime_log import log_event


class FakeDriver:
    default_session_id = "tab-1"

    def get_all_sessions(self):
        return ["tab-1"]

    def execute_js(self, _script, timeout=10):
        return {
            "status": "success",
            "state_token": "token-1",
            "tab_id": "tab-1",
            "url": "https://example.test/page?secret=1",
            "elements": [{"index": 1, "text": "审批正文", "value": "hidden-value"}],
        }


def read_log_lines(root: Path):
    files = list(root.glob("*/runtime.log"))
    assert len(files) == 1
    return [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]


def test_runtime_log_writes_sensitive_jsonl_under_dated_directory_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("GA_BROWSER_USE_LOG_ROOT", str(tmp_path))
    monkeypatch.delenv("GA_BROWSER_USE_LOG_SENSITIVE", raising=False)

    log_event(
        "browser_find",
        "end",
        fields={"status": "failed", "stage": "target_not_found"},
        sensitive={"query": "项目名称", "value": "研发项目", "password": "secret"},
    )

    lines = read_log_lines(tmp_path)

    assert lines[0]["tool"] == "browser_find"
    assert lines[0]["phase"] == "end"
    assert lines[0]["status"] == "failed"
    assert lines[0]["query"] == "项目名称"
    assert lines[0]["value"] == "研发项目"
    assert lines[0]["password"] == "secret"


def test_runtime_log_sensitive_switch_can_redact_values(monkeypatch, tmp_path):
    monkeypatch.setenv("GA_BROWSER_USE_LOG_ROOT", str(tmp_path))
    monkeypatch.setenv("GA_BROWSER_USE_LOG_SENSITIVE", "0")

    log_event(
        "browser_find",
        "end",
        fields={"status": "failed", "stage": "target_not_found", "url": "https://example.test/page?secret=1"},
        sensitive={"query": "项目名称", "value": "研发项目", "password": "secret"},
    )

    lines = read_log_lines(tmp_path)

    assert lines[0]["query"].startswith("[REDACTED")
    assert lines[0]["url"] == "https://example.test/page"
    raw = json.dumps(lines[0], ensure_ascii=False)
    assert "项目名称" not in raw
    assert "研发项目" not in raw
    assert "secret" not in raw


def test_runtime_log_sensitive_switch_on_allows_full_values(monkeypatch, tmp_path):
    monkeypatch.setenv("GA_BROWSER_USE_LOG_ROOT", str(tmp_path))
    monkeypatch.setenv("GA_BROWSER_USE_LOG_SENSITIVE", "1")

    log_event(
        "browser_action",
        "start",
        fields={"action": "input", "index": 3},
        sensitive={"text": "日报正文", "value": "完整值", "password": "secret"},
    )

    lines = read_log_lines(tmp_path)

    assert lines[0]["text"] == "日报正文"
    assert lines[0]["value"] == "完整值"
    assert lines[0]["password"] == "secret"


def test_runtime_log_can_be_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("GA_BROWSER_USE_LOG_ROOT", str(tmp_path))
    monkeypatch.setenv("GA_BROWSER_USE_LOG_ENABLED", "0")

    log_event("browser_state", "start", fields={"max_elements": 120})

    assert list(tmp_path.glob("*/runtime.log")) == []


def test_browser_action_layer_get_state_writes_runtime_log(monkeypatch, tmp_path):
    monkeypatch.setenv("GA_BROWSER_USE_LOG_ROOT", str(tmp_path))
    monkeypatch.delenv("GA_BROWSER_USE_LOG_SENSITIVE", raising=False)

    layer = BrowserActionLayer()

    result = layer.get_state(FakeDriver(), max_elements=5)

    lines = read_log_lines(tmp_path)
    assert result["status"] == "success"
    assert [line["phase"] for line in lines] == ["start", "end"]
    assert lines[0]["tool"] == "browser_state"
    assert lines[1]["element_count"] == 1
    assert lines[1]["url"] == "https://example.test/page?secret=1"
    assert lines[1]["elements"][0]["text"] == "审批正文"
    assert lines[1]["elements"][0]["value"] == "hidden-value"
    raw = json.dumps(lines, ensure_ascii=False)
    assert "审批正文" in raw
    assert "hidden-value" in raw
    assert "secret=1" in raw
