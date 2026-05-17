from pathlib import Path

import ga


def test_web_execute_js_handler_docstring_uses_peer_boundary():
    doc = ga.GenericAgentHandler.do_web_execute_js.__doc__ or ""

    assert "平级" in doc
    assert "低层" in doc
    assert "优先使用" + "工具" not in doc
    assert "web情况下的优先使用" + "工具，执行任何js达成对浏览器的*" + "完全*控制" not in doc


def test_browser_use_sop_uses_task_shape_decision_model():
    text = (Path(__file__).resolve().parents[1] / "memory" / "browser-use_sop.md").read_text(encoding="utf-8")

    assert "平级" in text
    assert "互补" in text
    assert "任务形态" in text
    assert "先判断任务形态" in text
    assert "优先策略：" + "普通网页交互先用" not in text
    assert "推荐" + "决策：" not in text
    assert "web_execute_js 不是 browser_* 的上级或下级" in text
    assert "browser_recipe 不是自由规划器" in text
