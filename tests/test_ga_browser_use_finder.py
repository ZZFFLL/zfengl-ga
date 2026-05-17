from ga_browser_use.finder import find_in_state


def make_state(elements):
    return {"status": "success", "tab_id": "tab-1", "elements": elements}


def test_find_prefers_label_and_control_kind_over_generic_text():
    state = make_state(
        [
            {"index": 1, "text": "签字意见说明", "labels": [], "control_kind": "button", "visible": True, "disabled": False},
            {"index": 2, "text": "", "labels": ["签字意见"], "control_kind": "contenteditable", "visible": True, "disabled": False},
        ]
    )

    result = find_in_state(state, query="签字意见", control_kind="contenteditable", max_results=5)

    assert result["status"] == "success"
    assert result["ambiguous"] is False
    assert result["matches"][0]["index"] == 2
    assert "label" in result["matches"][0]["reason"]


def test_find_table_row_and_column_match_ranks_first():
    state = make_state(
        [
            {
                "index": 1,
                "text": "审批意见",
                "labels": [],
                "visible": True,
                "disabled": False,
                "table_context": {"row_text": "李四", "column_header": "审批意见"},
            },
            {
                "index": 2,
                "text": "",
                "labels": ["输入框"],
                "visible": True,
                "disabled": False,
                "table_context": {"row_text": "张三", "column_header": "审批意见"},
            },
        ]
    )

    result = find_in_state(state, table={"row_text": "张三", "column_text": "审批意见"}, max_results=5)

    assert result["matches"][0]["index"] == 2
    assert "table row" in result["matches"][0]["reason"]


def test_find_table_locator_matches_indexer_emitted_table_context():
    state = make_state(
        [
            {
                "index": 1,
                "text": "",
                "labels": [],
                "visible": True,
                "disabled": False,
                "table_context": {
                    "row_index": 2,
                    "column_index": 2,
                    "cell_text": "1.00",
                    "row_text": "张三 1.00",
                    "row_header": "张三",
                    "column_header": "工时",
                },
            }
        ]
    )

    result = find_in_state(state, table={"row_text": "张三", "column_text": "工时"}, max_results=5)

    assert result["status"] == "success"
    assert result["matches"][0]["index"] == 1


def test_find_marks_near_tie_as_ambiguous():
    state = make_state(
        [
            {"index": 1, "text": "张三", "labels": [], "visible": True, "disabled": False},
            {"index": 2, "text": "张三", "labels": [], "visible": True, "disabled": False},
        ]
    )

    result = find_in_state(state, query="张三", max_results=5)

    assert result["status"] == "success"
    assert result["ambiguous"] is True
    assert [match["index"] for match in result["matches"][:2]] == [1, 2]


def test_find_returns_target_not_found_with_recovery():
    state = make_state([{"index": 1, "text": "保存", "labels": [], "visible": True, "disabled": False}])

    result = find_in_state(state, query="不存在", max_results=5)

    assert result["status"] == "failed"
    assert result["stage"] == "target_not_found"
    assert result["recovery"]["code"] == "refresh_state_then_find"


def test_find_safely_parses_string_max_results():
    state = make_state(
        [
            {"index": 1, "text": "保存", "labels": [], "visible": True, "disabled": False},
            {"index": 2, "text": "保存", "labels": [], "visible": True, "disabled": False},
        ]
    )
    result = find_in_state(state, query="保存", max_results="1")
    assert len(result["matches"]) == 1


def test_find_invalid_max_results_falls_back_to_default():
    state = make_state([{"index": 1, "text": "保存", "labels": [], "visible": True, "disabled": False}])
    result = find_in_state(state, query="保存", max_results="bad")
    assert result["status"] == "success"
    assert result["matches"][0]["index"] == 1


def test_find_target_not_found_recovery_preserves_constraints():
    state = make_state([{"index": 1, "text": "保存", "labels": [], "visible": True, "disabled": False}])
    table = {"row_text": "张三", "column_text": "审批意见"}
    result = find_in_state(
        state,
        query="不存在",
        role="textbox",
        control_kind="contenteditable",
        layer="modal",
        frame_path=[0],
        table=table,
        max_results=5,
    )
    next_args = result["recovery"]["next_args"]
    assert next_args["refresh"] is True
    assert next_args["query"] == "不存在"
    assert next_args["role"] == "textbox"
    assert next_args["control_kind"] == "contenteditable"
    assert next_args["layer"] == "modal"
    assert next_args["frame_path"] == [0]
    assert next_args["table"] == table


def test_find_returns_disabled_candidates_for_read_only_location():
    state = make_state(
        [
            {"index": 1, "text": "提交", "labels": [], "visible": True, "disabled": True},
        ]
    )

    result = find_in_state(state, query="提交", max_results=5)

    assert result["status"] == "success"
    assert result["matches"][0]["index"] == 1
    assert result["matches"][0]["element"]["disabled"] is True
