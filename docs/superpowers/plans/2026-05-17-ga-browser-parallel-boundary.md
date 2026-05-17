# GA Browser Parallel Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align GA's browser tool descriptions, SOP, and contract tests with the approved peer-boundary model where `web_execute_js` and `browser_*` are parallel, complementary tracks.

**Architecture:** This is a contract/documentation hardening pass, not a runtime capability expansion. The implementation updates tool schema descriptions, one handler docstring, and SOP guidance, then locks the boundary with focused tests so future edits do not reintroduce priority-biased or overclaiming language.

**Tech Stack:** Python, pytest, JSON tool schemas, Markdown SOP docs.

---

## Scope

This plan implements the approved boundary from `docs/superpowers/specs/2026-05-17-ga-browser-parallel-boundary-design.md`.

It must not:

- Add OA-business-specific recipes.
- Change the execution priority between `web_execute_js` and `browser_*`.
- Modify `E:\zfengl-ai-project\browser-use`.
- Add new browser runtime behavior unless a failing contract test proves a wording-only fix cannot work.
- Turn `browser_recipe` into a free-form browser planner.

## File Structure

- Modify: `E:\zfengl-ai-project\GenericAgent\assets\tools_schema.json`
  - Responsibility: English runtime tool descriptions shown to the model.
- Modify: `E:\zfengl-ai-project\GenericAgent\assets\tools_schema_cn.json`
  - Responsibility: Chinese runtime tool descriptions shown to the model.
- Modify: `E:\zfengl-ai-project\GenericAgent\ga.py`
  - Responsibility: remove the overclaiming `do_web_execute_js` handler docstring.
- Modify: `E:\zfengl-ai-project\GenericAgent\memory\browser-use_sop.md`
  - Responsibility: durable SOP guidance for GA browser-use capability use.
- Modify: `E:\zfengl-ai-project\GenericAgent\tests\test_browser_tool_schemas.py`
  - Responsibility: schema-level contract assertions.
- Create: `E:\zfengl-ai-project\GenericAgent\tests\test_browser_parallel_boundary_docs.py`
  - Responsibility: SOP and handler-docstring boundary assertions.

---

### Task 1: Add Schema Boundary Tests

**Files:**
- Modify: `E:\zfengl-ai-project\GenericAgent\tests\test_browser_tool_schemas.py`

- [ ] **Step 1: Add failing schema contract tests**

Append this test function to `tests/test_browser_tool_schemas.py`:

```python
def test_browser_tool_descriptions_use_parallel_boundary_terms():
    english = load_tools("assets/tools_schema.json")
    chinese = load_tools("assets/tools_schema_cn.json")

    en_web_js = tool_by_name(english, "web_execute_js")
    en_state = tool_by_name(english, "browser_state")
    en_find = tool_by_name(english, "browser_find")
    en_recipe = tool_by_name(english, "browser_recipe")
    en_action = tool_by_name(english, "browser_action")

    cn_web_js = tool_by_name(chinese, "web_execute_js")
    cn_state = tool_by_name(chinese, "browser_state")
    cn_find = tool_by_name(chinese, "browser_find")
    cn_recipe = tool_by_name(chinese, "browser_recipe")
    cn_action = tool_by_name(chinese, "browser_action")

    assert "peer low-level browser-control tool" in en_web_js["description"]
    assert "not above or below browser_* tools" in en_web_js["description"]
    assert "structured indexed snapshot" in en_state["description"]
    assert "not full-page extraction" in en_state["description"]
    assert "semantic locator" in en_find["description"]
    assert "query or table" in en_find["description"]
    assert "not a global search engine" in en_find["description"]
    assert "fixed deterministic" in en_recipe["description"]
    assert "not a general planner" in en_recipe["description"]
    assert "bounded indexed browser actions" in en_action["description"]
    assert "not arbitrary selector automation" in en_action["description"]

    assert "平级" in cn_web_js["description"]
    assert "低层浏览器控制工具" in cn_web_js["description"]
    assert "不是 browser_* 的上级或下级" in cn_web_js["description"]
    assert "结构化索引快照" in cn_state["description"]
    assert "不是网页全文抽取" in cn_state["description"]
    assert "语义定位" in cn_find["description"]
    assert "query 或 table" in cn_find["description"]
    assert "不是全局搜索引擎" in cn_find["description"]
    assert "固定且确定性" in cn_recipe["description"]
    assert "不是通用规划器" in cn_recipe["description"]
    assert "有边界的索引动作" in cn_action["description"]
    assert "不是任意 selector 自动化" in cn_action["description"]

    forbidden_english = [
        "primary browser action tool",
        "default ordinary interaction path",
        "fallback-only",
    ]
    forbidden_chinese = [
        "优先使用工具",
        "普通交互首选",
        "只能作为兜底",
    ]
    english_descriptions = "\n".join(
        tool_by_name(english, name)["description"]
        for name in ["web_execute_js", "browser_state", "browser_find", "browser_recipe", "browser_action"]
    )
    chinese_descriptions = "\n".join(
        tool_by_name(chinese, name)["description"]
        for name in ["web_execute_js", "browser_state", "browser_find", "browser_recipe", "browser_action"]
    )
    for phrase in forbidden_english:
        assert phrase not in english_descriptions
    for phrase in forbidden_chinese:
        assert phrase not in chinese_descriptions
```

- [ ] **Step 2: Run the schema test and confirm it fails for current wording**

Run:

```powershell
python -m pytest tests/test_browser_tool_schemas.py::test_browser_tool_descriptions_use_parallel_boundary_terms -q
```

Expected: FAIL because current schema descriptions do not yet contain the approved peer-boundary wording.

- [ ] **Step 3: Commit only if this task is executed separately**

Do not commit a failing test alone unless the execution strategy explicitly wants TDD checkpoint commits. If committing per task, use:

```powershell
git add tests/test_browser_tool_schemas.py
git commit -m "test: lock browser tool boundary schema wording"
```

---

### Task 2: Add SOP And Handler Boundary Tests

**Files:**
- Create: `E:\zfengl-ai-project\GenericAgent\tests\test_browser_parallel_boundary_docs.py`

- [ ] **Step 1: Create the failing doc-boundary test file**

Create `tests/test_browser_parallel_boundary_docs.py` with this exact content:

```python
from pathlib import Path

import ga


def test_web_execute_js_handler_docstring_uses_peer_boundary():
    doc = ga.GenericAgentHandler.do_web_execute_js.__doc__ or ""

    assert "平级" in doc
    assert "低层" in doc
    assert "优先使用工具" not in doc
    assert "完全" not in doc


def test_browser_use_sop_uses_task_shape_decision_model():
    text = Path("memory/browser-use_sop.md").read_text(encoding="utf-8")

    assert "平级" in text
    assert "互补" in text
    assert "任务形态" in text
    assert "先判断任务形态" in text
    assert "优先策略：普通网页交互先用" not in text
    assert "推荐决策：" not in text
    assert "web_execute_js 不是 browser_* 的上级或下级" in text
    assert "browser_recipe 不是自由规划器" in text
```

- [ ] **Step 2: Run the new test and confirm it fails for current docs**

Run:

```powershell
python -m pytest tests/test_browser_parallel_boundary_docs.py -q
```

Expected: FAIL because `ga.py` still says `web_execute_js` is the priority tool and the SOP still contains priority-biased decision wording.

- [ ] **Step 3: Commit only if this task is executed separately**

Do not commit a failing test alone unless the execution strategy explicitly wants TDD checkpoint commits. If committing per task, use:

```powershell
git add tests/test_browser_parallel_boundary_docs.py
git commit -m "test: lock browser boundary SOP wording"
```

---

### Task 3: Update Tool Schema Descriptions

**Files:**
- Modify: `E:\zfengl-ai-project\GenericAgent\assets\tools_schema.json`
- Modify: `E:\zfengl-ai-project\GenericAgent\assets\tools_schema_cn.json`
- Test: `E:\zfengl-ai-project\GenericAgent\tests\test_browser_tool_schemas.py`

- [ ] **Step 1: Replace the English `web_execute_js` description**

In `assets/tools_schema.json`, replace only the `description` value for function `web_execute_js` with:

```json
"Execute JavaScript in the real Chrome page as a peer low-level browser-control tool for probing, framework state inspection, complex DOM reads, CDP/special operations, and actions that indexed browser tools cannot represent safely. It is not above or below browser_* tools; choose by task shape. Multi-call OK with different switch_tab_id. Use no_monitor only for read-only probing. Execute JS in ```javascript blocks if no script arg, to avoid escaping"
```

- [ ] **Step 2: Replace the English `browser_state` description**

In `assets/tools_schema.json`, replace only the `description` value for function `browser_state` with:

```json
"Get a structured indexed snapshot from the real Chrome page for recoverable element targeting, including same-origin iframe metadata and field/control/layer context. This is not full-page extraction and not complex DOM reasoning. Use before browser_action when indexes may have changed."
```

- [ ] **Step 3: Replace the English `browser_find` description**

In `assets/tools_schema.json`, replace only the `description` value for function `browser_find` with:

```json
"Read-only semantic locator for indexed browser elements from the real Chrome page. Provide query or table as the real locator; role/layer/control_kind/frame_path are optional filters and are not sufficient by themselves. This is not a global search engine and not a browser_state replacement. Returns candidate indexes with score, reason, and ambiguity instead of acting."
```

- [ ] **Step 4: Replace the English `browser_recipe` description**

In `assets/tools_schema.json`, replace only the `description` value for function `browser_recipe` with:

```json
"Run a fixed deterministic bounded browser operation recipe in the real Chrome page. Recipes fail closed on ambiguity and are not a general planner. Use only for custom_select, layer_select, table_locate, and component_wait."
```

- [ ] **Step 5: Replace the English `browser_action` description**

In `assets/tools_schema.json`, replace only the `description` value for function `browser_action` with:

```json
"Perform bounded indexed browser actions against latest browser_state elements in the real Chrome page; this is not arbitrary selector automation or a form planner. Native select stays native select; custom dropdowns are not select. For submit/search after input, call keys with text Enter and omit index to use the focused element. SPA wait actions include wait_dom_stable, wait_not_busy, wait_route, and indexed wait_enabled. Verification fields verify/verify_text/verify_value/verify_selector are supported for click/input/select/keys only; wait actions reject verify. Failed verification returns stage verify_failed. selector is supported for wait_selector and as a custom busy selector for wait_not_busy."
```

- [ ] **Step 6: Replace the Chinese `web_execute_js` description**

In `assets/tools_schema_cn.json`, replace only the `description` value for function `web_execute_js` with:

```json
"在真实 Chrome 页面执行 JavaScript，作为与 browser_* 平级的低层浏览器控制工具，适合页面/框架状态探测、复杂 DOM 读取、CDP/特殊操作，以及 indexed 工具无法安全表达的动作。它不是 browser_* 的上级或下级；按任务形态选择。支持 Multi-call，可用不同 switch_tab_id 操作多标签页。no_monitor 仅用于只读探测。无 script 参数时执行正文 ```javascript 块，以免转义"
```

- [ ] **Step 7: Replace the Chinese `browser_state` description**

In `assets/tools_schema_cn.json`, replace only the `description` value for function `browser_state` with:

```json
"从真实 Chrome 页面获取结构化索引快照，用于可恢复的元素定位，包含同源 iframe 元数据以及 field/control/layer 上下文。它不是网页全文抽取工具，也不负责复杂 DOM 推理。索引可能变化时，先调用本工具再执行 browser_action。"
```

- [ ] **Step 8: Replace the Chinese `browser_find` description**

In `assets/tools_schema_cn.json`, replace only the `description` value for function `browser_find` with:

```json
"只读语义定位真实 Chrome 页面中的 indexed 元素。必须提供 query 或 table 作为真实定位条件；role/layer/control_kind/frame_path 只是可选过滤条件，单独使用不足以定位。它不是全局搜索引擎，也不是 browser_state 替代品。返回候选 index、评分、原因和是否歧义，不执行点击或输入。"
```

- [ ] **Step 9: Replace the Chinese `browser_recipe` description**

In `assets/tools_schema_cn.json`, replace only the `description` value for function `browser_recipe` with:

```json
"在真实 Chrome 页面运行固定且确定性的有界浏览器操作 recipe。recipe 遇到歧义会 fail closed 并返回候选，不是通用规划器。只用于 custom_select、layer_select、table_locate、component_wait。"
```

- [ ] **Step 10: Replace the Chinese `browser_action` description**

In `assets/tools_schema_cn.json`, replace only the `description` value for function `browser_action` with:

```json
"在真实 Chrome 页面中，基于最新 browser_state 元素执行有边界的索引动作；它不是任意 selector 自动化，也不是表单规划器。原生 select 仍然只表示原生 select，自定义下拉不是 select。输入后提交/搜索时，调用 keys 且 text 为 Enter，并且不要传 index，让按键发送到当前焦点元素。SPA 等待动作包括 wait_dom_stable、wait_not_busy、wait_route，以及需要索引的 wait_enabled。verify/verify_text/verify_value/verify_selector 只支持 click/input/select/keys；等待动作会拒绝 verify。验证失败返回 stage verify_failed。selector 支持 wait_selector，也可作为 wait_not_busy 的自定义忙碌选择器。"
```

- [ ] **Step 11: Run schema tests**

Run:

```powershell
python -m pytest tests/test_browser_tool_schemas.py -q
```

Expected: PASS.

- [ ] **Step 12: Commit only if this task is executed separately**

If committing per task, use:

```powershell
git add assets/tools_schema.json assets/tools_schema_cn.json tests/test_browser_tool_schemas.py
git commit -m "docs: clarify browser tool schema boundaries"
```

---

### Task 4: Update `web_execute_js` Handler Docstring

**Files:**
- Modify: `E:\zfengl-ai-project\GenericAgent\ga.py`
- Test: `E:\zfengl-ai-project\GenericAgent\tests\test_browser_parallel_boundary_docs.py`

- [ ] **Step 1: Replace the handler docstring**

In `ga.py`, replace the docstring under `GenericAgentHandler.do_web_execute_js`:

```python
'''web情况下的优先使用工具，执行任何js达成对浏览器的*完全*控制。支持将结果保存到文件供后续读取分析。'''
```

with:

```python
'''与 browser_* 平级的低层 JS/CDP/探测工具；用于直接脚本、框架状态读取、特殊控制和高层索引工具无法安全表达的动作。支持将长结果保存到文件供后续读取分析。'''
```

- [ ] **Step 2: Run the handler docstring test**

Run:

```powershell
python -m pytest tests/test_browser_parallel_boundary_docs.py::test_web_execute_js_handler_docstring_uses_peer_boundary -q
```

Expected: PASS.

- [ ] **Step 3: Commit only if this task is executed separately**

If committing per task, use:

```powershell
git add ga.py tests/test_browser_parallel_boundary_docs.py
git commit -m "docs: remove web_execute_js priority overclaim"
```

---

### Task 5: Update Browser-Use SOP Decision Model

**Files:**
- Modify: `E:\zfengl-ai-project\GenericAgent\memory\browser-use_sop.md`
- Test: `E:\zfengl-ai-project\GenericAgent\tests\test_browser_parallel_boundary_docs.py`

- [ ] **Step 1: Replace the opening priority strategy**

In `memory/browser-use_sop.md`, replace the current three bullets under `## 核心定位` with:

```markdown
- `web_scan` / `web_execute_js`：低层网页观察与 JS/CDP 操作，适合调试、复杂页面、框架状态探测、CDP、文件上传、跨域 iframe、截图等细节控制。
- `browser_state` / `browser_find` / `browser_action` / `browser_recipe`：结构化、可验证、可恢复的高层浏览器操作工具，适合像用户一样定位、点击、输入、原生选择、按键、等待元素或文本，并能处理同源 iframe 中被索引的元素。
- 平级策略：`web_execute_js` 不是 browser_* 的上级或下级，browser_* 也不是万能浏览器代理。先判断任务形态和组件类型，再选择低层 JS/CDP 轨道或结构化 indexed-action 轨道；不要为了完成目标把任一工具强行扩成通用自动化层。
```

- [ ] **Step 2: Replace the stale recommendation section**

In `memory/browser-use_sop.md`, replace this section:

```markdown
推荐决策：

1. 想知道页面上有什么：`web_scan(text_only=true)` 或 `browser_state`。
2. 想执行普通用户动作：`browser_state` / `browser_find` 定位，`browser_action` 执行。
3. 想处理常见自定义下拉、弹层选择、表格目标定位、组件条件检查：优先 `browser_recipe`。
4. 想导航：`web_execute_js` 执行 `location.href='...'`，或在已有页面中点链接。
5. 想执行复杂 JS / CDP / 上传 / 截图 / 跨域 iframe：读 `tmwebdriver_sop`，用 `web_execute_js`。
```

with:

```markdown
任务形态决策：

1. 页面读数、框架状态、隐藏字段、复杂 DOM、CDP、上传、截图、跨域 iframe：选择 `web_scan` / `web_execute_js` 低层轨道。
2. 已知要操作页面上的可交互元素，并且目标能被索引：选择 `browser_state` / `browser_find` / `browser_action` 结构化轨道。
3. 常见自定义下拉、弹层选择、表格目标定位、组件条件检查：选择固定 `browser_recipe`，让它在歧义时 fail closed。
4. 导航既可以用 `web_execute_js` 执行明确的 `location.href='...'`，也可以在已有页面中通过 indexed link/button 点击；按页面上下文选择，不做固定优先级。
5. browser_* 连续失败且 recovery 已要求停止重复时，不要原地撞墙；补充 query/table/layer/frame 约束，或切换到 `web_execute_js` / CDP 低层轨道。
```

- [ ] **Step 3: Replace the final quick rules**

In `memory/browser-use_sop.md`, replace the final numbered list beginning with `1. 要操作页面元素，先` with:

```markdown
1. 先判断任务形态和组件类型，再选 `web_execute_js` 低层轨道或 browser_* 结构化轨道。
2. 选择 browser_* 轨道时，先 `browser_state`，再用 index；state 太长或目标不明确时，用带 query/table 的 `browser_find` 缩小候选。
3. `browser_recipe` 不是自由规划器，只用于固定的 `custom_select`、`layer_select`、`table_locate`、`component_wait`，歧义就补约束。
4. `browser_action(keys, text="Enter")` 可以不传 index，输入后提交/搜索时优先复用当前焦点。
5. 失败先读 `recovery.stop_retry` / `recovery.next_args`；页面结构变了，旧 index 作废，要么按焦点继续，要么重新 `browser_state`，需要缩小候选时再用带 query/table 的 `browser_find(refresh=true)`。
```

- [ ] **Step 4: Run the SOP test**

Run:

```powershell
python -m pytest tests/test_browser_parallel_boundary_docs.py::test_browser_use_sop_uses_task_shape_decision_model -q
```

Expected: PASS.

- [ ] **Step 5: Commit only if this task is executed separately**

If committing per task, use:

```powershell
git add memory/browser-use_sop.md tests/test_browser_parallel_boundary_docs.py
git commit -m "docs: switch browser SOP to task-shape decisions"
```

---

### Task 6: Verify The Full Contract

**Files:**
- Test: `E:\zfengl-ai-project\GenericAgent\tests\test_browser_tool_schemas.py`
- Test: `E:\zfengl-ai-project\GenericAgent\tests\test_browser_parallel_boundary_docs.py`
- Test: `E:\zfengl-ai-project\GenericAgent\tests\test_browser_tool_handlers.py`

- [ ] **Step 1: Run focused tests**

Run:

```powershell
python -m pytest tests/test_browser_tool_schemas.py tests/test_browser_parallel_boundary_docs.py tests/test_browser_tool_handlers.py -q
```

Expected: PASS.

- [ ] **Step 2: Search for stale priority-biased wording**

Run:

```powershell
rg -n "优先使用工具|优先策略：普通网页交互先用|推荐决策：|default ordinary interaction path|primary browser action tool|fallback-only" ga.py assets/tools_schema.json assets/tools_schema_cn.json memory/browser-use_sop.md tests
```

Expected: no matches.

- [ ] **Step 3: Confirm no unintended runtime files changed**

Run:

```powershell
git diff --name-only
```

Expected output contains only:

```text
assets/tools_schema.json
assets/tools_schema_cn.json
ga.py
memory/browser-use_sop.md
tests/test_browser_tool_schemas.py
tests/test_browser_parallel_boundary_docs.py
```

- [ ] **Step 4: Final commit**

If all tasks are executed in one batch, commit with:

```powershell
git add assets/tools_schema.json assets/tools_schema_cn.json ga.py memory/browser-use_sop.md tests/test_browser_tool_schemas.py tests/test_browser_parallel_boundary_docs.py
git commit -m "docs: align browser tool boundary contracts"
```

Expected: commit succeeds and `git status --short` is clean.

---

## Self-Review

- Spec coverage: The plan covers schema descriptions, `ga.py` handler wording, SOP task-shape decisions, and tests that prevent regressions toward priority ordering or overclaiming.
- Simplicity check: The plan does not add runtime features, new recipes, new browser abstractions, or browser-use dependency changes.
- Boundary check: `web_execute_js` remains a peer low-level tool, not fallback-only; `browser_*` remains structured and bounded, not a universal browser agent.
- Test check: The plan adds failing tests first, then updates only wording and docs until tests pass.
