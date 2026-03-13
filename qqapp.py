import os, sys, re, threading, asyncio, queue as Q, socket, time, glob
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agentmain import GeneraticAgent
from llmcore import mykeys

try:
    import botpy
    from botpy.message import C2CMessage, GroupMessage
except Exception:
    print("Please install qq-botpy to use QQ module: pip install qq-botpy")
    sys.exit(1)

agent = GeneraticAgent()
agent.verbose = False

APP_ID = str(mykeys.get("qq_app_id", "") or "").strip()
APP_SECRET = str(mykeys.get("qq_app_secret", "") or "").strip()
ALLOWED = {str(x).strip() for x in mykeys.get("qq_allowed_users", []) if str(x).strip()}

_TAG_PATS = [r"<" + t + r">.*?</" + t + r">" for t in ("thinking", "summary", "tool_use", "file_content")]
_PROCESSED_IDS = deque(maxlen=1000)
_USER_TASKS = {}
_SEQ_LOCK = threading.Lock()
_MSG_SEQ = 1


def _next_msg_seq():
    global _MSG_SEQ
    with _SEQ_LOCK:
        _MSG_SEQ += 1
        return _MSG_SEQ


def _clean(text):
    for pat in _TAG_PATS:
        text = re.sub(pat, "", text, flags=re.DOTALL)
    return re.sub(r"\n{3,}", "\n\n", text).strip() or "..."


def _extract_files(text):
    return re.findall(r"\[FILE:([^\]]+)\]", text or "")


def _strip_files(text):
    return re.sub(r"\[FILE:[^\]]+\]", "", text or "").strip()


def _split_text(text, limit=1500):
    text = (text or "").strip() or "..."
    parts = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit * 0.6:
            cut = limit
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        parts.append(text)
    return parts or ["..."]


def _format_restore():
    files = glob.glob("./temp/model_responses_*.txt")
    if not files:
        return None, "❌ 没有找到历史记录"
    latest = max(files, key=os.path.getmtime)
    with open(latest, "r", encoding="utf-8") as f:
        content = f.read()
    users = re.findall(r"=== USER ===\n(.+?)(?==== |$)", content, re.DOTALL)
    resps = re.findall(r"=== Response ===.*?\n(.+?)(?==== Prompt|$)", content, re.DOTALL)
    count, restored = 0, []
    for u, r in zip(users, resps):
        u, r = u.strip(), r.strip()[:500]
        if u and r:
            restored.extend([f"[USER]: {u}", f"[Agent] {r}"])
            count += 1
    if not restored:
        return None, "❌ 历史记录里没有可恢复内容"
    return (restored, os.path.basename(latest), count), None


def _build_intents():
    try:
        return botpy.Intents(public_messages=True, direct_message=True)
    except Exception:
        intents = botpy.Intents.none() if hasattr(botpy.Intents, "none") else botpy.Intents()
        for attr in (
            "public_messages",
            "public_guild_messages",
            "direct_message",
            "direct_messages",
            "c2c_message",
            "c2c_messages",
            "group_at_message",
            "group_at_messages",
        ):
            if hasattr(intents, attr):
                try:
                    setattr(intents, attr, True)
                except Exception:
                    pass
        return intents


def _make_bot_class(app):
    intents = _build_intents()

    class _QQBot(botpy.Client):
        def __init__(self):
            super().__init__(intents=intents, ext_handlers=False)

        async def on_ready(self):
            name = getattr(getattr(self, "robot", None), "name", "QQBot")
            print(f"[QQ] bot ready: {name}")

        async def on_c2c_message_create(self, message: C2CMessage):
            await app.on_message(message, is_group=False)

        async def on_group_at_message_create(self, message: GroupMessage):
            await app.on_message(message, is_group=True)

        async def on_direct_message_create(self, message):
            await app.on_message(message, is_group=False)

    return _QQBot


class QQApp:
    def __init__(self):
        self.client = None

    async def send_text(self, chat_id, content, *, msg_id=None, is_group=False):
        if not self.client:
            return
        for part in _split_text(content):
            seq = _next_msg_seq()
            if is_group:
                await self.client.api.post_group_message(
                    group_openid=chat_id,
                    msg_type=0,
                    content=part,
                    msg_id=msg_id,
                    msg_seq=seq,
                )
            else:
                await self.client.api.post_c2c_message(
                    openid=chat_id,
                    msg_type=0,
                    content=part,
                    msg_id=msg_id,
                    msg_seq=seq,
                )

    async def send_done(self, chat_id, raw_text, *, msg_id=None, is_group=False):
        files = [p for p in _extract_files(raw_text) if os.path.exists(p)]
        body = _strip_files(_clean(raw_text))
        if files:
            body = (body + "\n\n" if body else "") + "\n".join([f"生成文件: {p}" for p in files])
        await self.send_text(chat_id, body or "...", msg_id=msg_id, is_group=is_group)

    async def handle_command(self, chat_id, cmd, *, msg_id=None, is_group=False):
        parts = (cmd or "").split()
        op = (parts[0] if parts else "").lower()
        if op == "/stop":
            state = _USER_TASKS.get(chat_id)
            if state:
                state["running"] = False
            agent.abort()
            await self.send_text(chat_id, "⏹️ 正在停止...", msg_id=msg_id, is_group=is_group)
        elif op == "/status":
            llm = agent.get_llm_name() if agent.llmclient else "未配置"
            await self.send_text(chat_id, f"状态: {'🔴 运行中' if agent.is_running else '🟢 空闲'}\nLLM: [{agent.llm_no}] {llm}", msg_id=msg_id, is_group=is_group)
        elif op == "/llm":
            if not agent.llmclient:
                return await self.send_text(chat_id, "❌ 当前没有可用的 LLM 配置", msg_id=msg_id, is_group=is_group)
            if len(parts) > 1:
                try:
                    n = int(parts[1])
                    agent.next_llm(n)
                    await self.send_text(chat_id, f"✅ 已切换到 [{agent.llm_no}] {agent.get_llm_name()}", msg_id=msg_id, is_group=is_group)
                except Exception:
                    await self.send_text(chat_id, f"用法: /llm <0-{len(agent.list_llms()) - 1}>", msg_id=msg_id, is_group=is_group)
            else:
                lines = [f"{'→' if cur else '  '} [{i}] {name}" for i, name, cur in agent.list_llms()]
                await self.send_text(chat_id, "LLMs:\n" + "\n".join(lines), msg_id=msg_id, is_group=is_group)
        elif op == "/restore":
            try:
                restored_info, err = _format_restore()
                if err:
                    return await self.send_text(chat_id, err, msg_id=msg_id, is_group=is_group)
                restored, fname, count = restored_info
                agent.abort()
                agent.history.extend(restored)
                await self.send_text(chat_id, f"✅ 已恢复 {count} 轮对话\n来源: {fname}\n(仅恢复上下文，请输入新问题继续)", msg_id=msg_id, is_group=is_group)
            except Exception as e:
                await self.send_text(chat_id, f"❌ 恢复失败: {e}", msg_id=msg_id, is_group=is_group)
        elif op == "/new":
            agent.abort()
            agent.history = []
            await self.send_text(chat_id, "🆕 已清空当前共享上下文", msg_id=msg_id, is_group=is_group)
        else:
            await self.send_text(
                chat_id,
                "📖 命令列表:\n/help - 显示帮助\n/status - 查看状态\n/stop - 停止当前任务\n/new - 清空当前上下文\n/restore - 恢复上次对话历史\n/llm [n] - 查看或切换模型",
                msg_id=msg_id,
                is_group=is_group,
            )

    async def run_agent(self, chat_id, text, *, msg_id=None, is_group=False):
        state = {"running": True}
        _USER_TASKS[chat_id] = state
        try:
            await self.send_text(chat_id, "思考中...", msg_id=msg_id, is_group=is_group)
            prompt = f"If you need to show files to user, use [FILE:filepath] in your response.\n\n{text}"
            dq = agent.put_task(prompt, source="qq")
            last_ping = time.time()
            while state["running"]:
                try:
                    item = await asyncio.to_thread(dq.get, True, 3)
                except Q.Empty:
                    if agent.is_running and time.time() - last_ping > 20:
                        await self.send_text(chat_id, "⏳ 还在处理中，请稍等...", msg_id=msg_id, is_group=is_group)
                        last_ping = time.time()
                    continue
                if "done" in item:
                    await self.send_done(chat_id, item.get("done", ""), msg_id=msg_id, is_group=is_group)
                    break
            if not state["running"]:
                await self.send_text(chat_id, "⏹️ 已停止", msg_id=msg_id, is_group=is_group)
        except Exception as e:
            import traceback

            print(f"[QQ] run_agent error: {e}")
            traceback.print_exc()
            await self.send_text(chat_id, f"❌ 错误: {e}", msg_id=msg_id, is_group=is_group)
        finally:
            _USER_TASKS.pop(chat_id, None)

    async def on_message(self, data, is_group=False):
        try:
            msg_id = getattr(data, "id", None)
            if msg_id in _PROCESSED_IDS:
                return
            _PROCESSED_IDS.append(msg_id)
            content = (getattr(data, "content", "") or "").strip()
            if not content:
                return
            author = getattr(data, "author", None)
            if is_group:
                chat_id = str(getattr(data, "group_openid", "") or "")
                user_id = str(getattr(author, "member_openid", "") or getattr(author, "id", "") or "unknown")
            else:
                user_id = str(getattr(author, "user_openid", "") or getattr(author, "id", "") or "unknown")
                chat_id = user_id
            public_access = not ALLOWED or "*" in ALLOWED
            if not public_access and user_id not in ALLOWED:
                print(f"[QQ] unauthorized user: {user_id}")
                return
            print(f"[QQ] message from {user_id} ({'group' if is_group else 'c2c'}): {content}")
            if content.startswith("/"):
                await self.handle_command(chat_id, content, msg_id=msg_id, is_group=is_group)
                return
            asyncio.create_task(self.run_agent(chat_id, content, msg_id=msg_id, is_group=is_group))
        except Exception:
            import traceback

            print("[QQ] handle_message error")
            traceback.print_exc()

    async def start(self):
        BotClass = _make_bot_class(self)
        self.client = BotClass()
        while True:
            try:
                print(f"[QQ] bot starting... {time.strftime('%m-%d %H:%M')}")
                await self.client.start(appid=APP_ID, secret=APP_SECRET)
            except Exception as e:
                print(f"[QQ] bot error: {e}")
            print("[QQ] reconnect in 5s...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        _lock_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _lock_sock.bind(("127.0.0.1", 19528))
    except OSError:
        print("[QQ] Another instance is already running, skipping...")
        sys.exit(1)

    if not APP_ID or not APP_SECRET:
        print("[QQ] ERROR: please set qq_app_id and qq_app_secret in mykey.py or mykey.json")
        sys.exit(1)
    if agent.llmclient is None:
        print("[QQ] ERROR: no usable LLM backend found in mykey.py or mykey.json")
        sys.exit(1)

    log_dir = os.path.join(os.path.dirname(__file__), "temp")
    os.makedirs(log_dir, exist_ok=True)
    _logf = open(os.path.join(log_dir, "qqapp.log"), "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _logf
    print("[NEW] QQ process starting, the above are history infos ...")
    print(f"[QQ] allow list: {'public' if not ALLOWED or '*' in ALLOWED else sorted(ALLOWED)}")
    threading.Thread(target=agent.run, daemon=True).start()
    asyncio.run(QQApp().start())
