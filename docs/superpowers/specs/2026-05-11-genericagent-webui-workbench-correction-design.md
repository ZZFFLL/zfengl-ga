# GenericAgent WebUI 工作台纠偏升级设计

日期：2026-05-11

## 背景

上一轮 WebUI 升级没有达到“交互、布局、风格整体升级”的目标。实际结果偏向保守增量：保留旧聊天气泡结构，只增加右侧工作上下文面板、少量 AntD token 和局部 CSS。用户打开页面后，主交互路径没有明显变化，聊天区仍像普通 IM 页面，右侧面板的信息价值也不足。

本设计用于纠偏：不再把“加面板、换颜色、调间距”当作升级成果，而是把 GenericAgent WebUI 从普通聊天页改成专业 Agent 工作台。

## 核心目标

把 WebUI 的主体验从“聊天气泡 + 附属执行日志”升级为“任务工作台 + 命令输入 + 执行轨迹 + 结果文档”。

完成后，用户应能在首屏和对话态立即识别出：

- 当前要做什么：中心区展示任务指令和任务上下文。
- 现在做到哪：执行轨迹和运行状态贴近当前任务。
- 下一步能做什么：command dock、停止按钮、可展开执行块和按需 inspector 给出明确操作入口。

## 纠偏原则

### 1. 中心工作区是主角

右侧面板不能再成为唯一明显变化。即使右侧隐藏，页面也必须明显区别于普通聊天页面。

中心区必须改为任务流结构：

- 用户消息不再是右侧气泡。
- 用户输入展示为 command block。
- 助手回复展示为全宽 response panel。
- 执行过程展示为 task trace，而不是普通消息内的装饰性折叠块。

### 2. 右侧区域必须有信息价值

右侧区域默认不常驻占位。没有运行任务、没有选中的执行步骤、没有错误或工具细节时，不显示低信息密度面板。

右侧只允许作为按需 inspector：

- 运行中：展示当前执行轮次、当前工具、工具状态、停止入口。
- 用户点击执行步骤：展示该步骤的 summary、工具调用列表、参数和结果预览。
- 错误或中断：展示错误原因、相关执行步骤和恢复建议。

禁止：

- 为了三栏布局完整而展示泛泛状态摘要。
- 展示“已配置 / 模型 / 自主行动”这类低价值卡片作为主内容。
- 在无执行记录时常驻空态面板。

### 3. 主题必须作用到真实页面

上一轮主要改 `theme.ts`，但主页面大量样式来自 Tailwind token 和自定义 CSS，所以视觉变化有限。本轮必须同步改：

- `frontends/webui/src/theme.ts`
- `frontends/webui/tailwind.config.ts`
- `frontends/webui/src/styles/base.css`
- `frontends/webui/src/styles/shell.css`
- `frontends/webui/src/styles/workbench.css`
- `frontends/webui/src/styles/chat.css`
- `frontends/webui/src/styles/execution.css`
- `frontends/webui/src/styles/context.css`
- `frontends/webui/src/styles/antd-overrides.css`

AntD token 只作为组件基础，不再被误认为完整主题系统。

### 4. 交互变化必须可感知

不是只换颜色，而是改变主要操作节奏：

- 空状态直接进入 command workspace，不做营销式 hero。
- 发送后出现 task item，用户 command、execution trace、response 同属一个任务单元。
- 运行中 composer dock、顶部状态、当前 task item 同步进入运行态。
- execution trace 支持点击定位 inspector。
- 停止入口在顶部和运行 inspector / dock 中都能被识别，但不重复制造噪音。

### 5. 静态测试必须防止旧形态回潮

测试不能只检查组件是否 import。需要加入结构性约束：

- `ChatMessageView` 不再使用 `justify-end` / `ga-message-user` 作为主用户消息气泡结构。
- `Composer` 必须暴露 command dock 样式类。
- 工作台 CSS 必须包含 task stream、command block、response panel、command dock。
- 右侧 inspector 必须是按需 open，不允许无条件常驻低价值状态面板。

## 信息架构

### 桌面端默认布局

默认布局为两栏：

1. 左侧会话资源栏
   - 会话、分组、置顶、最近对话。
   - 保留现有行为。
   - 视觉上继续收敛为工作台资源栏。

2. 中心任务工作台
   - 顶部为当前会话和运行控制。
   - 主体为 task stream。
   - 底部为 command dock。

右侧 inspector 不默认占位。只有满足下列条件之一时打开：

- 当前有运行中的 execution turn。
- 用户点击 task trace 中的某个 turn 或 tool call。
- 当前任务出现错误或中断。

### 移动端布局

移动端默认只显示中心任务工作台。

- 会话资源栏通过 Drawer 打开。
- Inspector 通过 Drawer 打开。
- Command dock 固定底部，但不得遮挡任务流末尾内容。

## 中心任务工作台

### Task Stream

对话态不再渲染为普通 message list，而是渲染为 task stream。

每个 task item 包含：

- Command block：用户输入的任务指令。
- Execution trace：当前任务的执行轮次、工具调用、状态。
- Response panel：最终回答或流式回答。

数据仍使用现有 `UiMessage` 和 `ExecutionTurn`，不新增后端模型。前端可以通过相邻的 user / assistant message 组合成 task item。

### Command Block

Command block 用于替代用户右侧气泡。

视觉要求：

- 全宽或接近全宽，左侧有命令标识和时间。
- 背景接近 editor prompt / terminal command，而不是聊天气泡。
- 长文本自然换行，不横向撑开。
- 不使用 `justify-end`、`max-w-[78%]` 这类 IM 气泡布局。

### Response Panel

Response panel 用于替代助手气泡。

视觉要求：

- 全宽文档式阅读区域。
- 更强的 markdown 阅读质量：标题、列表、代码块、表格、引用有清晰层级。
- 流式输出仍保留平滑显示，但表现为文档内容逐步生成。
- pending 状态显示为任务正在生成，而不是普通聊天 loading。

### Execution Trace

Execution trace 是主工作区的一部分，不只是右侧面板内容。

视觉要求：

- 以纵向 step rail 展示执行轮次。
- 每个 turn 有状态、标题、工具数量。
- 工具调用默认摘要展示，可展开预览。
- 点击 turn 或 tool call 时打开 inspector 并定位当前细节。

## Command Dock

Composer 改为 command dock，而不是普通 textarea。

必须包含：

- 任务输入区。
- 发送按钮。
- 运行中停止按钮。
- 当前模型简要显示或入口。
- 未配置 / 运行中 / 可发送状态提示。

视觉要求：

- 是整个页面的输入锚点。
- 更像开发工具命令栏，而不是聊天输入框。
- 与中心 task stream 对齐。
- 运行中有明确状态变化。

行为约束：

- 保留 Enter 发送、Shift+Enter 换行。
- 不改变 `POST /api/chat`、SSE、abort 等后端交互。
- 不增加复杂快捷键系统。

## Inspector

Inspector 是按需辅助区，不是默认第三栏。

### 打开条件

- `running === true` 且有当前 execution turn。
- 用户点击 execution turn。
- 用户点击 tool call。
- 当前任务错误或中断。

### 关闭条件

- 用户主动关闭。
- 切换会话。
- 当前无可展示执行细节，且不在运行中。

### 内容

Inspector 只展示高价值信息：

- 当前 step 标题、状态、summary。
- 工具调用列表。
- 选中工具的 args、result preview、status。
- 运行中停止入口。
- 错误时的错误文本和相关 step。

禁止把 inspector 填成普通状态概览卡片。

## 视觉方向

采用深色技术工作台路线，但不是纯黑装饰页。

关键词：

- Codex-like
- developer workbench
- dense
- calm
- precise
- command surface
- traceable execution

推荐色彩：

- 背景：深 slate / blue-black。
- 主面板：略亮于背景的深色 surface。
- 文本：高对比浅色。
- 辅助文本：低亮度 slate。
- Accent：绿色或青绿色，用于运行、active、focus，不大面积铺色。
- 代码块：深背景 + 明确边框。

如果保持浅色模式，则必须通过结构变化和强层级实现突破；不能只是浅色面板叠加。

本轮优先采用深色工作台，因为它能更明确地区分于旧浅色聊天页，也更符合 Codex / developer tool 的预期。

## AntD 使用策略

继续使用 AntD，但只用于合适的交互 primitive：

- `Layout`：页面骨架。
- `Splitter`：仅用于可选 inspector 或资源栏尺寸，不强行制造常驻三栏。
- `Drawer`：移动端 sidebar / inspector。
- `Button`、`Tooltip`、`Dropdown`：动作入口。
- `Select`：模型选择。
- `Tag`、`Badge`、`Alert`：状态表达。
- `Tabs` / `Segmented`：inspector 内细节切换，如果有必要。

不使用 AntD `Card` 堆叠页面结构。主工作台的 command / response / trace 使用自定义语义组件和 CSS。

## 文件设计

允许修改：

- `frontends/webui/src/App.tsx`
- `frontends/webui/src/components/chat/ChatHome.tsx`
- `frontends/webui/src/components/chat/ChatMessageView.tsx`
- `frontends/webui/src/components/composer/Composer.tsx`
- `frontends/webui/src/components/execution/InlineExecutionTurns.tsx`
- `frontends/webui/src/components/execution/InlineExecutionTurn.tsx`
- `frontends/webui/src/components/execution/ExecutionToolCallCard.tsx`
- `frontends/webui/src/components/context/*`
- `frontends/webui/src/components/shell/TopBar.tsx`
- `frontends/webui/src/components/sidebar/ConversationSidebar.tsx`
- `frontends/webui/src/state/*`
- `frontends/webui/src/styles/*`
- `frontends/webui/src/styles.css`
- `frontends/webui/src/theme.ts`
- `frontends/webui/tailwind.config.ts`
- `tests/*.test.mjs`

建议新增：

- `frontends/webui/src/state/task-stream-state.ts`
  - 把 `UiMessage[]` 投影为前端 task item。
  - 不修改后端数据结构。

- `frontends/webui/src/components/chat/TaskStream.tsx`
  - 负责渲染 task item 列表。

- `frontends/webui/src/components/chat/CommandBlock.tsx`
  - 负责用户 command 的工作台呈现。

- `frontends/webui/src/components/chat/ResponsePanel.tsx`
  - 负责助手 response 的文档式呈现。

- `frontends/webui/src/components/context/RunInspector.tsx`
  - 负责按需 inspector，不再是常驻低价值面板。

- `tests/webui_task_stream_state.test.mjs`
  - 验证 user / assistant message 到 task item 的投影规则。

禁止修改：

- `frontends/webui_server.py`
- GA core runtime
- 外部依赖项目
- subagent / run / artifact / checkpoint 后端契约

## 数据投影规则

前端 task stream 由现有 `UiMessage[]` 生成：

- user message 开启一个 task item。
- 紧随其后的 assistant message 归入同一个 task item。
- assistant-only legacy message 作为 system response item 展示。
- execution log 优先来自 assistant message 的 `executionLog`。
- 当前 streaming assistant 使用 live execution log。

这样可以重塑 UI，而不引入新后端实体。

## 硬验收标准

实现完成后必须满足：

1. 首屏和对话态不能再像普通聊天软件。
2. 用户输入不再以右侧气泡为主显示。
3. 助手输出不再以普通气泡为主显示。
4. 底部输入区必须是 command dock。
5. 执行过程必须在中心 task item 内形成可扫描 trace。
6. 右侧 inspector 不得在无信息价值时常驻显示。
7. Tailwind token、AntD token、自定义 CSS 必须同步改。
8. 不修改 WebUI 后端或 GA core。
9. 不新增 subagent / run / artifact / checkpoint 支撑。
10. 构建、前端状态测试、WebUI 后端回归测试必须通过。

## 静态测试标准

新增或更新静态测试，至少检查：

- `ChatMessageView.tsx` 不再包含 `justify-end` 用户气泡主结构。
- `ChatMessageView.tsx` 不再依赖 `ga-message-user` 作为用户主视觉。
- `TaskStream.tsx`、`CommandBlock.tsx`、`ResponsePanel.tsx` 存在并被使用。
- `Composer.tsx` 使用 command dock 类名。
- `RunInspector.tsx` 是按需渲染，不是无条件常驻状态面板。
- `tailwind.config.ts` 的 `app.*` token 与深色工作台方向一致。
- `frontends/webui_server.py` 没有被改动。

## 验证命令

必须通过：

```powershell
node --experimental-strip-types --test tests\execution_panel_state.test.mjs tests\chat_scroll_state.test.mjs tests\sidebar_selection.test.mjs tests\webui_inline_execution.test.mjs tests\webui_workbench_context_state.test.mjs tests\webui_workbench_static.test.mjs tests\webui_task_stream_state.test.mjs
py -3 -m unittest tests.test_webui_server -v
npm --prefix frontends/webui run build
git diff --check
```

如果某个测试文件尚未存在，实施计划必须先创建它。

## 成功判定

这次成功不是“测试通过”就算完成。测试通过只是底线。

真正成功的判定是：

- 视觉上能明显看出从聊天页变成 Agent 工作台。
- 中心区域成为任务流，而不是左右气泡。
- 执行过程和结果有明确结构。
- 右侧 inspector 只在有实际信息价值时出现。
- 主题变化作用到真实页面，而不是只作用到 AntD 控件。

如果页面打开后仍然主要像旧聊天页，本设计视为失败。
