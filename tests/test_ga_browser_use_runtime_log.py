import re
from pathlib import Path

import ga_browser_use.runtime_log as runtime_log
from ga_browser_use.actions import BrowserActionLayer
from ga_browser_use.recipes import BrowserRecipeRunner
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
            "elements": [{"index": 1, "role": "textbox", "control_kind": "textarea", "text": "审批正文", "value": "hidden-value"}],
        }


class FakeRecipeLayer:
    def __init__(self):
        self.find_results = [
            {"status": "success", "matches": [{"index": 4, "score": 0.9, "reason": "field row label", "element": {"index": 4, "layer": "main", "text": "工作类型"}}], "ambiguous": False},
            {"status": "success", "matches": [{"index": 22, "score": 0.95, "reason": "overlay option", "element": {"index": 22, "layer": "dropdown", "text": "代码开发"}}], "ambiguous": False},
            {"status": "success", "matches": [{"index": 4, "score": 0.9, "element": {"index": 4, "layer": "main", "value": "代码开发"}}], "ambiguous": False},
            {"status": "failed", "stage": "target_not_found", "recovery": {"code": "refresh_state_then_find"}},
        ]

    def find(self, driver, **kwargs):
        if len(self.find_results) > 1:
            return self.find_results.pop(0)
        return self.find_results[0]

    def run_action(self, driver, **kwargs):
        return {"status": "success", "action": kwargs["action"], "index": kwargs.get("index"), "page_changed": True}

    def get_state(self, driver, **kwargs):
        return {"status": "success", "elements": []}


def read_audit_log(root: Path) -> str:
    files = list(root.glob("*/audit-*.log"))
    assert len(files) == 1
    return files[0].read_text(encoding="utf-8")


def test_runtime_log_writes_readable_entry_with_sensitive_values_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("GA_BROWSER_USE_LOG_ROOT", str(tmp_path))
    monkeypatch.delenv("GA_BROWSER_USE_LOG_SENSITIVE", raising=False)

    log_event(
        "browser_find",
        "end",
        fields={"status": "failed", "stage": "target_not_found"},
        sensitive={"query": "项目名称", "value": "研发项目", "password": "secret"},
    )

    text = read_audit_log(tmp_path)

    assert re.search(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}\]", text)
    assert not re.search(r"\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\]", text)
    assert "browser_find END" in text
    assert "result:" in text
    assert 'query: "项目名称"' in text
    assert 'value: "研发项目"' in text
    assert "password: secret" in text


def test_runtime_log_sensitive_switch_can_redact_values(monkeypatch, tmp_path):
    monkeypatch.setenv("GA_BROWSER_USE_LOG_ROOT", str(tmp_path))
    monkeypatch.setenv("GA_BROWSER_USE_LOG_SENSITIVE", "0")

    log_event(
        "browser_find",
        "end",
        fields={"status": "failed", "stage": "target_not_found", "url": "https://example.test/page?secret=1"},
        sensitive={"query": "项目名称", "value": "研发项目", "password": "secret"},
    )

    text = read_audit_log(tmp_path)

    assert "browser_find END" in text
    assert "query: [REDACTED len=4]" in text
    assert "value: [REDACTED len=4]" in text
    assert "password: [REDACTED len=6]" in text
    assert 'url: "https://example.test/page"' in text
    assert "项目名称" not in text
    assert "研发项目" not in text
    assert "secret=1" not in text


def test_runtime_log_can_be_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("GA_BROWSER_USE_LOG_ROOT", str(tmp_path))
    monkeypatch.setenv("GA_BROWSER_USE_LOG_ENABLED", "0")

    log_event("browser_state", "start", fields={"max_elements": 120})

    assert list(tmp_path.glob("*/audit-*.log")) == []


def test_runtime_log_separates_events_with_blank_line(monkeypatch, tmp_path):
    monkeypatch.setenv("GA_BROWSER_USE_LOG_ROOT", str(tmp_path))
    monkeypatch.delenv("GA_BROWSER_USE_LOG_SENSITIVE", raising=False)

    log_event("browser_state", "start", fields={"max_elements": 120})
    log_event("browser_state", "end", fields={"status": "success"})

    text = read_audit_log(tmp_path)

    assert "\n\n[" in text
    assert text.endswith("\n\n")


def test_runtime_log_rotates_when_file_reaches_size_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("GA_BROWSER_USE_LOG_ROOT", str(tmp_path))
    monkeypatch.delenv("GA_BROWSER_USE_LOG_SENSITIVE", raising=False)
    monkeypatch.setattr(runtime_log, "MAX_LOG_FILE_BYTES", 400)

    payload = {"status": "success", "message": "x" * 180}

    log_event("browser_state", "start", fields=payload)
    log_event("browser_state", "end", fields=payload)

    day_dirs = list(tmp_path.iterdir())
    assert len(day_dirs) == 1
    day_dir = day_dirs[0]

    files = sorted(day_dir.glob("audit-*.log"))
    assert len(files) == 2
    assert all(re.fullmatch(r"audit-\d{14}\.log", path.name) for path in files)
    assert all(path.stat().st_size <= 400 for path in files)


def test_browser_action_layer_get_state_logs_readable_request_and_result(monkeypatch, tmp_path):
    monkeypatch.setenv("GA_BROWSER_USE_LOG_ROOT", str(tmp_path))
    monkeypatch.delenv("GA_BROWSER_USE_LOG_SENSITIVE", raising=False)

    layer = BrowserActionLayer()

    result = layer.get_state(FakeDriver(), max_elements=5)

    text = read_audit_log(tmp_path)
    assert result["status"] == "success"
    assert "browser_state START" in text
    assert "request:" in text
    assert "max_elements: 5" in text
    assert "browser_state END" in text
    assert "result:" in text
    assert "status: success" in text
    assert "element_count: 1" in text
    assert "elements_preview:" in text
    assert "index=1" in text
    assert 'text="审批正文"' in text
    assert "value=hidden-value" in text
    assert 'url: "https://example.test/page?secret=1"' in text


def test_browser_recipe_logs_readable_steps(monkeypatch, tmp_path):
    monkeypatch.setenv("GA_BROWSER_USE_LOG_ROOT", str(tmp_path))
    monkeypatch.delenv("GA_BROWSER_USE_LOG_SENSITIVE", raising=False)

    runner = BrowserRecipeRunner(FakeRecipeLayer())

    result = runner.run(FakeDriver(), recipe="custom_select", target={"query": "工作类型"}, option_text="代码开发")

    text = read_audit_log(tmp_path)
    assert result["status"] == "success"
    assert "browser_recipe START" in text
    assert "recipe: custom_select" in text
    assert 'option_text: "代码开发"' in text
    assert "browser_recipe END" in text
    assert "steps:" in text
    assert "browser_find status=success" in text
    assert "browser_action status=success action=click index=4" in text
