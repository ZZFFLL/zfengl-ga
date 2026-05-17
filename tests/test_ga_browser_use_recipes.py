from ga_browser_use.recipes import BrowserRecipeRunner


class FakeLayer:
    def __init__(self):
        self.calls = []
        self.find_results = [
            {"status": "success", "matches": [{"index": 10, "score": 0.9, "element": {"index": 10}}], "ambiguous": False},
            {"status": "success", "matches": [{"index": 22, "score": 0.95, "element": {"index": 22}}], "ambiguous": False},
        ]

    def find(self, driver, **kwargs):
        self.calls.append(("find", kwargs))
        return self.find_results.pop(0)

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


def test_custom_select_option_search_prefers_overlay_layer():
    layer = FakeLayer()
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="custom_select", target={"query": "所属部门"}, option_text="研发部")

    assert result["status"] == "success"
    assert layer.calls[3][0] == "find"
    assert layer.calls[3][1]["layer"] == "popover"


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


def test_layer_select_confirm_search_prefers_overlay_layer():
    layer = FakeLayer()
    layer.find_results = [
        {"status": "success", "matches": [{"index": 10, "element": {"index": 10}}], "ambiguous": False},
        {"status": "success", "matches": [{"index": 22, "element": {"index": 22}}], "ambiguous": False},
        {"status": "success", "matches": [{"index": 30, "element": {"index": 30}}], "ambiguous": False},
    ]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="layer_select", target={"query": "人员"}, option_text="张三", confirm_text="确定")

    assert result["status"] == "success"
    assert layer.calls[-2][0] == "find"
    assert layer.calls[-2][1]["layer"] == "popover"


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
    assert layer.calls == []


def test_component_wait_returns_component_not_ready_on_timeout():
    layer = FakeLayer()
    layer.find_results = [{"status": "failed", "stage": "target_not_found", "recovery": {"code": "refresh_state_then_find"}}]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="component_wait", condition="options_visible", target={"query": "研发部"}, timeout=1)

    assert result["status"] == "failed"
    assert result["stage"] == "component_not_ready"
    assert result["recovery"]["code"] == "wait_component"


def test_component_wait_layer_closed_requires_no_match():
    layer = FakeLayer()
    layer.find_results = [
        {"status": "success", "matches": [{"index": 1, "element": {"index": 1, "layer": "popover"}}], "ambiguous": False}
    ]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="component_wait", condition="layer_closed", target={"query": "弹层"}, timeout=1)

    assert result["status"] == "failed"
    assert result["stage"] == "component_not_ready"


def test_component_wait_element_enabled_rejects_disabled_match():
    layer = FakeLayer()
    layer.find_results = [
        {"status": "success", "matches": [{"index": 1, "element": {"index": 1, "disabled": True}}], "ambiguous": False}
    ]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="component_wait", condition="element_enabled", target={"query": "提交"}, timeout=1)

    assert result["status"] == "failed"
    assert result["stage"] == "component_not_ready"
