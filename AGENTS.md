# 仓库指南

## 项目概述

GenericAgent（zfengl-ga）是一个极简、可自我进化的自主 AI Agent 框架，基于 Python 构建。提供完整的 Agent 循环，具备工具调用能力（文件读写、代码执行、浏览器控制）、多 LLM 后端支持与自动故障转移、四级记忆体系（L1–L4），以及 10+ 前端适配器（Telegram、Streamlit、HeroUI、微信、QQ、钉钉、飞书、桌面宠物、终端 TUI、Discord 等）。项目以中文为主，通过 `GA_LANG` 环境变量支持英文。

## 架构与数据流

### 核心层（同步，基于生成器）

```
agentmain.py (GenericAgent)           — 编排器：任务队列、LLM 会话轮转、历史管理
  └─ agent_loop.py (agent_runner_loop) — 核心循环：LLM 调用 → 工具分发 → 结果收集 → 下一轮
       ├─ BaseHandler.dispatch() → GenericAgentHandler.do_*()   — 工具执行
       ├─ llmcore.py            — LLM 抽象层（Claude/OAI/Native/Mixin 会话）
       └─ event_sink            — 结构化事件流，推送到前端
```

**数据流：**
```
用户输入 → 前端 → GenericAgent.put_task() → task_queue
  → GenericAgent.run() 出队 → 构建系统提示词（sys_prompt + 记忆 L1/L2）
    → agent_runner_loop(client, prompt, handler, tools_schema)
      → 循环：client.chat(messages, tools) → 解析响应 → 分发工具 → yield
    → display_queue: {'next': delta} / {'done': full}
  → 前端渲染给用户
```

### 两种工具协议
- **ToolClient** — 文本提示注入，解析 `<tool_use>` XML 标签（用于不支持原生工具调用的模型）
- **NativeToolClient** — API 原生 `tool_use` 块（Claude、OpenAI 原生）

### 记忆体系（四级）
- **L1** `global_mem_insight.txt` — ≤30 行索引（导航指针 + 规则）
- **L2** `global_mem.txt` — 环境事实（路径、配置、凭证）
- **L3** `memory/*.md` — 任务相关 SOP、脚本、知识文档
- **L4** `memory/L4_raw_sessions/` — 压缩的历史会话存档

记忆通过 `get_global_memory()` 注入系统提示词。Agent 通过 `start_long_term_update` 工具自我更新记忆。

### 运行模式
1. **交互式 CLI** — 直接用户对话
2. **任务模式** (`--task IODIR`) — 文件 I/O，用于子 Agent 委托（`input.txt` → agent → `output.txt`）
3. **反思模式** (`--reflect SCRIPT`) — 事件驱动循环，遵循 `check()`/`init()`/`on_done()` 协议
4. **计划模式** — 扩展轮次（最多 480 轮），基于 `plan.md` 的步骤执行，强制验证
5. **目标模式** — 持续自主运行，直到时间/轮次预算耗尽
6. **自主模式** — 基于 TODO 的任务选择，生成报告
7. **监督模式** — 只读监控工作 Agent

### 插件系统
`plugins/hooks.py` — 事件注册表，使用 `@register('event_name')` 装饰器。事件：`agent_before/after`、`turn_before/after`、`llm_before/after`、`tool_before/after`。通过 `discover_and_load()` 自动发现插件。`langfuse_tracing.py` 导入时自激活。

## 关键目录

| 路径 | 用途 |
|------|------|
| `ga.py` | 工具处理器实现（`GenericAgentHandler`）— code_run、file_read/write/patch、web 工具、计划模式 |
| `llmcore.py` | LLM 抽象层 — 会话类、SSE 解析、工具客户端、故障转移 |
| `agent_loop.py` | 核心 Agent 循环 — `agent_runner_loop()`、`BaseHandler`、`StepOutcome`、事件发射 |
| `agentmain.py` | Agent 编排器 — `GenericAgent` 类、CLI 入口、会话管理 |
| `agent_streaming.py` | 显示流过滤 — 移除协议标签用于 UI 展示 |
| `frontends/` | 20+ 前端适配器（Telegram、HeroUI、Streamlit、TUI、桌面等） |
| `frontends/heroui/` | 全栈 Web UI — React/TS 前端 + aiohttp Python 桥接 + SQLite 持久化 |
| `frontends/chatapp_common.py` | 聊天前端公共工具 — `AgentChatMixin`、斜杠命令、文本处理 |
| `reflect/` | 反思/调度模块 — `scheduler.py`、`goal_mode.py`、`agent_team_worker.py` |
| `plugins/` | 插件系统 — `hooks.py` 注册表、`langfuse_tracing.py` |
| `memory/` | 记忆 SOP、密钥链、L4 存档目录 |
| `memory/keychain.py` | XOR 加密密钥存储 |
| `tests/` | 单元测试（pytest/unittest） |
| `ga_cli/` | CLI 工具 — `ga` 命令，前端启动子命令 |
| `assets/` | 工具 schema JSON、系统提示词 |
| `simphtml.py` | HTML 简化器，用于 LLM 浏览器上下文 |
| `TMWebDriver.py` | Chrome DevTools Protocol 封装，用于 web 工具 |

## 开发命令

### Python（核心）
```bash
# 安装
pip install -e .                    # 最小安装
pip install -e ".[ui]"              # + Streamlit、TUI、Rich
pip install -e ".[all-frontends]"   # + Telegram、QQ、微信等

# 运行
python agentmain.py                 # 交互式 CLI
python agentmain.py --task <dir>    # 任务模式
python agentmain.py --reflect reflect/goal_mode.py  # 目标模式
ga gui                              # HeroUI Web（通过 CLI）
ga tui                              # 终端 TUI
ga tg                               # Telegram 机器人

# 测试
python -m pytest tests/             # 全部测试
python -m pytest tests/test_agent_loop_events.py  # 单个文件
python -m unittest discover tests/  # 替代运行器
```

### JavaScript/TypeScript（HeroUI 前端）
```bash
cd frontends/heroui
pnpm install
pnpm dev          # Vite 开发服务器 :5178 → 代理到桥接 :14169
pnpm build        # tsc + vite build
pnpm test         # tsx --test src/*.test.mjs
```

## 代码规范与常见模式

### 格式
- **4 空格缩进**，全项目统一（无 tab）
- **无强制行长度限制** — 行长度经常 120–200+ 字符
- **紧凑惯用法**：单行 `if/else`、海象运算符（`:=`）、三元表达式
- **逗号打包导入**：`import os, sys, re, json, time`

### 命名规范
- **函数**：`snake_case` — `code_run`、`file_read`、`smart_format`
- **工具处理方法**：`do_` 前缀 — `do_code_run`、`do_file_read`、`do_web_scan`
- **类**：PascalCase — `GenericAgent`、`BaseSession`、`ClaudeSession`
- **常量**：`UPPER_SNAKE_CASE` — `NORMAL_WORKING_MEMORY_WINDOW`、`PLAN_MAX_TURNS`
- **私有状态**：`_` 前缀 — `_lock`、`_l4_t`、`_registry`

### 错误处理
- **裸 `except:`** 极为常见 — 用于容错，不总是最佳实践
- **字典返回**：工具返回 `{'status': 'error', 'msg': str(e)}` 而非抛异常
- **字符串前缀检测**：下游代码检查 `if data.startswith('Error:')`
- **日志**：`print()` + `[Info]`/`[Debug]`/`[Warn]`/`[Error]` 前缀（核心无结构化日志）

### 并发模式
- **线程，非 asyncio**：核心 Agent 循环是同步的，使用 `threading.Thread` + `queue.Queue`
- **基于生成器的流式传输**：LLM 响应通过 `yield` 流式传输；`agent_runner_loop` 是生成器
- **`yield from`** 全链路传递生成器
- **asyncio 仅在 HeroUI 中使用**：`aiohttp.web` 用于 HTTP/WS 桥接，将同步 Agent 包装在线程中
- **`threading.Lock`** 用于会话和管理器的线程安全

### 状态管理
- **`handler.working` 字典**：核心可变状态 — `key_info`、`related_sop`、`in_plan_mode`、`passed_sessions`
- **`self.history`**（GenericAgent 上）：扁平 `[USER]: ...` 字符串列表，用于展示
- **后端历史**：`self.llmclient.backend.history` — role/content 字典列表，用于 LLM
- **文件状态**：调度器读 `sche_tasks/*.json`，goal_mode 用 state JSON，任务 I/O 用 `input.txt`/`output.txt`
- **SQLite 状态**：HeroUI 持久化 sessions/messages/events/agent_state

### 配置
- **`mykey.py` / `mykey.json`**：主配置 — API 密钥、允许用户、功能开关。通过 `reload_mykeys()` 热重载
- **环境变量**：`GA_LANG`（zh/en）、`GOAL_STATE`（路径）、`HEROUI_BRIDGE_DB`（SQLite 路径）
- **工具 schema**：加载自 `assets/tools_schema.json`（英文）或 `assets/tools_schema_cn.json`（中文）
- **模块级常量** 在 `ga.py` 中定义行为阈值

### 导入模式
- **`sys.path` 操作** 很普遍 — 多数模块将父目录追加到 `sys.path`
- **带回退的条件导入** 用于可选依赖
- **相对导入** 仅在 `frontends/heroui/` 包中；其余全部使用绝对导入
- **`importlib.reload()`** 用于热重载配置和 HTML 简化器

### 前端连接模式
所有前端遵循相同模式：
```python
agent = GeneraticAgent()
threading.Thread(target=agent.run, daemon=True).start()
dq = agent.put_task(prompt, source=...)
# 轮询 dq.get() 获取 {'next': chunk} 和 {'done': full}
# agent.abort() 取消
```
斜杠命令（`/continue`、`/btw`、`/review`）通过猴子补丁 `GeneraticAgent._handle_slash_cmd` 安装。

## 重要文件

| 文件 | 角色 |
|------|------|
| `ga.py` | 工具实现 — Agent 的能力集 |
| `llmcore.py` | LLM 后端 — 所有模型交互逻辑 |
| `agent_loop.py` | Agent 循环引擎 — 分发、事件、流式传输 |
| `agentmain.py` | 入口点 — `GenericAgent` 类、CLI、会话管理 |
| `assets/sys_prompt.txt` | 系统提示词，定义 Agent 人格 |
| `assets/tools_schema.json` | 发送给 LLM 的工具定义 |
| `memory/plan_sop.md` | 计划模式 SOP — 探索 → 计划 → 执行 → 验证 |
| `memory/review_sop.md` | 代码审查 SOP — 对抗性审查协议 |
| `memory/memory_management_sop.md` | 记忆体系 SOP — L1–L4 规则 |
| `frontends/heroui/bridge.py` | HeroUI Web 桥接 — 最完善的前端 |
| `frontends/chatapp_common.py` | 前端公共基类与工具 |

## 运行时/工具链偏好

- **Python**：要求 3.10–3.13（pyproject.toml）
- **包管理**：`pip` / `setuptools`（Python）；`pnpm`（HeroUI 前端）
- **无 CI/CD**：无 `.github/workflows/`、无 Makefile、无 Dockerfile
- **无类型检查**：未配置 mypy/pyright
- **无 Lint**：未配置 ruff/flake8/pylint
- **热重载**：`mykeys` 配置按 mtime 变更重载；`simphtml` 每次 web_scan 前重载
- **端口约定**：HeroUI 桥接 `:14169`、Vite 开发 `:5178`、调度器锁 `:45762`、桌面宠物 toast `:41983`

## 测试与 QA

### 框架
- **Python**：`unittest`（标准库）+ `pytest` 兼容。无 mock 框架 — fake 对象在测试文件内联定义。
- **HeroUI**：Node.js 内置测试运行器，通过 `tsx --test` 执行

### 测试结构
- **`tests/test_agent_loop_events.py`**（15 个测试）— 最全面：Agent 循环生命周期、工具结果契约、事件发射
- **`tests/test_agent_streaming.py`**（8 个测试）— 显示过滤器、协议标签移除
- **`tests/test_heroui_session_store.py`**（5 个测试）— SQLite 持久化往返
- **`tests/test_heroui_agent_state.py`**（7 个测试）— 状态捕获/恢复
- **`tests/test_long_run_context.py`**（8 个测试）— 轮次阈值、检查点、停顿警告
- **`tests/test_llmcore_fast_ask.py`**（1 个测试）— native Claude 的 fast_ask
- **`tests/test_goal_mode.py`**（1 个测试）— 目标模式轮次计数
- **`tests/test_simple_http_server.py`**（3 个测试）— HTTP 服务器 JSON 处理

### 运行测试
```bash
python -m pytest tests/                              # 全部 Python 测试
python -m pytest tests/test_agent_loop_events.py     # 单文件
cd frontends/heroui && pnpm test                     # HeroUI 前端测试
```

### 测试规范
- Fake/mock 对象在测试文件内联定义 — 无 mock 框架
- `tmp_path` pytest fixture 用于临时目录
- `importlib` 动态加载用于测试导入链复杂的模块
- 无 `conftest.py`、无 pytest 配置文件
- 测试关注行为（逻辑结果），而非默认值（当前状态）
