# GA Browser 平级边界设计

## Goal

本设计的目标不是调整工具优先级，而是让 `web_execute_js` 与 `browser_*` 成为两条平级、互补、边界清晰的能力轨道。

- `browser_*` 负责结构化、可验证、可恢复的高层页面操作。
- `web_execute_js` 负责低层探测、特殊控制、以及高层工具不能稳定覆盖的场景。
- 两者不互相吞并，不把任何一边做成万能层。

本设计的核心价值是减少“看得见但总撞墙”的情况，同时避免为了完成目标而堆砌特例逻辑，导致通用性下降。

## Hard Constraints

- GA 仍只操作用户已经打开的真实 Chrome 会话。
- GA 不启动 Chrome，不创建新浏览器工作空间，不迁移登录态。
- GA 不修改 `E:\zfengl-ai-project\browser-use`。
- `web_execute_js` 与 `browser_*` 保持平级，不做工具优先级改造。
- `browser_*` 只能做可解释、可验证、可恢复的事情，不能被扩成通用自动化壳。
- 不为完成目标强行补“万能分支”，不为覆盖场景制造屎山代码。

## Current Observation

从最近一轮真实日报测试看，问题不在“有没有能力”，而在“工具职责和描述不够精确”。

典型现象：

- `是否休假` 能在 state 中被看到，但 `browser_find` 早期按文本直接找不到，说明需要更强的字段上下文，而不是更大的搜索能力。
- `项目名称` 真实组件是放大镜弹窗选择，不是联想输入，说明 SOP 和工具描述需要把组件类型说清楚。
- `工作类型` 的下拉存在多个残留 overlay，说明 recipe 需要 fail closed，而不是默认取第一个匹配。
- `web_execute_js` 在探测和验证上有效，但在普通交互上被过度使用，说明它需要保持平级但职责要明确。

## Design Principles

1. 平级并列，不做隐性主从。
   - 工具选择由任务形态决定，不由文档强行排优先级。

2. 描述必须精确到边界。
   - 每个 `browser_*` 工具都要明确“做什么、不做什么、返回什么、失败时怎么恢复”。

3. 只衍生通用能力，不强行泛化。
   - 能从现有元数据推出的能力就收进来。
   - 不能稳定衍生的能力就留给 `web_execute_js` 或低层 SOP。

4. 失败必须可解释。
   - `browser_*` 失败后应返回 recovery，而不是让模型继续猜。

5. 固定 recipe 只覆盖高复用模式。
   - 只保留稳定、常见、可复用的操作编排。
   - 不把 recipe 做成通用规划器。

## Tool Boundary Model

### `browser_state`

职责：把当前真实页面转成可索引、可恢复的结构化快照。

应明确输出：

- `index`
- `frame_path`
- `layer`
- `control_kind`
- `table_context`
- `action_hints`
- `state_token`

不应承诺：

- 网页全文抽取
- 复杂 DOM 推理
- 跨域 iframe 穿透
- 业务语义理解

### `browser_find`

职责：在 `browser_state` 快照上做语义定位。

应明确：

- 必须依赖 `query` 或 `table`
- `role`、`control_kind`、`layer`、`frame_path` 只是过滤条件
- 只返回候选，不执行动作
- 歧义时返回 candidates，不默认选第一个

不应承诺：

- 自由搜索引擎式全局匹配
- 无约束返回任意可见元素
- 替代 `browser_state`

### `browser_action`

职责：执行有限且确定的动作，并提供验证结果。

保留范围：

- `click`
- `input`
- `select`
- `keys`
- 有界等待类动作
- 受限验证能力

不应承诺：

- 任意 selector 点击 / 输入
- 复杂页面规划
- 通用表单推理
- 业务流程自动完成

### `browser_recipe`

职责：固定模式编排，不是自由规划器。

只保留这类模式：

- 自定义下拉选择
- 弹窗 / 抽屉 / 浮层选择
- 表格定位
- 组件等待

不应承诺：

- 覆盖所有页面操作
- 自动理解所有企业组件
- 递归式复杂编排

### `web_execute_js`

职责：低层探测、特殊控制、补位操作。

适合做：

- WfForm 或页面框架探测
- 复杂 DOM 读取
- 需要直接观察隐藏状态
- 跨域 iframe、上传、截图、CDP、特殊事件链

不应被降级，也不应承担普通交互的默认职责。

## What Can Be Derived

这些能力可以从现有实现自然衍生，不需要扩大到屎山级别：

- 同源 iframe 里的索引和动作。
- overlay / modal / drawer / dropdown 的层级优先级。
- `custom_select` 的固定选择流程。
- `layer_select` 的弹窗选择流程。
- 表格行列定位。
- `contenteditable` 和同源 editor body 的写入与回读。
- `verify_hint` 和明确的 recovery。

这些衍生都建立在已有元数据上，不需要引入大而全的新抽象。

## What Must Not Be Forced

以下能力不应该为了“统一设计”而强行塞进 `browser_*`：

- 跨域 iframe 高层自动化
- 文件上传
- 截图日志
- 浏览器级鼠标/键盘仿真替代
- closed Shadow DOM
- 任意 selector 的通用 click/input
- 录制 / 回放
- 多页面并发会话
- 业务特定 OA 规则写死进 recipe

这些要么留给 `web_execute_js` / CDP / SOP，要么明确不做。

## Recovery And Failure Semantics

每个 `browser_*` 工具失败后，都应尽量告诉模型下一步该做什么。

恢复原则：

- `browser_find` 失败：优先补 `query/table/layer/frame_path`，或刷新 state。
- `browser_action` 失败：优先读 `stage` 和 `recovery`，不要重复同样动作。
- `browser_recipe` 歧义：返回候选，不默认选第一个。
- `repeat_blocked`：停止原地撞墙，切换到更明确的定位或低层路径。

## Documentation Contract

后续需要把工具说明改成“平级职责”口径：

- `web_execute_js` 不再暗示自己是普通交互首选。
- `browser_*` 不再暗示自己可以通吃所有页面。
- `browser_find` 需要把 `query/table` 的主定位地位写清楚。
- `browser_recipe` 需要明确它是固定 recipe，不是通用代理。
- SOP 需要告诉模型：先判断组件类型，再选工具，而不是先猜后试。

## Validation Criteria

这个设计算成立，至少要满足以下判断：

- 日常表单操作能清楚区分：普通输入、原生 select、自定义下拉、弹窗选择、表格定位。
- `browser_*` 的失败结果能直接引导下一步，而不是让模型继续盲试。
- `web_execute_js` 仍能保留其低层价值，但不再污染普通交互路径。
- 工具描述更精确后，模型能少撞墙，而不是靠增加分支数量硬扛。

## Non-Goals

- 不做 browser-use runtime 替换。
- 不调整工具优先级。
- 不扩成万能浏览器自动化框架。
- 不为了“覆盖更多场景”而牺牲通用性。

