import os, sys, re, threading, asyncio, queue as Q, socket, time, glob, json
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agentmain import GeneraticAgent
from llmcore import mykeys

try:
    from dingtalk_stream import AckMessage, CallbackHandler, Credential, DingTalkStreamClient
    from dingtalk_stream.chatbot import ChatbotMessage
except Exception:
    print("Please install dingtalk-stream to use DingTalk: pip install dingtalk-stream")
    sys.exit(1)

agent = GeneraticAgent()
agent.verbose = False

CLIENT_ID = str(mykeys.get("dingtalk_client_id", "") or "").strip()
CLIENT_SECRET = str(mykeys.get("dingtalk_client_secret", "") or "").strip()
ALLOWED = {str(x).strip() for x in mykeys.get("dingtalk_allowed_users", []) if str(x).strip()}

_TAG_PATS = [r"<" + t + r">.*?</" + t + r">" for t in ("thinking", "summary", "tool_use", "file_content")]
_USER_TASKS = {}


def _clean(text):
    for pat in _TAG_PATS:
        text = re.sub(pat, "", text, flags=re.DOTALL)
    return re.sub(r"\n{3,}", "\n\n", text).strip() or "..."


def _extract_files(text):
    return re.findall(r"\[FILE:([^\]]+)\]", text or "")


def _strip_files(text):
    return re.sub(r"\[FILE:[^\]]+\]", "", text or "").strip()


def _split_text(text, limit=1800):
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


class DingTalkApp:
    def __init__(self):
        self.client = None
        self.access_token = None
        self.token_expiry = 0
        self.background_tasks = set()

    async def _get_access_token(self):
        if self.access_token and time.time() < self.token_expiry:
            return self.access_token

        def _fetch():
            resp = requests.post(
                "https://api.dingtalk.com/v1.0/oauth2/accessToken",
                json={"appKey": CLIENT_ID, "appSecret": CLIENT_SECRET},
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json()

        try:
            data = await asyncio.to_thread(_fetch)
            self.access_token = data.get("accessToken")
            self.token_expiry = time.time() + int(data.get("expireIn", 7200)) - 60
            return self.access_token
        except Exception as e:
            print(f"[DingTalk] token error: {e}")
            return None

    async def _send_batch_message(self, chat_id, msg_key, msg_param):
        token = await self._get_access_token()
        if not token:
            return False
        headers = {"x-acs-dingtalk-access-token": token}
        if chat_id.startswith("group:"):
            url = "https://api.dingtalk.com/v1.0/robot/groupMessages/send"
            payload = {
                "robotCode": CLIENT_ID,
                "openConversationId": chat_id[6:],
                "msgKey": msg_key,
                "msgParam": json.dumps(msg_param, ensure_ascii=False),
            }
        else:
            url = "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"
            payload = {
                "robotCode": CLIENT_ID,
                "userIds": [chat_id],
                "msgKey": msg_key,
                "msgParam": json.dumps(msg_param, ensure_ascii=False),
            }

        def _post():
            resp = requests.post(url, json=payload, headers=headers, timeout=20)
            body = resp.text
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}: {body[:300]}")
            try:
                result = resp.json()
            except Exception:
                result = {}
            errcode = result.get("errcode")
            if errcode not in (None, 0):
                raise RuntimeError(f"API errcode={errcode}: {body[:300]}")
            return True

        try:
            return await asyncio.to_thread(_post)
        except Exception as e:
            print(f"[DingTalk] send error: {e}")
            return False

    async def send_text(self, chat_id, content):
        for part in _split_text(content):
            await self._send_batch_message(chat_id, "sampleMarkdown", {"text": part, "title": "Agent Reply"})

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
            dq = agent.put_task(prompt, source="dingtalk")
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

            print(f"[DingTalk] run_agent error: {e}")
            traceback.print_exc()
            await self.send_text(chat_id, f"❌ 错误: {e}")
        finally:
            _USER_TASKS.pop(chat_id, None)

    async def on_message(self, content, sender_id, sender_name, conversation_type=None, conversation_id=None):
        try:
            if not content:
                return
            public_access = not ALLOWED or "*" in ALLOWED
            if not public_access and sender_id not in ALLOWED:
                print(f"[DingTalk] unauthorized user: {sender_id}")
                return
            is_group = conversation_type == "2" and conversation_id
            chat_id = f"group:{conversation_id}" if is_group else sender_id
            print(f"[DingTalk] message from {sender_name} ({sender_id}): {content}")
            if content.startswith("/"):
                await self.handle_command(chat_id, content)
                return
            task = asyncio.create_task(self.run_agent(chat_id, content))
            self.background_tasks.add(task)
            task.add_done_callback(self.background_tasks.discard)
        except Exception:
            import traceback

            print("[DingTalk] handle_message error")
            traceback.print_exc()

    async def start(self):
        handler = _DingTalkHandler(self)
        self.client = DingTalkStreamClient(Credential(CLIENT_ID, CLIENT_SECRET))
        self.client.register_callback_handler(ChatbotMessage.TOPIC, handler)
        print("[DingTalk] bot starting...")
        while True:
            try:
                await self.client.start()
            except Exception as e:
                print(f"[DingTalk] stream error: {e}")
            print("[DingTalk] reconnect in 5s...")
            await asyncio.sleep(5)


class _DingTalkHandler(CallbackHandler):
    def __init__(self, app):
        super().__init__()
        self.app = app

    async def process(self, message):
        try:
            chatbot_msg = ChatbotMessage.from_dict(message.data)
            text = ""
            if getattr(getattr(chatbot_msg, "text", None), "content", None):
                text = chatbot_msg.text.content.strip()
            extensions = getattr(chatbot_msg, "extensions", None) or {}
            recognition = ((extensions.get("content") or {}).get("recognition") or "").strip() if isinstance(extensions, dict) else ""
            if not text:
                text = recognition or str((message.data.get("text", {}) or {}).get("content", "") or "").strip()
            sender_id = getattr(chatbot_msg, "sender_staff_id", None) or getattr(chatbot_msg, "sender_id", None) or "unknown"
            sender_name = getattr(chatbot_msg, "sender_nick", None) or "Unknown"
            conversation_type = message.data.get("conversationType")
            conversation_id = message.data.get("conversationId") or message.data.get("openConversationId")
            await self.app.on_message(text, str(sender_id), sender_name, conversation_type, conversation_id)
            return AckMessage.STATUS_OK, "OK"
        except Exception as e:
            print(f"[DingTalk] callback error: {e}")
            return AckMessage.STATUS_OK, "Error"


if __name__ == "__main__":
    try:
        _lock_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _lock_sock.bind(("127.0.0.1", 19530))
    except OSError:
        print("[DingTalk] Another instance is already running, skipping...")
        sys.exit(1)

    if not CLIENT_ID or not CLIENT_SECRET:
        print("[DingTalk] ERROR: please set dingtalk_client_id and dingtalk_client_secret in mykey.py or mykey.json")
        sys.exit(1)
    if agent.llmclient is None:
        print("[DingTalk] ERROR: no usable LLM backend found in mykey.py or mykey.json")
        sys.exit(1)

    log_dir = os.path.join(os.path.dirname(__file__), "temp")
    os.makedirs(log_dir, exist_ok=True)
    _logf = open(os.path.join(log_dir, "dingtalkapp.log"), "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _logf
    print("[NEW] DingTalk process starting, the above are history infos ...")
    print(f"[DingTalk] allow list: {'public' if not ALLOWED or '*' in ALLOWED else sorted(ALLOWED)}")
    threading.Thread(target=agent.run, daemon=True).start()
    asyncio.run(DingTalkApp().start())
