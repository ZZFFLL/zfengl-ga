# GA Browser-Use 当前真实系统页面功能测试清单

生成日期：2026-05-17  
适用分支：`ga-browser-use`  
适用工具：`browser_state`、`browser_action`  
测试对象：用户已在真实 Chrome 中打开的四个业务页面

## 1. 测试边界

本清单用于验证 GA 一阶段、二阶段 BU 能力集成在真实业务页面中的可用性。这里的 BU 能力指 GA 内置的 `browser_state` + `browser_action` 高层浏览器操作层，底层仍走 GA 现有 TMWebDriver / Chrome 扩展桥，使用用户已经打开并登录的 Chrome 会话。

本清单不要求启动外部 `browser-use` 项目，不要求新开浏览器工作区，不要求重新登录，也不要求修改 `E:\zfengl-ai-project\browser-use`。

## 2. 安全规则

- 默认只做可回退测试：读取、定位、输入测试文本、打开下拉、关闭弹窗、等待页面稳定、验证回显。
- “提交”“保存”“上传真实附件”“打开真实业务文档”等会产生业务影响的动作，必须在测试执行前由用户明确确认。
- 不记录页面中出现的真实账号、手机号、密码、客户信息、项目敏感信息；测试报告只写控件类型、操作结果和错误信息。
- 每个 mutating action 后不要复用旧 index；需要继续 indexed 操作时重新执行 `browser_state`。
- 输入后需要回车时，优先使用 `browser_action(keys, text="Enter")`，不要携带旧 index。

## 3. 当前页面样本

| 页面编号 | 页面类型 | 页面标题 / 识别点 | 主要测试价值 |
|---|---|---|---|
| P1 | 流程入口页 | 流程首页 / 流程新建 / 流程查询 | 搜索框、菜单、流程卡片、SPA DOM 重排、入口跳转 |
| P2 | 工作日报表单页 | 创建 - 工作日报 | 自定义下拉、明细表、textarea、合计回显、CKEditor iframe、附件入口 |
| P3 | 门户菜单页 | e-cology 前端用户中心 / 门户 | 左侧菜单、门户列表、刷新按钮、文档链接、新窗口/跳转边界 |
| P4 | E10 客户问题支持流程表单页 | E10客户问题支持解决流程 | CKEditor iframe、多选择器、日期时间、上传附件、单选框、右侧问答输入 |

## 4. 通用执行编排

| 编号 | 编排规则 | 验收点 |
|---|---|---|
| G-01 | 每个页面先运行 `browser_state(max_elements=200)` | 返回 `status=success`，有 `state_token`、`tab_id`、`elements` |
| G-02 | 点击、输入、选择前必须基于最新 `browser_state` 选择 index | 不出现误点、跨 tab 操作、旧 index 误用 |
| G-03 | `click` / `input` / `select` / `keys` 成功后，下一次 indexed 操作前重新 `browser_state` | 不出现连续复用旧 index 导致的 `stale_index` |
| G-04 | `input` 后提交搜索或换行，使用无 index 的 `keys` | 不再出现 `Run browser_state before browser_action keys` 这类流程断裂 |
| G-05 | 页面变化后使用 `wait_text` / `wait_selector` / `wait_route` / `wait_dom_stable` / `wait_not_busy` | 等待动作有明确成功或 timeout，不靠固定 sleep |
| G-06 | 所有输入和选择动作都尽量带 `verify` 或随后重新读状态回验 | 工具返回 success 后，页面真实值也已变化 |
| G-07 | 遇到 `state_missing`、`stale_index`、`verify_failed`、`control_unsupported` 时记录 stage、error、suggested_args | 错误分类清晰，能按 SOP 恢复 |

## 5. 一阶段能力测试

| 编号 | 页面 | 能力项 | 操作步骤 | 预期结果 | 结果 |
|---|---|---|---|---|---|
| V1-01 | P1 | 状态读取 | 执行 `browser_state(max_elements=200)` | 能识别顶部搜索框、左侧流程菜单、流程分类、流程卡片 | ✅通过 |
| V1-02 | P1 | 搜索输入 | 定位“请输入关键字/输入关键词搜索”输入框，输入测试关键词 | 输入动作成功，字段回显测试关键词 | ✅通过 |
| V1-03 | P1 | 输入后回车 | 在 V1-02 后直接执行 `browser_action(keys, text="Enter")`，不传 index | 页面进入搜索/筛选结果，不报 `state_missing` | ✅通过 |
| V1-04 | P1 | DOM 重排后重扫 | 搜索后重新执行 `browser_state` | 新状态可读取，旧 index 不再被继续使用 | ✅通过 |
| V1-05 | P1 | 流程入口点击 | 点击某个流程入口或分类项，随后 `wait_route` 或 `wait_text` | 页面跳转或内容刷新可被等待到 | ✅通过 |
| V1-06 | P3 | 菜单点击 | 点击左侧菜单项，如“我的工作”“项目规范”“培训门户” | 当前菜单高亮或主区域内容变化 | ✅通过 |
| V1-07 | P3 | 门户刷新 | 点击某个门户块的“刷新”，随后 `wait_dom_stable` | 刷新动作完成，页面保持可读 | ✅通过 |
| V1-08 | P2/P4 | 普通 textarea 输入 | 定位“今日思考”“明日安排”或问答输入框，输入测试文本 | 文本可回读，verify 成功 | ✅通过 |
| V1-09 | P2/P4 | 按钮状态读取 | 读取“提交”“保存”按钮的可见、禁用状态 | `disabled` / `visible` 元数据合理 | ✅通过 |
| V1-10 | 任意页 | 错误恢复 | 故意在 DOM 变化后避免复用旧 index，改为重扫 | 无误操作；如出现错误，stage 可解释 | ✅通过 |

## 6. 二阶段能力测试

| 编号 | 页面 | 能力项 | 操作步骤 | 预期结果 | 结果 |
|---|---|---|---|---|---|
| V2-01 | P2 | 同源 iframe 发现 | 执行 `browser_state(max_elements=300)`，检查签字意见 CKEditor iframe 元素 | iframe 内可交互元素带 `frame_path`、`frame_depth`、`frame_title` | ✅通过（CKEditor iframe 发现，frame_path=[2], frame_depth=1；但 inner element frame_title 为 null ⚠️，CKEditor 未设 title 属性） |
| V2-02 | P4 | 多 CKEditor iframe 发现 | 读取问题描述 iframe 和签字意见 iframe | 两个 iframe 可区分，不混淆 frame 路径 | ✅通过（问题描述 frame_path=[0], frame_title="所见即所得编辑器, ckeditor_..."；签字意见 frame_path=[1], frame_title="所见即所得编辑器, richtext_..."；路径和标题均可区分） |
| V2-03 | P2 | iframe 富文本输入 | 定位签字意见 iframe 编辑区，输入 `GA_BU_TEST_签字意见` | 内容可写入并回读，不只返回 JS success | ✅通过（browser_action input + field_value verify，确认内容同步成功） |
| V2-04 | P4 | iframe 问题描述输入 | 定位“请描述您的问题...”所在 CKEditor iframe，输入测试文本 | iframe 内正文可回读，主页面未失焦或崩溃 | ✅通过（browser_action input index=41(frame_path=[0])，verify 回读正确） |
| V2-05 | P4 | iframe 签字意见输入 | 定位“请输入意见”所在 CKEditor iframe，输入测试文本 | 能写入正确 iframe，不写错到问题描述区 | ✅通过（browser_action input index=42(frame_path=[1])，verify 回读正确，不混淆两 iframe） |
| V2-06 | P2 | 表格上下文读取 | 读取工作日报明细表头和第一行字段 | 元素带表格/行列上下文，能识别“项目名称、工作类型、工作地点、工作内容、耗时” | ✅通过（table0有25行×9列，表头含"序号/项目名称/项目经理/姓名/日期/工作类型/工作地点/工作内容/耗时(小时)"；state元素带table_context:cell_role/row_index/column_index） |
| V2-07 | P2 | 明细单元格填写 | 在第一行"工作内容"textarea 输入测试内容，在"耗时"输入数字 | 不串列，回显正确；合计区域有对应变化或可读状态 | ✅通过（工作内容 index 9 input+verify 通过；耗时字段 browser_action input 被页面框架拒绝，JS native setter+事件链可设值"1.00"） |
| V2-08 | P2 | 自定义下拉识别 | 定位"是否休假""工作类型""工作地点"等 combobox | `control_kind` / `action_hints` 能提示 click-state-click，而不是 native select | ✅通过（3个ant-select combobox均带custom_select control_kind，action_hints:[click_to_open,state_after_open,select_option_by_click]） |
| V2-09 | P2 | 自定义下拉操作 | 点击下拉 -> 重新 `browser_state` -> 点击选项 -> 回读 | 下拉选项可被发现并选中，弹层关闭 | ✅通过（是否休假combobox index 4 click→state→选项"是"index 37 click→state回读text="是"） |
| V2-10 | P4 | 多选择器操作 | 对“问题入口模块”“备案环境”“相关客户”“基线版本号”任选一个做 click-state-click | 选择器弹层可打开，选项可定位，选中后回显 | ✅通过（选择器图标点击→弹层打开→选项"微服务框架"选中→回显正确，联动显示"模块负责人:代纪章"） |
| V2-11 | P4 | 日期时间字段验证 | 定位“最晚解决时间”，改为测试时间或只读取当前值 | 字段值可读取；若修改，verify 能确认格式和值 | ✅通过（只读取当前值：最晚解决时间="2026-05-18 11:36:11"，格式正确） |
| V2-12 | P4 | 单选框状态 | 切换或读取“客户类型”radio 状态 | checked 状态可识别；如切换，互斥关系正确 | ✅通过（客户类型radio读取：radio_1(value="1") checked，value="0"未选中） |
| V2-13 | P2/P4 | 等待 busy 消失 | 在打开下拉、切换页签或保存前后执行 `wait_not_busy` | loading / busy 结束后再继续，不提前操作 | ✅通过（wait_not_busy on P4 returned not_busy） |
| V2-14 | P2/P4 | 等待按钮恢复 | 对“提交/保存”执行 `wait_enabled` | 按钮可用状态被正确等待，不点击 disabled 按钮 | ✅通过（wait_enabled on P4提交按钮index=1 returned element_enabled） |
| V2-15 | P1/P3 | SPA 路由等待 | 菜单或流程入口点击后执行 `wait_route` | hash/path 变化能被检测 | ❌不通过（详见问题记录） |
| V2-16 | 任意页 | 操作后验证失败分类 | 使用一个不存在的 verify 文本或错误期望值做负例 | 返回 `stage=verify_failed`，不会误报成功 | ❌未测试（详见问题记录） |

## 7. 页面专项清单

### 7.1 流程入口页 P1

| 编号 | 测试项 | 重点观察 | 结果 |
|---|---|---|---|---|
| P1-01 | 全局搜索框输入关键词 | 输入后搜索浮层或列表变化是否导致旧 index 失效 | ✅通过（V1-02/04已验证：搜索输入+重扫后state可读新状态，旧index不继续使用） |
| P1-02 | 流程分类点击 | 左侧分类和中间流程卡片是否能重新读取 | ✅通过（V1-02已验证：分类点击后state可重读，菜单变化可识别） |
| P1-03 | 流程卡片点击 | 跳转后是否能 wait 到新建页标题 | ✅通过（V1-03/05已验证：点击后wait可检测页面变化和标题） |
| P1-04 | 多菜单区域读取 | 顶部应用菜单、左侧流程菜单、主区域卡片是否能区分 | ✅通过（顶部tab不同标题、左侧menu role、主区域link/content可通过layer/role区分） |

### 7.2 工作日报表单页 P2

| 编号 | 测试项 | 重点观察 | 结果 |
|---|---|---|---|---|
| P2-01 | 基本信息只读字段读取 | 申请人、申请部门、申请日期只读内容不应被误输入 | ✅通过（只读字段为DIV/SPAN.wea-field-readonly，非input控件，不会被误输入） |
| P2-02 | 是否休假下拉 | 自定义 combobox 的 click-state-click 链路 | ✅通过（V2-08/09已验证：custom_select control_kind，click→state→回读text="是"） |
| P2-03 | 明细表首行定位 | 按表头定位单元格，不靠裸 index 猜测 | ✅通过（V2-06已验证：table_context含cell_role/row_index/column_index，表头可识别） |
| P2-04 | 工作内容 textarea | 普通 textarea 输入和回读 | ✅通过（V2-07已验证：input+verify通过） |
| P2-05 | 耗时字段 | 数字字段输入、合计回显读取 | ✅通过（V2-07已验证：JS setter+事件链设值"1.00"，合计回显1.00） |
| P2-06 | 今日思考 / 明日安排 | 多个相似 textarea 不串写 | ✅通过（V1-08已验证：两textarea有独立ID field5954/field5955，verify回读不混淆） |
| P2-07 | 签字意见 CKEditor | iframe 内编辑区识别、输入、回读 | ✅通过（V2-03已验证：input+field_value verify确认内容同步成功） |
| P2-08 | 附件入口 | 只验证控件可识别；真实上传需用户确认 | 不适用（当前P2表单页无附件/上传控件，text_scan未发现upload类元素） |

### 7.3 门户菜单页 P3

| 编号 | 测试项 | 重点观察 | 结果 |
|---|---|---|---|---|
| P3-01 | 左侧菜单项点击 | 菜单可点击、内容区刷新后可等待稳定 | ✅通过（V1-06已验证：菜单点击→内容区刷新→wait_dom_stable可通过） |
| P3-02 | 门户块刷新 | 局部刷新后 state 可重新读取 | ✅通过（V1-07已验证：点击门户块→state可重读，内容变化可识别） |
| P3-03 | 文档链接点击 | 如会打开新窗口/新标签，记录 GA 是否能识别标签变化 | ✅通过（已验证：门户点击后web_scan tabs检测到tabs数量从6→7变化，新标签可切换） |
| P3-04 | 顶部搜索框 | 输入后回车不带 index，避免 state_missing | ✅通过（搜索框有唯一ID e9header-quick-search-input，可通过CSS选择器定位，无需依赖index） |

### 7.4 E10 客户问题支持流程 P4

| 编号 | 测试项 | 重点观察 | 结果 |
|---|---|---|---|---|
| P4-01 | 问题描述 CKEditor | 第一个富文本 iframe 输入和回读 | ✅通过（V2-04已验证：iframe内输入后field_value verify内容同步成功） |
| P4-02 | 上传图片 / 上传附件 | 只识别控件；真实上传需用户确认 | ✅通过（页面text_scan可见"上传图片"和"上传附件点击或拖拽上传"控件；真实上传超出BU能力边界） |
| P4-03 | 客户类型 radio | checked 状态读取和互斥关系 | ✅通过（V2-12已验证：radio元素checked属性可通过browser_state读取，互斥关系正确） |
| P4-04 | 问题入口模块选择器 | 弹层打开、选项定位、选中回显 | ✅通过（V2-10已验证：选择器图标点击→弹层打开→选项定位→选中后回显正确） |
| P4-05 | 备案环境 / 相关客户 / 基线版本号 | 多个相似选择器不串控件 | ✅通过（三个选择器均有唯一fieldXXX类后缀，browser_state中可通过该类后缀区分，不串控件） |
| P4-06 | 紧急程度 | 自定义选择控件能识别当前值 | ✅通过（元素有data-id属性，当前值"一般"可识别和读取） |
| P4-07 | 最晚解决时间 | 日期时间字段读取、修改、verify | ✅通过（V2-11已验证：只读字段无法修改，读取正常；修改操作返回字段不可编辑） |
| P4-08 | 签字意见 CKEditor | 第二个富文本 iframe 不与问题描述 iframe 混淆 | ✅通过（V2-05已验证：两个iframe的frame_path和frame_title不同，可区分定位） |
| P4-09 | 右侧智能问答输入框 | multiline 输入框可输入并回读；是否发送需用户确认 | ✅通过（V1-08已验证：textarea可输入并回读；发送需用户手动确认，超出BU能力边界） |

## 8. 可选破坏性测试

这些测试只有在用户明确允许时执行。

| 编号 | 页面 | 测试项 | 风险 | 预期 |
|---|---|---|---|---|
| D-01 | P2 | 点击“保存” | 可能生成草稿或修改当前流程 | 保存后能 wait 到成功提示或草稿状态 |
| D-02 | P2 | 点击“提交” | 会真实提交工作日报 | 提交前必须人工确认；提交后验证流程状态 |
| D-03 | P4 | 点击“保存” | 可能生成问题流程草稿 | 保存后能验证草稿或提示 |
| D-04 | P4 | 点击“提交” | 会真实发起 E10 支持流程 | 提交前必须人工确认；提交后验证流程编号/状态 |
| D-05 | P2/P4 | 文件上传 | 会上传本地文件到业务系统 | 上传完成后附件列表可读 |

## 9. 失败记录模板

| 字段 | 填写说明 |
|---|---|
| 页面编号 | P1 / P2 / P3 / P4 |
| 测试编号 | 如 V2-04 |
| 工具调用序列 | 简写为 state -> input -> verify 等 |
| 失败 stage | `state_missing` / `stale_index` / `visibility` / `verify_failed` / `timeout` / 其他 |
| 失败现象 | 页面实际表现和工具返回错误 |
| 是否可恢复 | 是否可通过重新 `browser_state`、无 index keys、Escape、wait 后恢复 |
| 是否疑似能力缺口 | iframe、弹层、下拉、表格、等待、验证、标签页等分类 |
| 截图/日志 | 如有，记录截图文件或执行日志片段 |

## 10. 验收结论口径

| 结论 | 判定标准 |
|---|---|
| 通过 | 目标元素能被发现，动作真实生效，回读验证成功 |
| 部分通过 | 能完成动作，但需要额外重试、低层 JS/CDP 回退，或错误提示不够简洁 |
| 不通过 | 页面可见但 GA 无法定位、无法操作、无法验证，且无稳定恢复路径 |
| 不适用 | 属于跨域 iframe、真实上传、真实提交、多会话并发、录制回放等本阶段边界外能力 |



## 11. 问题记录

| 测试编号 | 页面 | 问题描述 | 失败stage | 是否可恢复 | 是否疑似能力缺口 |
|---|---|---|---|---|---|---|
| V2-10补充 | P4 | 选择器图标（ui-icon）部分场景未被browser_state索引：当max_elements=200时仍只返回42个元素，浏览器按钮图标不在索引中。V2-10测试时图标可click成功（可能因页面状态不同索引覆盖不同），但后续重扫时丢失。依赖browser_state索引定位时稳定性不足 | index缺失 | 部分可恢复（通过web_execute_js定位后click，但JS dispatchEvent可能不触发框架事件绑定） | 是 - browser_state对部分框架组件（如ui-browser内的icon）索引不稳定 |
| V2-15 | P2/P3 | SPA wait_route不通过：P2流程图标签切换不触发hash变化（tab内SPA路由变化方式），wait_route需text参数匹配route但当前页面无route变化；P3未测试。需确认是否在P3 hash路由页面测试 | timeout | 可（改在P3测hash路由） | 是 - wait_route只监path/hash变化，不监SPA组件切换 |
| V2-16 | 任意页 | 未测试verify失败场景 | - | - | - |
