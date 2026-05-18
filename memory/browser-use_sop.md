# Browser-* 使用 SOP

- 直接使用 `browser_use_index` / `browser_find` / `browser_action` / `browser_recipe`。
- 本文件只记录编排、坑、恢复策略和边界；工具参数、枚举、字段定义以 `assets/tools_schema*.json` 为准。
- 这里的 `browser-*` 指 GA 内置的高层结构化浏览器操作层，不是外部 `browser-use` Python 项目运行时。
- 底层仍走 TMWebDriver / `assets/tmwd_cdp_bridge` 接管用户真实 Chrome，因此继承用户登录态、Cookie、当前页面上下文。

## 核心定位

- `browser_*` 是结构化 indexed-action 轨道：先读 state，再按 index / semantic locator 操作。
- `web_scan` / `web_execute_js` 是低层 JS/CDP 轨道：适合复杂 DOM、框架状态、CDP、上传、截图、跨域 iframe 等。
- 两条轨道平级互补，不存在固定优先级；不要为了完成目标把任一轨道扩成万能自动化层。
- 选择标准不是“哪个工具更高级”，而是“当前页面目标能否被 state 索引，操作是否适合有界动作”。

## 快速决策

- 目标是页面上可交互元素，且能被索引：走 `browser_use_index` -> `browser_find`/人工判断 -> `browser_action`。
- 目标是常见自定义下拉、弹层选择、表格目标定位、短时组件等待：优先试固定 `browser_recipe`。
- 目标需要读复杂 DOM、调用页面框架实例、上传文件、截图、CDP、跨域 iframe、Shadow DOM：切回 `tmwebdriver_sop`。
- 同一动作失败两次、返回 `recovery.stop_retry=true` 或 `repeat_blocked`：停止原地重试，换定位、recipe 或低层路径。

## 结构化浏览器工具编排（iframe/弹层版）

1. 同源 iframe 表单优先流程：调用 `browser_use_index`，将 `max_elements` 设置为至少 `150` -> `browser_find` -> `browser_recipe` / `browser_action`。
2. 如果 `browser_find` 返回 `target_not_found` 且 recovery 提示快照被截断，不要重复同一查询；先刷新 `browser_use_index` 并提高 `max_elements`。
3. 对 `combobox` / `custom_select`：先定位触发器，再用 `browser_recipe(custom_select)`；不要先猜测 option index。
4. 对打开后的弹层/下拉：如果 recovery 提示 `component_wait`，先等待 `options_visible` 或 `layer_closed`，再重试，不要盲目重复 click。
5. 同一路径连续两次失败后，必须换轨到 `web_execute_js` 或重新探测结构，禁止第三次用相同参数重试。

## 基本流程

### 1. 先 state，再 indexed action

标准顺序：
```json
{"tool": "browser_use_index", "args": {"max_elements": 120}}
{"tool": "browser_action", "args": {"action": "click", "index": 12}}
```

要点：
- `click` / `input` / `select` / `wait_index` / `wait_enabled` 依赖最近一次 `browser_use_index`。
- 页面变化后旧 index 可能失效；不要猜旧 index。
- `browser_use_index` 输出里的 `scan_anchor` 是给 `web_scan` 文本到可操作 index 的引路字段，不会自动执行 recipe。

### 2. state 太长或目标不明确，用 browser_find 缩小

语义定位：
```json
{"tool": "browser_find", "args": {"query": "审批意见", "control_kind": "contenteditable", "max_results": 5}}
```

表格定位：
```json
{"tool": "browser_find", "args": {"table": {"row_text": "张三", "column_text": "工时"}, "max_results": 5}}
```

要点：
- `query` 或 `table` 才是真正定位条件。
- `role`、`control_kind`、`layer`、`frame_path` 只是过滤条件，不能单独使用。
- `ambiguous=true` 时补约束，不要拿第一个候选直接操作。
- `browser_find` 只返回候选，不代表页面已经被操作。

### 3. mutating action 后刷新 state

以下动作成功后可能导致 DOM 改变：
- `click`
- `input`
- `select`
- `keys`

后续还要 indexed action 时，重新 `browser_use_index` 或用 `browser_find(refresh=true)` 重新定位。

### 4. input 后提交，优先 keys without index

搜索框、评论框、命令框：
```json
{"tool": "browser_action", "args": {"action": "input", "index": 52, "text": "openai"}}
{"tool": "browser_action", "args": {"action": "keys", "text": "Enter"}}
```

不要这样：
```json
{"tool": "browser_action", "args": {"action": "keys", "index": 52, "text": "Enter"}}
```

原因：
- `input` 后输入框通常仍是 activeElement。
- 输入后 DOM 可能弹下拉或重排，旧 index 容易失效。
- `keys` 不传 index 时会发给当前焦点，更适合“输入后回车”。

### 5. 操作后验证，不靠 success 自嗨

能读回字段值时使用：
```json
{"tool": "browser_action", "args": {"action": "input", "index": 38, "text": "同意", "verify": "field_value", "verify_value": "同意"}}
```

页面跳转或提交后使用有界等待：
```json
{"tool": "browser_action", "args": {"action": "wait_text", "text": "提交成功", "timeout": 10}}
```

要点：
- 等待动作只证明条件出现/消失，不证明业务成功。
- `verify_failed` 后先读页面状态，不要重复写同一个值。

## Recipe 用法

### custom_select

用于常见自定义下拉。优先让 recipe 做 trigger -> state -> option -> click 的固定编排：
```json
{"tool": "browser_recipe", "args": {"recipe": "custom_select", "target": {"query": "工作类型"}, "option_text": "代码开发", "max_results": 5}}
```

使用条件：
- 有明确字段名或目标语义。
- 选项文本明确。
- 下拉 trigger 和 option 能被 state/find 索引。

失败后：
- `ambiguous_target`：补 `target.query`、`layer`、`table` 或更具体文本。
- 找不到 option：先 `browser_use_index` 看 overlay 是否打开，再决定拆解或低层探测。
- 搜索型下拉、虚拟列表、深层滚动不保证覆盖。

### layer_select

用于弹窗、抽屉、popover 中的有界选择：
```json
{"tool": "browser_recipe", "args": {"recipe": "layer_select", "target": {"query": "选择人员"}, "option_text": "张三"}}
```

需要确认按钮时显式给出：
```json
{"tool": "browser_recipe", "args": {"recipe": "layer_select", "target": {"query": "选择人员"}, "option_text": "张三", "confirm_text": "确定"}}
```

不要让 recipe 猜确认按钮。

### table_locate

只定位，不编辑：
```json
{"tool": "browser_recipe", "args": {"recipe": "table_locate", "table": {"row_text": "张三", "column_text": "工时"}}}
```

返回 index 后，再按目标控件类型决定 `click` / `input` / `wait_enabled`。

不负责：
- 分页
- 虚拟滚动
- 单元格编辑
- 行内复杂控件业务流程

### component_wait

用于短时间等组件状态稳定：
```json
{"tool": "browser_recipe", "args": {"recipe": "component_wait", "condition": "options_visible", "target": {"query": "工作类型"}, "timeout": 10}}
```

要点：
- 只做有界轮询，不是长期监控。
- 只接受 query 类目标；已有 index 的可见/启用等待用 `browser_action(wait_index|wait_enabled)`。
- 底层非 `target_not_found` 错误会直接返回，不吞成 timeout。

## 常见场景

### 搜索

```json
{"tool": "browser_use_index", "args": {"max_elements": 120}}
{"tool": "browser_action", "args": {"action": "input", "index": 52, "text": "openai"}}
{"tool": "browser_action", "args": {"action": "keys", "text": "Enter"}}
{"tool": "browser_action", "args": {"action": "wait_text", "text": "openai", "timeout": 10}}
```

### 普通表单填写

```json
{"tool": "browser_find", "args": {"query": "审批意见", "control_kind": "contenteditable", "refresh": true}}
{"tool": "browser_action", "args": {"action": "input", "index": 38, "text": "同意", "verify": "field_value", "verify_value": "同意"}}
```

### 自定义下拉选择

优先 recipe：
```json
{"tool": "browser_recipe", "args": {"recipe": "custom_select", "target": {"query": "工作类型"}, "option_text": "代码开发"}}
```

必要时拆解：
```json
{"tool": "browser_find", "args": {"query": "工作类型", "control_kind": "custom_select", "refresh": true}}
{"tool": "browser_action", "args": {"action": "click", "index": 4}}
{"tool": "browser_use_index", "args": {"max_elements": 120}}
{"tool": "browser_find", "args": {"query": "代码开发", "layer": "dropdown"}}
{"tool": "browser_action", "args": {"action": "click", "index": 22}}
```

### 弹层选择

```json
{"tool": "browser_recipe", "args": {"recipe": "layer_select", "target": {"query": "选择项目"}, "option_text": "研发项目", "confirm_text": "确定"}}
```

### 关闭弹窗或菜单

```json
{"tool": "browser_action", "args": {"action": "keys", "text": "Escape"}}
```

## 错误恢复

### state_missing

- indexed action 前缺 state。
- `keys` 如果是 input 后提交，按 recovery 改成不传 index。
- 其他 indexed action 先 `browser_use_index`，再重新选 index。

### stale_index

- 旧 index 或旧 tab 不能继续用。
- 先刷新 state；如果有字段名/表格语义，用 `browser_find(refresh=true)` 缩小。
- 不要猜旧 index。

### visibility

- 元素不可见、零尺寸、被遮挡、disabled 或 readonly。
- 如果 recovery 给了 `find_clickable_in_same_field`，按它找同字段内更合适的可点击控件。
- 如果是页面 loading、遮罩或弹层，先等稳定或关闭遮挡。
- 不要用 JS 硬写 readonly/disabled 字段来伪造成功。

### invalid_args

- 动作和目标类型不匹配。
- `select` 只适合原生 select；自定义下拉走 `custom_select` 或拆解。
- `input` 只适合输入类元素；按钮、链接、普通 div 不要 input。

### ambiguous_target

- 候选太接近，工具拒绝猜。
- 补字段名、行列、层级、frame、控件类型。
- 不要直接点第一个。

### repeat_blocked

- 同一目标同一动作重复失败，工具已熔断。
- 必须换策略：更强语义定位、固定 recipe、或低层 `web_execute_js` / CDP。

## 能力边界

### 适合

- 用户真实 Chrome 当前页的轻量交互。
- 普通点击、输入、原生 select、按键、短时等待。
- 同源 iframe 中已被 state 索引出的元素。
- state 输出太长时的语义定位。
- 常见自定义下拉、弹层选择、表格目标定位、组件短时等待。
- contenteditable / 同源 designMode editor body 的直接输入。

### 不适合

- 大规模内容抽取、结构化爬取、全文读取。
- 文件上传、截图、验证码、Cookie/Tab/CDP 管理。
- 跨域 iframe、closed Shadow DOM、复杂坐标合成。
- 需要 `isTrusted=true` 的敏感操作。
- 调用前端框架私有 API、处理虚拟列表深层滚动、搜索型下拉复杂过滤。
- 录制回放、长期监控、多页面并发会话。

### 关键实现事实

- `browser_use_index` 默认只返回可见元素；`include_invisible=true` 也不会暴露隐藏父 iframe 子树。
- `browser_find` 不会扩大 state 的可见范围；state 找不到的，find 也不会凭空找到。
- `browser_find(refresh=true)` 后仍 `target_not_found` 且 `stop_retry=true` 时，停止重复同一查询。
- `browser_recipe` 依赖 `browser_find` 和 indexed action；目标没被索引时 recipe 也不能操作。
- `browser_action` 成功修改页面后会清空缓存 state，防止复用旧 index。
- `browser_use_index` 不再输出 `recipe_hint` / `action_hints`；组件级流程由显式 `browser_recipe` 参数驱动。

## 何时切回 tmwebdriver_sop

遇到以下情况，不要继续用 browser_* 撞墙：
- 需要文件上传、截图、验证码、CDP、Cookie/Tab 管理。
- 跨域 iframe 或 Shadow DOM 不能被 state 索引。
- 页面组件必须调用框架实例、vnode、私有 API 才能正确触发业务状态。
- `browser_action` / `browser_recipe` 连续失败，且 recovery 要求停止重复。
- 需要绕过浏览器弹窗、自动下载限制、autofill 保护值等 Chrome 级问题。

此时按 `tmwebdriver_sop.md` 使用 `web_execute_js`、CDP bridge、DataTransfer、vnode 或截图等低层方案。

## 禁止/反模式

- 禁止把 SOP 当工具 schema；参数细节以 JSON schema 为准。
- 禁止 mutating action 后复用旧 index。
- 禁止 input 后按 Enter 还带旧 index。
- 禁止把 `browser_find` 当全局搜索。
- 禁止把 `browser_recipe` 当自由规划器。
- 禁止在 `ambiguous=true` 时点第一个候选。
- 禁止在 `repeat_blocked` 后继续重复同一动作。
- 禁止为了短期成功加入业务系统前缀或业务字段硬编码。

## 最小心智模型

1. 能索引就走 browser_*；不能索引或需要底层能力就走 `tmwebdriver_sop`。
2. browser_* 轨道先 state；目标不明确用 find；组件流程用固定 recipe。
3. 动作成功后旧 index 作废；输入后提交用 keys without index。
4. 失败先读 recovery；stop_retry 就换路径。
5. SOP 讲怎么编排，schema 讲参数定义，不重复背工具说明。
