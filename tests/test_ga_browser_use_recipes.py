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


def test_component_wait_returns_component_not_ready_on_timeout():
    layer = FakeLayer()
    layer.find_results = [{"status": "failed", "stage": "target_not_found", "recovery": {"code": "refresh_state_then_find"}}]
    runner = BrowserRecipeRunner(layer)

    result = runner.run(None, recipe="component_wait", condition="options_visible", target={"query": "研发部"}, timeout=1)

    assert result["status"] == "failed"
    assert result["stage"] == "component_not_ready"
    assert result["recovery"]["code"] == "wait_component"
