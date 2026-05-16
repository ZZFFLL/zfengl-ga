from browser_indexer import build_browser_state_script, normalize_state_result


def test_build_browser_state_script_contains_index_state_and_limit():
    script = build_browser_state_script(include_invisible=False, max_elements=3)

    assert "window.__GA_BROWSER_ACTION_STATE__" in script
    assert "const maxElements = 3;" in script
    assert "const includeInvisible = false;" in script
    assert "a[href]" in script
    assert "[onclick]" in script
    assert "[contenteditable=\"true\"]" in script


def test_build_browser_state_script_defaults_to_visible_elements_only():
    script = build_browser_state_script()

    assert "const includeInvisible = false;" in script


def test_build_browser_state_script_clamps_max_elements():
    low = build_browser_state_script(max_elements=0)
    high = build_browser_state_script(max_elements=9999)

    assert "const maxElements = 1;" in low
    assert "const maxElements = 500;" in high


def test_build_browser_state_script_infers_native_roles():
    script = build_browser_state_script()

    assert "const nativeRoleOf = (element, tag, type) =>" in script
    assert 'if (tag === "a" && element.hasAttribute("href")) {' in script
    assert 'if (tag === "button") {' in script
    assert 'if (tag === "select") {' in script
    assert 'if (tag === "textarea") {' in script
    assert 'if (tag === "input") {' in script
    assert 'role: element.getAttribute("role") || nativeRoleOf(element, tag, type),' in script


def test_build_browser_state_script_separates_cached_nodes_from_snapshots():
    script = build_browser_state_script()

    assert "const snapshots = elements.map((element, index) =>" in script
    assert "const stateToken =" in script
    assert "window.__GA_BROWSER_ACTION_STATE__ = { token: stateToken, elements };" in script
    assert "state_token: stateToken," in script
    assert "elements: snapshots," in script


def test_build_browser_state_script_uses_collision_resistant_token():
    script = build_browser_state_script()

    assert "window.__GA_BROWSER_STATE_COUNTER__" in script
    assert "Math.random().toString(36).slice(2)" in script
    assert "const stateToken = `${Date.now()}:${window.__GA_BROWSER_STATE_COUNTER__}:${randomPart}:${elements.length}`;" in script


def test_build_browser_state_script_bounds_snapshot_text_and_value():
    script = build_browser_state_script()

    assert "return String(value || \"\").slice(0, 240);" in script
    assert "text: boundedText(textOf(element))," in script
    assert "value: boundedText(value)," in script


def test_normalize_state_result_adds_indices_and_defaults():
    raw = {
        "status": "success",
        "backend": "tmwd_user_chrome",
        "tab_id": "11",
        "url": "https://example.test",
        "title": "Example",
        "state_token": "abc",
        "viewport": {"width": 1280, "height": 720},
        "elements": [
            {"tag": "button", "text": "Submit", "bbox": {"x": 1, "y": 2, "width": 3, "height": 4}},
            {"index": 7, "tag": "input", "value": "secret", "type": "password"},
        ],
    }

    state = normalize_state_result(raw)

    assert state["status"] == "success"
    assert state["backend"] == "tmwd_user_chrome"
    assert state["tab_id"] == "11"
    assert state["state_token"] == "abc"
    assert state["elements"][0]["index"] == 1
    assert state["elements"][0]["visible"] is True
    assert state["elements"][0]["disabled"] is False
    assert state["elements"][1]["index"] == 7
    assert state["elements"][1]["value"] == "[REDACTED]"


def test_normalize_state_result_adds_top_level_defaults():
    state = normalize_state_result({"status": "success"})

    assert state["backend"] == ""
    assert state["tab_id"] == ""
    assert state["url"] == ""
    assert state["title"] == ""
    assert state["state_token"] == ""
    assert state["viewport"] == {}
    assert state["elements"] == []


def test_normalize_state_result_fills_element_defaults():
    element = normalize_state_result({"elements": [{}]})["elements"][0]

    assert element == {
        "index": 1,
        "tag": "",
        "type": "",
        "role": "",
        "text": "",
        "value": "",
        "visible": True,
        "disabled": False,
        "bbox": {},
        "selector_hint": "",
    }


def test_normalize_state_result_rejects_non_dict():
    state = normalize_state_result("not a dict")

    assert state == {
        "status": "failed",
        "stage": "dom_event",
        "error": "browser_state returned a non-object result",
    }


def test_normalize_state_result_preserves_failed_result():
    state = normalize_state_result({
        "status": "failed",
        "stage": "browser_unavailable",
        "error": "no tab",
    })

    assert state == {
        "status": "failed",
        "stage": "browser_unavailable",
        "error": "no tab",
    }


def test_normalize_state_result_fills_failed_result_defaults():
    state = normalize_state_result({"status": "failed"})

    assert state == {
        "status": "failed",
        "stage": "dom_event",
        "error": "browser_state failed",
    }
