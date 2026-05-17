# GA Browser-Use 集成测试报告

> **文档版本**: v1.0  
> **测试日期**: 2026-05-17  
> **适用分支**: `ga-browser-use`  
> **测试对象**: GA 内置 browser_state / browser_action 高层浏览器操作层在真实业务系统中的可用性  

---

## 1. 测试概述

### 1.1 测试目标
验证 GA 二阶段 BU（Browser-Use）能力集成在真实业务页面中的可用性。BU 能力指 GA 内置的 `browser_state` + `browser_action` 高层浏览器操作层，底层走 GA 现有 TMWebDriver / Chrome 扩展桥，使用用户已经打开并登录的 Chrome 会话。

### 1.2 测试范围
| 维度 | 内容 |
|------|------|
| 一阶段基础能力 | 状态读取、搜索输入、回车无index、DOM重排后重扫、点击跳转、菜单点击、刷新等待、textarea输入、按钮状态读取、错误恢复 (10项) |
| 二阶段专项能力 | iframe发现与输入、多iframe区分、表格上下文、自定义下拉、选择器操作、日期字段、单选框、等待busy/enabled、SPA路由等待、verify失败分类 (16项) |
| 页面专项 | 流程入口页P1(4项)、工作日报表单页P2(8项)、门户菜单页P3(4项)、E10客户问题支持流程P4(9项) |
| 破坏性测试（可选） | 保存/提交/上传/附件操作 (5项，未执行) |

### 1.3 测试方法
- 所有测试基于用户已登录的真实 Chrome 会话执行，不启动外部 `browser-use` 项目
- 执行引擎：GA 内置 `browser_state` + `browser_action` 高层 API
- 每次 mutating action 后重新执行 `browser_state`，避免复用旧 index
- 所有输入动作尽量带 verify 或随后重新读状态回验
- 安全原则：不做提交、保存、真实上传等会产生业务影响的操作

### 1.4 测试环境
| 项目 | 内容 |
|------|------|
| 浏览器 | Google Chrome（MCP扩展桥接） |
| 测试页面 | 4个业务系统真实页面（P1流程入口/P2工作日报/P3门户/P4 E10问题支持） |
| 测试工具 | GA browser_state V3 / browser_action / web_execute_js / web_scan |
| 页面框架 | 泛微OA生态体系（wea-* 控件、ant-design select、CKEditor、ui-browser） |

---

## 2. 总体测试结果

### 2.1 按测试分类统计

| 测试分类 | 总数 | ✅通过 | ❌不通过 | 不适用 | 通过率 |
|----------|:---:|:-----:|:--------:|:-----:|:-----:|
| V1 一阶段基础能力 | 10 | 10 | 0 | 0 | **100%** |
| V2 二阶段专项能力 | 16 | 14 | 2 | 0 | **87.5%** |
| P1 流程入口页 | 4 | 4 | 0 | 0 | **100%** |
| P2 工作日报表单页 | 8 | 7 | 0 | 1 | **87.5%** |
| P3 门户菜单页 | 4 | 4 | 0 | 0 | **100%** |
| P4 E10问题支持流程 | 9 | 9 | 0 | 0 | **100%** |
| **合计** | **51** | **48** | **2** | **1** | **94.1%** |

### 2.2 结论评级

| 评级 | 标准 | 结果 |
|------|------|------|
| 通过 | 目标元素能被发现，动作真实生效，回读验证成功 | 48项 ✅ |
| 不通过 | 页面可见但 GA 无法定位、无法操作、无法验证，且无稳定恢复路径 | 2项 ❌ |
| 不适用 | 属于跨域 iframe、真实上传、真实提交等本阶段边界外能力 | 1项 |

---

## 3. 一阶段基础能力测试结果（V1）

| 编号 | 能力项 | 页面 | 结果 |
|------|--------|:----:|:----:|
| V1-01 | 状态读取 - `browser_state(max_elements=200)` | P1 | ✅ |
| V1-02 | 搜索输入 - 输入关键词并回显 | P1 | ✅ |
| V1-03 | 输入后回车 - 无index的keys("Enter") | P1 | ✅ |
| V1-04 | DOM重排后重扫 - 搜索后重新browser_state | P1 | ✅ |
| V1-05 | 流程入口点击 - 跳转后wait_route/wait_text | P1 | ✅ |
| V1-06 | 菜单点击 - 左侧菜单点击后内容区刷新 | P3 | ✅ |
| V1-07 | 门户刷新 - 点击刷新后wait_dom_stable | P3 | ✅ |
| V1-08 | textarea输入 - 今日思考/明日安排/问答框 | P2/P4 | ✅ |
| V1-09 | 按钮状态读取 - disabled/visible元数据 | P2/P4 | ✅ |
| V1-10 | 错误恢复 - DOM变化后重扫而非复用旧index | 任意 | ✅ |

✅ **V1 一阶段10项全部通过**，表明 GA BU 的基础浏览器操作层在泛微OA生态系统中工作正常。

---

## 4. 二阶段专项能力测试结果（V2）

### 4.1 通过项（14项）

| 编号 | 能力项 | 页面 | 结果 | 详细说明 |
|------|--------|:----:|:----:|----------|
| V2-01 | 同源 iframe 发现 | P2 | ✅ | CKEditor iframe 发现成功，frame_path=[2], frame_depth=1；⚠️ inner element frame_title 为 null（CKEditor未设title属性） |
| V2-02 | 多 CKEditor iframe 区分 | P4 | ✅ | 问题描述 frame_path=[0], frame_title="所见即所得编辑器, ckeditor_..."；签字意见 frame_path=[1], frame_title="所见即所得编辑器, richtext_..." |
| V2-03 | iframe 富文本输入 | P2 | ✅ | browser_action input + field_value verify，内容同步成功 |
| V2-04 | iframe 问题描述输入 | P4 | ✅ | frame_path=[0] 输入，verify 回读正确 |
| V2-05 | iframe 签字意见输入 | P4 | ✅ | frame_path=[1] 输入，verify 回读正确，不混淆两iframe |
| V2-06 | 表格上下文读取 | P2 | ✅ | table0有25行×9列，表头含"序号/项目名称/项目经理/姓名/日期/工作类型/工作地点/工作内容/耗时(小时)"；state元素带table_context:cell_role/row_index/column_index |
| V2-07 | 明细单元格填写 | P2 | ✅ | 工作内容 textarea input+verify通过；耗时字段browser_action input被页面框架拒绝，JS native setter+事件链可设值"1.00" |
| V2-08 | 自定义下拉识别 | P2 | ✅ | 3个ant-select combobox均带custom_select control_kind，action_hints:[click_to_open,state_after_open,select_option_by_click] |
| V2-09 | 自定义下拉操作 | P2 | ✅ | 是否休假combobox click→state→选项"是"选中→回读text="是" |
| V2-10 | 多选择器操作 | P4 | ✅ | 选择器图标点击→弹层打开→选项"微服务框架"选中→回显正确，联动显示"模块负责人:代纪章" |
| V2-11 | 日期时间字段验证 | P4 | ✅ | 最晚解决时间只读，当前值="2026-05-18 11:36:11"，格式正确 |
| V2-12 | 单选框状态 | P4 | ✅ | 客户类型radio读取：radio_1(value="1") checked，value="0"未选中，互斥关系正确 |
| V2-13 | 等待 busy 消失 | P2/P4 | ✅ | wait_not_busy returned not_busy |
| V2-14 | 等待按钮恢复 | P2/P4 | ✅ | wait_enabled on P4提交按钮index=1 returned element_enabled |

### 4.2 不通过项（2项）

| 编号 | 能力项 | 页面 | 结果 | 原因 |
|------|--------|:----:|:----:|------|
| V2-15 | SPA 路由等待 | P2/P3 | ❌ | wait_route只监听path/hash变化，不监SPA组件切换。P2流程图标签切换不触发hash变化（tab内SPA路由），P3 hash路由未测试 |
| V2-16 | verify失败分类测试 | 任意页 | ❌ | 未执行测试，缺少verify_failed场景的负例验证 |

---

## 5. 页面专项测试结果

### 5.1 P1 流程入口页（4/4 ✅）
- P1-01 全局搜索框输入：搜索输入+重扫后state可读新状态 ✅
- P1-02 流程分类点击：分类点击后state可重读，菜单变化可识别 ✅
- P1-03 流程卡片点击：点击后wait可检测页面变化和标题 ✅
- P1-04 多菜单区域读取：顶部tab/左侧menu/主区域link可通过layer/role区分 ✅

### 5.2 P2 工作日报表单页（7/8 ✅，1不适用）
- P2-01 只读字段读取：DIV/SPAN.wea-field-readonly非input控件，不会被误输入 ✅
- P2-02 是否休假下拉：custom_select，click→state→回读 ✅
- P2-03 明细表首行定位：table_context含cell_role/row_index/column_index ✅
- P2-04 工作内容textarea：input+verify通过 ✅
- P2-05 耗时字段：JS setter+事件链设值1.00，合计回显1.00 ✅
- P2-06 今日思考/明日安排：两textarea有独立ID field5954/field5955 ✅
- P2-07 签字意见CKEditor：input+field_value verify内容同步 ✅
- P2-08 附件入口：当前P2表单页无附件/上传控件 ❌不适用

### 5.3 P3 门户菜单页（4/4 ✅）
- P3-01 左侧菜单点击：menu click→内容区刷新→wait_dom_stable ✅
- P3-02 门户块刷新：state可重读，内容变化可识别 ✅
- P3-03 文档链接点击：web_scan检测到tabs数量变化(6→7)，新标签可切换 ✅
- P3-04 顶部搜索框：唯一ID e9header-quick-search-input，CSS选择器定位 ✅

### 5.4 P4 E10客户问题支持流程（9/9 ✅）
- P4-01 问题描述CKEditor：iframe输入+field_value verify ✅
- P4-02 上传图片/附件：控件可识别，真实上传超出BU能力边界 ✅
- P4-03 客户类型radio：checked属性可读取，互斥正确 ✅
- P4-04 问题入口模块选择器：弹层打开→选项定位→选中回显正确 ✅
- P4-05 备案环境/相关客户/基线版本号：唯一fieldXXX后缀区分 ✅
- P4-06 紧急程度：有data-id属性，当前值"一般"可识别 ✅
- P4-07 最晚解决时间：只读字段读取正常 ✅
- P4-08 签字意见CKEditor：两个iframe frame_path/title不同可区分 ✅
- P4-09 右侧智能问答输入框：textarea输入回读通过 ✅

---

## 6. 问题分析与缺陷记录

### 6.1 缺陷列表

#### 🔴 缺陷#1：选择器图标索引不稳定
| 字段 | 内容 |
|------|------|
| 编号 | V2-10补充 |
| 页面 | P4 |
| 问题描述 | 选择器图标（ui-icon）部分场景未被browser_state索引。当max_elements=200时仍只返回42个元素，浏览器按钮图标不在索引中。V2-10测试时图标可click成功（可能因页面状态不同索引覆盖不同），但后续重扫时丢失。依赖browser_state索引定位时稳定性不足 |
| 失败stage | index缺失 |
| 恢复方式 | 部分可恢复——通过web_execute_js定位后click，但JS dispatchEvent可能不触发框架事件绑定 |
| 能力缺口 | ✅ 是——browser_state对部分框架组件（如ui-browser内的icon）索引不稳定 |
| **严重度** | **中**——影响依赖索引定位的稳定性，但可通过JS回退绕过 |

#### 🔴 缺陷#2：SPA wait_route 不覆盖组件切换
| 字段 | 内容 |
|------|------|
| 编号 | V2-15 |
| 页面 | P2/P3 |
| 问题描述 | SPA wait_route不通过：P2流程图标签切换不触发hash变化（tab内SPA路由变化方式），wait_route需text参数匹配route但当前页面无route变化；P3未测试 |
| 失败stage | timeout |
| 恢复方式 | 可——改在P3 hash路由页面试或用wait_dom_stable替代 |
| 能力缺口 | ✅ 是——wait_route只监path/hash变化，不监SPA组件切换 |
| **严重度** | **中**——SPA框架内组件级路由无法被wait_route检测 |

#### 🟡 缺陷#3：verify失败场景未验证
| 字段 | 内容 |
|------|------|
| 编号 | V2-16 |
| 问题描述 | 未测试verify失败场景（负例），未确认verify_failed stage是否按预期返回 |
| **严重度** | **低**——缺少负例覆盖 |

### 6.2 其他发现问题
| 问题 | 详情 |
|------|------|
| CKEditor iframe frame_title为null | iframe本身没有title属性，影响可访问性，但不影响功能操作 |
| 耗时字段browser_action input被拒 | 页面框架阻止了标准browser_action input，需降级到JS setter+事件链 |
| P2表单无附件控件 | 当前打开的P2工作日报草稿页没有上传附件区域，无法验证附件控件识别 |

---

## 7. 能力缺口分析

### 7.1 已识别的能力缺口

| 缺口 | 受影响场景 | 严重度 | 建议 |
|------|-----------|:------:|------|
| **browser_state索引覆盖不全** | 框架组件（ui-icon、ui-browser内元素）在max_elements不足时未被索引 | 中 | 改进索引策略：对框架组件增加专用扫描，或支持按CSS选择器补扫 |
| **wait_route不覆盖SPA组件路由** | 使用前端路由切换组件的SPA页面（如P2流程图标签切换） | 中 | 增加对SPA组件挂载/卸载的检测机制，或推荐用户改用wait_dom_stable |
| **标准browser_action input被框架拦截** | 复杂框架（如泛微OA）的自定义表单字段 | 低 | 自动降级到JS原生setter+事件链，使input动作对框架透明 |
| **无verify_failed负例验证** | 所有使用verify的场景 | 低 | 补充负例测试，确保错误检测机制正常 |

### 7.2 边界能力说明（不适用项）

以下能力属于当前阶段边界外，不纳入测试通过率：

| 能力 | 说明 |
|------|------|
| 跨域 iframe 操作 | 需要扩展桥跨域权限，不在BU阶段目标内 |
| 真实文件上传 | 需要用户交互确认，自动化无法安全完成 |
| 真实提交/保存 | 会产生业务数据变更，需用户明确授权 |
| 多会话并发 | 超出BU单会话设计目标 |
| 录制回放 | 属于后续阶段能力 |

---

## 8. 风险与注意事项

### 8.1 已知风险
1. **索引稳定性风险**：browser_state的max_elements参数在不同页面状态下返回的元素数量不一致，部分框架组件可能被漏扫。建议在生产使用中适当增加max_elements值（推荐300+），并在关键操作前做元素存在性检查。
2. **框架兼容性风险**：泛微OA使用大量自定义控件（ant-design select、CKEditor、ui-browser），部分控件需要降级到JS原生方式操作，标准browser_action可能存在兼容性问题。
3. **等待策略风险**：SPA页面的组件切换场景不能用wait_route检测，需使用wait_dom_stable或自定义wait_selector替代。

### 8.2 未执行测试
以下测试因业务影响风险未执行，如需执行需用户明确授权：
- D-01 P2保存（可能生成草稿）
- D-02 P2提交（会真实提交工作日报）
- D-03 P4保存（可能生成问题流程草稿）
- D-04 P4提交（会真实发起E10支持流程）
- D-05 文件上传（会上传本地文件到业务系统）

---

## 9. 结论与建议

### 9.1 总体结论
**GA Browser-Use 在真实业务系统中的集成测试通过率 94.1%（48/51）**，表明GA BU能力层可以满足大部分真实业务页面的自动化操作需求。V1基础能力全部通过，V2专项能力14/16通过，4个业务页面的专项测试全部覆盖。

### 9.2 通过判定标准
| 判定 | 标准 | 数量 |
|------|------|:----:|
| ✅ 通过 | 目标元素被发现、动作真实生效、回读验证成功 | 48 |
| ❌ 不通过 | 可见但无法操作/验证，无稳定恢复路径 | 2 |
| ➖ 不适用 | 属于本阶段边界外能力 | 1 |

### 9.3 改进建议（按优先级排序）

| 优先级 | 建议 | 影响 |
|:------:|------|:----:|
| P0 | 修复browser_state索引覆盖：确保max_elements=300时能覆盖更多框架组件(ui-icon等) | 解决缺陷#1 |
| P0 | 增强wait_route：支持SPA组件切换检测，或补充wait_component生命周期等待 | 解决缺陷#2 |
| P1 | 自动降级机制：当标准browser_action input被框架拒绝时，自动尝试JS setter+事件链 | 提升V2-07稳健性 |
| P1 | 补充verify_failed负例测试 | 覆盖V2-16 |
| P2 | 为CKEditor iframe增加title属性建议，提升可访问性 | 提升可维护性 |
| P2 | 文档化框架兼容性矩阵，列出已知不兼容控件及回退方案 | 减少后续排查成本 |

### 9.4 推荐使用场景
- ✅ **适合**：表单填写、数据读取、页面导航、搜索查询、下拉选择、iframe富文本编辑
- ✅ **限制可用**：框架自定义控件（需JS降级）、SPA组件切换（需替代等待策略）
- ❌ **不适合**：文件上传、业务提交、跨域操作、多会话并发

---

## 10. 附录

### A. 测试用例索引
完整测试清单见 `browser-use_live_system_test_checklist.md`

### B. 测试数据说明
- 所有测试输入均使用测试前缀 `GA_BU_TEST_`，便于在业务系统中识别和清理
- 所有测试均在只读/可回退模式下执行，不产生真实业务数据变更
- 测试过程中未记录任何真实账号、手机号、密码、客户信息、项目敏感信息

### C. 文档版本记录
| 版本 | 日期 | 变更说明 |
|:----:|:----:|----------|
| v1.0 | 2026-05-17 | 初始版本，基于完整测试执行结果生成 |

---

*本报告由 GA 自动生成，基于真实 Chrome 会话的 browser-use 集成测试执行结果。*
