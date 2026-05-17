from ga_browser_use.results import (
    FailureFuse,
    add_recovery,
    failed_result,
    recovery_for_stage,
)


def test_failed_result_includes_recovery_for_state_missing():
    result = failed_result("click", "state_missing", "Run browser_state before browser_action click.", 4)

    assert result["status"] == "failed"
    assert result["stage"] == "state_missing"
    assert result["recovery"]["code"] == "refresh_state"
    assert result["recovery"]["next_tool"] == "browser_state"
    assert result["recovery"]["stop_retry"] is False


def test_recovery_for_custom_select_misuse_points_to_recipe():
    recovery = recovery_for_stage("control_unsupported", action="select")

    assert recovery["code"] == "use_custom_select_recipe"
    assert recovery["next_tool"] == "browser_recipe"
    assert recovery["next_args"]["recipe"] == "custom_select"


def test_add_recovery_preserves_hint_and_suggested_args():
    result = {"status": "failed", "stage": "state_missing", "hint": "old", "suggested_args": {"action": "keys"}}

    updated = add_recovery(result, action="keys", index=8)

    assert updated["hint"] == "old"
    assert updated["suggested_args"] == {"action": "keys"}
    assert updated["recovery"]["code"] == "use_focused_keys"


def test_failure_fuse_ignores_success_results():
    fuse = FailureFuse()
    success = {"status": "success", "action": "click", "index": 5, "result": "clicked"}

    first = fuse.record(success, tab_id="tab-1", url="https://example.test/form", target={})
    second = fuse.record(success, tab_id="tab-1", url="https://example.test/form", target={})
    third = fuse.record(success, tab_id="tab-1", url="https://example.test/form", target={})

    assert first == success
    assert second == success
    assert third == success
    assert "recovery" not in third


def test_add_recovery_merges_suggested_args_into_recovery_next_args():
    result = {
        "status": "failed",
        "stage": "state_missing",
        "suggested_args": {"action": "keys", "text": "Enter"},
    }

    updated = add_recovery(result, action="keys", index=8)

    assert updated["recovery"]["code"] == "use_focused_keys"
    assert updated["recovery"]["next_args"] == {"action": "keys", "text": "Enter"}


def test_add_recovery_copies_existing_recovery_before_mutation():
    recovery = {"code": "custom", "message": "keep", "stop_retry": False, "next_args": {"action": "click"}}
    result = {"status": "failed", "stage": "custom", "recovery": recovery}

    updated = add_recovery(result, action="click", index=3)
    updated["recovery"]["stop_retry"] = True
    updated["recovery"]["next_args"]["index"] = 3

    assert recovery == {"code": "custom", "message": "keep", "stop_retry": False, "next_args": {"action": "click"}}


def test_failure_fuse_blocks_third_identical_failure():
    fuse = FailureFuse()
    result = {"status": "failed", "stage": "stale_index", "action": "click", "index": 5}
    target = {"stable_key": "button#save", "selector_hint": "button#save", "text": "Save"}

    first = fuse.record(result, tab_id="tab-1", url="https://example.test/form", target=target)
    second = fuse.record(result, tab_id="tab-1", url="https://example.test/form", target=target)
    third = fuse.record(result, tab_id="tab-1", url="https://example.test/form", target=target)

    assert first["stage"] == "stale_index"
    assert first["recovery"]["stop_retry"] is False
    assert second["recovery"]["stop_retry"] is True
    assert third["stage"] == "repeat_blocked"
    assert third["recovery"]["code"] == "stop_repeating"


def test_failure_fuse_resets():
    fuse = FailureFuse()
    result = {"status": "failed", "stage": "stale_index", "action": "click", "index": 5}

    fuse.record(result, tab_id="tab-1", url="https://example.test/form", target={})
    fuse.reset()
    after_reset = fuse.record(result, tab_id="tab-1", url="https://example.test/form", target={})

    assert after_reset["stage"] == "stale_index"
    assert after_reset["recovery"]["stop_retry"] is False
