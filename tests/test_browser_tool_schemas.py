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
    assert "real semantic locator" in find["description"].lower()
    assert "role/layer/control_kind/frame_path" in find["description"]
    assert "not sufficient by themselves" in find["description"].lower()
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
    assert recipe["parameters"]["properties"]["timeout"]["maximum"] == 60
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
    assert "真实语义定位" in find["description"]
    assert "role/layer/control_kind/frame_path" in find["description"]
    assert "单独使用不足以定位" in find["description"]
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
    assert recipe["parameters"]["properties"]["timeout"]["maximum"] == 60
    assert recipe["parameters"]["properties"]["max_results"]["default"] == 5


def test_browser_tool_descriptions_use_parallel_boundary_terms():
    english = load_tools("assets/tools_schema.json")
    chinese = load_tools("assets/tools_schema_cn.json")

    en_web_js = tool_by_name(english, "web_execute_js")
    en_state = tool_by_name(english, "browser_state")
    en_find = tool_by_name(english, "browser_find")
    en_recipe = tool_by_name(english, "browser_recipe")
    en_action = tool_by_name(english, "browser_action")

    cn_web_js = tool_by_name(chinese, "web_execute_js")
    cn_state = tool_by_name(chinese, "browser_state")
    cn_find = tool_by_name(chinese, "browser_find")
    cn_recipe = tool_by_name(chinese, "browser_recipe")
    cn_action = tool_by_name(chinese, "browser_action")

    assert "peer low-level browser-control tool" in en_web_js["description"]
    assert "not above or below browser_* tools" in en_web_js["description"]
    assert "structured indexed snapshot" in en_state["description"]
    assert "not full-page extraction" in en_state["description"]
    assert "field context" in en_state["description"]
    assert "recipe_hint" in en_state["description"]
    assert "semantic locator" in en_find["description"]
    assert "query or table" in en_find["description"]
    assert "field labels" in en_find["description"]
    assert "not a global search engine" in en_find["description"]
    assert "fixed deterministic" in en_recipe["description"]
    assert "advisory" in en_recipe["description"]
    assert "not a general planner" in en_recipe["description"]
    assert "bounded indexed browser actions" in en_action["description"]
    assert "recovery" in en_action["description"]
    assert "not arbitrary selector automation" in en_action["description"]

    assert "平级" in cn_web_js["description"]
    assert "低层浏览器控制工具" in cn_web_js["description"]
    assert "不是 browser_* 的上级或下级" in cn_web_js["description"]
    assert "结构化索引快照" in cn_state["description"]
    assert "不是网页全文抽取" in cn_state["description"]
    assert "字段上下文" in cn_state["description"]
    assert "recipe_hint" in cn_state["description"]
    assert "语义定位" in cn_find["description"]
    assert "query 或 table" in cn_find["description"]
    assert "字段标签" in cn_find["description"]
    assert "不是全局搜索引擎" in cn_find["description"]
    assert "固定且确定性" in cn_recipe["description"]
    assert "提示" in cn_recipe["description"]
    assert "不是通用规划器" in cn_recipe["description"]
    assert "有边界的索引动作" in cn_action["description"]
    assert "恢复建议" in cn_action["description"]
    assert "不是任意 selector 自动化" in cn_action["description"]

    forbidden_english = [
        "primary browser " + "action tool",
        "default ordinary " + "interaction path",
        "fallback" + "-only",
    ]
    forbidden_chinese = [
        "优先使用" + "工具",
        "普通交互" + "首选",
        "只能作为" + "兜底",
    ]
    english_descriptions = "\n".join(
        tool_by_name(english, name)["description"]
        for name in ["web_execute_js", "browser_state", "browser_find", "browser_recipe", "browser_action"]
    )
    chinese_descriptions = "\n".join(
        tool_by_name(chinese, name)["description"]
        for name in ["web_execute_js", "browser_state", "browser_find", "browser_recipe", "browser_action"]
    )
    for phrase in forbidden_english:
        assert phrase not in english_descriptions
    for phrase in forbidden_chinese:
        assert phrase not in chinese_descriptions
