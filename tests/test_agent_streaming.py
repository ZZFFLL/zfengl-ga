from agent_streaming import ModelDisplayStreamFilter, extract_model_process_summary


def drain_filter(chunks):
    stream_filter = ModelDisplayStreamFilter()
    visible = []
    for chunk in chunks:
        text = stream_filter.feed(chunk)
        if text:
            visible.append(text)
    tail = stream_filter.finish()
    if tail:
        visible.append(tail)
    return "".join(visible)


def test_filter_removes_thinking_tool_use_and_file_content_blocks():
    text = (
        "before "
        "<thinking>private reasoning</thinking>"
        "<summary>需要读取 package.json</summary>"
        "visible "
        "<tool_use>{\"name\":\"file_read\",\"arguments\":{\"path\":\"package.json\"}}</tool_use>"
        "<file_content>secret file body</file_content>"
        "after"
    )

    assert drain_filter([text]) == "before visible after"


def test_filter_handles_protocol_tags_split_across_chunks():
    assert (
        drain_filter(
            [
                "hello <thin",
                "king>private</thinking> wor",
                "ld <tool_",
                "use>{}</tool_use> done",
            ]
        )
        == "hello  world  done"
    )


def test_filter_fails_closed_when_blocked_opening_tag_exceeds_retained_buffer():
    assert (
        drain_filter(
            [
                "visible <think",
                "ing " + ("x" * 80) + " private leaked " + ("x" * 80),
                ">secret</thinking> after",
            ]
        )
        == "visible  after"
    )


def test_filter_drops_incomplete_blocked_opening_tag_at_eof():
    assert drain_filter(["visible <thinking private leaked text"]) == "visible "


def test_filter_preserves_unrelated_less_than_text_at_eof():
    assert drain_filter(["visible 2 < 3"]) == "visible 2 < 3"


def test_extract_model_process_summary_prefers_summary_tag():
    assert (
        extract_model_process_summary(
            "<summary>已经拿到脚本字段，准备总结</summary>\n正文",
            thinking="private reasoning",
        )
        == "已经拿到脚本字段，准备总结"
    )


def test_filter_treats_malformed_summary_parameter_close_as_protocol_block():
    text = "<summary>查询当前记忆文件内容</parameter>可见正文"

    assert drain_filter([text]) == "可见正文"
    assert extract_model_process_summary(text) == "查询当前记忆文件内容"


def test_extract_model_process_summary_uses_bounded_thinking_first_line_when_no_summary():
    text = extract_model_process_summary(
        "正文没有摘要",
        thinking="第一行推理内容会被截断到安全长度。" * 10,
    )

    assert text.startswith("第一行推理内容")
    assert len(text) <= 90


def test_extract_model_process_summary_uses_visible_text_fallback():
    assert (
        extract_model_process_summary(
            "我会先查看当前目录。\n然后调用工具。",
            thinking="",
        )
        == "我会先查看当前目录。"
    )
