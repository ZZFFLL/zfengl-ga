import json
from pathlib import Path


def load_tools(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


ACTION_ENUM = [
    "click",
    "input",
    "select",
    "keys",
    "wait_index",
    "wait_text",
    "wait_selector",
    "wait_dom_stable",
    "wait_not_busy",
    "wait_enabled",
    "wait_route",
]


def tool_by_name(tools, name):
    for item in tools:
        function = item.get("function", {})
        if function.get("name") == name:
            return function
    raise AssertionError(f"tool not found: {name}")


def test_english_schema_exposes_browser_tools():
    tools = load_tools("assets/tools_schema.json")

    state = tool_by_name(tools, "browser_state")
    find = tool_by_name(tools, "browser_find")
    recipe = tool_by_name(tools, "browser_recipe")
    action = tool_by_name(tools, "browser_action")

    assert "indexed" in state["description"].lower()
    assert "same-origin" in state["description"].lower()
    assert "iframe" in state["description"].lower()
    assert "field/control/layer" in state["description"].lower()
    assert state["parameters"]["properties"]["max_elements"]["default"] == 120
    assert "read-only" in find["description"].lower()
    assert "query" in find["parameters"]["properties"]
    assert "refresh" in find["parameters"]["properties"]
    assert find["parameters"]["properties"]["max_results"]["default"] == 5
    assert "omit index" in action["description"]
    assert "Native select" in action["description"]
    assert "SPA wait actions" in action["description"]
    assert "Verification fields" in action["description"]
    assert "focused element" in action["parameters"]["properties"]["index"]["description"]
    assert action["parameters"]["properties"]["action"]["enum"] == ACTION_ENUM
    assert action["parameters"]["properties"]["verify"]["enum"] == [
        "field_value",
        "text",
        "selector",
        "element_text",
    ]
    assert "verify_failed" in action["parameters"]["properties"]["verify"]["description"]
    assert "verify_text" in action["parameters"]["properties"]
    assert "verify_value" in action["parameters"]["properties"]
    assert "verify_selector" in action["parameters"]["properties"]
    assert recipe["parameters"]["properties"]["recipe"]["enum"] == [
        "custom_select",
        "layer_select",
        "table_locate",
        "component_wait",
    ]
    assert recipe["parameters"]["properties"]["condition"]["enum"] == [
        "layer_open",
        "layer_closed",
        "options_visible",
        "field_value",
        "element_enabled",
        "not_busy",
    ]
    assert "verify" not in recipe["parameters"]["properties"]
    assert recipe["parameters"]["properties"]["timeout"]["default"] == 10
    assert recipe["parameters"]["properties"]["max_results"]["default"] == 5


def test_chinese_schema_exposes_browser_tools():
    tools = load_tools("assets/tools_schema_cn.json")

    state = tool_by_name(tools, "browser_state")
    find = tool_by_name(tools, "browser_find")
    recipe = tool_by_name(tools, "browser_recipe")
    action = tool_by_name(tools, "browser_action")

    assert "索引" in state["description"]
    assert "真实 Chrome" in state["description"]
    assert "同源 iframe" in state["description"]
    assert "field/control/layer" in state["description"]
    assert state["parameters"]["properties"]["include_invisible"]["default"] is False
    assert state["parameters"]["properties"]["max_elements"]["default"] == 120
    assert "只读定位" in find["description"]
    assert "query" in find["parameters"]["properties"]
    assert "refresh" in find["parameters"]["properties"]
    assert find["parameters"]["properties"]["max_results"]["default"] == 5
    assert "index" in action["parameters"]["properties"]
    assert "selector" in action["parameters"]["properties"]
    assert "不要传 index" in action["description"]
    assert "原生 select" in action["description"]
    assert "SPA 等待动作" in action["description"]
    assert "验证失败" in action["description"]
    assert "当前焦点元素" in action["parameters"]["properties"]["index"]["description"]
    assert action["parameters"]["properties"]["action"]["enum"] == ACTION_ENUM
    assert action["parameters"]["properties"]["verify"]["enum"] == [
        "field_value",
        "text",
        "selector",
        "element_text",
    ]
    assert "verify_failed" in action["parameters"]["properties"]["verify"]["description"]
    assert "verify_text" in action["parameters"]["properties"]
    assert "verify_value" in action["parameters"]["properties"]
    assert "verify_selector" in action["parameters"]["properties"]
    assert action["parameters"]["properties"]["timeout"]["default"] == 10
    assert recipe["parameters"]["properties"]["recipe"]["enum"] == [
        "custom_select",
        "layer_select",
        "table_locate",
        "component_wait",
    ]
    assert recipe["parameters"]["properties"]["condition"]["enum"] == [
        "layer_open",
        "layer_closed",
        "options_visible",
        "field_value",
        "element_enabled",
        "not_busy",
    ]
    assert "verify" not in recipe["parameters"]["properties"]
    assert recipe["parameters"]["properties"]["timeout"]["default"] == 10
    assert recipe["parameters"]["properties"]["max_results"]["default"] == 5
