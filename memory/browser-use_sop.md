# Browser-Use 能力 SOP

本 SOP 说明 GA 新增的浏览器接管能力：`browser_state` + `browser_action`。

注意：这里的 "browser-use 能力" 指 GA 内置的高层浏览器操作层，不是外部 `browser-use` Python 项目运行时。底层仍走 TMWebDriver / `assets/tmwd_cdp_bridge` 接管用户真实 Chrome，因此继承用户登录态、Cookie、当前页面上下文。

## 核心定位

- `web_scan` / `web_execute_js`：低层网页观察与 JS/CDP 操作，适合调试、复杂页面、CDP、文件上传、iframe、截图等细节控制。
- `browser_state` / `browser_action`：高层浏览器操作工具，适合像用户一样点击、输入、选择、按键、等待元素或文本。
- 优先策略：普通网页交互先用 `browser_state` + `browser_action`；遇到 isTrusted、文件上传、跨域 iframe、复杂自定义组件、CDP 坐标点击时，再回到 `tmwebdriver_sop` 的 `web_execute_js` / CDP 桥方案。

## 两个工具的职责

### browser_state

用途：读取真实 Chrome 当前标签页的可交互元素，生成稳定的短期索引。

返回重点：
- `state_token`：本轮索引快照令牌，后续 indexed action 依赖它。
- `tab_id`：当前标签页 ID，用于防止跨 tab 误操作。
- `elements[]`：可交互元素列表，每个元素含 `index`、`tag`、`role`、`text`、`value`、`visible`、`disabled`、`bbox`、`selector_hint`。

适用时机：
- 要点击、输入、选择某个页面元素前。
- 页面 DOM 刚变化、SPA 路由变化、弹窗/下拉出现后。
- action 返回 `state_missing` / `stale_index` 且仍需 indexed 操作时。

不要把 `browser_state` 当成网页全文抽取工具。需要全文、复杂 DOM、隐藏内容、CDP 或直接 JS 时读 `tmwebdriver_sop`，用 `web_scan` / `web_execute_js`。

### browser_action

用途：对真实 Chrome 当前页面执行有限的高层动作。

支持动作：
| action | 是否通常需要 index | 用途 |
|---|---:|---|
| `click` | 是 | 点击 indexed 元素 |
| `input` | 是 | 向 input / textarea / contenteditable 输入文本 |
| `select` | 是 | 选择原生 `<select>` 的 option |
| `keys` | 否，特殊场景可带 | 发送 Enter / Escape / Tab / Control+A / Backspace |
| `wait_index` | 是 | 等待 indexed 元素可见，支持节点 detached 后基于 identity 的 selector fallback |
| `wait_text` | 否 | 等待页面出现指定文本 |
| `wait_selector` | 否 | 等待 CSS selector 出现 |

## 基本编排原则

### 1. indexed 操作前先 state

标准流程：
```json
{"tool": "browser_state", "args": {"max_elements": 120}}
```

然后选取目标 index：
```json
{"tool": "browser_action", "args": {"action": "click", "index": 12}}
```

`click` / `input` / `select` / `wait_index` 必须基于最近一次 `browser_state` 的 index。没有 state 或 tab 不一致时，工具会拒绝执行。

### 2. mutating action 成功后不要复用旧 index

以下动作成功后页面可能变化，GA 会主动清空缓存 state：
- `click`
- `input`
- `select`
- `keys`

因此，动作成功后如果还要对另一个 indexed 元素操作，必须重新调用 `browser_state`。

错误模式：
```json
{"action": "input", "index": 52, "text": "openai"}
{"action": "keys", "index": 52, "text": "Enter"}
```

正确模式：
```json
{"action": "input", "index": 52, "text": "openai"}
{"action": "keys", "text": "Enter"}
```

原因：`input` 后输入框仍通常是当前焦点元素，按 Enter 应直接发给 activeElement，不要再绑定旧 index。

### 3. input 后提交/搜索，优先 keys without index

搜索框、评论框、命令框等场景：
```json
{"action": "input", "index": 52, "text": "openai"}
{"action": "keys", "text": "Enter"}
{"action": "wait_text", "text": "openai", "timeout": 10}
```

不要在 input 后为了按 Enter 重新 `browser_state`。很多站点输入后会弹下拉、重排 DOM、隐藏原输入框，重扫反而容易丢目标。

如果 `keys(index=...)` 返回：
```json
{
  "status": "failed",
  "stage": "state_missing",
  "hint": "...without index...",
  "suggested_args": {"action": "keys", "text": "Enter"}
}
```
应直接按 `suggested_args` 重试。

### 4. 等待优先选 wait_text / wait_selector

页面提交、搜索、登录、跳转后，优先用：
```json
{"action": "wait_text", "text": "目标文本", "timeout": 10}
```
或：
```json
{"action": "wait_selector", "selector": ".result-item", "timeout": 10}
```

`wait_index` 只适合等待刚刚通过 `browser_state` 得到的那个 indexed 元素变可见。它不是通用搜索工具。

## 常见场景流程

### 搜索框：输入并回车

1. `browser_state`
2. 找到搜索输入框 index
3. `browser_action(input, index, text)`
4. `browser_action(keys, text="Enter")`，不要传 index
5. `wait_text` 或 `wait_selector` 等待结果

示例：
```json
{"action": "input", "index": 52, "text": "openai"}
{"action": "keys", "text": "Enter"}
{"action": "wait_text", "text": "openai", "timeout": 10}
```

### 点击按钮后等待页面变化

```json
{"action": "click", "index": 8}
{"action": "wait_text", "text": "提交成功", "timeout": 10}
```

如果下一步还要点新页面按钮：
```json
{"tool": "browser_state", "args": {"max_elements": 120}}
{"action": "click", "index": 3}
```

### 选择原生 select

```json
{"action": "select", "index": 21, "value": "US"}
```

如果是 Vue/AntD/MUI 自定义下拉，不要强行用 `select`。优先：
1. `browser_action(click)` 打开下拉。
2. `browser_state` 重新扫下拉选项。
3. `browser_action(click)` 点选项。
4. 若失败，读 `tmwebdriver_sop`，改用 vnode 或 CDP 坐标点击。

### 关闭弹窗或菜单

```json
{"action": "keys", "text": "Escape"}
```

`Escape` 通常不需要 index，直接发给当前页面/焦点。

### 表单清空并重新输入

对普通 input / textarea：
```json
{"action": "keys", "index": 12, "text": "Control+A"}
{"action": "keys", "index": 12, "text": "Backspace"}
{"action": "input", "index": 12, "text": "新内容"}
```

注意：`Control+A` / `Backspace` 只对 value-backed input / textarea 做确定性处理。contenteditable 的编辑按键会被拒绝，避免合成键盘事件假成功。contenteditable 要改内容时直接用 `input`。

### SPA 重渲染后等待旧元素回来

`wait_index` 支持节点 detached 后基于 `selector_hint` + tag/role/text 身份校验 fallback。

适合：
- 元素短暂重渲染。
- 同一个按钮/输入框被框架替换为新 DOM 节点。

不适合：
- 原 cached 节点仍 attached 但 hidden，这时不会 fallback 到其他相似元素。
- 页面上有多个同名同文本元素且语义无法区分，此时应重新 `browser_state`。

## 错误恢复策略

### state_missing

含义：indexed action 需要 state，但当前没有可用 state。

处理：
- 如果是 `keys` 且目的是 input 后回车/Tab/Escape：重试 `keys` 且不要传 index。
- 如果是 `click` / `input` / `select` / `wait_index`：先 `browser_state` 再重试。

### stale_index

含义：index 来源过期，或 tab 已切换。

处理：
1. 调用 `browser_state` 获取新 index。
2. 重新选择目标元素。
3. 再执行 action。

不要猜旧 index。

### visibility

含义：元素不可见、disabled、readonly，或当前状态不能操作。

处理：
- 先 `wait_text` / `wait_selector` / `browser_state(include_invisible=true)` 判断页面状态。
- 如果是 readonly/disabled，不要硬写；先找正确入口或解除页面状态。
- 如果是被弹层遮挡，先 Escape 或点关闭按钮。

### invalid_args

含义：动作和目标类型不匹配。

典型：
- `input` 用在 button/link 上。
- `select` 用在非 `<select>` 上。
- `keys` 使用了不支持的 key。

处理：重新 `browser_state` 选正确元素；复杂组件转 `tmwebdriver_sop`。

## 能力边界

本节按当前代码实现总结，不按理想能力描述。

### 当前实现事实

- `browser_state` 只索引有限交互元素：链接、按钮、`input`、`textarea`、`select`、常见 ARIA role、`onclick`、`tabindex`、`contenteditable=true`。
- `browser_state` 默认只返回可见元素；只有显式设置 `include_invisible=true` 才会包含不可见元素。
- 单次索引默认最多 120 个元素，代码允许的 `max_elements` 范围是 1-500。
- 元素快照只保留短文本和短 value，文本/value 最多约 240 字符；密码 value 会被 `[REDACTED]`。
- `selector_hint` 只是辅助提示，形式只有 `tag#id`、`tag[name="..."]` 或裸 `tag`，不是强定位保证。
- `browser_action` 只支持 7 个动作：`click`、`input`、`select`、`keys`、`wait_index`、`wait_text`、`wait_selector`。
- `click` / `input` / `select` / `wait_index` 必须依赖最近一次 `browser_state` 生成的 index 和 state token。
- `click` / `input` / `select` / `keys` 成功后会清空缓存 state，避免继续复用旧 index。
- 工具失败时会返回结构化结果：`status=failed`，并带 `stage`、`error`；部分场景会额外带 `hint` / `suggested_args`。

### 适合

- 对用户真实 Chrome 当前页面做普通交互：点击、输入、原生 select、按 Enter/Escape/Tab、等待文本或 selector。
- 已登录页面中的轻量操作，因为底层仍沿用 TMWebDriver / Chrome 扩展接管用户浏览器。
- 搜索框、评论框、普通表单等“输入后回车”的流程：`input(index)` 后直接 `keys(text="Enter")`，不要传 index。
- SPA 中短暂重渲染后的等待：`wait_index` 可在原节点 detached 后基于 selector hint + tag/role/text 做受限 fallback。
- 需要少写 JS、以高层动作完成的日常网页控制。

### 不适合

- 大规模内容抽取、正文抓取、结构化爬取；`browser_state` 不是网页全文提取工具。
- 文件上传、验证码截图、CDP 截图、网络抓包、Cookie/Tab/CDP 管理。
- 跨域 iframe、closed Shadow DOM、复杂 iframe 坐标合成。
- 需要 `isTrusted=true` 的敏感点击或浏览器级交互；当前 `click` 是 DOM `el.click()`。
- 复杂自定义组件内部状态操作，例如 AntD/MUI/Vue 自定义 Select；`select` 只支持原生 `<select>`。
- 对任意 CSS selector 直接 `click` / `input`；当前 selector 只用于 `wait_selector`，`wait_index` fallback 也只由工具内部受限使用。
- 多元素同名同文本且无法靠 tag/role/text 区分的页面，容易超出当前 identity check 能力。

### 关键限制

- `input` 只允许 `input` / `textarea` / `contenteditable`。对 button/link/普通 div 会返回 `invalid_args`。
- `select` 只允许原生 `<select>`，不支持自定义下拉。
- `keys` 只支持 `Enter`、`Escape`、`Tab`、`Control+A`、`Backspace`。
- `keys` 不传 index 时，会作用在 `document.activeElement || document.body`；这是 `input` 后提交搜索/表单的推荐路径。
- `Control+A` / `Backspace` 只对 value-backed `input` / `textarea` 做确定性处理；contenteditable 上会拒绝，避免合成键盘事件假成功。
- `wait_text` 只是判断 `document.body.innerText.includes(text)`，适合粗粒度等待，不适合精确语义判断。
- `wait_selector` 只是等待 `document.querySelector(selector)` 出现，不判断可见性和业务语义。
- `wait_index` 如果原 cached 节点仍 attached 但 hidden，不会 fallback 到其他元素；这能避免误匹配，但可能导致超时。
- `wait_index` detached fallback 当前只用 `querySelector` 找第一个匹配，再做 tag/role/text 校验；页面上多个候选时可能等不到正确那个。
- 后台标签页、页面节流、复杂加载状态仍受 Chrome 行为影响；必要时按 `tmwebdriver_sop` 用 CDP `Page.bringToFront`。

### 何时切回 tmwebdriver_sop

遇到以下情况，不要继续反复调用 `browser_action`：
- 同一目标连续失败两次。
- 需要 CDP、截图、文件上传、iframe、Shadow DOM、网络/Cookie/Tab 操作。
- 页面控件明显是复杂前端组件，普通 click/input/select 不能触发真实业务状态。
- 需要直接执行 JS、读取复杂 DOM、调用页面框架实例或 vnode。
- 需要绕过浏览器弹窗、自动下载限制、autofill 保护值等 Chrome 级问题。

这些场景继续读 `tmwebdriver_sop`，使用 `web_execute_js`、CDP 桥、vnode、DataTransfer、截图等低层方案。

## 和旧工具的配合

推荐决策：
1. 只是看页面摘要或 DOM 文本：`web_scan`。
2. 想执行普通用户动作：`browser_state` + `browser_action`。
3. 想导航：`web_execute_js` 执行 `location.href='...'`，或在已有页面中点链接。
4. 想执行复杂 JS / CDP / 上传 / 截图 / iframe：读 `tmwebdriver_sop`，用 `web_execute_js`。
5. 新能力失败两次以上，不要原地反复试：切换到 `tmwebdriver_sop` 的低层调试路径。

## 禁止/反模式

- 禁止在 mutating action 后继续复用旧 index。
- 禁止 input 后为了按 Enter 重新扫 state；优先 `keys` without index。
- 禁止把 `selector` 当成通用 click/input 定位方式；selector 仅用于 `wait_selector`，`wait_index` fallback 由工具内部控制。
- 禁止对非输入元素执行 `input` 后假设成功。
- 禁止忽略 `status=failed` 的 `stage`、`hint`、`suggested_args`。
- 禁止遇到复杂自定义组件时无脑重复 click；应读 `tmwebdriver_sop`。

## 最小心智模型

记住三句话：

1. 要操作页面元素，先 `browser_state`，再用 index。
2. 成功输入后要提交，直接 `keys Enter`，不要传 index。
3. 页面结构变了，旧 index 作废；要么按焦点继续，要么重新 `browser_state`。
