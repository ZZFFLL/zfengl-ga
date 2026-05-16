# GA Browser Action Layer Design

## 背景

GA 当前已经具备真实 Chrome 浏览器操作链路：`ga.py` 暴露 `web_scan` 和 `web_execute_js`，底层通过 `TMWebDriver.py` 与 `assets/tmwd_cdp_bridge` Chrome 扩展通信。这个链路的最大价值是直接操作用户已经打开的 Chrome，因此天然保留真实登录态、站点 Cookie、本机浏览器环境和用户当前页面。

`browser-use` 的直接接入路径主要依赖标准 CDP URL、托管 Chromium、Chrome profile 或 Cloud browser。普通用户正常打开 Chrome 时不会自动开启 remote debugging，因此 browser-use runtime 不能稳定、无感地接管用户已经打开的普通 Chrome。如果强行把 browser-use 作为主接管层，会破坏本次目标：用户只需要正常打开浏览器，GA 必须延续其真实登录态。

因此，本设计不把 browser-use runtime 作为默认后端，而是吸收 browser-use 的浏览器操作模型：`state -> indexed element -> action`。GA 新增一个 Browser Action Layer，把这套模型落到现有 `TMWebDriver + tmwd_cdp_bridge` 上。

## 目标

新增一组 browser-use 风格的浏览器操作能力，使 GA 能在用户真实 Chrome 中执行更稳定的 indexed actions，同时保留现有浏览器工具和登录态。

成功标准：

- 用户正常打开 Chrome，已安装并连接 `tmwd_cdp_bridge` 后，GA 可以基于当前页面生成可交互元素索引。
- GA 可以用元素索引执行常见动作：点击、输入、选择、按键、等待。
- 第一版不要求用户开启 Chrome remote debugging，不启动无登录态浏览器，不复制 profile。
- 现有 `web_scan` 和 `web_execute_js` 的行为保持不变。
- 新能力失败时返回结构化错误，不伪装成功，不悄悄 fallback 到隔离浏览器。

## 非目标

- 不替换 `web_scan`。
- 不替换 `web_execute_js`。
- 不默认启动 browser-use Chromium。
- 不默认调用 browser-use Cloud。
- 不把 browser-use Agent 嵌入 GA 形成 nested-agent 执行。
- 不在第一版模拟完整 CDP WebSocket 给 browser-use runtime 使用。
- 不修改 `E:\zfengl-ai-project\browser-use` 源码。

## 当前代码依据

GA 现有工具面：

- `assets/tools_schema.json` 只暴露 `web_scan` 和 `web_execute_js` 两个浏览器工具。
- `ga.py` 中 `web_scan` 调 `simphtml.get_html(...)` 获取简化 HTML 和 tab 列表。
- `ga.py` 中 `web_execute_js` 调 `simphtml.execute_js_rich(...)` 执行 JS 并监控页面变化。
- `TMWebDriver.execute_js(...)` 把 code 发送给浏览器会话，等待结果和新 tab 信息。

插件桥能力：

- `assets/tmwd_cdp_bridge/manifest.json` 已有 `debugger`、`scripting`、`tabs`、`cookies` 权限。
- `background.js` 已支持 `cmd: "cdp"`、`cmd: "batch"`、`cmd: "tabs"`。
- `background.js` 的 WebSocket 消息处理会把 JSON object code 直接路由到 `handleExtMessage(...)`。
- `handleCDP(...)` 和 `handleBatch(...)` 可调用 `chrome.debugger.sendCommand(...)`。
- 这意味着第一版无需新增扩展协议即可发起部分 CDP 命令，例如 `Input.dispatchMouseEvent`、`Page.captureScreenshot`、`DOM.setFileInputFiles`。

browser-use 能力参考：

- browser-use CLI 的 `state` 输出 indexed DOM representation。
- browser-use 的 click、hover、dblclick 等动作最终基于 CDP `Input.dispatchMouseEvent`。
- browser-use 的 upload 最终基于 CDP `DOM.setFileInputFiles`。
- browser-use 的直接真实 Chrome 接入依赖 `browser-use connect` 找到已有 remote debugging Chrome，普通 Chrome 默认不满足这个前提。

## 架构

新增 Browser Action Layer，位于 GA 工具层和现有浏览器桥之间。

```
LLM tool call
  -> ga.py tool handler
  -> browser_actions.py
  -> browser_indexer.py
  -> TMWebDriver.execute_js(...)
  -> tmwd_cdp_bridge WebSocket
  -> Chrome extension
  -> user Chrome tab
```

### 组件边界

`browser_indexer.py`

- 负责在当前 tab 生成可操作元素索引。
- 不执行动作。
- 输出结构化 `BrowserState`。
- 每次 state 调用都生成新的索引快照。

`browser_actions.py`

- 负责根据 index 执行动作。
- 持有最近一次 state 的 selector map 或 locator hint。
- 处理 index 过期、元素不可见、动作失败等错误。
- 只依赖 `TMWebDriver`，不直接依赖 GA handler。

`ga.py`

- 新增工具 handler。
- 不改变原有 `web_scan` / `web_execute_js`。
- 负责把工具参数转给 `browser_actions.py`，把结果格式化为 tool output。

`assets/tools_schema.json` 和 `assets/tools_schema_cn.json`

- 新增两个工具 schema：`browser_state` 和 `browser_action`。
- 不修改现有工具描述和参数。

## 工具契约

### `browser_state`

用途：获取当前 tab 的可操作元素索引。它面向动作，不面向全文阅读。

参数：

```json
{
  "switch_tab_id": "optional tab id",
  "include_invisible": false,
  "max_elements": 120
}
```

返回：

```json
{
  "status": "success",
  "backend": "tmwd_user_chrome",
  "tab_id": "123",
  "url": "https://example.com",
  "title": "Example",
  "viewport": {"width": 1280, "height": 720, "scroll_x": 0, "scroll_y": 240},
  "elements": [
    {
      "index": 1,
      "tag": "button",
      "role": "button",
      "text": "登录",
      "value": "",
      "visible": true,
      "disabled": false,
      "bbox": {"x": 1100, "y": 32, "width": 80, "height": 36},
      "selector_hint": "button.login"
    }
  ]
}
```

### `browser_action`

用途：基于 `browser_state` 的 index 执行动作。

参数：

```json
{
  "action": "click",
  "index": 1,
  "text": "optional text",
  "value": "optional value",
  "path": "optional file path",
  "timeout": 10,
  "switch_tab_id": "optional tab id"
}
```

第一版 action 白名单：

- `click`
- `input`
- `select`
- `keys`
- `wait_index`
- `wait_text`
- `wait_selector`

返回：

```json
{
  "status": "success",
  "action": "click",
  "index": 1,
  "tab_id": "123",
  "result": "clicked",
  "page_changed": true
}
```

失败返回：

```json
{
  "status": "failed",
  "action": "click",
  "index": 1,
  "stage": "locate",
  "error": "Element index 1 is stale. Run browser_state again."
}
```

## P0 实现范围

P0 只实现低侵入动作层。

`browser_state`：

- 扫描 `a[href]`、`button`、`input`、`textarea`、`select`、`[role=button]`、`[role=link]`、`[contenteditable=true]`、带 click handler 的明显交互元素。
- 过滤 `display:none`、`visibility:hidden`、`opacity:0`、尺寸为 0、超出 viewport 且不可滚动到的元素。
- 提取 text、aria-label、placeholder、title、value、disabled、bbox。
- 为每个元素生成 `index` 和稳定性有限的 locator hint。
- 返回 tab 信息和 viewport 信息。

`browser_action`：

- `click`：优先通过 locator 找元素，滚动到可见区域后点击。P0 可以优先 DOM click，必要时用 CDP mouse event。
- `input`：focus、清空、赋值，触发 `input` 和 `change` 事件。
- `select`：对原生 `select` 设置 value 或按可见文本匹配 option。
- `keys`：支持 `Enter`、`Escape`、`Tab`、`Control+A`、`Backspace`。
- `wait_index`：等待某 index 对应元素重新出现。
- `wait_text`：等待页面出现指定文本。
- `wait_selector`：等待 CSS selector 出现。

P0 不做：

- 文件上传。
- 截图。
- 跨 iframe 深度定位。
- Shadow DOM 完整遍历。
- browser-use runtime 对接。

## P1 实现范围

P1 在 P0 真实可用后推进。

- `screenshot`：通过 `cmd: cdp` 调 `Page.captureScreenshot`。
- `upload`：通过 DOM/CDP 定位 file input，调用 `DOM.setFileInputFiles`。
- `click` 默认升级为真实 CDP mouse event。
- `input` 默认升级为 CDP key event 或 browser-use 风格 typing。
- 支持 iframe 内元素索引和 frame id。
- 加入 state cache 失效策略：导航、reload、DOM 大变化、动作后自动失效。

## P2 实现范围

P2 只在 P1 证明价值后考虑。

- 可选接入 browser-use CDP backend。
- 若检测到标准 CDP URL 可用，可用 browser-use CLI/SDK 执行专业动作。
- 借鉴 browser-use DOM serializer 的可访问性树和 DOMSnapshot 思路。
- 支持复杂 dropdown、drag、hover、rightclick、dblclick。

## 数据流

### 获取 state

1. LLM 调 `browser_state`。
2. `ga.py` 确保 `TMWebDriver` 初始化并有活动浏览器 session。
3. `browser_indexer.py` 生成 JS indexer 脚本。
4. `TMWebDriver.execute_js(...)` 把脚本发到当前 tab。
5. 插件桥在真实 Chrome 页面执行脚本。
6. 返回 indexed elements。
7. Python 侧保存最近一次 state 快照，用于后续 action。

### 执行动作

1. LLM 调 `browser_action`，传 action 和 index。
2. Python 侧查最近一次 state 快照。
3. 若 index 不存在或快照过期，返回 stale 错误。
4. 根据 action 生成 JS 或 CDP batch。
5. 通过 `TMWebDriver.execute_js(...)` 发送。
6. 插件桥执行动作。
7. `simphtml.execute_js_rich(...)` 或新封装返回动作结果和页面变化。
8. 动作后标记 state cache 过期。

## 错误处理

错误阶段固定为：

- `browser_unavailable`：没有可用浏览器 session。
- `state_missing`：没有最近一次 state，要求先调用 `browser_state`。
- `stale_index`：index 不存在或页面已变化。
- `locate`：无法重新定位元素。
- `visibility`：元素不可见或被遮挡。
- `dom_event`：DOM action 失败。
- `cdp`：CDP command 失败。
- `timeout`：等待超时。
- `invalid_args`：参数不合法。

所有失败必须结构化返回，不能吞掉异常后返回 success。

## 安全与隐私

- 默认只操作用户当前真实 Chrome，不复制 profile，不上传 Cookie，不调用 Cloud browser。
- `browser_state` 不应返回 Cookie、localStorage、sessionStorage。
- `browser_action` 的 `input` 工具输出不回显敏感文本。对 password 类型输入框，返回 `"[REDACTED]"`。
- 文件上传必须要求明确本地文件路径，并校验文件存在、是文件、非空。
- 不对 `chrome://`、`edge://`、扩展页面、浏览器内部页面执行动作。

## 侵入性评估

P0 侵入性：低到中等。

原因：

- 新增工具，不改旧工具语义。
- 新增 Python 模块，不改 `TMWebDriver` 核心协议。
- 复用当前插件桥已有 WebSocket、JS 和 CDP 通道。
- 不要求 browser-use 直接接入普通 Chrome。

P1 侵入性：中等。

原因：

- 截图、上传、真实鼠标事件需要更多 CDP 命令。
- iframe 和 selector cache 会增加状态管理复杂度。
- 需要更完整的集成测试。

不建议的高侵入路线：

- 模拟完整 CDP WebSocket 给 browser-use runtime 使用。
- 强制托管用户 Chrome 启动。
- 替换 `web_scan` 或 `web_execute_js`。
- 将 browser-use Agent 作为 GA 默认浏览器执行器。

## 测试计划

### 单元测试

- indexer 过滤隐藏元素。
- indexer 保留 button、link、input、textarea、select、contenteditable。
- indexer 正确提取 text、aria-label、placeholder、value、bbox。
- action 参数校验：未知 action、缺 index、缺 text、缺 path。
- stale index 返回结构化错误。

### 后端契约测试

- `browser_state` 工具输出不进入最终回答正文的错误位置。
- `browser_action` 工具输出能被 WebUI/LibreChat 执行面板识别。
- 旧 `web_scan` 和 `web_execute_js` 的显示契约不变。

### 集成烟测

- 打开一个本地 HTML 测试页。
- 调 `browser_state` 获取输入框和按钮 index。
- 调 `browser_action input` 输入文本。
- 调 `browser_action click` 点击按钮。
- 再调 `browser_state` 验证页面状态变化。

真实 Chrome + 插件桥烟测可在 P0 完成后执行，避免设计阶段依赖外部浏览器状态。

## 验收标准

- 新增工具在 schema 中可见。
- 未连接浏览器时返回结构化错误。
- 已连接浏览器时能生成 indexed elements。
- 可在真实用户 Chrome 页面完成 `state -> input -> click -> state`。
- `web_scan` 和 `web_execute_js` 测试不回归。
- 不改 browser-use 仓库源码。

## 结论

本设计把 browser-use 的价值定位为操作模型参考，而不是默认运行时依赖。GA 的真实浏览器接管能力来自 `tmwd_cdp_bridge`，它已经具备对用户普通 Chrome 的无感连接和部分 CDP command 能力。第一版应在这个基础上补齐 indexed action layer，以最小侵入获得 browser-use 风格的浏览器操作体验。
