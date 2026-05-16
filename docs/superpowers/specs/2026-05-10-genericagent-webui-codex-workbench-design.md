# GenericAgent WebUI Codex 工作台升级设计

日期：2026-05-10

## 目标

在当前 `zfengl-ga-long-webui` 分支的前端工程拆解版本上，继续提升 GenericAgent WebUI 的产品质感和交互效率。升级方向是“Codex 风格工作台”：克制、专业、高密度、低噪音，强调聊天、执行过程和会话管理的清晰组织，而不是只做配色替换。

本设计只基于现有 `frontends/webui_server.py` 已暴露的 WebUI 专属后端能力，不新增 subagent、run、artifact、checkpoint 等后端实体或展示契约。

## 非目标

- 不做 subagent 状态可视化。
- 不新增 run / artifact / checkpoint 后端模型。
- 不做任务重试、接管、分叉、回放等新能力。
- 不重写 WebUI 技术栈。
- 不把页面改成营销页、展示页或大面积装饰型界面。
- 不为了视觉效果引入新的重量级 UI 库。

## 当前可用后端能力

当前设计只使用这些已有接口和数据结构：

- `GET /api/state`：运行状态、当前模型、模型列表、自主行动状态、当前会话、会话列表、分组、执行日志。
- `GET /api/conversations`、`GET /api/conversations/:id`：会话列表与会话详情。
- `POST /api/conversations`：创建会话。
- `PATCH /api/conversations/:id`：重命名会话。
- `DELETE /api/conversations/:id`：删除会话。
- `POST /api/conversations/:id/activate`：激活会话。
- `POST /api/conversations/:id/pin`：置顶会话。
- `POST /api/conversations/:id/move`：移动会话到分组。
- `GET /api/groups`、`POST /api/groups`、`PATCH /api/groups/:id`、`DELETE /api/groups/:id`：分组管理。
- `POST /api/chat` 和 `GET /api/chat/:task_id/stream`：发起任务与 SSE 流。
- `POST /api/abort`：停止当前任务。
- `POST /api/llm`：切换模型。
- `POST /api/reinject`：重新注入 System Prompt。
- `POST /api/new`：兼容的新会话重置。
- `POST /api/continue`：兼容旧会话恢复。
- `POST /api/autonomous`：开启或关闭自主行动。

已有前端核心数据包括 `RuntimeState`、`ConversationSummary`、`ConversationDetail`、`UiMessage`、`ExecutionTurn` 和 `ExecutionToolCall`。

## 设计方向

采用“主流 AI 工作台布局 + Codex 风格收敛”的方案，不从零设计。

参考的主流模式包括：

- ChatGPT / Claude 的左侧会话导航、中心聊天主工作区、顶部状态动作。
- Codex / Cursor 类工具的低噪音工具栏、清晰运行态、可展开执行过程。
- Linear / GitHub 类工作台的紧凑列表、明确选择态、克制色彩和密集信息呈现。

落地时不照搬某个产品，而是抽取这些共同点：

- 信息架构稳定。
- 主要工作内容居中。
- 次要状态贴近上下文。
- 操作分主次，不把所有按钮平铺。
- 执行过程可读，但不抢占聊天主体。

## 页面架构

桌面端采用三层工作台结构：

1. 左侧会话导航
   - 保留分组、置顶、最近会话、批量删除、移动、重命名、删除等现有能力。
   - 视觉上从“普通列表”升级为更像工作台资源栏：更紧凑的 row、高质量 active state、清晰 section header。
   - 折叠态只保留新建和展开入口，避免塞入过多功能。

2. 中间主工作区
   - 顶部显示当前会话标题、运行状态、模型状态和关键操作。
   - 主体显示消息流，消息卡片降低装饰感，提升代码、表格、引用、工具结果阅读质量。
   - 底部 composer 固定为核心输入面板，强化输入态、运行态、禁用态和错误态。

3. 右侧上下文面板
   - 不做 subagent inspector。
   - 只承载当前已有的 `execution_log`、运行状态摘要和兼容操作。
   - 桌面端可以作为可折叠辅助面板；移动端使用 Drawer。
   - 右侧面板不是“新后端能力”的入口，而是把已有执行日志、工具调用和状态组织得更清楚。

## AntD 使用策略

AntD 作为交互骨架，不只是换按钮样式。

优先使用：

- `Layout`：页面骨架和 Sider 语义。
- `Splitter`：桌面端左右区域尺寸调整，给工作台更强的专业工具感。
- `Button`、`Tooltip`、`Dropdown`：统一动作入口和图标按钮提示。
- `Select`：模型选择。
- `Tabs` 或 `Segmented`：右侧面板的“执行 / 状态”轻切换。
- `Card`：只用于消息、执行 turn、工具调用等真实内容容器，不做卡片套卡片。
- `Tag`、`Badge`、`Progress`：运行状态、工具状态和模型状态。
- `Timeline`：可选用于执行过程的纵向时间线，但只基于已有 `ExecutionTurn`。
- `Drawer`、`Modal`：移动端辅助面板与确认流程。
- `Skeleton`、`Empty`、`Alert`：加载、空态和错误态。

避免：

- 大面积 `Card` 包页面 section。
- 过度圆角、玻璃拟态、强渐变、漂浮装饰。
- 在组件内部散落 raw hex，优先通过主题 token 和少量 CSS 变量统一。
- 用自定义 div 重造 AntD 已经稳定提供的交互控件。

## 视觉系统

风格关键词：Codex、workbench、dense、calm、precise。

视觉原则：

- 背景更接近专业工具台，而不是浅色网页：主背景低对比，内容面板清晰但不过分发光。
- 主色保持克制，建议继续沿用当前青绿色系，但降低“按钮感”，更多用于 active state、focus ring、状态点。
- 文本层级明确：标题、meta、body、辅助文本分别有固定字号和颜色。
- 圆角控制在 6-12px，避免过度胶囊化。
- 阴影只用于真正浮层、composer、active panel，不用于每个列表项。
- 交互态必须可见：hover、active、focus、disabled、loading 都要统一。

需要重点打磨的区域：

- 会话列表 active row：比现在更精致，避免仅靠左色条。
- 顶部栏：减少散装信息，形成“当前上下文 + 运行控制 + 更多操作”的稳定结构。
- 消息卡片：assistant 更像文档块，user 更像命令输入块，不追求聊天软件气泡感。
- 执行过程：从“附属日志”变成可扫描的操作记录，但不压过正文。
- Composer：做成整个界面最稳定的输入锚点，运行时清楚反馈。

## 交互升级

1. 会话导航
   - 保留现有分组和批量删除。
   - 分组标题、数量、空态、hover action 要更清晰。
   - 会话 item 的主点击区和更多操作区必须分离，减少误触。
   - 运行中不可切换的状态要用 disabled 样式明确表达。

2. 顶部栏
   - 左侧显示当前会话标题和状态。
   - 中间不堆内容，避免标题被动作挤压。
   - 右侧保留模型选择、运行状态、停止按钮、更多菜单。
   - “重新注入 System Prompt”“自主行动”“恢复旧会话”继续放入更多菜单，避免高频区噪音。

3. 消息区
   - 空状态不做营销式 hero，直接给可用入口和最近上下文提示。
   - 流式输出保持已有平滑显示，不改变协议。
   - 消息 markdown 提升阅读质量：代码块、表格、列表、引用、链接都要有专业工具感。
   - 执行日志仍内联在 assistant 消息中，但样式更收敛，可折叠、可扫描。

4. 右侧上下文面板
   - 只基于当前 `execution_log` 和 `RuntimeState`。
   - 默认展示当前任务摘要、模型、自主行动状态、最近执行 turn。
   - 展开某个 execution turn 后展示工具调用明细。
   - 如果没有执行日志，展示紧凑空态，不制造虚假结构。

5. Composer
   - 输入区保持底部主锚点。
   - 发送、停止、运行中、未配置、空输入等状态要清楚。
   - 保留键盘提交逻辑，不引入复杂快捷键系统。
   - 错误反馈靠近 composer 或顶部 `Alert`，避免只在 console 或 toast。

## 响应式策略

桌面端：

- 左侧 sidebar 固定或可折叠。
- 中间 chat 作为主列。
- 右侧上下文面板可折叠或通过 Splitter 调整宽度。

平板端：

- 保留左侧或右侧之一，另一侧转 Drawer。
- 主聊天区优先。

移动端：

- 默认只显示聊天。
- 会话导航通过 Drawer。
- 上下文面板通过 Drawer。
- Composer 和顶部栏必须不遮挡正文。

## 可访问性与质量标准

- 交互目标最小 44px。
- 所有图标按钮必须有 `aria-label` 或 `Tooltip`。
- focus ring 不移除，且在深浅背景上都可见。
- 文本对比度达到常规阅读要求。
- 动效只使用 opacity / transform，避免布局抖动。
- 尊重 `prefers-reduced-motion`。
- 不引入横向滚动，代码块和表格在内容内滚动。

## 实现边界

允许修改：

- `frontends/webui/src/App.tsx`
- `frontends/webui/src/theme.ts`
- `frontends/webui/src/styles/*`
- `frontends/webui/src/components/app/*`
- `frontends/webui/src/components/chat/*`
- `frontends/webui/src/components/composer/*`
- `frontends/webui/src/components/execution/*`
- `frontends/webui/src/components/shell/*`
- `frontends/webui/src/components/sidebar/*`
- 必要的前端 state/domain helper
- 前端状态测试

原则上不修改：

- `frontends/webui_server.py`
- GA 本体运行逻辑
- 外部依赖项目

只有在现有前端类型与已存在 API 不匹配时，才允许做极小的前端类型或 API wrapper 调整。

## 验证标准

设计实现后必须通过：

- `npm --prefix frontends/webui run build`
- 现有前端状态测试。
- 与 WebUI 相关的后端测试，如 `tests.test_webui_server`。
- `git diff --check`

需要人工或浏览器检查的视觉标准：

- 桌面宽屏没有空洞和拥挤感。
- 窄屏不出现横向滚动。
- 会话列表、消息区、composer、执行日志四个区域视觉层级明确。
- 运行中、停止、错误、空态、未配置状态都能被用户一眼识别。

## 分阶段计划

第一阶段：工作台骨架升级

- 用 AntD `Layout` / `Splitter` 组织桌面布局。
- 保留当前组件拆分边界。
- 完成桌面三栏结构和移动 Drawer 策略。

第二阶段：导航与顶部栏质感升级

- 打磨会话 sidebar、分组、active state、批量选择。
- 重排 TopBar 动作层级。
- 统一按钮、图标、Tooltip、Dropdown 行为。

第三阶段：聊天与 Composer 升级

- 打磨消息卡片、markdown、代码块、表格。
- 优化空态和流式输出视觉。
- 强化 composer 的输入、运行、禁用、错误反馈。

第四阶段：执行过程与状态面板升级

- 基于现有 `ExecutionTurn` 做更清晰的内联执行块。
- 增加右侧上下文面板，但只展示已有 `execution_log` 与 `RuntimeState`。
- 不引入 subagent 概念。

第五阶段：视觉统一与验证

- 收敛 theme token 和 CSS 变量。
- 检查移动端、桌面端、focus、hover、loading、disabled。
- 跑构建和测试。

## 成功判定

完成后，WebUI 应该从“浅色聊天页面”升级为“专业 Agent 工作台”：

- 用户能清楚知道当前会话、模型、运行状态和可用操作。
- 会话管理更像生产力工具，而不是普通列表。
- 消息阅读和执行过程可扫描、可展开、不过度抢占注意力。
- 页面高级感来自布局、层级、节奏和交互一致性，而不是单纯换色。
- 所有变化都能在现有 WebUI 后端能力上完成，不增加 GA 本体侵入面。
