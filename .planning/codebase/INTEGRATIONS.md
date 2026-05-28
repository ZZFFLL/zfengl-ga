---
title: External Integrations
focus: tech
generated_at: 2026-05-28
last_mapped_commit: 0741fd20140a70bbe4317edcf72b228e4c279422
---

# External Integrations

## Integration Model

GenericAgent treats external services as optional runtime adapters. Core LLM connectivity is configured through `mykey.py` or `mykey.json` and consumed by `llmcore.py`. Frontends and bots read credentials from the same configuration layer through `llmcore.mykeys` or their own workspace config resolver.

Do not commit secrets. `.gitignore` excludes `mykey.py`, `.env`, `auth.json`, `temp/`, and most runtime memory files.

## LLM Providers and APIs

**Core LLM protocol implementation:** `llmcore.py`
- `NativeClaudeSession` sends Anthropic Messages-compatible requests to `apibase` + `/v1/messages` or equivalent paths, with native `tools` conversion from OpenAI-style function schema to Claude `input_schema`.
- `NativeOAISession` sends OpenAI-compatible requests through `_openai_stream`, supporting `chat_completions` and `responses` API modes.
- `ClaudeSession` and `LLMSession` provide older text-tool-protocol Claude/OpenAI-compatible sessions.
- `MixinSession` provides multi-session failover by referencing named sessions from configuration.
- `NativeToolClient` wraps native Claude/OAI sessions; `ToolClient` wraps text-protocol sessions.

**Supported config selectors:** `agentmain.py`, `llmcore.py`, `mykey_template_en.py`
- Variable names containing `native` + `claude` resolve to `NativeClaudeSession`.
- Variable names containing `native` + `oai` resolve to `NativeOAISession`.
- Variable names containing `mixin` create failover sessions.
- Other names containing `claude` or `oai` use deprecated text-protocol classes.

**Provider catalog evidence:** `assets/configure_mykey.py`
- Direct/compatible providers include Anthropic Claude, OpenAI, DeepSeek, Kimi/Moonshot, Qwen/DashScope, Zhipu/GLM, MiniMax, Stepfun, Baidu Qianfan, Volcengine Ark/Doubao, Xiaomi MiMo, Tencent TokenHub.
- Relay providers include CC Switch relay, OpenRouter, CRS, and GMI Serving.
- Provider definitions include default `apibase`, `model`, API protocol type, and public console/key acquisition hints; actual credentials come from local config only.

**HTTP behavior:** `llmcore.py`
- Uses `requests.post(..., stream=sess.stream, timeout=(connect_timeout, read_timeout), proxies=sess.proxies, verify=sess.verify)`.
- Retryable HTTP statuses include `408`, `409`, `425`, `429`, `500`, `502`, `503`, `504`, Cloudflare `520`-`529`, with exponential delay and `retry-after` support.
- OpenAI-compatible mode sends Bearer auth and targets `/v1/chat/completions` or `/v1/responses` through `auto_make_url`.
- Claude native mode sends either `x-api-key` for `sk-ant-` keys or `Authorization: Bearer` for relay-style tokens.
- Anthropic/Claude beta headers are assembled in `NativeClaudeSession`, including context and thinking-related beta flags.

**Vision/image probing:** `probe_image_support.py`, `memory/vision_api.template.py`
- `probe_image_support.py` loads a selected config from `mykey.py`, calls a text-only request, then sends a 1x1 PNG through OpenAI-compatible `chat/completions` or `responses` API.
- `memory/vision_api.template.py` supports Claude, OpenAI-compatible, and ModelScope vision calls, with ModelScope default endpoint `https://api-inference.modelscope.cn` and model `Qwen/Qwen3-VL-235B-A22B-Instruct`.

## Secrets, Auth, and Configuration

**Primary secret/config files:**
- `mykey.py` — local Python config module; ignored by `.gitignore`.
- `mykey.json` — JSON fallback loaded by `llmcore.py` if `mykey.py` cannot be imported.
- `mykey_template.py` and `mykey_template_en.py` — templates with placeholder values and comments.
- `ga_config/mykey.py` and `ga_config/mykey.json` — workspace config locations used by `frontends/fsapp.py`.

**Config loading:**
- `llmcore.py` reloads `mykey.py` via `importlib.reload` and falls back to `mykey.json` beside the project root.
- `frontends/fsapp.py` resolves config in this order: `ga_config/mykey.json`, `ga_config/mykey.py`, workspace `mykey.json`, workspace `mykey.py`, project `mykey.json`, project `mykey.py`.
- `assets/configure_mykey.py` generates local config and masks input while typing.

**Common secret/config keys:**
- LLM: `apikey`, `apibase`, `model`, `proxy`, `api_mode`, `reasoning_effort`, `thinking_type`, `max_retries`, `read_timeout` inside provider config dictionaries.
- Global proxy: `proxy` in `mykey_template_en.py` and provider configs; Discord also reads `proxy` for `discord.Client` in `frontends/dcapp.py`.
- Telegram: `tg_bot_token`, `tg_allowed_users` in `frontends/tgapp.py`.
- QQ: `qq_app_id`, `qq_app_secret`, `qq_allowed_users` in `frontends/qqapp.py`.
- Feishu: `fs_app_id`, `fs_app_secret`, `fs_allowed_users` in `frontends/fsapp.py` and `docs/SETUP_FEISHU.md`.
- WeCom: `wecom_bot_id`, `wecom_secret`, `wecom_allowed_users` in `frontends/wecomapp.py`.
- DingTalk: `dingtalk_client_id`, `dingtalk_client_secret`, `dingtalk_allowed_users` in `frontends/dingtalkapp.py`.
- Discord: `discord_bot_token`, `discord_allowed_users` in `frontends/dcapp.py`.
- Langfuse: `langfuse_config` in `plugins/langfuse_tracing.py`.

**Local key storage helper:** `memory/keychain.py`
- Stores secrets at `Path.home() / "ga_keychain.enc"`.
- Uses a username-derived XOR mask, not OS-native secure storage; treat it as lightweight obfuscation rather than strong cryptographic protection.
- `SecretStr.__repr__` masks values and exposes `.use()` for raw access.

## Browser, Web, and CDP Integrations

**TMWebDriver local bridge:** `TMWebDriver.py`
- Default host/port: `127.0.0.1:18765` for WebSocket and `127.0.0.1:18766` for HTTP/remote link.
- Uses `simple_websocket_server.WebSocketServer` for browser sessions and `bottle` plus `wsgiref.simple_server` for HTTP routes.
- HTTP endpoints include `/api/longpoll`, `/api/result`, and `/link`.
- Supports WebSocket, extension WebSocket, and HTTP long-poll sessions.
- `execute_js` sends JavaScript to the selected browser tab and waits for result/ack with timeout handling.

**Chrome extension/CDP bridge:** `assets/tmwd_cdp_bridge/background.js`, `assets/tmwd_cdp_bridge/content.js`
- Extension WebSocket target is `ws://127.0.0.1:18765`.
- Uses Chrome extension APIs: `chrome.debugger`, `chrome.cookies`, `chrome.tabs`, `chrome.management`, `chrome.contentSettings`, `chrome.declarativeNetRequest`, and `chrome.alarms`.
- Removes CSP response headers through `declarativeNetRequest` to permit page script execution.
- Supports commands for cookies, CDP, batch CDP, tab listing/creation/switching, extension management, and content settings.
- Content script injects a visible `ljq_driver` connection badge and forwards DOM-carried requests to the extension runtime.

**Agent web tools:** `ga.py`, `simphtml.py`
- `ga.py` lazily initializes `TMWebDriver` in `first_init_driver()` for `web_scan` and browser execution flows.
- `simphtml.py` uses BeautifulSoup and injected JavaScript to reduce a page DOM into a token-efficient representation.

## Frontends, Bots, and Platform Adapters

**CLI and desktop launchers:**
- `agentmain.py` is the core interactive CLI/REPL entrypoint.
- `ga_cli/cli.py` exposes `ga` commands for CLI, GUI, TUI, launch, hub, configure, status, and update.
- `launch.pyw` starts Streamlit, optional bot processes, optional scheduler, and wraps the UI with PyWebView.
- `hub.pyw` is a Tkinter service launcher that discovers frontend and reflect services.

**Streamlit/PyWebView:** `frontends/stapp.py`, `launch.pyw`
- `frontends/stapp.py` uses Streamlit for the Cowork UI and runs a background `GeneraticAgent` thread.
- `launch.pyw` runs `streamlit run frontends/stapp.py` on a free port in `18501`-`18599`, then opens a PyWebView window.
- `launch.pyw` can spawn Telegram, QQ, Feishu, WeChat, WeCom, DingTalk, and scheduler subprocesses based on flags.

**HeroUI bridge and React UI:** `frontends/heroui/bridge.py`, `frontends/heroui/src/api.ts`, `frontends/heroui/vite.config.ts`
- Python bridge uses `aiohttp.web` and defaults to `http://127.0.0.1:14169` and `ws://127.0.0.1:14169/ws`.
- Vite dev server defaults to `http://127.0.0.1:5178` and proxies bridge routes to `GA_HEROUI_API_TARGET`.
- HTTP endpoints include `/status`, `/config`, `/model-profiles`, `/model-profile`, `/sessions`, `/session/new`, `/session/{sid}`, `/session/{sid}/prompt`, `/session/{sid}/messages`, `/session/{sid}/events`, `/session/{sid}/cancel`, `/sops`, `/sops/{sop_id}`, `/path/open`.
- Frontend subscribes to turn events with `EventSource` and falls back to polling `/session/{sid}/messages` in `frontends/heroui/src/api.ts`.
- WebSocket `/ws` is events/notifications only; command/data flows stay on HTTP/SSE.

**Desktop web2 bridge:** `frontends/desktop_bridge.py`, `frontends/desktop/static/ga-web.js`
- Python bridge uses `aiohttp.web` and defaults to `BRIDGE_HOST=127.0.0.1`, `BRIDGE_PORT=14168`.
- Static desktop adapter hardcodes HTTP bridge `:14168` and WebSocket `:14168/ws` in `frontends/desktop/static/ga-web.js`.
- HTTP endpoints overlap with HeroUI but serve static frontend files from `frontends/desktop/static/`.

**Tauri desktop shell:** `frontends/desktop/src-tauri/`
- Tauri v2 shell loads static assets from `frontends/desktop/static/`.
- Bundle targets include NSIS and DMG in `frontends/desktop/src-tauri/tauri.conf.json`.

**Terminal UIs:**
- `frontends/tuiapp_v2.py` uses Textual/Rich and auto-installs missing `rich`/`textual` on first run.
- `frontends/tui_v3.py` is a single-file Rich-based TUI with persisted settings under `temp/tui_v3_settings.json`.

**Qt UI:** `frontends/qtapp.py`
- Requires `PySide6` and optionally `markdown`.

**Telegram:** `frontends/tgapp.py`
- Uses `python-telegram-bot` imports (`ApplicationBuilder`, handlers, filters, `HTTPXRequest`, `RetryAfter`).
- Reads `tg_allowed_users` from `mykey` and uses commands such as `/help`, `/stop`, `/continue`, `/btw`, `/review`, `/llm`.
- Single-instance lock uses local port `19527` or nearby behavior where configured in the module; runtime process logs redirect to `temp/tgapp.log` through `frontends/chatapp_common.py`.

**QQ:** `frontends/qqapp.py`
- Uses `qq-botpy` (`botpy.Client`, C2C/group messages).
- Reads `qq_app_id`, `qq_app_secret`, `qq_allowed_users`.
- Single-instance lock port is `19528`.

**Feishu/Lark:** `frontends/fsapp.py`, `docs/SETUP_FEISHU.md`
- Uses `lark_oapi` and `lark.ws.Client` long-connection mode.
- Configures app credentials `fs_app_id` and `fs_app_secret`; optional allowed users are Open IDs.
- Sends messages/cards and handles files/media under `temp/feishu_media`.
- Docs require Feishu bot permissions such as `im:message`, `im:message:send_as_bot`, and `contact:user.id:readonly` in `docs/SETUP_FEISHU.md`.

**WeCom/Enterprise WeChat:** `frontends/wecomapp.py`
- Uses `wecom_aibot_sdk.WSClient` and `generate_req_id`.
- Reads `wecom_bot_id`, `wecom_secret`, `wecom_allowed_users`.
- Handles text/image/file events, encrypted media downloads, media uploads, and stream replies.
- Single-instance lock port is `19531`; media files go under `temp/media`.

**DingTalk:** `frontends/dingtalkapp.py`
- Uses `dingtalk_stream` (`DingTalkStreamClient`, `Credential`, `CallbackHandler`, `ChatbotMessage`).
- Reads `dingtalk_client_id`, `dingtalk_client_secret`, `dingtalk_allowed_users`.
- Fetches OAuth access token from `https://api.dingtalk.com/v1.0/oauth2/accessToken`.
- Sends group/user robot messages through `https://api.dingtalk.com/v1.0/robot/groupMessages/send` and `https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend`.
- Single-instance lock port is `19530`.

**Discord:** `frontends/dcapp.py`
- Uses `discord.py` and requires Message Content Intent according to module comments.
- Reads `discord_bot_token`, `discord_allowed_users`, and optional `proxy`.
- Stores active channel metadata in `temp/discord_active_channels.json` and media in `temp/discord_media`.

**WeChat/iLink:** `frontends/wechatapp.py`
- Uses `requests`, `qrcode`, and `Crypto.Cipher.AES` from PyCryptodome.
- Base API is `https://ilinkai.weixin.qq.com`; CDN upload base is `https://novac2c.cdn.weixin.qq.com/c2c`.
- Token state is stored under `Path.home() / ".wxbot" / "token.json"`.
- QR login calls `/ilink/bot/get_bot_qrcode` and `/ilink/bot/get_qrcode_status`; message polling/sending uses `/ilink/bot/getupdates` and `/ilink/bot/sendmessage`.
- Uploads encrypt file bytes with AES-ECB before posting to CDN upload URLs.

**ACP/JSON-RPC bridge:** `frontends/genericagent_acp_bridge.py`
- Implements line-delimited JSON-RPC over stdio for an Agent Client Protocol-style integration.
- Redirects normal stdout to stderr so the JSON-RPC channel remains clean.
- Exposes initialize/session creation/prompt handling and returns `agentCapabilities` with MCP-related capabilities disabled.

## Databases, Storage, and Persistence

**HeroUI SQLite session store:** `frontends/heroui/session_store.py`
- Default path is `frontends/heroui/.data/sessions.sqlite3` from `frontends/heroui/bridge_core/session.py`.
- Tables: `sessions`, `messages`, `events`, `agent_state`.
- Uses SQLite foreign keys and stores payload/state JSON in text columns.
- Tests in `tests/test_heroui_session_store.py` verify schema creation, round-trips, deletes, and corrupt state handling.

**Runtime logs and model responses:**
- `llmcore.py` writes prompts/responses to `temp/model_responses/model_responses_<pid or id>.txt` via `_write_llm_log`.
- `agentmain.py` sets `self.log_path` under `temp/model_responses/`.
- `frontends/chatapp_common.py` redirects bot logs to `temp/*.log` files.

**Frontend/media storage:**
- Feishu media: `temp/feishu_media` in `frontends/fsapp.py`.
- Discord media and active-channel state: `temp/discord_media`, `temp/discord_active_channels.json` in `frontends/dcapp.py`.
- WeCom media: `temp/media` in `frontends/wecomapp.py`.
- WeChat token state: `~/.wxbot/token.json` in `frontends/wechatapp.py`.

**Memory/SOP storage:**
- SOPs and memory files live under `memory/`.
- `agentmain.py` creates `memory/global_mem.txt` and `memory/global_mem_insight.txt` when missing.
- HeroUI bridge exposes SOP listing/detail/save for existing Markdown files under `memory/` in `frontends/heroui/bridge_core/routes.py`.
- `.gitignore` ignores most `memory/*` but whitelists selected SOPs and helper modules.

**Browser bridge generated config:**
- `agentmain.py` initializes `assets/tmwd_cdp_bridge/config.js` with a random `TID` if absent.
- `.gitignore` excludes `assets/tmwd_cdp_bridge/config.js`.

## Observability and Tracing

**Default logs:**
- Console logging is pervasive across `agentmain.py`, `agent_loop.py`, `llmcore.py`, frontends, and bot adapters.
- Bot frontends use `frontends/chatapp_common.py::redirect_log` to append logs in `temp/`.
- LLM prompt/response logging is done by `llmcore.py::_write_llm_log` unless replaced by tracing hooks.

**Langfuse optional tracing:** `plugins/langfuse_tracing.py`
- Self-activates only when `langfuse_config` exists in local config and the `langfuse` package imports successfully.
- Registers hooks for `agent_before`, `agent_after`, `llm_before`, `llm_after`, `tool_before`, and `tool_after`.
- Wraps Claude/OpenAI SSE parsers in `llmcore.py` to extract usage and model details for tracing.

**Plugin hook system:** `plugins/hooks.py`
- Provides `register`, `trigger`, `unregister`, `clear`, `has`, and `discover_and_load`.
- `agentmain.py` calls `discover_and_load()` on startup, so `plugins/*.py` modules can register hooks without editing core code.

## Network Ports and Protocols

| Integration | Default endpoint / port | Protocol | Files |
|---|---:|---|---|
| HeroUI bridge | `127.0.0.1:14169` | HTTP, WebSocket, SSE | `frontends/heroui/bridge.py`, `frontends/heroui/bridge_core/routes.py` |
| HeroUI Vite dev server | `127.0.0.1:5178` | HTTP dev server + proxy | `frontends/heroui/vite.config.ts`, `frontends/heroui/start.cmd` |
| Desktop web2 bridge | `127.0.0.1:14168` | HTTP, WebSocket | `frontends/desktop_bridge.py`, `frontends/desktop/static/ga-web.js` |
| TMWebDriver WebSocket | `127.0.0.1:18765` | WebSocket | `TMWebDriver.py`, `assets/tmwd_cdp_bridge/background.js` |
| TMWebDriver HTTP/remote link | `127.0.0.1:18766` | HTTP / long-poll | `TMWebDriver.py` |
| Streamlit via PyWebView | random `18501`-`18599` | HTTP local Streamlit | `launch.pyw` |
| Tkinter hub singleton | `127.0.0.1:19735` bind lock | TCP bind lock | `hub.pyw` |
| QQ singleton | `127.0.0.1:19528` bind lock | TCP bind lock | `frontends/qqapp.py` |
| DingTalk singleton | `127.0.0.1:19530` bind lock | TCP bind lock | `frontends/dingtalkapp.py` |
| WeCom singleton | `127.0.0.1:19531` bind lock | TCP bind lock | `frontends/wecomapp.py` |
| Desktop pet hook | `127.0.0.1:41983` | HTTP query updates | `frontends/stapp.py` |
| Anthropic/Claude APIs | provider `apibase` | HTTPS + SSE/JSON | `llmcore.py`, `mykey_template_en.py` |
| OpenAI-compatible APIs | provider `apibase` | HTTPS + SSE/JSON | `llmcore.py`, `probe_image_support.py` |
| DingTalk REST | `https://api.dingtalk.com` | HTTPS JSON | `frontends/dingtalkapp.py` |
| Feishu/Lark | Feishu cloud via SDK | WebSocket long connection + HTTPS | `frontends/fsapp.py`, `docs/SETUP_FEISHU.md` |
| WeChat/iLink | `https://ilinkai.weixin.qq.com` | HTTPS JSON polling | `frontends/wechatapp.py` |
| WeChat CDN | `https://novac2c.cdn.weixin.qq.com/c2c` | HTTPS binary upload | `frontends/wechatapp.py` |

## Security Considerations from Integration Surface

- `mykey.py` and `.env` are gitignored in `.gitignore`; keep all real credentials there or in local workspace config.
- `assets/tmwd_cdp_bridge/background.js` removes CSP headers and uses `chrome.debugger`; install/use the extension only in trusted browser profiles.
- `frontends/desktop/src-tauri/tauri.conf.json` sets `"csp": null`; the desktop shell relies on local assets and bridge locality rather than CSP enforcement.
- `memory/keychain.py` masks secret display but stores data with a reversible XOR transform; use only for local convenience.
- Bot adapters enforce optional allowlists such as `tg_allowed_users`, `fs_allowed_users`, `wecom_allowed_users`, `dingtalk_allowed_users`, `discord_allowed_users`, and `qq_allowed_users`. Empty allowlists often mean public access per `frontends/chatapp_common.py::public_access`.
- HeroUI SOP editing in `frontends/heroui/bridge_core/routes.py` restricts writes to existing Markdown files under `memory/` and validates paths with `resolve().relative_to(...)`.

## Evidence and Examples Inspected

- `llmcore.py`
- `agentmain.py`
- `agent_loop.py`
- `ga.py`
- `mykey_template_en.py`
- `assets/configure_mykey.py`
- `probe_image_support.py`
- `memory/vision_api.template.py`
- `memory/keychain.py`
- `TMWebDriver.py`
- `assets/tmwd_cdp_bridge/background.js`
- `assets/tmwd_cdp_bridge/content.js`
- `simphtml.py`
- `frontends/chatapp_common.py`
- `frontends/tgapp.py`
- `frontends/qqapp.py`
- `frontends/fsapp.py`
- `frontends/wecomapp.py`
- `frontends/dingtalkapp.py`
- `frontends/dcapp.py`
- `frontends/wechatapp.py`
- `frontends/stapp.py`
- `launch.pyw`
- `hub.pyw`
- `frontends/heroui/bridge.py`
- `frontends/heroui/bridge_core/routes.py`
- `frontends/heroui/bridge_core/session.py`
- `frontends/heroui/session_store.py`
- `frontends/heroui/src/api.ts`
- `frontends/heroui/vite.config.ts`
- `frontends/heroui/start.cmd`
- `frontends/desktop_bridge.py`
- `frontends/desktop/static/ga-web.js`
- `frontends/desktop/src-tauri/tauri.conf.json`
- `plugins/hooks.py`
- `plugins/langfuse_tracing.py`
- `docs/SETUP_FEISHU.md`
- `.gitignore`

## Gaps and Unknowns

- Real `mykey.py`, `mykey.json`, `.env`, credential, and token file contents were not read and must remain local-only.
- Actual deployed LLM providers cannot be determined without reading local secrets; only supported provider/config shapes are evidenced.
- Feishu, DingTalk, WeCom, QQ, Telegram, Discord, and WeChat live connectivity was not exercised; evidence is from source code and docs only.
- External service permission configuration is documented most completely for Feishu in `docs/SETUP_FEISHU.md`; other bot platform permission scopes are mostly embedded in code comments or SDK usage.
- No CI/CD or hosted production deployment configuration was detected in inspected manifests.
- No centralized metrics/log aggregation is present unless optional Langfuse tracing is configured with `langfuse_config`.
- `frontends/dcapp.py` requires `discord.py`, but this dependency is absent from `pyproject.toml` optional dependency groups.
- `assets/configure_mykey.py` lists WeCom dependency as `wecombot`, while live code imports `wecom_aibot_sdk` and `pyproject.toml` declares `wecom-aibot-sdk>=1.0`.
