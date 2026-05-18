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


def test_find_rejects_unbounded_locator():
    state = make_state([{"index": 1, "text": "保存", "labels": [], "visible": True, "disabled": False}])

    result = find_in_state(state, max_results=5)

    assert result["status"] == "failed"
    assert result["stage"] == "invalid_args"
    assert result["recovery"]["code"] == "provide_locator"
    assert result["recovery"]["stop_retry"] is True


def test_find_rejects_role_filter_without_semantic_locator():
    state = make_state([{"index": 1, "role": "button", "text": "保存", "labels": [], "visible": True, "disabled": False}])

    result = find_in_state(state, role="button", max_results=5)

    assert result["status"] == "failed"
    assert result["stage"] == "invalid_args"
    assert result["recovery"]["code"] == "provide_locator"
    assert result["recovery"]["stop_retry"] is True


def test_find_rejects_control_layer_and_frame_without_semantic_locator():
    state = make_state(
        [
            {
                "index": 1,
                "control_kind": "contenteditable",
                "layer": "modal",
                "frame_path": [0],
                "text": "保存",
                "labels": [],
                "visible": True,
                "disabled": False,
            }
        ]
    )

    result = find_in_state(state, control_kind="contenteditable", layer="modal", frame_path=[0], max_results=5)

    assert result["status"] == "failed"
    assert result["stage"] == "invalid_args"
    assert result["recovery"]["code"] == "provide_locator"
    assert result["recovery"]["stop_retry"] is True


def test_find_preserves_state_failure_stage():
    state = {
        "status": "failed",
        "stage": "browser_unavailable",
        "error": "Chrome unavailable",
        "recovery": {"code": "fallback_low_level", "next_tool": "web_execute_js"},
    }

    result = find_in_state(state, query="保存", max_results=5)

    assert result["status"] == "failed"
    assert result["stage"] == "browser_unavailable"
    assert result["error"] == "Chrome unavailable"
    assert result["recovery"]["code"] == "fallback_low_level"


def test_find_safely_parses_string_max_results():
    state = make_state(
        [
            {"index": 1, "text": "保存", "labels": [], "visible": True, "disabled": False},
            {"index": 2, "text": "保存", "labels": [], "visible": True, "disabled": False},
        ]
    )
    result = find_in_state(state, query="保存", max_results="1")
    assert result["status"] == "success"
    assert len(result["matches"]) == 1
    assert result["ambiguous"] is True


def test_find_keeps_ambiguity_when_integer_max_results_truncates_matches():
    state = make_state(
        [
            {"index": 1, "text": "保存", "labels": [], "visible": True, "disabled": False},
            {"index": 2, "text": "保存", "labels": [], "visible": True, "disabled": False},
        ]
    )
    result = find_in_state(state, query="保存", max_results=1)
    assert result["status"] == "success"
    assert len(result["matches"]) == 1
    assert result["ambiguous"] is True


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


def test_find_target_not_found_recovery_expands_truncated_state_budget():
    state = {
        "status": "success",
        "truncated": True,
        "truncation": {
            "omitted_count": 12,
            "iframe_omitted_count": 4,
            "total_limit": 120,
            "main_reserved": 72,
            "frame_reserved": 48,
        },
        "elements": [
            {
                "index": 1,
                "text": "提交",
                "role": "button",
                "control_kind": "button",
                "layer": "main",
                "frame_path": [],
            }
        ],
    }

    result = find_in_state(state, query="是否休假", control_kind="custom_select", max_results=5)

    assert result["status"] == "failed"
    assert result["stage"] == "target_not_found"
    assert result["recovery"]["code"] == "refresh_state_then_find"
    assert result["recovery"]["next_tool"] == "browser_use_index"
    assert result["recovery"]["next_args"]["max_elements"] == 150
    assert result["recovery"]["follow_up"]["next_tool"] == "browser_find"
    assert result["recovery"]["follow_up"]["next_args"]["refresh"] is True
    assert result["recovery"]["follow_up"]["next_args"]["query"] == "是否休假"
    assert result["recovery"]["follow_up"]["next_args"]["control_kind"] == "custom_select"
    assert "omitted 12 elements" in result["recovery"]["message"]
    assert "iframe" in result["recovery"]["message"].lower()


def test_find_target_not_found_recovery_mentions_iframe_when_only_iframe_count_present():
    state = {
        "status": "success",
        "truncated": True,
        "truncation": {"omitted_count": 0, "iframe_omitted_count": 2, "total_limit": 120},
        "elements": [{"index": 1, "text": "提交", "visible": True, "disabled": False}],
    }

    result = find_in_state(state, query="iframe field", max_results=5)

    assert result["status"] == "failed"
    assert "iframe" in result["recovery"]["message"].lower()
    assert result["recovery"]["next_tool"] == "browser_use_index"
    assert result["recovery"]["next_args"]["max_elements"] == 150
    assert result["recovery"]["follow_up"]["next_args"]["query"] == "iframe field"


def test_find_prefers_dropdown_option_when_layer_filter_is_dropdown():
    state = make_state(
        [
            {
                "index": 3,
                "text": "否",
                "role": "option",
                "control_kind": "option",
                "layer": "dropdown",
                "visible": True,
                "disabled": False,
                "frame_path": [0],
            },
            {
                "index": 7,
                "text": "否",
                "role": "text",
                "control_kind": "text",
                "layer": "main",
                "visible": True,
                "disabled": False,
                "frame_path": [0],
            },
        ]
    )

    result = find_in_state(state, query="否", layer="dropdown", max_results=5)

    assert result["status"] == "success"
    assert result["matches"][0]["index"] == 3
    assert result["matches"][0]["element"]["layer"] == "dropdown"


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


def test_find_matches_adjacent_row_label_for_custom_select():
    state = make_state(
        [
            {
                "index": 4,
                "text": "请选择",
                "labels": [],
                "control_kind": "custom_select",
                "visible": True,
                "disabled": False,
                "field_context": {
                    "nearby_text": "是否休假",
                    "row_label": "是否休假",
                    "previous_cell_text": "是否休假",
                    "field_id": "field5956",
                    "field_name": "sfxj",
                },
            },
            {
                "index": 9,
                "text": "是否休假说明",
                "labels": [],
                "control_kind": "button",
                "visible": True,
                "disabled": False,
            },
        ]
    )

    result = find_in_state(state, query="是否休假", control_kind="custom_select", max_results=5)

    assert result["status"] == "success"
    assert result["ambiguous"] is False
    assert result["matches"][0]["index"] == 4
    assert "field row label" in result["matches"][0]["reason"]


def test_find_ranks_scan_anchor_field_label_over_generic_text():
    state = make_state(
        [
            {
                "index": 2,
                "text": "工作类型说明",
                "labels": [],
                "control_kind": "custom_select",
                "visible": True,
                "disabled": False,
            },
            {
                "index": 4,
                "text": "",
                "labels": [],
                "control_kind": "custom_select",
                "visible": True,
                "disabled": False,
                "scan_anchor": {
                    "field_label": "工作类型",
                    "near_text": "工作类型",
                    "row_text": "",
                    "column_text": "",
                },
            },
        ]
    )

    result = find_in_state(state, query="工作类型", control_kind="custom_select", max_results=5)

    assert result["status"] == "success"
    assert result["ambiguous"] is False
    assert result["matches"][0]["index"] == 4
    assert "scan anchor field label" in result["matches"][0]["reason"]


def test_find_matches_scan_anchor_near_text_without_field_context():
    state = make_state(
        [
            {
                "index": 8,
                "text": "",
                "labels": [],
                "control_kind": "native_input",
                "visible": True,
                "disabled": False,
                "scan_anchor": {
                    "field_label": "",
                    "near_text": "请填写项目名称",
                    "row_text": "",
                    "column_text": "",
                },
            }
        ]
    )

    result = find_in_state(state, query="项目名称", control_kind="native_input", max_results=5)

    assert result["status"] == "success"
    assert result["matches"][0]["index"] == 8
    assert "scan anchor near text" in result["matches"][0]["reason"]


def test_find_matches_field_id_and_field_name():
    state = make_state(
        [
            {
                "index": 3,
                "text": "",
                "labels": [],
                "control_kind": "native_input",
                "visible": True,
                "disabled": False,
                "field_context": {"field_id": "field6358_0", "field_name": "workType"},
            }
        ]
    )

    by_id = find_in_state(state, query="field6358_0", control_kind="native_input", max_results=5)
    by_name = find_in_state(state, query="workType", control_kind="native_input", max_results=5)

    assert by_id["matches"][0]["index"] == 3
    assert "field id" in by_id["matches"][0]["reason"]
    assert by_name["matches"][0]["index"] == 3
    assert "field name" in by_name["matches"][0]["reason"]


def test_find_keeps_ambiguous_for_duplicate_field_labels():
    state = make_state(
        [
            {
                "index": 1,
                "text": "",
                "labels": [],
                "control_kind": "custom_select",
                "visible": True,
                "disabled": False,
                "field_context": {"row_label": "工作类型", "previous_cell_text": "工作类型"},
            },
            {
                "index": 2,
                "text": "",
                "labels": [],
                "control_kind": "custom_select",
                "visible": True,
                "disabled": False,
                "field_context": {"row_label": "工作类型", "previous_cell_text": "工作类型"},
            },
        ]
    )

    result = find_in_state(state, query="工作类型", control_kind="custom_select", max_results=5)

    assert result["status"] == "success"
    assert result["ambiguous"] is True
    assert [match["index"] for match in result["matches"][:2]] == [1, 2]


def test_find_keeps_exact_label_when_field_context_is_weaker():
    state = make_state(
        [
            {
                "index": 1,
                "text": "休假",
                "labels": ["休假"],
                "control_kind": "custom_select",
                "visible": True,
                "disabled": False,
                "field_context": {
                    "nearby_text": "是否休假",
                    "row_label": "是否休假",
                    "previous_cell_text": "是否休假",
                },
            },
            {
                "index": 2,
                "text": "是否休假",
                "labels": [],
                "control_kind": "custom_select",
                "visible": True,
                "disabled": False,
                "field_context": {
                    "nearby_text": "是否休假",
                    "row_label": "是否休假",
                    "previous_cell_text": "是否休假",
                },
            },
        ]
    )

    result = find_in_state(state, query="休假", control_kind="custom_select", max_results=5)

    assert result["status"] == "success"
    assert result["ambiguous"] is False
    assert result["matches"][0]["index"] == 1
    assert "exact label" in result["matches"][0]["reason"]


def test_find_table_locator_matches_scan_anchor_when_table_context_absent():
    state = make_state(
        [
            {
                "index": 6,
                "text": "",
                "labels": [],
                "visible": True,
                "disabled": False,
                "scan_anchor": {
                    "field_label": "",
                    "near_text": "",
                    "row_text": "张三 1.00",
                    "column_text": "工时",
                },
            }
        ]
    )

    result = find_in_state(state, table={"row_text": "张三", "column_text": "工时"}, max_results=5)

    assert result["status"] == "success"
    assert result["matches"][0]["index"] == 6
    assert "scan anchor table row" in result["matches"][0]["reason"]
    assert "scan anchor table column" in result["matches"][0]["reason"]


def test_find_table_locator_uses_scan_anchor_when_table_context_is_weaker():
    state = make_state(
        [
            {
                "index": 7,
                "text": "",
                "labels": [],
                "visible": True,
                "disabled": False,
                "table_context": {"row_text": "张三"},
                "scan_anchor": {
                    "field_label": "",
                    "near_text": "",
                    "row_text": "张三 1.00",
                    "column_text": "工时",
                },
            }
        ]
    )

    result = find_in_state(state, table={"row_text": "张三", "column_text": "工时"}, max_results=5)

    assert result["status"] == "success"
    assert result["matches"][0]["index"] == 7
    assert "scan anchor table column" in result["matches"][0]["reason"]


def test_find_caps_public_match_score_at_one():
    state = make_state(
        [
            {
                "index": 3,
                "text": "",
                "labels": [],
                "control_kind": "native_input",
                "visible": True,
                "disabled": False,
                "field_context": {"field_id": "field6358_0", "field_name": "field6358_0"},
            }
        ]
    )

    result = find_in_state(state, query="field6358_0", control_kind="native_input", max_results=5)

    assert result["status"] == "success"
    assert result["matches"][0]["index"] == 3
    assert result["matches"][0]["score"] <= 1.0
