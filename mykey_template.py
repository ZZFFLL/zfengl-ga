# ══════════════════════════════════════════════════════════════════════════════
#  GenericAgent — mykey.py 配置模板（复制为 mykey.py 后填入真实凭证）
# ══════════════════════════════════════════════════════════════════════════════
#  文件中的每个"变量"即一条 session 配置。agentmain.py 只扫描变量名同时包含
#  'api' / 'config' / 'cookie' 的条目，根据变量名里的关键字决定实例化哪个
#  Session 类型：
#
#      关键字组合                      → Session 类
#      ────────────────────────────────────────────────────────────
#      含 'native' 且 'claude'         → NativeClaudeSession  (Claude 原生协议 + 原生工具)
#      含 'native' 且 'oai'            → NativeOAISession     (OpenAI 协议 + 原生工具)
#      含 'claude'（不含 native）      → ClaudeSession        (Claude 原生协议 + 文本协议工具)
#      含 'oai'（不含 native）         → LLMSession           (OpenAI 协议 + 文本协议工具)
#      含 'sider'                       → SiderLLMSession
#      含 'mixin'                       → MixinSession         (多 session 故障转移)
#
#  优先级自上而下：native_claude_xxx 会走 NativeClaudeSession；如果变量名只写
#  oai_claude_xxx 则依然会被 'claude' 抢先匹配，去走 ClaudeSession，所以命名要
#  注意含义。
#
# ══════════════════════════════════════════════════════════════════════════════
#  apibase 自动拼接规则：
#      'http://host:2001'                      → 补 /v1/chat/completions
#      'http://host:2001/v1'                   → 补 /chat/completions
#      'http://host:2001/v1/chat/completions'  → 原样使用
#  NativeClaudeSession 会额外附加 ?beta=true，用于触发 Anthropic beta 协议。
#
# ══════════════════════════════════════════════════════════════════════════════
#  运行时参数调整：在 GA REPL 里输入
#      /session.reasoning_effort=high
#      /session.thinking_type=adaptive
#      /session.thinking_budget_tokens=32768
#      /session.temperature=0.3
#      /session.max_tokens=16384
#  会在当前 session 的 backend 上做 setattr，当场生效，直到换模型或重启。
#  reasoning_effort 合法值: none / minimal / low / medium / high / xhigh
#  thinking_type 合法值:     adaptive / enabled / disabled
#
# ══════════════════════════════════════════════════════════════════════════════
#  所有字段速查（按 BaseSession.__init__ 顺序）
# ─── 鉴权 / 路由 ─────────────────────────────────────────────────────────────
#   apikey          必填。sk-ant-* 用 x-api-key 头；其它（sk-*, cr_*, amp_*…）
#                   一律用 Authorization: Bearer，由 NativeClaudeSession 自动判断。
#   apibase         必填。参见上方 apibase 自动拼接规则。
#   model           必填。后缀 '[1m]' 触发 context-1m-2025-08-07 beta（发出前会
#                   自动去掉 [1m]）。
#   name            可选。展示名；也是 mixin_config['llm_nos'] 引用的凭据。不填
#                   默认取 model。
#   proxy           可选。单 session 代理，'http://127.0.0.1:2082' 这种。不填则
#                   即使全局设置了 proxy 也不走。
# ─── 容量 / 超时 ─────────────────────────────────────────────────────────────
#   context_win     默认 24000（NativeClaudeSession 默认 28000）。仅作为历史裁
#                   剪阈值，不是硬上下文限制。
#   max_retries     默认 1。_openai_stream 遇到 429/408/5xx 的自动重试次数。
#   timeout         连接超时秒数，默认 5。
#   read_timeout    流式读取超时秒数，默认 30。
# ─── 推理 / 思考 ─────────────────────────────────────────────────────────────
#   reasoning_effort  OpenAI o 系列或 Responses API 的思考预算等级。Claude 侧
#                     会映射到 output_config.effort（xhigh → max）。
#   thinking_type     Claude 原生 thinking 块。
#                     'adaptive'  (CC 默认)   → 让模型自己决定预算
#                     'enabled'                → 必须配合 thinking_budget_tokens
#                     'disabled'               → 不发送 thinking 字段
#   thinking_budget_tokens  仅当 thinking_type='enabled' 时生效。参考:
#                     low≈4096, medium≈10240, high≈32768
# ─── 采样 ──────────────────────────────────────────────────────────────────
#   temperature     默认 1.0。Kimi/Moonshot 会被强制改成 1.0；MiniMax 会被夹到
#                   (0, 1]。
#   max_tokens      默认 8192。
# ─── 传输 ──────────────────────────────────────────────────────────────────
#   stream          默认 True。NativeClaudeSession 会根据此值决定走 SSE 流式
#                   还是一次性 JSON。流式更及时；某些被 CDN 截断 SSE 的渠道可
#                   以改成 False 先保命。
#   api_mode        'chat_completions'（默认）或 'responses'。仅对 LLMSession /
#                   NativeOAISession 生效。
# ─── 缓存 ──────────────────────────────────────────────────────────────────
#   prompt_cache    默认 True。NativeClaudeSession 恒开启双滚动 cache_control；
#                   LLMSession/NativeOAISession 走 OAI 中继时，若 model 名含
#                   'claude' 或 'anthropic' 会自动在最后两条 user 打
#                   cache_control: ephemeral。设 False 只有在上游 relay 不认
#                   cache_control 字段会直接报错时才用。
# ─── NativeClaudeSession 专属 ───────────────────────────────────────────────
#   fake_cc_system_prompt
#                   默认 False。关键字段：**所有反代/镜像 Claude Code 协议的渠道
#                   都必须置 True**（anyrouter、claude-relay-service 等）。
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
#  示例 1 — OpenRouter (OAI 协议 → Claude / GPT / Gemini 等，含缓存优化)
# ──────────────────────────────────────────────────────────────────────────────
#  OpenRouter 是最通用的多模型 OAI 中继，https://openrouter.ai/api/v1。
#  model 名用 provider/model 格式（如 anthropic/claude-opus-4-6）。

oai_config_openrouter = {
    'name': 'openrouter-claude',                     # /llms 显示名 & mixin 引用名；省略则取 model
    'apikey': 'sk-or-<your-openrouter-key>',         # OpenRouter key 形如 sk-or-xxx；Bearer 鉴权
    'apibase': 'https://openrouter.ai/api/v1',       # 补齐到 /v1/chat/completions
    'model': 'anthropic/claude-opus-4-6',            # provider/model 格式；名含 'claude' 会自动打 ephemeral
    'api_mode': 'chat_completions',                  # 'chat_completions'（默认）|'responses'
    'prompt_cache': True,                            # bool 默认 True；关掉会禁用 cache_control 标记
    'temperature': 1,                                # float 默认 1.0；非负
    'max_tokens': 16384,                             # int 默认 8192；回复最大 token 数
    'max_retries': 3,                                # int 默认 1；429/408/5xx 自动重试次数
    'connect_timeout': 10,                           # int 秒 默认 5（最小 1）；TCP 连接超时
    'read_timeout': 120,                             # int 秒 默认 30（最小 5）；流式读取单次超时
    # 'context_win': 60000,                          # int 默认 24000；历史裁剪 token 阈值，非硬上下文
    # 'proxy': 'http://127.0.0.1:2082',              # 可选单 session 代理；不填则不走代理
}

# ══════════════════════════════════════════════════════════════════════════════
#  示例 2 — 通用 OAI 兼容代理 (chat/completions 模式)
# ──────────────────────────────────────────────────────────────────────────────
#  任何支持 /v1/chat/completions 的中转站（ohmyapi、one-api、newapi 等）都用
#  这种方式。变量名含 'oai' 即可。支持 GPT / Claude / Gemini / Grok 等。
oai_config = {
    'name': 'my-oai-proxy',                          # /llms 显示名 & mixin 引用名
    'apikey': 'sk-<your-proxy-key>',                 # Bearer 鉴权
    'apibase': 'http://<your-proxy-host>:2001',      # 自动补 /v1/chat/completions
    'model': 'gpt-5.4',                              # 或 claude-opus-4-6、gemini-3-flash 等
    'api_mode': 'chat_completions',                  # 'chat_completions'（默认）|'responses'
    # 'reasoning_effort': 'high',                    # none|minimal|low|medium|high|xhigh
                                                     # chat_completions → payload.reasoning_effort
                                                     # responses        → payload.reasoning.effort
    'max_retries': 3,                                # int 默认 1
    'connect_timeout': 10,                           # int 秒 默认 5（最小 1）
    'read_timeout': 120,                             # int 秒 默认 30（最小 5）
    # 'temperature': 1.0,                            # float 默认 1.0
    # 'max_tokens': 8192,                            # int 默认 8192
    # 'prompt_cache': True,                          # bool 默认 True；仅 model 名含 claude/anthropic 时生效
    # 'proxy': 'http://127.0.0.1:2082',              # 可选单 session HTTP 代理
    # 'context_win': 16000,                          # int 默认 24000；历史裁剪阈值
}

# 多配几个也行，变量名含 'oai' 即可
# oai_config2 = {
#     'apikey': 'sk-...',
#     'apibase': 'http://your-proxy:2001',
#     'model': 'claude-opus-4-6',
# }


# ══════════════════════════════════════════════════════════════════════════════
#  示例 3 — OpenAI Responses API (gpt/o 系列，reasoning_effort 支持)
# ──────────────────────────────────────────────────────────────────────────────
#  对接 OpenAI /v1/responses 端点。reasoning_effort 会以 reasoning.effort
#  字段写进 payload；运行时也可用 /session.reasoning_effort=high 现场调。
# oai_config_responses = {
#     'name': 'gpt-responses',                       # /llms 显示名
#     'apikey': 'sk-<your-openai-key>',              # Bearer 鉴权
#     'apibase': 'https://api.openai.com/v1',        # 补齐到 /v1/responses（因为 api_mode=responses）
#     'model': 'gpt-5.4',                            # gpt-5/o 系列
#     'api_mode': 'responses',                       # 改走 /v1/responses 端点
#     'reasoning_effort': 'high',                    # none|minimal|low|medium|high|xhigh
#                                                    # responses 模式下写进 payload.reasoning.effort
#     'max_retries': 2,                              # int 默认 1
#     'read_timeout': 120,                           # int 秒 默认 30
# }


# ══════════════════════════════════════════════════════════════════════════════
#  示例 4 — Anthropic 原生 (api.anthropic.com)
# ──────────────────────────────────────────────────────────────────────────────
#  官方端点，apikey 以 sk-ant- 开头 → 自动切到 x-api-key 鉴权。

native_claude_config_anthropic = {
    'name': 'anthropic-direct',              # /llms 显示名 & mixin 引用名
    'apikey': 'sk-ant-<your-anthropic-key>', # sk-ant- 前缀 → 自动走 x-api-key 头
    'apibase': 'https://api.anthropic.com',  # Messages 端点；NativeClaudeSession 自动附加 ?beta=true
    'model': 'claude-opus-4-6[1m]',          # [1m] 触发 context-1m-2025-08-07 beta；上游前自动剥掉
    # ── 思考控制（thinking_type 与 reasoning_effort 独立，可同时写）──
    'thinking_type': 'adaptive',             # 合法值: 'adaptive' / 'enabled' / 'disabled'
                                             #   adaptive = Claude Code 默认，模型自决预算
                                             #   enabled  = 必须配 thinking_budget_tokens
                                             #   disabled = 发送 {"type":"disabled"}
    # 'thinking_type': 'enabled',
    # 'thinking_budget_tokens': 32768,       # int，仅 thinking_type='enabled' 生效
                                             #   参考: low≈4096 / medium≈10240 / high≈32768
    # ── 推理等级（Claude 侧写进 payload.output_config.effort）──
    #   合法值: 'none' / 'minimal' / 'low' / 'medium' / 'high' / 'xhigh'
    #   映射:  low/medium/high 原值传递；xhigh → 'max'；
    #          none/minimal 被 llmcore 打 WARN 丢弃（Claude 不支持这两档）
    #   运行时可覆盖: REPL 输入 /session.reasoning_effort=high 当场生效
    # 'reasoning_effort': 'high',
    'temperature': 1,                        # float 默认 1.0
    'max_tokens': 32768,                     # int 默认 8192；Claude 回复最大 token 数
    # 'context_win': 800000,                 # int 默认 28000（NativeClaudeSession）；历史裁剪阈值
    # 'prompt_cache': True,                  # bool 默认 True；NativeClaudeSession 恒开双滚动 cache_control
    # 'stream': True,                        # bool 默认 True；False → 一次性 JSON（CDN 截断 SSE 时用）
    # 'max_retries': 3,                      # int 默认 1
    # 'connect_timeout': 10,                 # int 秒 默认 5（最小 1）
    # 'read_timeout': 180,                   # int 秒 默认 30（最小 5）
    # 'fake_cc_system_prompt': False,        # bool 默认 False；真 Anthropic 端点不需开
}


# ══════════════════════════════════════════════════════════════════════════════
#  示例 5 — anyrouter (Claude Code 社区中继；含镜像站)
# ──────────────────────────────────────────────────────────────────────────────

native_claude_config_anyrouter = {
    'name': 'anyrouter',                     # /llms 显示名 & mixin 引用名
    'apikey': 'sk-<your-anyrouter-key>',     # 非 sk-ant- 前缀 → Bearer 鉴权
    'apibase': 'https://<your-anyrouter-mirror-host>',  # 镜像站根域名
    'model': 'claude-opus-4-6[1m]',          # 必须带 [1m]，网关强制 1m-beta
    'fake_cc_system_prompt': True,           # bool 必填 True；网关会校验 CC 固定系统串
    'thinking_type': 'adaptive',             # 'adaptive'/'enabled'/'disabled'；必填，不发 thinking 会被拒
    # 'reasoning_effort': 'high',            # 可选；写进 Claude output_config.effort
    'max_retries': 5,                        # int；镜像偶发 503，多重试几次
    'read_timeout': 300,                     # int 秒；1m 上下文响应可能很慢
    # 'max_tokens': 32768,                   # int 默认 8192
    # 'prompt_cache': True,                  # bool 默认 True
    # 'stream': True,                        # bool 默认 True
}


# ══════════════════════════════════════════════════════════════════════════════
#  示例 6 — claude-relay-service (CRS) 反代 Claude Max
# ──────────────────────────────────────────────────────────────────────────────
#  CRS 需要 fake_cc_system_prompt=True

native_claude_config_crs_claude = {
    'name': 'crs-claude-max',                # /llms 显示名
    'apikey': 'cr_<your-crs-claude-key>',    # cr_ 开头 → Bearer 鉴权（64 位 hex）
    'apibase': 'https://<your-crs-host>/api',# CRS 的 Anthropic 兼容路径
    'model': 'claude-opus-4-6[1m]',          # [1m] 触发 1m beta
    'fake_cc_system_prompt': True,           # bool 必填 True；CRS 也校验 CC 系统串
    'thinking_type': 'adaptive',             # 'adaptive'/'enabled'/'disabled'
    # 'reasoning_effort': 'high',            # 可选；写进 output_config.effort
    'max_tokens': 32768,                     # int；CRS 允许大 max_tokens
    'max_retries': 3,                        # int
    'read_timeout': 180,                     # int 秒
}


# ══════════════════════════════════════════════════════════════════════════════
#  示例 7 — CRS 反代 Gemini Ultra (Antigravity 通道)
# ──────────────────────────────────────────────────────────────────────────────
#  CRS 把 Google Antigravity (Gemini Ultra) 包装成 Anthropic 风格接口。
#  URL 路径带 /antigravity/api：
#    - 'claude-opus-4-6-thinking'  (CRS 原始名)
#    - 'claude-opus-4-6[1m]'       (触发 1m beta，CRS 会忽略多余的 beta)
#    - 'claude-opus-4-6'           (最简)

native_claude_config_crs_gemini = {
    'name': 'crs-gemini-ultra',              # /llms 显示名
    'apikey': 'cr_<your-crs-gemini-key>',    # cr_ 前缀 → Bearer
    'apibase': 'https://<your-crs-gemini-host>/antigravity/api',  # 特殊的 antigravity 路径
    'model': 'claude-opus-4-6-thinking',     # 或 'claude-opus-4-6[1m]' 或 'claude-opus-4-6'，实测三种等价
    'fake_cc_system_prompt': True,           # bool 必填 True
    # 'thinking_type': 'adaptive',           # CRS Gemini 不强制 thinking，可留空
    'max_tokens': 32768,                     # int
    'max_retries': 3,                        # int
    'read_timeout': 180,                     # int 秒；SSE 偶尔被上游截断
}


# ══════════════════════════════════════════════════════════════════════════════
#  示例 8 — 智谱 GLM-5.1 (Anthropic 兼容协议)
# ──────────────────────────────────────────────────────────────────────────────
#  智谱提供了 Anthropic 兼容接口 /api/anthropic，走 NativeClaudeSession。
#  变量名含 'native' + 'claude' 即可。apikey 是智谱格式 (xxx.yyy)。

native_claude_glm_config = {
    'name': 'glm-5.1',                               # /llms 显示名
    'apikey': '<your-zhipu-apikey>',                 # 形如 f0f1b798xxxx.F8SSbzxxxx；非 sk-ant- → Bearer
    'apibase': 'https://open.bigmodel.cn/api/anthropic',  # 智谱 Anthropic 兼容端点
    'model': 'glm-5.1',                              # 智谱 model id，无 [1m] 支持
    'max_retries': 3,                                # int
    'connect_timeout': 10,                           # int 秒
    'read_timeout': 180,                             # int 秒
    # 'fake_cc_system_prompt': False,                # 智谱不做 CC 指纹校验，保持默认 False
}


# ══════════════════════════════════════════════════════════════════════════════
#  示例 9 — MiniMax (双端点：OAI chat/completions + Anthropic Messages)
# ──────────────────────────────────────────────────────────────────────────────
#  MiniMax 同时提供 OAI 和 Anthropic 兼容接口，同一个 key 两个端点都能用：
#    - /v1             → chat/completions (LLMSession)
#    - /anthropic      → Anthropic Messages (NativeClaudeSession)
#  OAI 路径会返回 <think> 标签（M2.7 自带思考）；Anthropic 路径更简洁。
#  温度自动修正为 (0, 1]，支持 M2.7 / M2.5 全系列，204K 上下文。

# MiniMax OAI 路径
oai_config_minimax = {
    'name': 'minimax-oai',                           # /llms 显示名
    'apikey': 'sk-<your-minimax-key>',               # 形如 sk-cp-xxxxxxxxx；Bearer 鉴权
    'apibase': 'https://api.minimaxi.com/v1',        # OAI 兼容端点
    'model': 'MiniMax-M2.7',                         # 模型 id；名含 'minimax' 会被 llmcore 把 temp 夹到 (0.01,1.0]
    # 'model': 'MiniMax-M2.7-highspeed',             # 高速档
    'context_win': 50000,                            # int；MiniMax 204K 上下文，此处是裁剪阈值
    # 'temperature': 0.7,                            # 会被自动 clamp 到 (0.01, 1.0]
    # 'max_tokens': 8192,                            # int 默认 8192
    # 'max_retries': 3,                              # int
}

# MiniMax Anthropic 路径（推荐——响应更简洁，无额外 <think> 标签）
# native_claude_config_minimax = {
#     'name': 'minimax-anthropic',                   # /llms 显示名
#     'apikey': 'sk-<your-minimax-key>',             # 与 OAI 路径同一个 key
#     'apibase': 'https://api.minimaxi.com/anthropic',  # Anthropic Messages 兼容端点
#     'model': 'MiniMax-M2.7',
#     'max_retries': 3,                              # int
#     # 'fake_cc_system_prompt': False,              # MiniMax 不做 CC 指纹校验
# }


# ══════════════════════════════════════════════════════════════════════════════
#  示例 10 — Kimi / Moonshot (OAI 兼容)
# ──────────────────────────────────────────────────────────────────────────────
#  注意：Kimi/Moonshot 温度会被 llmcore.py 强制改为 1.0，写什么都会被覆盖。
# oai_config_kimi = {
#     'name': 'kimi-k2',                             # /llms 显示名
#     'apikey': 'sk-<your-moonshot-key>',            # Bearer 鉴权
#     'apibase': 'https://api.moonshot.cn/v1',       # Moonshot OAI 端点
#     'model': 'kimi-k2-turbo-preview',              # 名含 'kimi' 或 'moonshot' → temperature 被强制 1.0
#     # 'temperature': 0.3,                          # ← 无效，会被 llmcore 覆盖为 1.0
#     # 'max_tokens': 8192,                          # int 默认 8192
# }


# ══════════════════════════════════════════════════════════════════════════════
#  示例 11 — Mixin 故障转移 (多 session 自动回退)
# ──────────────────────────────────────────────────────────────────────────────
#  llm_nos 里的字符串必须和被引用 session 的 'name' 字段匹配（也可以写整数索
#  引）。约束：引用的 session 必须都是 Native 或者都不是 Native，不能混。
# mixin_config_claude_fallback = {
#     'llm_nos': ['anyrouter', 'crs-claude-max', 'anthropic-direct'],
#                                  # list；元素为其他 session 的 name（str）或整数索引
#                                  # 约束：引用的 session 必须全是 Native 或全不是，不能混
#     'max_retries': 8,            # int；整个 rotation 的总重试次数上限
#     'base_delay': 1.5,           # float 秒；指数退避起始延迟（retry n 时延迟≈base_delay * 2^n）
#     'spring_back': 300,          # int 秒；切到备用节点后多久再尝试回到第一个节点
# }


# ══════════════════════════════════════════════════════════════════════════════
#  示例 12 — Sider (需要额外 pip 包 sider_ai_api)
# ══════════════════════════════════════════════════════════════════════════════
# sider_cookie = 'token=Bearer%20eyJhbGciOiJIUz...'


# ══════════════════════════════════════════════════════════════════════════════
#  全局 HTTP 代理（所有没有单独指定 proxy 的 session 共用）
# ══════════════════════════════════════════════════════════════════════════════
# proxy = 'http://127.0.0.1:2082'


# ══════════════════════════════════════════════════════════════════════════════
#  聊天平台集成（可选；未填写的平台不会启动对应 adapter）
# ══════════════════════════════════════════════════════════════════════════════
# tg_bot_token = '84102K2gYZ...'
# tg_allowed_users = [6806...]
# qq_app_id = '123456789'
# qq_app_secret = 'xxxxxxxxxxxxxxxx'
# qq_allowed_users = ['your_user_openid']           # 留空或 ['*'] 表示允许所有 QQ 用户
# fs_app_id = 'cli_xxxxxxxxxxxxxxxx'
# fs_app_secret = 'xxxxxxxxxxxxxxxx'
# fs_allowed_users = ['ou_xxxxxxxxxxxxxxxx']        # 留空或 ['*'] 表示允许所有飞书用户
# wecom_bot_id = 'your_bot_id'
# wecom_secret = 'your_bot_secret'
# wecom_allowed_users = ['your_user_id']            # 留空或 ['*'] 表示允许所有企业微信用户
# wecom_welcome_message = '你好，我在线上。'
# dingtalk_client_id = 'your_app_key'
# dingtalk_client_secret = 'your_app_secret'
# dingtalk_allowed_users = ['your_staff_id']        # 留空或 ['*'] 表示允许所有钉钉用户
