from ga_browser_use.recipes import BrowserRecipeRunner


class FakeLayer:
    def __init__(self):
        self.calls = []
        self.find_results = [
            {"status": "success", "matches": [{"index": 10, "score": 0.9, "element": {"index": 10, "layer": "main"}}], "ambiguous": False},
            {"status": "success", "matches": [{"index": 22, "score": 0.95, "element": {"index": 22, "layer": "dropdown"}}], "ambiguous": False},
        ]

    def find(self, driver, **kwargs):
        self.calls.append(("find", kwargs))
        if len(self.find_results) > 1:
            return self.find_results.pop(0)
        return self.find_results[0]

    def run_action(self, driver, **kwargs):
        self.calls.append(("action", kwargs))
        return {"status": "success", "action": kwargs["action"], "index": kwargs.get("index")}

    def get_state(self, driver, **kwargs):
        self.calls.append(("state", kwargs))
        return {"status": "success", "elements": []}


def test_custom_select_recipe_runs_trigger_state_option_click():
    layer = FakeLayer()
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="custom_select", target={"query": "所属部门"}, option_text="研发部")

    assert result["status"] == "success"
    assert [call[0] for call in layer.calls] == ["find", "action", "state", "find", "action"]
    assert result["steps"][-1]["index"] == 22


def test_custom_select_requires_bounded_target_before_any_action():
    layer = FakeLayer()
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="custom_select", option_text="研发部")

    assert result["status"] == "failed"
    assert result["stage"] == "invalid_args"
    assert "target.query or target.index" in result["error"]
    assert layer.calls == []


def test_layer_select_requires_bounded_target_before_any_action():
    layer = FakeLayer()
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="layer_select", target={"query": "   "}, option_text="张三")

    assert result["status"] == "failed"
    assert result["stage"] == "invalid_args"
    assert "target.query or target.index" in result["error"]
    assert layer.calls == []


def test_custom_select_rejects_invalid_index_before_any_find():
    layer = FakeLayer()
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="custom_select", target={"index": 0}, option_text="研发部")

    assert result["status"] == "failed"
    assert result["stage"] == "invalid_args"
    assert "target.index must be a positive integer" in result["error"]
    assert layer.calls == []


def test_custom_select_option_search_does_not_hard_filter_popover():
    layer = FakeLayer()
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="custom_select", target={"query": "所属部门"}, option_text="研发部")

    assert result["status"] == "success"
    assert layer.calls[3][0] == "find"
    assert "layer" not in layer.calls[3][1]


def test_custom_select_refuses_main_layer_singleton_option_after_open():
    layer = FakeLayer()
    layer.find_results = [
        {"status": "success", "matches": [{"index": 10, "element": {"index": 10, "layer": "main"}}], "ambiguous": False},
        {"status": "success", "matches": [{"index": 22, "element": {"index": 22, "layer": "main"}}], "ambiguous": False},
    ]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="custom_select", target={"query": "所属部门"}, option_text="研发部")

    assert result["status"] == "failed"
    assert result["stage"] == "target_not_found"
    assert result["recipe"] == "custom_select"
    assert [call[0] for call in layer.calls] == ["find", "action", "state", "find"]


def test_layer_select_refuses_ambiguous_option():
    layer = FakeLayer()
    layer.find_results = [
        {"status": "success", "matches": [{"index": 10, "element": {"index": 10}}], "ambiguous": False},
        {
            "status": "success",
            "matches": [{"index": 21, "element": {"index": 21}}, {"index": 22, "element": {"index": 22}}],
            "ambiguous": True,
        },
    ]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="layer_select", target={"query": "人员"}, option_text="张三")

    assert result["status"] == "failed"
    assert result["stage"] == "ambiguous_target"
    assert result["recovery"]["code"] == "use_layer_select_recipe"


def test_layer_select_refuses_main_layer_singleton_confirm_after_open():
    layer = FakeLayer()
    layer.find_results = [
        {"status": "success", "matches": [{"index": 10, "element": {"index": 10, "layer": "main"}}], "ambiguous": False},
        {"status": "success", "matches": [{"index": 22, "element": {"index": 22, "layer": "dropdown"}}], "ambiguous": False},
        {"status": "success", "matches": [{"index": 30, "element": {"index": 30, "layer": "main"}}], "ambiguous": False},
    ]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="layer_select", target={"query": "人员"}, option_text="张三", confirm_text="确定")

    assert result["status"] == "failed"
    assert result["stage"] == "target_not_found"
    assert result["recipe"] == "layer_select"
    assert [call[0] for call in layer.calls] == ["find", "action", "state", "find", "action", "find"]


def test_layer_select_confirm_search_does_not_hard_filter_popover():
    layer = FakeLayer()
    layer.find_results = [
        {"status": "success", "matches": [{"index": 10, "element": {"index": 10, "layer": "main"}}], "ambiguous": False},
        {"status": "success", "matches": [{"index": 22, "element": {"index": 22, "layer": "dropdown"}}], "ambiguous": False},
        {"status": "success", "matches": [{"index": 30, "element": {"index": 30, "layer": "modal"}}], "ambiguous": False},
    ]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="layer_select", target={"query": "人员"}, option_text="张三", confirm_text="确定")

    assert result["status"] == "success"
    assert layer.calls[-2][0] == "find"
    assert "layer" not in layer.calls[-2][1]


def test_table_locate_returns_first_match_without_action():
    layer = FakeLayer()
    layer.find_results = [
        {"status": "success", "matches": [{"index": 7, "element": {"index": 7}}], "ambiguous": False}
    ]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="table_locate", table={"row_text": "张三", "column_text": "审批意见"})

    assert result["status"] == "success"
    assert result["matches"][0]["index"] == 7
    assert [call[0] for call in layer.calls] == ["find"]


def test_table_locate_failure_includes_steps_without_action():
    layer = FakeLayer()
    layer.find_results = [{"status": "failed", "stage": "target_not_found", "recovery": {"code": "refresh_state_then_find"}}]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="table_locate", table={"row_text": "张三"})

    assert result["status"] == "failed"
    assert result["steps"][0]["tool"] == "browser_find"
    assert [call[0] for call in layer.calls] == ["find"]


def test_table_locate_refuses_ambiguous_match():
    layer = FakeLayer()
    layer.find_results = [
        {
            "status": "success",
            "matches": [{"index": 7, "element": {"index": 7}}, {"index": 8, "element": {"index": 8}}],
            "ambiguous": True,
        }
    ]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="table_locate", table={"row_text": "张三", "column_text": "审批意见"})

    assert result["status"] == "failed"
    assert result["stage"] == "ambiguous_target"
    assert [candidate["index"] for candidate in result["candidates"]] == [7, 8]


def test_table_locate_requires_locator_constraints():
    layer = FakeLayer()
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="table_locate", table={})

    assert result["status"] == "failed"
    assert result["stage"] == "invalid_args"
    assert "header_text" in result["error"]
    assert layer.calls == []


def test_component_wait_returns_component_not_ready_on_timeout():
    layer = FakeLayer()
    layer.find_results = [{"status": "failed", "stage": "target_not_found", "recovery": {"code": "refresh_state_then_find"}}]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="component_wait", condition="options_visible", target={"query": "研发部"}, timeout=0)

    assert result["status"] == "failed"
    assert result["stage"] == "component_not_ready"
    assert result["recovery"]["code"] == "wait_component"
    assert result["recovery"]["next_args"]["target"] == {"query": "研发部"}
    assert result["recovery"]["next_args"]["max_results"] == 5


def test_component_wait_recovery_preserves_switch_tab_id():
    layer = FakeLayer()
    layer.find_results = [{"status": "failed", "stage": "target_not_found", "recovery": {"code": "refresh_state_then_find"}}]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(
        None,
        recipe="component_wait",
        condition="options_visible",
        target={"query": "研发部"},
        timeout=0,
        switch_tab_id="tab-b",
    )

    assert result["status"] == "failed"
    assert result["recovery"]["next_args"]["switch_tab_id"] == "tab-b"


def test_component_wait_polls_until_later_find_satisfies_condition():
    layer = FakeLayer()
    layer.find_results = [
        {"status": "failed", "stage": "target_not_found", "recovery": {"code": "refresh_state_then_find"}},
        {"status": "success", "matches": [{"index": 3, "element": {"index": 3}}], "ambiguous": False},
    ]
    runner = BrowserRecipeRunner(layer)
    runner._component_wait_poll_interval = 0

    result = runner.run(None, recipe="component_wait", condition="options_visible", target={"query": "研发部"}, timeout=1)

    assert result["status"] == "success"
    assert result["condition"] == "options_visible"
    assert result["match"]["index"] == 3
    assert [call[0] for call in layer.calls] == ["state", "find", "state", "find"]


def test_component_wait_element_enabled_can_use_later_enabled_match():
    layer = FakeLayer()
    layer.find_results = [
        {
            "status": "success",
            "matches": [
                {"index": 3, "element": {"index": 3, "disabled": True}},
                {"index": 4, "element": {"index": 4, "disabled": False}},
            ],
            "ambiguous": False,
        },
    ]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="component_wait", condition="element_enabled", target={"query": "提交"}, timeout=0)

    assert result["status"] == "success"
    assert result["match"]["index"] == 4


def test_component_wait_clamps_large_string_timeout():
    layer = FakeLayer()
    layer.find_results = [
        {"status": "success", "matches": [{"index": 3, "element": {"index": 3}}], "ambiguous": False},
    ]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="component_wait", condition="options_visible", target={"query": "研发部"}, timeout="999999")

    assert result["status"] == "success"
    assert result["timeout"] == 60


def test_component_wait_negative_timeout_clamps_to_minimum():
    layer = FakeLayer()
    layer.find_results = [
        {"status": "success", "matches": [{"index": 3, "element": {"index": 3}}], "ambiguous": False},
    ]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="component_wait", condition="options_visible", target={"query": "研发部"}, timeout=-10)

    assert result["status"] == "success"
    assert result["timeout"] == 1


def test_component_wait_rejects_index_target_for_indexed_wait_action():
    layer = FakeLayer()
    runner = BrowserRecipeRunner(layer)

    result = runner.run(
        None,
        recipe="component_wait",
        condition="element_enabled",
        target={"index": 5},
        timeout=7,
        switch_tab_id="tab-b",
    )

    assert result["status"] == "failed"
    assert result["stage"] == "invalid_args"
    assert result["recovery"]["next_tool"] == "browser_action"
    assert result["recovery"]["next_args"] == {
        "action": "wait_enabled",
        "index": 5,
        "timeout": 7,
        "switch_tab_id": "tab-b",
    }
    assert layer.calls == []


def test_component_wait_rejects_index_target_with_query_recovery_for_value_condition():
    layer = FakeLayer()
    runner = BrowserRecipeRunner(layer)

    result = runner.run(
        None,
        recipe="component_wait",
        condition="field_value",
        target={"index": 5, "query": "审批意见"},
        timeout=4,
        switch_tab_id="tab-b",
    )

    assert result["status"] == "failed"
    assert result["stage"] == "invalid_args"
    assert result["recovery"]["next_tool"] == "browser_recipe"
    assert result["recovery"]["next_args"] == {
        "recipe": "component_wait",
        "condition": "field_value",
        "target": {"query": "审批意见"},
        "timeout": 4,
        "switch_tab_id": "tab-b",
    }
    assert layer.calls == []


def test_component_wait_rejects_index_target_without_wait_index_for_closed_condition():
    layer = FakeLayer()
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="component_wait", condition="layer_closed", target={"index": 5}, timeout=4)

    assert result["status"] == "failed"
    assert result["stage"] == "invalid_args"
    assert result["recovery"]["next_tool"] == "browser_state"
    assert result["recovery"]["code"] == "use_query_component_wait"
    assert result["recovery"].get("next_args", {}) != {"action": "wait_index", "index": 5}
    assert layer.calls == []


def test_component_wait_rejects_invalid_index_before_recovery():
    layer = FakeLayer()
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="component_wait", condition="element_enabled", target={"index": 0}, timeout=4)

    assert result["status"] == "failed"
    assert result["stage"] == "invalid_args"
    assert "target.index must be a positive integer" in result["error"]
    assert result["recovery"]["next_tool"] == "browser_find"
    assert layer.calls == []


def test_component_wait_layer_closed_does_not_treat_state_missing_as_success():
    layer = FakeLayer()
    layer.find_results = [{"status": "failed", "stage": "state_missing", "recovery": {"code": "refresh_state"}}]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="component_wait", condition="layer_closed", target={"query": "弹层"}, timeout=0)

    assert result["status"] == "failed"
    assert result["stage"] == "component_not_ready"
    assert result["last_find"]["stage"] == "state_missing"


def test_component_wait_layer_closed_succeeds_on_target_not_found():
    layer = FakeLayer()
    layer.find_results = [{"status": "failed", "stage": "target_not_found", "recovery": {"code": "refresh_state_then_find"}}]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="component_wait", condition="layer_closed", target={"query": "弹层"}, timeout=0)

    assert result["status"] == "success"
    assert result["condition"] == "layer_closed"


def test_component_wait_layer_closed_requires_no_match():
    layer = FakeLayer()
    layer.find_results = [
        {"status": "success", "matches": [{"index": 1, "element": {"index": 1, "layer": "popover"}}], "ambiguous": False}
    ]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="component_wait", condition="layer_closed", target={"query": "弹层"}, timeout=0)

    assert result["status"] == "failed"
    assert result["stage"] == "component_not_ready"


def test_component_wait_element_enabled_rejects_disabled_match():
    layer = FakeLayer()
    layer.find_results = [
        {"status": "success", "matches": [{"index": 1, "element": {"index": 1, "disabled": True}}], "ambiguous": False}
    ]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="component_wait", condition="element_enabled", target={"query": "提交"}, timeout=0)

    assert result["status"] == "failed"
    assert result["stage"] == "component_not_ready"
