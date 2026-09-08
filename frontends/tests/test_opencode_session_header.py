"""验证 OpenCode 请求必须携带稳定会话标识。"""

from __future__ import annotations

import llmcore


class _ErrorResponse:
    """模拟模型服务返回失败响应，避免测试访问外部网络。"""

    status_code = 400
    text = "模拟失败"

    def __enter__(self):
        """返回可供请求上下文管理器使用的模拟响应。"""
        return self

    def __exit__(self, _type, _value, _traceback):
        """不吞掉测试中可能出现的异常。"""
        return False


def test_native_oai_opencode_request_has_stable_session_header(monkeypatch):
    """同一原生会话的每次 OpenCode 请求都传递同一个会话标识。"""
    captured_headers = []

    # 记录真实请求路径组装出的请求头，并用本地失败响应及时结束生成器。
    def fake_post(_url, *, headers, **_kwargs):
        captured_headers.append(headers)
        return _ErrorResponse()

    monkeypatch.setattr(llmcore.requests, "post", fake_post)
    session = llmcore.NativeOAISession(
        {
            "apikey": "test-key",
            "apibase": "https://opencode.ai/zen/go/v1",
            "model": "deepseek-v4-flash",
            "stream": False,
        }
    )

    for _ in range(2):
        next(session.raw_ask([{"role": "user", "content": "测试"}]))

    assert [headers["x-opencode-session"] for headers in captured_headers] == [
        session._session_id,
        session._session_id,
    ]
