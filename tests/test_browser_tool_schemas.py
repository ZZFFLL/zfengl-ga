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
    action = tool_by_name(tools, "browser_action")

    assert "indexed" in state["description"].lower()
    assert state["parameters"]["properties"]["max_elements"]["default"] == 120
    assert action["parameters"]["properties"]["action"]["enum"] == ACTION_ENUM


def test_chinese_schema_exposes_browser_tools():
    tools = load_tools("assets/tools_schema_cn.json")

    state = tool_by_name(tools, "browser_state")
    action = tool_by_name(tools, "browser_action")

    assert "索引" in state["description"]
    assert "真实 Chrome" in state["description"]
    assert state["parameters"]["properties"]["max_elements"]["default"] == 120
    assert "index" in action["parameters"]["properties"]
    assert "selector" in action["parameters"]["properties"]
    assert action["parameters"]["properties"]["action"]["enum"] == ACTION_ENUM
    assert action["parameters"]["properties"]["timeout"]["default"] == 10
