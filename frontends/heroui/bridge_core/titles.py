from __future__ import annotations

import contextlib
import importlib
from typing import Any, Callable


def is_untitled_session_title(title: str) -> bool:
    normalized = (title or "").strip().lower()
    return normalized in {"new chat", "新会话"}


def build_initial_title_prompt(first_user_message: str, first_assistant_message: str) -> str:
    return (
        "请根据下面这组会话开头内容，生成一个简洁中文会话标题。\n"
        "要求：\n"
        "1. 只输出标题本身，不要解释。\n"
        "2. 长度控制在 8 到 20 个中文字符之间。\n"
        "3. 要综合用户第一条消息和助手第一次正文回复，不要直接照抄用户原句。\n"
        "4. 不要包含引号、句号、序号、前缀。\n\n"
        f"用户第一条消息：{' '.join(first_user_message.split())}\n"
        f"助手第一次正文回复：{' '.join(first_assistant_message.split())}"
    )


def build_title_regeneration_prompt(user_messages: list[str]) -> str:
    bullet_lines = [f"{index + 1}. {' '.join(message.split())}" for index, message in enumerate(user_messages)]
    return (
        "请根据以下最近 5 轮以内的用户消息，为这个会话生成一个简洁中文标题。\n"
        "要求：\n"
        "1. 只输出标题本身，不要解释。\n"
        "2. 长度控制在 8 到 20 个中文字符之间。\n"
        "3. 不要包含引号、句号、序号、前缀。\n"
        "4. 标题要概括主题，不要照抄整句。\n\n"
        f"用户消息：\n{chr(10).join(bullet_lines)}"
    )


def generate_title_with_current_model(
    prompt: str,
    llm_no: int,
    ensure_ga_import_path: Callable[[], Any],
    fast_ask_fn: Callable[[str, str], Any],
    reload_mykeys_fn: Callable[[], tuple[dict[str, Any], Any]],
) -> str:
    ensure_ga_import_path()
    agentmain = importlib.import_module("agentmain")
    agent = agentmain.GenericAgent()
    agent.next_llm(llm_no)
    cfg_name = resolve_llm_config_name(agent, llm_no, reload_mykeys_fn)
    raw = fast_ask_fn(prompt, cfg_name)
    title = " ".join(str(raw or "").strip().replace("\n", " ").split())
    title = title.strip("“”\"'`·-:：,.，。；; ")
    return title[:40]


def resolve_llm_config_name(
    agent: Any,
    llm_no: int,
    reload_mykeys_fn: Callable[[], tuple[dict[str, Any], Any]],
) -> str:
    mykeys, _ = reload_mykeys_fn()
    entries = [
        (key, cfg)
        for key, cfg in mykeys.items()
        if any(marker in key for marker in ("api", "config", "cookie"))
    ]
    if not entries:
        raise ValueError("No usable LLM configs found in mykey")

    active_name = ""
    with contextlib.suppress(Exception):
        active_name = str(getattr(agent.llmclient.backend, "name", "") or "").strip()
    if active_name:
        for key, cfg in entries:
            if str(cfg.get("name") or "").strip() == active_name:
                return key

    return entries[llm_no % len(entries)][0]
