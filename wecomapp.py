import os, sys, re, threading, asyncio, queue as Q, socket, time, glob
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agentmain import GeneraticAgent
from llmcore import mykeys

try:
    from wecom_aibot_sdk import WSClient, generate_req_id
except Exception:
    print("Please install wecom_aibot_sdk to use WeCom: pip install wecom_aibot_sdk")
    sys.exit(1)

agent = GeneraticAgent()
agent.verbose = False

BOT_ID = str(mykeys.get("wecom_bot_id", "") or "").strip()
SECRET = str(mykeys.get("wecom_secret", "") or "").strip()
WELCOME = str(mykeys.get("wecom_welcome_message", "") or "").strip()
ALLOWED = {str(x).strip() for x in mykeys.get("wecom_allowed_users", []) if str(x).strip()}

_TAG_PATS = [r"<" + t + r">.*?</" + t + r">" for t in ("thinking", "summary", "tool_use", "file_content")]
_PROCESSED_IDS = deque(maxlen=1000)
_USER_TASKS = {}


def _clean(text):
    for pat in _TAG_PATS:
        text = re.sub(pat, "", text, flags=re.DOTALL)
    return re.sub(r"\n{3,}", "\n\n", text).strip() or "..."


def _extract_files(text):
    return re.findall(r"\[FILE:([^\]]+)\]", text or "")


def _strip_files(text):
    return re.sub(r"\[FILE:[^\]]+\]", "", text or "").strip()


def _split_text(text, limit=1200):
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


class WeComApp:
    def __init__(self):
        self.client = None
        self.chat_frames = {}

    def _body(self, frame):
        if hasattr(frame, "body"):
            return frame.body or {}
        if isinstance(frame, dict):
            return frame.get("body", frame)
        return {}

    async def send_text(self, chat_id, content):
        if not self.client:
            return
        frame = self.chat_frames.get(chat_id)
        if not frame:
            print(f"[WeCom] no frame found for chat: {chat_id}")
            return
        for part in _split_text(content):
            stream_id = generate_req_id("stream")
            await self.client.reply_stream(frame, stream_id, part, finish=True)

    async def send_done(self, chat_id, raw_text):
        files = [p for p in _extract_files(raw_text) if os.path.exists(p)]
        body = _strip_files(_clean(raw_text))
        if files:
            body = (body + "\n\n" if body else "") + "\n".join([f"生成文件: {p}" for p in files])
        await self.send_text(chat_id, body or "...")

    async def handle_command(self, chat_id, cmd):
        parts = (cmd or "").split()
        op = (parts[0] if parts else "").lower()
        if op == "/stop":
            state = _USER_TASKS.get(chat_id)
            if state:
                state["running"] = False
            agent.abort()
            await self.send_text(chat_id, "⏹️ 正在停止...")
        elif op == "/status":
            llm = agent.get_llm_name() if agent.llmclient else "未配置"
            await self.send_text(chat_id, f"状态: {'🔴 运行中' if agent.is_running else '🟢 空闲'}\nLLM: [{agent.llm_no}] {llm}")
        elif op == "/llm":
            if not agent.llmclient:
                return await self.send_text(chat_id, "❌ 当前没有可用的 LLM 配置")
            if len(parts) > 1:
                try:
                    n = int(parts[1])
                    agent.next_llm(n)
                    await self.send_text(chat_id, f"✅ 已切换到 [{agent.llm_no}] {agent.get_llm_name()}")
                except Exception:
                    await self.send_text(chat_id, f"用法: /llm <0-{len(agent.list_llms()) - 1}>")
            else:
                lines = [f"{'→' if cur else '  '} [{i}] {name}" for i, name, cur in agent.list_llms()]
                await self.send_text(chat_id, "LLMs:\n" + "\n".join(lines))
        elif op == "/restore":
            try:
                restored_info, err = _format_restore()
                if err:
                    return await self.send_text(chat_id, err)
                restored, fname, count = restored_info
                agent.abort()
                agent.history.extend(restored)
                await self.send_text(chat_id, f"✅ 已恢复 {count} 轮对话\n来源: {fname}\n(仅恢复上下文，请输入新问题继续)")
            except Exception as e:
                await self.send_text(chat_id, f"❌ 恢复失败: {e}")
        elif op == "/new":
            agent.abort()
            agent.history = []
            await self.send_text(chat_id, "🆕 已清空当前共享上下文")
        else:
            await self.send_text(
                chat_id,
                "📖 命令列表:\n/help - 显示帮助\n/status - 查看状态\n/stop - 停止当前任务\n/new - 清空当前上下文\n/restore - 恢复上次对话历史\n/llm [n] - 查看或切换模型",
            )

    async def run_agent(self, chat_id, text):
        state = {"running": True}
        _USER_TASKS[chat_id] = state
        try:
            await self.send_text(chat_id, "思考中...")
            prompt = f"If you need to show files to user, use [FILE:filepath] in your response.\n\n{text}"
            dq = agent.put_task(prompt, source="wecom")
            last_ping = time.time()
            while state["running"]:
                try:
                    item = await asyncio.to_thread(dq.get, True, 3)
                except Q.Empty:
                    if agent.is_running and time.time() - last_ping > 20:
                        await self.send_text(chat_id, "⏳ 还在处理中，请稍等...")
                        last_ping = time.time()
                    continue
                if "done" in item:
                    await self.send_done(chat_id, item.get("done", ""))
                    break
            if not state["running"]:
                await self.send_text(chat_id, "⏹️ 已停止")
        except Exception as e:
            import traceback

            print(f"[WeCom] run_agent error: {e}")
            traceback.print_exc()
            await self.send_text(chat_id, f"❌ 错误: {e}")
        finally:
            _USER_TASKS.pop(chat_id, None)

    async def on_text(self, frame):
        try:
            body = self._body(frame)
            if not isinstance(body, dict):
                return
            msg_id = body.get("msgid") or f"{body.get('chatid', '')}_{body.get('sendertime', '')}"
            if msg_id in _PROCESSED_IDS:
                return
            _PROCESSED_IDS.append(msg_id)
            from_info = body.get("from", {}) if isinstance(body.get("from", {}), dict) else {}
            sender_id = str(from_info.get("userid", "") or "unknown")
            chat_id = str(body.get("chatid", "") or sender_id)
            content = str((body.get("text", {}) or {}).get("content", "") or "").strip()
            if not content:
                return
            public_access = not ALLOWED or "*" in ALLOWED
            if not public_access and sender_id not in ALLOWED:
                print(f"[WeCom] unauthorized user: {sender_id}")
                return
            self.chat_frames[chat_id] = frame
            print(f"[WeCom] message from {sender_id}: {content}")
            if content.startswith("/"):
                await self.handle_command(chat_id, content)
                return
            asyncio.create_task(self.run_agent(chat_id, content))
        except Exception:
            import traceback

            print("[WeCom] handle_message error")
            traceback.print_exc()

    async def on_enter_chat(self, frame):
        if not WELCOME or not self.client:
            return
        try:
            await self.client.reply_welcome(frame, {"msgtype": "text", "text": {"content": WELCOME}})
        except Exception as e:
            print(f"[WeCom] welcome error: {e}")

    async def on_connected(self, frame):
        print("[WeCom] connected")

    async def on_authenticated(self, frame):
        print("[WeCom] authenticated")

    async def on_disconnected(self, frame):
        print("[WeCom] disconnected")

    async def on_error(self, frame):
        print(f"[WeCom] error: {frame}")

    async def start(self):
        self.client = WSClient({
            "bot_id": BOT_ID,
            "secret": SECRET,
            "reconnect_interval": 1000,
            "max_reconnect_attempts": -1,
            "heartbeat_interval": 30000,
        })
        self.client.on("connected", self.on_connected)
        self.client.on("authenticated", self.on_authenticated)
        self.client.on("disconnected", self.on_disconnected)
        self.client.on("error", self.on_error)
        self.client.on("message.text", self.on_text)
        self.client.on("event.enter_chat", self.on_enter_chat)
        print("[WeCom] bot starting...")
        await self.client.connect_async()
        while True:
            await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        _lock_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _lock_sock.bind(("127.0.0.1", 19529))
    except OSError:
        print("[WeCom] Another instance is already running, skipping...")
        sys.exit(1)

    if not BOT_ID or not SECRET:
        print("[WeCom] ERROR: please set wecom_bot_id and wecom_secret in mykey.py or mykey.json")
        sys.exit(1)
    if agent.llmclient is None:
        print("[WeCom] ERROR: no usable LLM backend found in mykey.py or mykey.json")
        sys.exit(1)

    log_dir = os.path.join(os.path.dirname(__file__), "temp")
    os.makedirs(log_dir, exist_ok=True)
    _logf = open(os.path.join(log_dir, "wecomapp.log"), "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _logf
    print("[NEW] WeCom process starting, the above are history infos ...")
    print(f"[WeCom] allow list: {'public' if not ALLOWED or '*' in ALLOWED else sorted(ALLOWED)}")
    threading.Thread(target=agent.run, daemon=True).start()
    asyncio.run(WeComApp().start())
