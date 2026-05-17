# Browser-Use 能力 SOP

本 SOP 说明 GA 新增的浏览器接管能力：`browser_state` + `browser_find` + `browser_action` + `browser_recipe`。

注意：这里的 "browser-use 能力" 指 GA 内置的高层浏览器操作层，不是外部 `browser-use` Python 项目运行时。底层仍走 TMWebDriver / `assets/tmwd_cdp_bridge` 接管用户真实 Chrome，因此继承用户登录态、Cookie、当前页面上下文。

## 核心定位

- `web_scan` / `web_execute_js`：低层网页观察与 JS/CDP 操作，适合调试、复杂页面、框架状态探测、CDP、文件上传、跨域 iframe、截图等细节控制。
- `browser_state` / `browser_find` / `browser_action` / `browser_recipe`：结构化、可验证、可恢复的高层浏览器操作工具，适合像用户一样定位、点击、输入、原生选择、按键、等待元素或文本，并能处理同源 iframe 中被索引的元素。
- 平级策略：`web_execute_js` 不是 browser_* 的上级或下级，browser_* 也不是万能浏览器代理。先判断任务形态和组件类型，再选择低层 JS/CDP 轨道或结构化 indexed-action 轨道；不要为了完成目标把任一工具强行扩成通用自动化层。两条轨道互补，不按固定优先级排序。
- 记忆短句：web_execute_js 不是 browser_* 的上级或下级。

## 结构化 browser_* 工具编排建议

- `browser_state` 用于刷新索引和读取字段上下文；看到 `recipe_hint` 时，只表示该控件适合某个固定 recipe，不表示工具会自动执行 recipe。
- `browser_find` 用于只读定位。优先提供真实语义条件，例如字段名、表格行列、字段 id/name；`role`、`control_kind`、`layer`、`frame_path` 只是过滤条件，不能单独作为定位。
- `browser_action` 用于有界索引动作。失败时必须读取 `recovery`，不要对同一 index 反复执行同一动作。
- `browser_recipe` 只用于固定场景：`custom_select`、`layer_select`、`table_locate`、`component_wait`。它不是通用表单规划器，遇到歧义会返回候选并停止。
- 如果 `browser_find(refresh=true)` 后仍然 `target_not_found` 且 `recovery.stop_retry=true`，不要继续重复同一查询；改用更窄的字段/层级约束，或切换到平级的 `web_execute_js` 做低层探测。

## 四个工具的职责

### browser_state

用途：读取真实 Chrome 当前标签页的可交互元素，生成稳定的短期索引；同源 iframe / frame 会递归索引，跨域 iframe 不会被高层工具穿透。

返回重点：
- `state_token`：本轮索引快照令牌，后续 indexed action 依赖它。
- `tab_id`：当前标签页 ID，用于防止跨 tab 误操作。
- `elements[]`：可交互元素列表，每个元素含 `index`、`tag`、`role`、`text`、`value`、`visible`、`disabled`、`bbox`、`selector_hint`、`frame_path`、`frame_depth`、`frame_url`、`frame_title`，以及 field/control/layer/table 等只读上下文。

适用时机：
- 要点击、输入、选择某个页面元素前。
- 页面 DOM 刚变化、SPA 路由变化、弹窗/下拉出现后。
- action 返回 `state_missing` / `stale_index` 且仍需 indexed 操作时。

不要把 `browser_state` 当成网页全文抽取工具。需要全文、复杂 DOM、隐藏内容、CDP 或直接 JS 时读 `tmwebdriver_sop`，用 `web_scan` / `web_execute_js`。

### browser_find

用途：只读定位真实 Chrome 当前页面中的 indexed 元素。它不会点击、输入、选择或按键，只返回候选 index、评分、原因和是否歧义。

优先使用场景：
- `browser_state` 输出太长，或失败 recovery 已明确给出可执行的 `browser_find` 参数。
- `browser_state` 输出太长，需要按 label、field、table、layer、frame 缩小目标。
- 旧 index 失效后，需要刷新并重新定位目标。
- 表格、弹层、AntD 选项存在多个相似文本，需要先判断候选。

关键参数：
- `query`：目标标签、文本或值。
- `role` / `control_kind` / `layer` / `frame_path`：硬过滤条件。
- `table`：表格定位条件，常用 `row_text` + `column_text`。
- `refresh=true`：先刷新 `browser_state` 再定位。

规则：
- `ambiguous=true` 时不要直接选第一个，先用更具体的 `query`、`table`、`layer` 或 `frame_path` 缩小范围。
- `status=failed` 且 `stage=target_not_found` 时，按 `recovery` 决定是否 refresh 或转低层工具。
- `browser_find` 返回的是候选 index，不代表已经操作成功；真正点击/输入仍需 `browser_action` 或 `browser_recipe`。

### browser_action

用途：对真实 Chrome 当前页面执行有限的高层动作。

支持动作：
| action | 是否通常需要 index | 用途 |
|---|---:|---|
| `click` | 是 | 点击 indexed 元素 |
| `input` | 是 | 向 input / textarea / contenteditable / 同源 designMode editor body 输入文本 |
| `select` | 是 | 选择原生 `<select>` 的 option |
| `keys` | 否，特殊场景可带 | 发送 Enter / Escape / Tab / Control+A / Backspace |
| `wait_index` | 是 | 等待 indexed 元素可见，支持节点 detached 后基于 identity 的 selector fallback |
| `wait_text` | 否 | 等待页面出现指定文本 |
| `wait_selector` | 否 | 等待 CSS selector 出现 |
| `wait_dom_stable` | 否 | 等待 DOM 在有界时间内稳定 |
| `wait_not_busy` | 否 | 等待页面或自定义 busy selector 不再忙 |
| `wait_enabled` | 是 | 等待 indexed 元素变为可用 |
| `wait_route` | 否 | 等待当前路由/URL 包含目标文本或 value |

可选验证：`verify` 支持 `field_value`、`text`、`selector`、`element_text`，但只用于 `click` / `input` / `select` / `keys`。所有等待动作都会拒绝 `verify`；`field_value` 必须有非空期望值。验证失败会返回 `status=failed` 且 `stage=verify_failed`。

### browser_recipe

用途：运行有边界的常见组件操作编排。它不是自动浏览器代理，只支持固定 recipe。

支持 recipe：
- `custom_select`：AntD/React 自定义下拉，走 trigger -> state -> option -> click。
- `layer_select`：弹窗、抽屉、popover 中选择人员/项目/文档等通用选择流程。
- `table_locate`：按 `row_text` + `column_text` 定位表格中的 indexed 目标。
- `component_wait`：在 timeout 内按 state/find 做有界轮询，等待 layer/options/field/enabled/not_busy 等组件条件。

规则：
- recipe 返回 `ambiguous_target` 时不要强行点击，必须补充更具体条件。
- recipe 返回的 `steps` 是诊断依据，失败后先读最后一个失败 step。
- `table_locate` 只定位，不做通用表格编辑。
- `component_wait` 是有界组件条件等待：每轮刷新 state 后 find，直到条件满足或 timeout；它不等于业务成功保证。
- `custom_select` / `layer_select` 必须提供 `target.query` 或 `target.index`，不能让 recipe 无目标 broad-find 后点击任意元素。
- `component_wait` 不接受 `target.index`；已有 index 且只是等可见/启用时用 `browser_action(wait_index|wait_enabled)`，`field_value`、`layer_closed`、`not_busy` 等条件必须改用 query 目标。
- recipe 的 `timeout` 会被工具限制在 0-60 秒范围内，不能作为长期监控或无限等待使用。
- 跨域 iframe、文件上传、截图、CDP 坐标、私有组件 API 仍走 `tmwebdriver_sop`。

## 基本编排原则

### 0. failure recovery 优先于猜测

失败结果里如果有 `recovery`，优先按它执行，不要自己猜下一步。

- `recovery.next_tool` 指定下一步工具。
- `recovery.next_args` 给出下一步参数骨架。
- `recovery.stop_retry=true` 时停止重复同一个动作。
- `stage=repeat_blocked` 表示工具已阻止重复撞墙，必须换定位、recipe 或低层路径。
- 老字段 `hint` / `suggested_args` 仍可参考，但优先读 `recovery`。

### 1. indexed 操作前先 state

标准流程：
```json
{"tool": "browser_state", "args": {"max_elements": 120}}
```

然后选取目标 index：
```json
{"tool": "browser_action", "args": {"action": "click", "index": 12}}
```

`click` / `input` / `select` / `wait_index` / `wait_enabled` 必须基于最近一次 `browser_state` 的 index。没有 state 或 tab 不一致时，工具会拒绝执行。

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

### 4. 等待优先选 wait_text / wait_selector / SPA waits / component_wait

页面提交、搜索、登录、跳转后，优先用：
```json
{"action": "wait_text", "text": "目标文本", "timeout": 10}
```
或：
```json
{"action": "wait_selector", "selector": ".result-item", "timeout": 10}
```

SPA 页面没有稳定文本或 selector 时，再按页面形态选有界等待：
```json
{"action": "wait_route", "value": "/results", "timeout": 10}
{"action": "wait_dom_stable", "timeout": 10}
{"action": "wait_not_busy", "selector": ".ant-spin-spinning", "timeout": 10}
{"tool": "browser_recipe", "args": {"recipe": "component_wait", "condition": "options_visible", "target": {"query": "研发部"}, "timeout": 10}}
```

等待动作只表示“等条件出现/消失”，不做结果验证；不要给 `wait_*` 传 `verify`。

`component_wait` 会在 timeout 内刷新 state 并重复 find，适合等待组件条件短时间变化；它只接受 query 类目标。已有 index 且只是等可见/启用时用 `browser_action(wait_index|wait_enabled)`；关闭、字段值、not_busy 这类条件不能用 `wait_index` 代替。

`wait_index` 只适合等待刚刚通过 `browser_state` 得到的那个 indexed 元素变可见。它不是通用搜索工具。

### 5. state 输出太长时先 browser_find

不要人工在很长的 `browser_state.elements` 中反复猜 index。优先：
```json
{"tool": "browser_find", "args": {"query": "审批意见", "control_kind": "contenteditable", "max_results": 5}}
```

表格目标：
```json
{"tool": "browser_find", "args": {"table": {"row_text": "张三", "column_text": "审批意见"}, "max_results": 5}}
```

命中后再执行：
```json
{"tool": "browser_action", "args": {"action": "input", "index": 38, "text": "同意", "verify": "field_value", "verify_value": "同意"}}
```

如果 `browser_find` 返回 `ambiguous=true`，先补充约束，不要直接用第一个候选。

### 6. 标准输入/提交/等待/重扫顺序

推荐顺序：
1. `browser_state`
2. `browser_action(input, index, text, verify="field_value", verify_value=text)`
3. 提交/搜索时执行 `browser_action(keys, text="Enter")`，不要传 index
4. 按页面变化选择 `wait_text` / `wait_selector` / `wait_route` / `wait_dom_stable` / `wait_not_busy`
5. 下一次 indexed action 前重新 `browser_state`

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

如果是 React/Vue/AntD/MUI 自定义下拉，不要强行用 `select`。优先：
```json
{"tool": "browser_recipe", "args": {"recipe": "custom_select", "target": {"query": "所属部门"}, "option_text": "研发部", "max_results": 5}}
```

如果 recipe 返回歧义，再手动拆解：
1. `browser_action(click)` 打开下拉。
2. `browser_state` 或 `browser_find` 重新扫下拉选项。
3. `browser_action(click)` 点选项。
4. 如果菜单项仍无法索引或点击，读 `tmwebdriver_sop`，改用 vnode 或 CDP 坐标点击。

原生 `<select>` 中如果目标 `<option>` 自身 disabled，或位于 disabled `<optgroup>` 下，`select` 会拒绝执行。

### 弹层/抽屉/Popover 选择

优先用：
```json
{"tool": "browser_recipe", "args": {"recipe": "layer_select", "target": {"query": "选择人员"}, "option_text": "张三", "max_results": 5}}
```

如果需要点击确认按钮，必须显式给 `confirm_text`：
```json
{"tool": "browser_recipe", "args": {"recipe": "layer_select", "target": {"query": "选择人员"}, "option_text": "张三", "confirm_text": "确定"}}
```

不要让 recipe 在没有 `confirm_text` 的情况下猜测确认按钮。

### 表格行列定位

只定位：
```json
{"tool": "browser_recipe", "args": {"recipe": "table_locate", "table": {"row_text": "张三", "column_text": "审批意见"}}}
```

返回目标 index 后，再根据目标类型决定 `browser_action(input|click)`。`table_locate` 不负责分页、虚拟滚动、键盘导航或通用单元格编辑。

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
- 优先读 `recovery.next_tool` / `recovery.next_args`。
- 如果是 `keys` 且目的是 input 后回车/Tab/Escape：重试 `keys` 且不要传 index。
- 如果是 `click` / `input` / `select` / `wait_index`：先按 recovery 默认调用 `browser_state`；只有已有 query/table 语义定位时，才用 `browser_find(refresh=true)` 缩小候选。

### stale_index

含义：index 来源过期，或 tab 已切换。

处理：
1. 优先按 recovery 调用 `browser_state` 获取新 index；如果已经有 query/table 语义定位，再调用 `browser_find(refresh=true)` 重新缩小候选。
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

处理：重新 `browser_find` / `browser_state` 选正确元素；复杂组件先看是否适合 `browser_recipe`，不适合再转 `tmwebdriver_sop`。

### ambiguous_target

含义：`browser_find` 或 `browser_recipe` 找到多个相近候选，工具拒绝猜测。

处理：
- 增加 `query` 细节。
- 增加 `table.row_text` / `table.column_text`。
- 增加 `role` / `control_kind` / `layer` / `frame_path`。
- 不要直接选第一个候选执行点击。

### repeat_blocked

含义：同一 tab、URL、动作、目标、失败阶段重复失败，工具已熔断，避免继续撞墙。

处理：
- 停止重复同一个 `browser_action`；`repeat_blocked` 的 `recovery` 通常只有 `stop_retry=true`，不会替你指定下一步工具。
- 换策略：刷新后用更强约束 `browser_find` 重新定位，或改用适配场景的 `browser_recipe`。
- 如果仍失败，转 `tmwebdriver_sop` 做低层诊断。

## 能力边界

本节按当前代码实现总结，不按理想能力描述。

### 当前实现事实

- `browser_state` 只索引有限交互元素：链接、按钮、`input`、`textarea`、`select`、常见 ARIA role、`onclick`、`tabindex`、`contenteditable=true`、`.ant-select-selector`、`.ant-picker`、`.ui-browser-item`、`.ui-browser` 下的 tree/menu item，以及保留下来的可操作 icon button/link。
- `browser_state` 会递归索引同源 iframe / frame，并在元素快照中记录 `frame_path`、`frame_depth`、`frame_url`、`frame_title`。隐藏或零尺寸的父 iframe 会让子元素不可见；跨域 iframe 不会被高层工具穿透。
- `browser_state` 默认只返回可见元素；显式设置 `include_invisible=true` 只会包含可见 frame 链内的不可见元素，隐藏父/祖先 iframe 子树不会暴露。
- 单次索引默认最多 120 个元素，代码允许的 `max_elements` 范围是 1-500。
- 元素快照只保留短文本和短 value，文本/value 最多约 240 字符；密码 value 会被 `[REDACTED]`。
- 元素快照包含 labels、attributes、validation、stable_key、field_context、table_context、layer、control_kind、action_hints 等只读上下文；表格上下文用于判断行/列/表头/单元格位置，不提供单元格编辑封装。
- `browser_state` 对 AntD / `ui-browser` 只做有限增强：会额外索引常见自定义下拉触发器、日期控件、tree/menu item 和可操作的 icon button/link，并通过 `control_kind` / `action_hints` 提示后续流程；这不是通用组件库适配层。
- `selector_hint` 只是辅助提示，形式只有 `tag#id`、`tag[name="..."]` 或裸 `tag`，不是强定位保证。
- `browser_action` 支持 11 个动作：`click`、`input`、`select`、`keys`、`wait_index`、`wait_text`、`wait_selector`、`wait_dom_stable`、`wait_not_busy`、`wait_enabled`、`wait_route`。
- `click` / `input` / `select` / `wait_index` / `wait_enabled` 必须依赖最近一次 `browser_state` 生成的 index 和 state token；同源 iframe 内元素通过 `frame_path` 关联到对应 frame。
- `click` / `input` / `select` / `keys` 成功后会清空缓存 state，避免继续复用旧 index。
- `input` 支持直接写入 contenteditable，也支持同源 iframe contenteditable / designMode editor body；建议用 `verify="field_value"` + 非空 `verify_value` 确认实际值。它不保证调用编辑器私有 API，也不保证跨域 iframe。
- `select` 只支持原生 `<select>`，并会拒绝 disabled option / disabled optgroup。React/AntD/MUI/Vue 自定义下拉优先用 `browser_recipe(custom_select)`；recipe 歧义或失败后再拆成 click -> state/find -> click。
- SPA waits 都是有界等待：`wait_dom_stable`、`wait_not_busy`、`wait_enabled`、`wait_route` 不应被当成无限等待或业务成功保证。
- `browser_find` 是只读定位层：复用或刷新当前 state，必须提供真实语义定位 `query` 或 `table`，再用 `role`、`control_kind`、`layer`、`frame_path` 做可选过滤和评分，`max_results` 被限制在 1-20；只给 role/layer/control_kind/frame_path 会被拒绝，避免返回任意可见元素；它只返回候选 index，不执行动作。
- `browser_find` 会返回 disabled 候选，方便判断控件存在或后续等待启用；真正的 disabled/read-only 拒绝仍由 `browser_action` 执行层负责。
- `browser_find` 的 `ambiguous=true` 是硬信号：候选分数接近，必须增加约束，不允许直接拿第一个候选操作。
- `browser_find` 的可重试 recovery 会保留 `switch_tab_id` 和 `include_invisible`，避免重试时跑到错误标签页或可见性模式；如果 `refresh=true` 后仍找不到目标，会返回 `stop_retry=true`，需要补充更强约束或换策略。
- `browser_recipe` 只支持 `custom_select`、`layer_select`、`table_locate`、`component_wait` 四类有界 recipe；不接受自由文本流程，也不会变成自动浏览器代理。
- `custom_select` / `layer_select` 必须提供明确 target；内部按 `browser_find` -> `click` -> `browser_state` -> `browser_find` -> `click` 编排；`layer_select` 只有传入 `confirm_text` 才会点击确认按钮。
- `table_locate` 只调用 `browser_find` 定位候选，要求至少提供 `row_text`、`column_text` 或 `header_text` 之一；它不负责分页、虚拟滚动、单元格写入或提交。
- `component_wait` 当前是有界组件条件等待型 recipe：在 timeout 内按 `browser_state` -> `browser_find` 轮询 query 目标，判断 `layer_open`、`layer_closed`、`options_visible`、`field_value`、`element_enabled`、`not_busy`；已有 index 的可见/启用等待交给 `browser_action(wait_index|wait_enabled)`，其他条件改用 query。
- 工具失败时会返回结构化结果：`status=failed`，并带 `stage`、`error`；部分场景会额外带 `hint` / `suggested_args`。
- 新失败结果优先带 `recovery`；`stale_index` / `verify_failed` 默认先回到 `browser_state` 取新索引，不再无语义地调用 `browser_find(refresh=true)`；`recovery.stop_retry=true` 或 `stage=repeat_blocked` 时必须停止重复同一动作，改用有 query/table 的 `browser_find`、固定 `browser_recipe` 或低层路径。

### 适合

- 对用户真实 Chrome 当前页面做普通交互：点击、输入、原生 select、按 Enter/Escape/Tab、等待文本或 selector。
- 已登录页面中的轻量操作，因为底层仍沿用 TMWebDriver / Chrome 扩展接管用户浏览器。
- 同源 iframe 内已被 `browser_state` 索引出的元素操作。
- `browser_state` 输出过长或候选过多时，用 `browser_find` 按 query 或 table 语义定位，再叠加控件类型、弹层、frame 等过滤条件缩小范围。
- 常见 AntD/React 自定义下拉、弹层选择和表格目标定位：优先用固定 `browser_recipe`，让工具在歧义时 fail closed。
- 搜索框、评论框、普通表单等“输入后回车”的流程：`input(index)` 后直接 `keys(text="Enter")`，不要传 index。
- SPA 中短暂重渲染后的等待：`wait_index` 可在原节点 detached 后基于 selector hint + tag/role/text 做受限 fallback。
- SPA 加载、按钮启用、路由变化的有界等待：`wait_not_busy`、`wait_dom_stable`、`wait_enabled`、`wait_route`。
- contenteditable 或同源 iframe editor body 的直接输入，并用 `field_value` 验证。
- 表格上下文阅读和目标定位：用 row/column/header/cell metadata 或 `browser_recipe(table_locate)` 找目标，不把它当成编辑表格的高级 API。
- 需要少写 JS、以高层动作完成的日常网页控制。

### 不适合

- 大规模内容抽取、正文抓取、结构化爬取；`browser_state` 不是网页全文提取工具。
- 文件上传、验证码截图、CDP 截图、网络抓包、Cookie/Tab/CDP 管理。
- 跨域 iframe、closed Shadow DOM、复杂 iframe 坐标合成；这类场景走 `tmwebdriver_sop` / CDP bridge。
- 需要 `isTrusted=true` 的敏感点击或浏览器级交互；当前 `click` 是 DOM `el.click()`。
- 复杂自定义组件内部状态操作，例如直接改 AntD/MUI/Vue 私有状态、调用组件实例、搜索型下拉输入过滤、处理虚拟列表深层滚动；高层工具只支持被索引出的触发器/选项和固定 recipe。
- 编辑器私有 API、跨域富文本 iframe、表格单元格编辑 wrapper；当前高层工具只提供直接 contenteditable/input 和只读 metadata。
- 对任意 CSS selector 直接 `click` / `input`；当前 selector 只用于 `wait_selector`，`wait_index` fallback 也只由工具内部受限使用。
- 多元素同名同文本且无法靠 tag/role/text 区分的页面，容易超出当前 identity check 能力。
- 录制回放、长期监控、多页面并发会话、结构化导出和截图日志；这些不是当前四个高层工具的职责。

### 关键限制

- `input` 只允许 `input` / `textarea` / `contenteditable` / 同源 designMode editor body。对 button/link/普通 div 会返回 `invalid_args`。
- `select` 只允许原生 `<select>`，不支持自定义下拉。
- `keys` 只支持 `Enter`、`Escape`、`Tab`、`Control+A`、`Backspace`。
- `keys` 不传 index 时，会优先作用在顶层文档或可见同源 iframe 内的当前焦点元素；这是 `input` 后提交搜索/表单的推荐路径。
- `Control+A` / `Backspace` 只对 value-backed `input` / `textarea` 做确定性处理；contenteditable 上会拒绝，避免合成键盘事件假成功。
- `wait_text` 在顶层文档和可见同源 iframe 文档中查找文本，适合粗粒度等待，不适合精确语义判断。
- `wait_selector` 在顶层文档和可见同源 iframe 文档中等待 selector 出现，不判断命中元素自身可见性和业务语义。
- `wait_not_busy` 只检查默认或指定 busy selector 的消失，不等于业务处理完成。
- `wait_dom_stable` 只判断一段时间内 DOM 变化趋稳，不保证数据已加载正确。
- `wait_route` 只匹配 URL/route 字符串，不保证页面数据完成渲染。
- `wait_enabled` 依赖 indexed 元素；目标变化后仍应重新 `browser_state`。
- `wait_index` 如果原 cached 节点仍 attached 但 hidden，不会 fallback 到其他元素；这能避免误匹配，但可能导致超时。
- `wait_index` detached fallback 当前只用 `querySelector` 找第一个匹配，再做 tag/role/text 校验；页面上多个候选时可能等不到正确那个。
- `browser_find` 会返回 disabled 候选；如果目的是等待一个 disabled 按钮恢复可用，可以用 `browser_find` 定位后再调用 `browser_action(wait_enabled, index=...)`。
- `browser_find` 不会扩大 `browser_state` 的底层可见范围；隐藏父/祖先 iframe、跨域 iframe、未被索引的 Shadow DOM 内容仍找不到。
- `browser_recipe` 依赖 `browser_find` 和 indexed action；如果目标元素没有被 state 索引，recipe 也不会 magically 操作它。
- `custom_select` / `layer_select` 不处理搜索型下拉里的输入过滤、慢速选项渲染、虚拟滚动加载、分页选择或树节点展开；这类需要先稳定页面、刷新 state/find，必要时拆解为低层步骤。
- `component_wait` 只轮询可通过 query 定位的组件条件，timeout 会限制总等待时间且最大 60 秒；如果页面仍在加载，先用 `wait_not_busy` / `wait_dom_stable` / `wait_text` / `wait_selector`，再用 recipe 检查组件条件。
- 后台标签页、页面节流、复杂加载状态仍受 Chrome 行为影响；必要时按 `tmwebdriver_sop` 用 CDP `Page.bringToFront`。

### 何时切回 tmwebdriver_sop

遇到以下情况，不要继续反复调用 `browser_action`：
- 同一目标连续失败两次，或返回 `recovery.stop_retry=true` / `stage=repeat_blocked`。
- 需要 CDP、截图、文件上传、跨域 iframe、Shadow DOM、网络/Cookie/Tab 操作。
- 页面控件明显是复杂前端组件，普通 click/input/select 不能触发真实业务状态。
- 需要直接执行 JS、读取复杂 DOM、调用页面框架实例或 vnode。
- 需要绕过浏览器弹窗、自动下载限制、autofill 保护值等 Chrome 级问题。

这些场景继续读 `tmwebdriver_sop`，使用 `web_execute_js`、CDP 桥、vnode、DataTransfer、截图等低层方案。

## 和旧工具的配合

任务形态决策：
1. 页面读数、框架状态、隐藏字段、复杂 DOM、CDP、上传、截图、跨域 iframe：选择 `web_scan` / `web_execute_js` 低层轨道。
2. 已知要操作页面上的可交互元素，并且目标能被索引：选择 `browser_state` / `browser_find` / `browser_action` 结构化轨道。
3. 常见自定义下拉、弹层选择、表格目标定位、组件条件检查：选择固定 `browser_recipe`，让它在歧义时 fail closed。
4. 导航既可以用 `web_execute_js` 执行明确的 `location.href='...'`，也可以在已有页面中通过 indexed link/button 点击；按页面上下文选择，不做固定优先级。
5. browser_* 连续失败且 recovery 已要求停止重复时，不要原地撞墙；补充 query/table/layer/frame 约束，或切换到 `web_execute_js` / CDP 低层轨道。

## 禁止/反模式

- 禁止在 mutating action 后继续复用旧 index。
- 禁止 input 后为了按 Enter 重新扫 state；优先 `keys` without index。
- 禁止把 `selector` 当成通用 click/input 定位方式；selector 仅用于 `wait_selector`，`wait_index` fallback 由工具内部控制。
- 禁止对非输入元素执行 `input` 后假设成功。
- 禁止忽略 `status=failed` 的 `stage`、`recovery`、`hint`、`suggested_args`。
- 禁止在 `ambiguous=true` 时直接使用第一个候选 index。
- 禁止在 `recovery.stop_retry=true` 或 `repeat_blocked` 后继续重复同一动作。
- 禁止把 `component_wait` 当成业务完成或无限等待器；它只在 `timeout` 内做 state/find 有界轮询。
- 禁止把 `browser_recipe` 当成自由规划工具；browser_recipe 不是自由规划器，只支持四个固定 recipe。
- 禁止遇到复杂自定义组件时无脑重复 click；先按 recovery/recipe 处理，仍失败再读 `tmwebdriver_sop`。

## 最小心智模型

记住五句话：

1. 先判断任务形态和组件类型，再选 `web_execute_js` 低层轨道或 browser_* 结构化轨道。
2. 选择 browser_* 轨道时，先 `browser_state`，再用 index；state 太长或目标不明确时，用带 query/table 的 `browser_find` 缩小候选。
3. `browser_recipe` 不是自由规划器，只用于固定的 `custom_select`、`layer_select`、`table_locate`、`component_wait`，歧义就补约束。
4. `browser_action(keys, text="Enter")` 可以不传 index，输入后提交/搜索时优先复用当前焦点。
5. 失败先读 `recovery.stop_retry` / `recovery.next_args`；页面结构变了，旧 index 作废，要么按焦点继续，要么重新 `browser_state`，需要缩小候选时再用带 query/table 的 `browser_find(refresh=true)`。
