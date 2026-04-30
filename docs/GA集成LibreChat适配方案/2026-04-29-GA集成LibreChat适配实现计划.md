# GA 集成 LibreChat 适配实现计划

> 日期：2026-04-29
> 目标项目：`E:\zfengl-ai-project\GenericAgent`
> 对接项目：`E:\zfengl-ai-project\LibreChat`
> 计划类型：独立 adapter 模块实现计划
> 实施原则：只在 GA 项目新增中间层；LibreChat 侧只做 custom endpoint 配置；不改 GA core，不改 LibreChat 源码。

## 1. 实现目标

第一阶段目标是做出一个能被 LibreChat custom endpoint 直接调用的 GA adapter，让用户在 LibreChat 里获得完整基础聊天体验：

- OpenAI-compatible `/v1/chat/completions`。
- 真流式 SSE 输出。
- GA 累积快照转 OpenAI delta，避免重复刷屏。
- 过程摘要和工具调用摘要可以在 LibreChat 中显示。
- 会话元数据从 body 或 headers 进入 adapter。
- 页面刷新、浏览器关闭后，LibreChat 仍可凭历史 `messages` 继续对话。
- GA 现有历史会话可通过 `/v1/ga/sessions` 查询和读取。
- busy、abort、错误响应有明确行为。

第一阶段不做：

- 不做 SQLite 状态库。
- 不做多用户并发运行。
- 不做真正 conversation 级 GA runtime 隔离。
- 不做 LibreChat 前端改造。
- 不做图片和附件。
- 不开放有副作用的 GA session restore 接口。

## 2. 关键架构决策

### 2.1 新模块位置

新增目录：

```text
frontends/librechat_adapter/
```

第一阶段新增文件：

```text
frontends/librechat_adapter/
├── __init__.py
├── server.py
├── protocol.py
├── metadata.py
├── streaming.py
├── events.py
├── ga_sessions.py
├── sessions.py
├── runner.py
└── README.md
```

第一阶段新增测试：

```text
tests/frontends/
├── __init__.py
├── test_librechat_adapter_protocol.py
├── test_librechat_adapter_metadata.py
├── test_librechat_adapter_streaming.py
├── test_librechat_adapter_events.py
├── test_librechat_adapter_ga_sessions.py
├── test_librechat_adapter_runner.py
└── test_librechat_adapter_server.py
```

### 2.2 技术栈

- HTTP server：Python 标准库 `http.server.ThreadingHTTPServer` 和 `BaseHTTPRequestHandler`。
- 并发与队列：Python 标准库 `threading`、`queue`。
- 测试：现有项目风格 `unittest`。
- JSON、时间、ID：标准库 `json`、`time`、`uuid`、`hashlib`。
- 不引入 FastAPI、Flask、pydantic、SQLAlchemy 等外部依赖。

### 2.3 对话上下文恢复规则

LibreChat 消息是第一阶段“页面刷新、浏览器关闭、adapter 重启后继续聊天”的上下文来源。

adapter 维护一个内存会话表：

```text
conversation_key = user_id + ":" + conversation_id
```

处理规则：

1. 如果当前 `conversation_key` 已在本 adapter 进程中活跃，且没有切换会话，则把最新用户消息作为 GA 输入，避免重复注入完整历史。
2. 如果 adapter 刚启动、会话首次进入、或用户切换了 `conversation_key`，则先清理当前 GA runtime 可见上下文，再用 LibreChat 请求里的 `messages` 构造上下文 prompt。
3. 第一阶段使用单 GA runtime，因此每次切换 conversation 都以 LibreChat 的 `messages` 重新注入上下文；这样页面刷新和系统重启后能继续聊，但不同 conversation 不承诺并行隔离。
4. 如果 LibreChat 请求中没有 `conversation_id`，使用 `local-single-user/default-conversation` fallback，并记录 metadata source。

## 3. 文件职责

### 3.1 `protocol.py`

职责：

- 解析 OpenAI Chat Completions 请求。
- 规范化 `messages`。
- 从 message content 中提取文本和图片引用信息。
- 构造非流式 completion 响应。
- 构造 SSE chunk。
- 构造 OpenAI 风格错误响应。
- 把 LibreChat messages 转成 GA prompt。

核心接口：

```python
def parse_chat_request(body: dict) -> ChatRequest:
    ...

def normalize_messages(messages: list[dict]) -> list[NormalizedMessage]:
    ...

def build_prompt_from_messages(
    messages: list[NormalizedMessage],
    include_history: bool,
    max_context_chars: int = 32000,
) -> str:
    ...

def make_completion_response(request_id: str, model: str, content: str) -> dict:
    ...

def make_sse_chunk(request_id: str, model: str, delta: dict, finish_reason=None) -> str:
    ...

def make_error_payload(message: str, code: str, type_: str = "ga_error") -> dict:
    ...
```

测试覆盖：

- string content message。
- OpenAI multimodal list content 中的 text part。
- system/developer/user/assistant 顺序保留。
- 只取最新 user message。
- 首次会话 include_history 时生成带历史上下文的 prompt。
- 非首次会话 include_history 为 false 时只发送最新用户文本。
- 空 messages 返回 `bad_request`。
- 未知模型返回 `model_not_found`。
- OpenAI chunk JSON 包含 `chat.completion.chunk`、`delta.content`、`finish_reason`。

### 3.2 `metadata.py`

职责：

- 从请求体和 headers 提取 LibreChat 会话元数据。
- 提供 fallback。
- 标识元数据来源。
- 生成 adapter 内部 conversation key。

核心接口：

```python
@dataclass
class LibreChatRequestMeta:
    conversation_id: str
    parent_message_id: str
    user_id: str
    request_id: str
    source: str

def extract_request_meta(body: dict, headers) -> LibreChatRequestMeta:
    ...

def conversation_key(meta: LibreChatRequestMeta) -> str:
    ...
```

提取优先级：

1. body：`conversation_id`、`parent_message_id`、`user`。
2. headers：`x-ga-librechat-conversation-id`、`x-ga-librechat-parent-message-id`、`x-ga-librechat-user-id`。
3. fallback：`local-single-user/default-conversation`。

测试覆盖：

- body 优先于 headers。
- headers 可以补齐 body 缺失字段。
- 空值、原始模板字符串、`undefined`、`null` 都视为缺失。
- fallback 生成稳定 conversation key。
- request_id 每次请求唯一。

### 3.3 `streaming.py`

职责：

- 把 GA `next` 累积快照转成 OpenAI `delta.content`。
- 避免重复输出。
- 在 `done` 时补齐剩余 delta。

核心接口：

```python
class DeltaTracker:
    def __init__(self):
        self.last_full_text = ""

    def consume_snapshot(self, current_full_text: str) -> str:
        ...
```

规则：

- `hello` -> delta `hello`。
- `hello world` -> delta ` world`。
- 重复 `hello world` -> delta 空字符串。
- 快照回退不发送内容，并标记异常状态。
- 前缀不一致时只发送可证明的新增部分；不能证明则让 runner 终止本轮流式并返回错误。

测试覆盖：

- `["hello", "hello world"]` 输出 `["hello", " world"]`。
- 重复快照不输出 delta。
- `done` 快照补齐最后 delta。
- 空字符串不输出。
- 回退快照不重复输出旧文本。
- 中文、换行、Markdown 不被破坏。

### 3.4 `events.py`

职责：

- 解析 GA 输出中的过程信息。
- 清洗 assistant 最终内容。
- 渲染 LibreChat 可展示的 Markdown 过程块。

核心接口：

```python
@dataclass
class GAProcessEvent:
    type: str
    turn: int | None
    tool_name: str
    summary: str
    content_delta: str

def strip_summary_blocks(text: str) -> str:
    ...

def parse_process_events(text: str) -> list[GAProcessEvent]:
    ...

def render_process_markdown(events: list[GAProcessEvent]) -> str:
    ...
```

第一阶段复用现有 `frontends.webui_server.strip_summary_blocks` 和 `parse_execution_log` 的正则思路，但实现放在 adapter 自己模块里，避免互相耦合。

测试覆盖：

- `<summary>...</summary>` 被提取为 `reasoning_summary`。
- `LLM Running (Turn N)` 能识别 turn。
- assistant 展示内容不包含原始 `<summary>`。
- Markdown 过程块包含“思考过程”和“最终回复”边界。
- 长摘要按长度限制截断。

### 3.5 `ga_sessions.py`

职责：

- 包装 GA 现有 `frontends/continue_cmd.py` 会话能力。
- 提供只读 session 列表。
- 提供只读 session 消息读取。
- 不暴露本地绝对路径。

核心接口：

```python
@dataclass
class GASessionSummary:
    id: str
    path: str
    updated_at: int
    relative_time: str
    rounds: int
    preview: str
    native_history_available: bool

class GASessionBridge:
    def list_sessions(self, limit: int = 20) -> list[GASessionSummary]:
        ...

    def read_session(self, session_id: str) -> dict:
        ...
```

安全规则：

- `session_id` 使用文件路径 hash 加 mtime 生成，不包含原始路径。
- 内部映射只允许指向 `temp/model_responses` 下的 `model_responses_*.txt` 或 snapshot 文件。
- HTTP 响应不返回 `path`。
- `read_session` 返回 `extract_ui_messages(path)` 的清洗结果。

测试覆盖：

- 有历史文件时返回 session 列表。
- session id 不包含 `:\`、`/`、`\`、`model_responses`。
- 无效 session id 返回 `not_found`。
- 读取结果是 `{role, content}` 列表。
- assistant 内容不含 `<summary>` 原文。

### 3.6 `sessions.py`

职责：

- 管理 adapter 当前进程内的 LibreChat conversation 状态。
- 决定当前请求是否需要注入完整 LibreChat messages。
- 在单 GA runtime 下处理 conversation 切换。

核心接口：

```python
@dataclass
class RuntimeConversationState:
    key: str
    last_parent_message_id: str
    seen_message_count: int
    updated_at: float

class InMemoryConversationManager:
    def should_include_history(self, key: str, parent_message_id: str, message_count: int) -> bool:
        ...

    def mark_seen(self, key: str, parent_message_id: str, message_count: int) -> None:
        ...

    def is_switching_conversation(self, key: str) -> bool:
        ...
```

第一阶段策略：

- adapter 当前只持有一个 GA runtime。
- 如果请求 key 与 active key 不同，需要 runner 清理 GA 当前上下文，然后使用完整 LibreChat messages 构造 prompt。
- 同一 key 连续请求只发最新 user message。

测试覆盖：

- 首次看到 key 需要 include_history。
- 同一 key 且 message_count 增加时不需要重复注入完整历史。
- 切换 key 时返回 switching。
- fallback key 稳定。

### 3.7 `runner.py`

职责：

- 创建和持有 GA runtime。
- 调用 `agent.put_task(...)`。
- 读取 GA display queue。
- 管理 busy、abort、客户端断开。
- 把 protocol、metadata、sessions、streaming、events 串起来。

核心接口：

```python
class LibreChatAdapterRunner:
    def __init__(self, agent):
        ...

    def chat(self, request: ChatRequest, meta: LibreChatRequestMeta):
        ...

    def stream_chat(self, request: ChatRequest, meta: LibreChatRequestMeta):
        ...

    def abort_current(self) -> dict:
        ...
```

第一阶段运行规则：

- 如果 `agent.is_running` 或 runner 已有 running task，直接返回 `429 busy`。
- 进入新 conversation key 时调用 `continue_cmd.reset_conversation(agent, message=None)` 清理当前 runtime。
- 根据 `sessions.should_include_history(...)` 决定 prompt 是否包含完整 LibreChat messages。
- `source` 使用 `librechat`。
- `images` 第一阶段传空列表。
- stream 模式中每个 GA `next` 先经 `events.strip_summary_blocks`，再经 `DeltaTracker`。
- `done` 发送最后增量、finish chunk、`[DONE]`。
- 客户端断开时调用 `agent.abort()`，任务标记为 aborted。

测试覆盖：

- busy 时不会调用 `put_task`。
- 首次会话使用完整 messages prompt。
- 同一会话第二次只使用最新 user prompt。
- 切换 conversation 时会 reset GA runtime。
- queue 中 `next/done` 转成 delta。
- `abort_current` 调用 fake agent abort。

### 3.8 `server.py`

职责：

- 启动 HTTP server。
- 路由 `/health`、`/v1/models`、`/v1/chat/completions`、`/v1/ga/sessions`。
- 校验 Authorization。
- 输出 OpenAI-compatible JSON 和 SSE。

命令：

```powershell
py -3 -m frontends.librechat_adapter.server --host 127.0.0.1 --port 18601
```

认证规则：

- `/health` 不强制认证，但返回 `configured`。
- `/v1/models`、`/v1/chat/completions`、`/v1/ga/*` 校验 `Authorization: Bearer <GA_API_KEY>`。
- 如果未设置 `GA_API_KEY`，非 health 接口返回 `401 unauthorized`。

测试覆盖：

- `/health` 返回 adapter service 名。
- 缺少 Authorization 返回 401。
- `/v1/models` 返回 `generic-agent`。
- 非 JSON body 返回 `bad_request`。
- unknown path 返回 OpenAI 风格错误。

## 4. 实施任务拆分

### Task 1：创建 adapter 骨架

文件：

- 新建：`frontends/librechat_adapter/__init__.py`
- 新建：`frontends/librechat_adapter/protocol.py`
- 新建：`frontends/librechat_adapter/metadata.py`
- 新建：`frontends/librechat_adapter/streaming.py`
- 新建：`frontends/librechat_adapter/events.py`
- 新建：`frontends/librechat_adapter/ga_sessions.py`
- 新建：`frontends/librechat_adapter/sessions.py`
- 新建：`frontends/librechat_adapter/runner.py`
- 新建：`frontends/librechat_adapter/server.py`
- 新建：`tests/frontends/__init__.py`

步骤：

1. 新建目录和空模块。
2. 每个模块先写最小 docstring，说明责任边界。
3. 不导入 LibreChat 代码。
4. 不改 `frontends/webui_server.py`。

验证：

```powershell
py -3 -m py_compile frontends\librechat_adapter\__init__.py frontends\librechat_adapter\protocol.py frontends\librechat_adapter\metadata.py frontends\librechat_adapter\streaming.py frontends\librechat_adapter\events.py frontends\librechat_adapter\ga_sessions.py frontends\librechat_adapter\sessions.py frontends\librechat_adapter\runner.py frontends\librechat_adapter\server.py
```

### Task 2：实现 metadata 提取

文件：

- 修改：`frontends/librechat_adapter/metadata.py`
- 新建：`tests/frontends/test_librechat_adapter_metadata.py`

测试先写：

- `test_body_fields_win_over_headers`
- `test_headers_fill_missing_body_fields`
- `test_fallback_meta_when_all_fields_missing`
- `test_template_literal_values_are_treated_as_missing`
- `test_conversation_key_is_stable`

实现要点：

- header 读取需要兼容大小写。
- `""`、`"undefined"`、`"null"`、以 `"{{"` 开头且以 `"}}"` 结尾的值视为缺失。
- fallback 不阻断第一阶段本地单用户使用。

验证：

```powershell
py -3 -m unittest tests.frontends.test_librechat_adapter_metadata -v
```

### Task 3：实现 protocol 请求与响应

文件：

- 修改：`frontends/librechat_adapter/protocol.py`
- 新建：`tests/frontends/test_librechat_adapter_protocol.py`

测试先写：

- `test_parse_chat_request_accepts_basic_messages`
- `test_normalize_messages_accepts_text_parts`
- `test_build_prompt_includes_history_for_first_seen_conversation`
- `test_build_prompt_uses_latest_user_only_for_active_conversation`
- `test_make_sse_chunk_matches_openai_shape`
- `test_make_error_payload_matches_openai_shape`
- `test_empty_messages_raise_bad_request`

实现要点：

- `model` 默认要求 `generic-agent`。
- `stream` 默认 false。
- `messages` 必须是非空 list。
- prompt 构造中明确标记历史上下文：

```text
### LibreChat Conversation Context
[system] ...
[user] ...
[assistant] ...

### Current User Message
...
```

- `max_context_chars` 从最近消息向前截断，避免超长历史压垮 GA。

验证：

```powershell
py -3 -m unittest tests.frontends.test_librechat_adapter_protocol -v
```

### Task 4：实现 DeltaTracker

文件：

- 修改：`frontends/librechat_adapter/streaming.py`
- 新建：`tests/frontends/test_librechat_adapter_streaming.py`

测试先写：

- `test_snapshot_sequence_emits_only_suffix`
- `test_duplicate_snapshot_emits_empty_delta`
- `test_done_snapshot_can_emit_remaining_suffix`
- `test_empty_snapshot_emits_empty_delta`
- `test_regressed_snapshot_does_not_repeat_old_text`
- `test_multiline_chinese_markdown_is_preserved`

实现要点：

- 最简单可靠策略：正常前缀追加时取 suffix。
- 重复和回退不输出。
- 前缀不一致时返回空 delta 并记录 `regressed=True`，第一阶段不做复杂修补。

验证：

```powershell
py -3 -m unittest tests.frontends.test_librechat_adapter_streaming -v
```

### Task 5：实现过程事件解析

文件：

- 修改：`frontends/librechat_adapter/events.py`
- 新建：`tests/frontends/test_librechat_adapter_events.py`

测试先写：

- `test_strip_summary_blocks_removes_private_summary`
- `test_parse_summary_blocks_as_reasoning_events`
- `test_turn_markers_are_preserved_as_process_events`
- `test_render_process_markdown_has_clear_sections`
- `test_long_summary_is_truncated`

实现要点：

- 可复制 `frontends/webui_server.py` 当前正则思路，但代码放在 adapter 内。
- 不输出原始隐藏推理。
- 默认通过 Markdown 分区塞进 `delta.content`。

验证：

```powershell
py -3 -m unittest tests.frontends.test_librechat_adapter_events -v
```

### Task 6：实现 GA session bridge 只读接口能力

文件：

- 修改：`frontends/librechat_adapter/ga_sessions.py`
- 新建：`tests/frontends/test_librechat_adapter_ga_sessions.py`

测试先写：

- `test_list_sessions_returns_opaque_ids`
- `test_list_sessions_does_not_expose_paths`
- `test_read_session_returns_ui_messages`
- `test_read_missing_session_returns_not_found`
- `test_read_session_strips_summary_blocks`

实现要点：

- 复用 `frontends.continue_cmd.list_sessions`。
- 复用 `frontends.continue_cmd.extract_ui_messages`。
- `session_id` 由 `sha256(path + mtime)` 生成。
- bridge 内部保存 `session_id -> path` 映射。
- 每次 list 刷新映射，read 只读映射内 path。

验证：

```powershell
py -3 -m unittest tests.frontends.test_librechat_adapter_ga_sessions -v
```

### Task 7：实现进程内会话管理

文件：

- 修改：`frontends/librechat_adapter/sessions.py`
- 新建或扩展：`tests/frontends/test_librechat_adapter_runner.py`

测试先写：

- `test_first_request_for_conversation_includes_history`
- `test_second_request_for_same_conversation_uses_latest_only`
- `test_switching_conversation_requires_runtime_reset`
- `test_mark_seen_updates_parent_message_id`

实现要点：

- 只做内存态，不写 SQLite。
- 记录 active key。
- 切换 key 时告诉 runner 需要 reset。
- 不做多 runtime。

验证：

```powershell
py -3 -m unittest tests.frontends.test_librechat_adapter_runner -v
```

### Task 8：实现 runner

文件：

- 修改：`frontends/librechat_adapter/runner.py`
- 扩展：`tests/frontends/test_librechat_adapter_runner.py`

测试先写：

- `test_busy_returns_error_without_put_task`
- `test_stream_chat_calls_put_task_with_librechat_source`
- `test_stream_chat_emits_delta_chunks_from_snapshots`
- `test_done_emits_finish_chunk`
- `test_conversation_switch_resets_agent_context`
- `test_abort_current_calls_agent_abort`

FakeAgent 设计：

- `is_running`
- `history`
- `handler`
- `llmclient.backend.history`
- `put_task(query, source, images)`
- `abort()`

实现要点：

- runner 不知道 HTTP。
- runner 输出 Python dict 或 SSE-ready chunk，由 server 写 wire format。
- `queue.Empty` 输出 heartbeat 或继续等待。
- 捕获 GA 异常并转成 OpenAI error payload。

验证：

```powershell
py -3 -m unittest tests.frontends.test_librechat_adapter_runner -v
```

### Task 9：实现 HTTP server

文件：

- 修改：`frontends/librechat_adapter/server.py`
- 新建：`tests/frontends/test_librechat_adapter_server.py`

测试先写：

- `test_health_without_auth`
- `test_models_requires_auth`
- `test_models_returns_generic_agent`
- `test_chat_requires_auth`
- `test_sessions_requires_auth`
- `test_unknown_route_returns_error`

实现要点：

- 基于 `BaseHTTPRequestHandler`。
- `_read_json`、`_send_json`、`_send_openai_error`、`_send_sse` 做成私有函数。
- `Authorization` 必须匹配 `Bearer {GA_API_KEY}`。
- 启动入口支持：

```powershell
py -3 -m frontends.librechat_adapter.server --host 127.0.0.1 --port 18601
```

验证：

```powershell
py -3 -m unittest tests.frontends.test_librechat_adapter_server -v
py -3 -m py_compile frontends\librechat_adapter\server.py
```

### Task 10：写 adapter README 和 LibreChat 配置片段

文件：

- 新建：`frontends/librechat_adapter/README.md`

内容必须包含：

- 启动命令。
- 环境变量 `GA_API_KEY`。
- LibreChat custom endpoint 配置。
- `/health`、`/v1/models`、`/v1/chat/completions`、`/v1/ga/sessions` 示例。
- 第一阶段限制：单 runtime、无 SQLite、无附件、多 conversation 通过 messages 重新注入上下文。

验证：

```powershell
Select-String -LiteralPath frontends\librechat_adapter\README.md -Pattern 'GA_API_KEY','/v1/chat/completions','/v1/ga/sessions','titleConvo'
```

### Task 11：本地手动 smoke test

前置：

```powershell
$env:GA_API_KEY='local-ga-dev-key'
py -3 -m frontends.librechat_adapter.server --host 127.0.0.1 --port 18601
```

另开 PowerShell 验证：

```powershell
curl.exe http://127.0.0.1:18601/health
curl.exe http://127.0.0.1:18601/v1/models -H "Authorization: Bearer local-ga-dev-key"
curl.exe http://127.0.0.1:18601/v1/ga/sessions -H "Authorization: Bearer local-ga-dev-key"
curl.exe -N http://127.0.0.1:18601/v1/chat/completions -H "Authorization: Bearer local-ga-dev-key" -H "Content-Type: application/json" -d "{\"model\":\"generic-agent\",\"stream\":true,\"messages\":[{\"role\":\"user\",\"content\":\"用一句话回复：GA LibreChat adapter smoke test\"}]}"
```

验收：

- health 正常。
- models 返回 `generic-agent`。
- sessions 返回 list，即使为空也返回合法 JSON。
- chat completions 流式输出至少包含首个 role chunk、content chunk、finish chunk、`[DONE]`。
- 服务端无 traceback。

### Task 12：LibreChat placeholder 验证

目标：

- 验证 LibreChat custom endpoint headers 中的 placeholder 是否真的展开。

LibreChat 配置片段：

```yaml
endpoints:
  custom:
    - name: 'ga'
      apiKey: '${GA_API_KEY}'
      baseURL: 'http://127.0.0.1:18601/v1'
      models:
        default: ['generic-agent']
        fetch: false
      titleConvo: false
      modelDisplayLabel: 'GenericAgent'
      dropParams: ['stop', 'frequency_penalty', 'presence_penalty']
      headers:
        x-ga-librechat-conversation-id: '{{LIBRECHAT_BODY_CONVERSATIONID}}'
        x-ga-librechat-parent-message-id: '{{LIBRECHAT_BODY_PARENTMESSAGEID}}'
        x-ga-librechat-user-id: '{{LIBRECHAT_USER_ID}}'
```

验证方式：

- adapter 在 metadata 提取时打印一行精简日志：`source=header conversation_id=... parent_message_id=... user_id=...`。
- 从 LibreChat 发送一条消息。
- 确认日志不是空值，不是 `{{...}}` 原始模板。

如果 `conversation_id` placeholder 不可用：

- 第一阶段继续 fallback 单用户模式。
- 文档记录实际可用字段名。
- 第二阶段会话隔离前必须解决。

## 5. 第一阶段总验证命令

```powershell
py -3 -m unittest tests.frontends.test_librechat_adapter_metadata -v
py -3 -m unittest tests.frontends.test_librechat_adapter_protocol -v
py -3 -m unittest tests.frontends.test_librechat_adapter_streaming -v
py -3 -m unittest tests.frontends.test_librechat_adapter_events -v
py -3 -m unittest tests.frontends.test_librechat_adapter_ga_sessions -v
py -3 -m unittest tests.frontends.test_librechat_adapter_runner -v
py -3 -m unittest tests.frontends.test_librechat_adapter_server -v
py -3 -m py_compile frontends\librechat_adapter\__init__.py frontends\librechat_adapter\protocol.py frontends\librechat_adapter\metadata.py frontends\librechat_adapter\streaming.py frontends\librechat_adapter\events.py frontends\librechat_adapter\ga_sessions.py frontends\librechat_adapter\sessions.py frontends\librechat_adapter\runner.py frontends\librechat_adapter\server.py
```

可选回归：

```powershell
py -3 -m unittest tests.test_webui_server -v
```

## 6. 第二阶段进入条件

满足以下条件后再进入 SQLite 和持久绑定：

- 第一阶段 LibreChat 能稳定流式对话。
- placeholder 已验证，能拿到稳定 `conversation_id`。
- GA session 查询和读取接口可用。
- abort 后能重新发起下一轮请求。
- 没有出现前端重复 delta 或大段重复历史注入。

第二阶段新增文件：

```text
frontends/librechat_adapter/storage.py
tests/frontends/test_librechat_adapter_storage.py
```

第二阶段能力：

- SQLite 保存 conversation 映射。
- SQLite 保存 task_runs。
- SQLite 保存 process_events 摘要。
- LibreChat conversation 与 GA native session 绑定。
- 可选 `POST /v1/ga/sessions/{session_id}/restore`。

第二阶段明确不保存：

- 不保存模型原始隐藏推理链。
- 不保存完整工具输出。
- 不保存 LibreChat 已经持久化的完整消息正文。

## 7. 完成定义

第一阶段完成定义：

- `frontends/librechat_adapter/` 独立模块存在。
- `/health`、`/v1/models`、`/v1/chat/completions`、`/v1/ga/sessions`、`/v1/ga/sessions/{session_id}` 可用。
- LibreChat custom endpoint 可以调用 GA。
- GA 输出是流式的，不是最终一次性返回。
- GA 累积快照不会导致 LibreChat 重复显示。
- 页面刷新、浏览器关闭、adapter 重启后，能依赖 LibreChat `messages` 继续之前聊天。
- GA 历史会话能通过只读接口查询和读取。
- busy、abort、错误响应行为明确。
- 不修改 LibreChat 源码。
- 不修改 GA core。
- 不引入外部依赖。
- 单元测试和 py_compile 通过。
