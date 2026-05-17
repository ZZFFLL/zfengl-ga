# GA Browser Structured Tool Optimization Design

## Goal

本设计针对真实日报测试暴露出的 `browser_*` 问题做一轮小步优化，让 `browser_state` / `browser_find` / `browser_action` / `browser_recipe` 在常见企业表单页面中更少撞墙。

目标不是替代 `web_execute_js`，也不是把 `browser_*` 扩成万能浏览器代理。`web_execute_js` 仍然是平级低层轨道，适合框架 API 探测、复杂 DOM 读取、CDP 和特殊操作。本轮只增强 `browser_*` 自己应该承担的结构化定位、固定 recipe 和失败引导能力。

## Evidence From Real Test

来自 `temp/model_responses/model_responses_590168.txt` 的真实调用情况：

- `web_execute_js`: 24 次
- `web_scan`: 8 次
- `browser_state`: 8 次
- `browser_find`: 6 次
- `browser_action`: 4 次
- `browser_recipe`: 0 次

这说明当前问题不是“没有浏览器工具”，而是：

- `browser_find` 对 OA 表单字段定位命中率低。
- `browser_recipe` 虽然存在，但模型没有被足够强地引导使用。
- `browser_action` 遇到零尺寸 wrapper / 自定义组件时 recovery 不够可执行。
- `browser_state` 输出元素，但字段级上下文还不够稳定。

## Hard Constraints

- 不修改 `E:\zfengl-ai-project\browser-use`。
- 不改变 GA 只接管用户已打开 Chrome 的前提。
- 不调整 `web_execute_js` 与 `browser_*` 的平级关系。
- 不新增业务专用 OA recipe。
- 不支持任意 selector click/input。
- 不做跨域 iframe、文件上传、截图日志、录制回放、多页面并发会话。
- 不做“大而全组件库适配层”。
- 所有新增能力必须能用单元测试或现有 browser fixture 证明。

## Current Implementation Findings

### `browser_state`

现有 `ga_browser_use/indexer.py` 已输出：

- `labels`
- `field_context`
- `table_context`
- `layer`
- `control_kind`
- `action_hints`
- `frame_path`

但实际不足：

- `finder.py` 已读取 `field_context.nearby_text`，但 `indexer.py` 没有产出 `nearby_text`。
- 企业表单常见结构是“字段名在左侧 `td`，控件在右侧 `td`”，控件自身没有 label。
- `table_context.row_text` 经常包含整行文本，但 `browser_find(query="是否休假")` 不会把“相邻字段名单元格”作为强标签。
- 自定义控件的可点击入口、放大镜按钮和真实字段归属没有稳定联系。

### `browser_find`

现有 `finder.py` 是可控的只读定位器，要求 `query` 或 `table`。这个边界正确，应保留。

不足：

- scoring 主要匹配元素自身 `text/value/labels/field_context.labels`。
- 对相邻 label、同一表格行中的字段名、字段 mark/id/name 的权重不足。
- `target_not_found` recovery 默认建议 refresh 后重试同一 locator；真实场景里这会诱导模型重复撞墙。

### `browser_action`

现有 `browser_action` 已有 stale-index、state_missing、verify_failed、repeat_blocked 等保护。

不足：

- 对自定义 select 的 `select` 误用可以建议 `browser_recipe(custom_select)`，但对 `click` 点到零尺寸 wrapper 的恢复不够具体。
- 对 `control_kind=custom_select` 的点击成功后，只告诉页面变化，不能直接引导“下一步用 state/find 找 option 或用 recipe”。
- 对同一目标重复失败的 `repeat_blocked` 只说 stop retry，没有给出更强的策略分叉。

### `browser_recipe`

现有 `browser_recipe` 支持：

- `custom_select`
- `layer_select`
- `table_locate`
- `component_wait`

边界正确，不应扩成自由规划器。

不足：

- 它依赖模型主动调用；真实流程中调用次数为 0。
- `custom_select` 对 `target.index` 的验证天然受限，因为刷新 state 后 index 会变，当前失败闭环偏保守。
- 没有形成“从 `browser_state` 元数据到 recipe 参数”的明显提示链路。

## Design Principles

1. 增强字段上下文，不写业务语义。
   - 只识别通用 DOM 结构，例如表格左右相邻单元格、同一行字段名、控件 id/name、按钮所在字段容器。

2. 强化 recovery，不改变优先级。
   - `browser_*` 失败时更明确地提示下一步，但不要求模型必须放弃 `web_execute_js`。

3. 让 recipe 可发现，不让 recipe 自由规划。
   - 通过 `recipe_hint` / `action_hints` / recovery 给出可执行参数。
   - recipe 仍只接受固定 enum 和 bounded target。

4. 保持 fail closed。
   - 多个 dropdown 残留、多个候选、无法确认回填时，返回 ambiguity 或 component_not_ready，不默认选第一个。

5. 优先减少真实撞墙，不追求通吃。
   - 只覆盖常见企业表单和 AntD/wea-select 模式，不追求所有 React 动态网页。

## Proposed Changes

### 1. Field Context V2

在 `browser_state` 的元素快照中补充有限字段上下文。

新增或稳定字段：

```json
{
  "field_context": {
    "labels": [],
    "nearby_text": "是否休假",
    "row_label": "是否休假",
    "previous_cell_text": "是否休假",
    "next_cell_text": "",
    "field_id": "field5956",
    "field_name": "sfxj",
    "field_container_hint": "td"
  }
}
```

提取规则：

- 若元素在 `td/th/gridcell` 中，读取同一行左侧最近的非空单元格文本作为 `previous_cell_text`。
- 若左侧文本明显像字段名，写入 `row_label` 和 `nearby_text`。
- 若元素或祖先节点存在 `id/name` 命中 `field\d+(_\d+)?`，写入 `field_id`。
- 若元素在 `.wea-field`、`.wea-browser`、`.wea-select`、`.ant-select`、`.ant-picker` 容器内，读取容器附近的表格 label。
- 不扫描全 DOM，不跨业务规则，不猜字段含义。

收益：

- `browser_find(query="是否休假", control_kind="custom_select")` 可命中右侧 combobox。
- `browser_find(query="工作类型", control_kind="custom_select")` 可命中明细表内的 custom select。
- 放大镜按钮可以获得所属字段上下文，减少“点外壳 rect=0”。

### 2. Finder Scoring V2

增强 `browser_find` scoring，但仍要求 `query` 或 `table`。

评分调整：

- exact `labels` match：保持最高权重。
- `field_context.row_label` / `previous_cell_text` exact match：新增高权重。
- `field_context.nearby_text` contains query：新增中高权重。
- `field_context.field_id` / `field_name` exact match：新增高权重。
- `table_context.row_header` / `column_header` match：保持并补强。
- `control_kind` 作为 hard filter 时继续加权。
- `layer != main` 继续轻微加权，但不能压过字段 label。

失败策略：

- 首次 `target_not_found`：可建议 `refresh=true`。
- refresh 后仍 `target_not_found`：`stop_retry=true`，建议补 `control_kind/layer/table/frame_path` 或切换轨道。
- 若 query 命中行文本但没有控件候选：返回 `context_only_candidates`，提示用户/模型刷新 state 或使用低层探测，而不是假装成功。

### 3. Action Recovery V2

增强 `browser_action` 的失败和成功提示。

新增场景：

- `click` 目标 bbox 为 0 或不可见：
  - 返回 `stage="visibility"` 或现有阶段。
  - recovery 增加 `code="find_clickable_in_same_field"`。
  - next suggestion: `browser_find(query=<field_context.nearby_text>, control_kind="button" 或 "custom_select", refresh=true)`。

- `click` 目标 `control_kind=custom_select` 成功：
  - 返回 `next_action_hint`：页面可能展开 dropdown，下一步应 `browser_state` 或 `browser_recipe(custom_select)`。
  - 不自动执行 recipe。

- `select` 误用于 custom select：
  - 保留现有 `use_custom_select_recipe`。
  - 如果 cached element 有 `field_context.nearby_text`，补齐 `next_args.target.query`。
  - 如果传入了 `text/value`，补齐 `option_text`。

- `repeat_blocked`：
  - recovery 除 `stop_retry=true` 外，增加 `alternatives`：
    - 有 field context：建议 `browser_find` 加 `control_kind`。
    - custom select：建议 `browser_recipe(custom_select)`。
    - 无上下文：建议 `browser_state(max_elements=...)` 或低层 `web_execute_js` 探测。

### 4. Recipe Discoverability

不新增 recipe 类型，增强 recipe 被模型发现和正确调用的机会。

`browser_state` 对相关元素增加 `recipe_hint`：

```json
{
  "recipe_hint": {
    "recipe": "custom_select",
    "target": {"query": "工作类型"},
    "requires": ["option_text"]
  }
}
```

适用对象：

- `control_kind=custom_select`
- `.ant-select-*`
- `.wea-select`
- `.wea-browser` / 放大镜按钮
- modal/drawer/popover 中 option-like 元素

约束：

- `recipe_hint` 只是提示，不自动执行。
- 不为普通 input/button 生成 recipe。
- 如果字段上下文为空，不生成 `target.query`，只保留 `target.index` 或不生成 hint。

### 5. Recipe Reliability Tightening

保持现有 recipe 枚举，不扩展自由流程。

优化点：

- `custom_select` 支持 `target.query` 时优先找字段 trigger，再找 overlay option。
- `custom_select` option 查找优先 `layer=dropdown/popover/modal`，但不能硬过滤到只剩空结果；仍保留现有 overlay preference。
- `layer_select` 继续要求 bounded target + option_text；只有 `confirm_text` 存在才点确认。
- `component_wait` 遇到底层 `browser_state` / `browser_find` 非 target_not_found 错误时继续 fail fast，不吞成 timeout。

## Non-Goals

本轮不做：

- OA 专用字段流程。
- 自动填写日报业务流程。
- 任意 CSS selector click/input。
- 文件上传。
- 截图或视觉日志。
- 跨域 iframe 高层操作。
- shadow DOM 穿透。
- 录制回放。
- 多 tab 并发 session 管理。
- 修改外部 `browser-use` 仓库。

## Expected Behavior After Optimization

### Case 1: 是否休假

当前失败：

```json
browser_find({"query": "是否休假"})
// target_not_found
```

优化后期望：

```json
browser_find({"query": "是否休假", "control_kind": "custom_select"})
```

返回：

```json
{
  "status": "success",
  "matches": [
    {
      "index": 4,
      "reason": "field row label; control_kind; visible"
    }
  ],
  "ambiguous": false
}
```

### Case 2: 工作类型

优化后：

- `browser_find(query="工作类型", control_kind="custom_select")` 找到对应 select trigger。
- `browser_state` 对该元素给出 `recipe_hint.recipe="custom_select"`。
- 模型可以调用：

```json
browser_recipe({
  "recipe": "custom_select",
  "target": {"query": "工作类型"},
  "option_text": "代码开发"
})
```

### Case 3: 项目名称放大镜

优化后：

- 放大镜按钮或其 button wrapper 带 `field_context.nearby_text="项目名称"`。
- 点到零尺寸外壳失败时，recovery 提示找同字段里的 button/icon。
- 不把项目选择业务写进 recipe；仍作为通用 `layer_select` / bounded action 流程。

### Case 4: 多个残留 dropdown

优化后：

- `browser_find` 和 `browser_recipe` 仍 fail closed。
- overlay option 优先可见且 layer 正确的候选。
- 如多个同分候选，返回 `ambiguous=true`，不默认点第一个。

## Test Strategy

新增或扩展测试：

1. `tests/test_browser_indexer.py`
   - 表格左 label / 右 custom select 结构产出 `nearby_text`、`row_label`、`previous_cell_text`。
   - `.wea-select` / `.ant-select` 能得到 `control_kind=custom_select` 和 `recipe_hint`。
   - 放大镜按钮能继承所在字段上下文。

2. `tests/test_ga_browser_use_finder.py`
   - `query="是否休假"` 能通过 `field_context.row_label` 命中 custom select。
   - `query="工作类型"` + `control_kind=custom_select` 能排除同页其他 dropdown。
   - refresh 后仍找不到目标时返回 `stop_retry=true`。
   - 多个同名字段返回 `ambiguous=true`。

3. `tests/test_browser_actions.py`
   - zero-rect / invisible click recovery 包含 `find_clickable_in_same_field`。
   - custom select `select` 误用 recovery 自动补 `target.query` 和 `option_text`。
   - custom select click 成功返回 next action hint，但不自动执行 recipe。

4. `tests/test_ga_browser_use_recipes.py`
   - `custom_select` 使用 `target.query` 走 trigger -> state -> option -> click -> verify。
   - 多 dropdown 残留时优先 visible overlay，歧义时 fail closed。
   - `component_wait` 不吞底层异常为 timeout。

5. Schema / SOP tests
   - 工具描述不声称通吃。
   - SOP 说明 recipe_hint 是提示，不是自动规划。

## Verification Commands

聚焦验证：

```powershell
python -m pytest tests/test_browser_indexer.py tests/test_ga_browser_use_finder.py tests/test_browser_actions.py tests/test_ga_browser_use_recipes.py tests/test_browser_tool_handlers.py tests/test_browser_tool_schemas.py -q
git diff --check
```

如果只改 finder/indexer，可先跑：

```powershell
python -m pytest tests/test_browser_indexer.py tests/test_ga_browser_use_finder.py -q
```

如果改 action/recovery，可先跑：

```powershell
python -m pytest tests/test_browser_actions.py tests/test_ga_browser_use_results.py -q
```

## Rollout Plan

建议分三步实现，避免一次改太多：

1. Field Context V2 + Finder Scoring V2。
   - 目标：让 `browser_find` 能定位常见企业表单字段。

2. Action Recovery V2 + recipe_hint。
   - 目标：失败后给模型可执行下一步，成功点击 custom select 后能知道下一步怎么选。

3. Recipe Reliability Tightening + SOP/schema 对齐。
   - 目标：让 `custom_select` / `layer_select` 更可发现、更稳，但不扩大为自由流程。

每步都必须有独立测试和 focused verification。

## Success Criteria

- `browser_find` 不再在“字段名在相邻单元格、控件本身无 label”的常见表单结构上直接失败。
- `browser_state` 能输出字段上下文和有限 `recipe_hint`。
- `browser_action` 的失败 recovery 能阻止重复撞墙，并给出更具体的下一步。
- `browser_recipe` 在 custom select / layer select 场景中更容易被模型正确调用。
- 不引入业务专用规则。
- 不改变 `web_execute_js` 的平级低层定位。
- focused tests 全部通过。
