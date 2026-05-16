# GA 浏览器操作能力高级测试清单

本文是 `tests/browser-use_test_checklist.md` 的进阶版。基础能力已经验证无阻断后，再执行本清单。

难度定义：比基础清单高 2 级，重点不是再验证“能不能点、能不能输”，而是验证 GA 在复杂页面变化中是否会正确编排 `browser_state` / `browser_action`，并在当前实现边界内及时停止错误路径。

## 范围边界

本清单只验证当前已实现能力：

- `browser_state(include_invisible=false, max_elements=120, switch_tab_id/tab_id)`，包含同源 iframe 元数据和 field/control/layer/table 上下文。
- `browser_action(action=click/input/select/keys/wait_index/wait_text/wait_selector/wait_dom_stable/wait_not_busy/wait_enabled/wait_route, index/text/value/selector/timeout/verify/switch_tab_id/tab_id)`
- state token 生命周期、tab 隔离、mutating action 后 state 清空。
- `wait_index` 的 cached node 优先和 detached fallback。
- `input` / `select` / `keys` / `verify` 的实现边界。

本清单不把以下能力算作新工具通过项：

- 文件上传、截图、验证码视觉、网络抓包、Cookie/CDP/Tab 管理。
- 跨域 iframe / closed Shadow DOM 穿透。
- `isTrusted=true` 点击。
- 任意 CSS selector 直接 click/input。
- 大规模网页正文抽取。

## 高级验收标准

| 等级 | 要求 |
| --- | --- |
| P3 | 多步骤业务流、动态 DOM、焦点提交、错误恢复、max_elements 截断全部符合预期。 |
| P4 | tab state 隔离、wait_index 边界、复杂自定义组件路径选择、真实站点连续任务验证全部符合预期。 |
| 失败条件 | GA 在 mutation 后复用旧 index、input 后为按 Enter 重扫 state、连续失败两次仍重复同一错误动作、把边界失败解释成页面成功。 |

## 记录要求

每个用例至少记录：

| 字段 | 内容 |
| --- | --- |
| 工具序列 | 例如 `browser_state -> input -> keys without index -> wait_text -> browser_state` |
| 关键返回 | `status`、`stage`、`error`、`result`、`tab_id`、`suggested_args` |
| 页面证据 | `#status` 文本、`#audit-log` 记录、重新 state 后的 text/value |
| 编排判断 | 是否重扫 state、是否使用焦点 keys、是否切换到旧工具 |
| 结论 | 通过 / 未通过 / 边界符合预期 |

## 高级测试页准备

用 `web_execute_js` 注入测试页。该步骤只是准备 fixture，后续交互必须用 `browser_state` / `browser_action` 完成。

```javascript
(() => {
  document.title = "GA Browser Advanced Fixture";
  document.body.innerHTML = `
    <main id="advanced-root" style="font-family: sans-serif; padding: 24px; line-height: 1.5;">
      <h1>GA Browser Advanced Fixture</h1>
      <p id="status">advanced-ready</p>
      <ol id="audit-log" style="max-height: 180px; overflow: auto; border: 1px solid #ccc; padding: 8px 8px 8px 28px;"></ol>

      <section id="wizard" aria-label="wizard area" style="margin-top: 16px; border: 1px solid #999; padding: 12px;">
        <h2>Wizard</h2>
        <div id="wizard-step">step:1</div>
        <input id="user-name" name="userName" placeholder="User name" value="">
        <button id="wizard-next" disabled>Next Step</button>
      </section>

      <section id="smart-search-area" aria-label="smart search area" style="margin-top: 16px; border: 1px solid #999; padding: 12px;">
        <h2>Smart Search</h2>
        <input id="smart-search" name="smartSearch" placeholder="Smart search" value="">
        <div id="suggestions" hidden></div>
      </section>

      <section id="rerender-area" aria-label="rerender area" style="margin-top: 16px; border: 1px solid #999; padding: 12px;">
        <h2>Rerender Area</h2>
        <button id="rerender-start">Rerender Start</button>
        <button id="rerender-sibling">Rerender Sibling</button>
        <div id="rerender-result"></div>
      </section>

      <section id="advanced-select-area" aria-label="advanced select area" style="margin-top: 16px; border: 1px solid #999; padding: 12px;">
        <h2>Selects</h2>
        <select id="native-priority" name="priority">
          <option value="">Choose priority</option>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
        </select>
        <div id="fake-priority" role="combobox" tabindex="0" style="display: inline-block; margin-left: 12px; border: 1px solid #666; padding: 4px 8px; cursor: pointer;">Fake Priority</div>
        <div id="fake-priority-menu" hidden style="display: inline-block; border: 1px solid #666; padding: 4px 8px;">
          <button id="fake-low">Fake Low</button>
          <button id="fake-high">Fake High</button>
        </div>
      </section>

      <section id="list-area" aria-label="large list area" style="margin-top: 16px; border: 1px solid #999; padding: 12px;">
        <h2>Large List</h2>
        <button id="build-large-list">Build Large List</button>
        <div id="large-list"></div>
      </section>

      <section id="wait-area" aria-label="wait edge area" style="margin-top: 16px; border: 1px solid #999; padding: 12px;">
        <h2>Wait Edges</h2>
        <button id="identity-target">Identity Target</button>
        <button id="duplicate-wait">Duplicate Wait</button>
      </section>

      <section id="guard-area" aria-label="guard area" style="margin-top: 16px; border: 1px solid #999; padding: 12px;">
        <h2>Guards</h2>
        <input id="guarded-input" placeholder="Guarded input" value="">
        <button id="guard-submit" disabled>Guard Submit</button>
        <button id="open-async-modal">Open Async Modal</button>
        <div id="async-modal-host"></div>
      </section>

      <section id="layer-area" aria-label="layer area" style="margin-top: 16px; border: 1px solid #999; padding: 12px;">
        <h2>Layer Priority</h2>
        <button id="open-layered-menu">Open Layered Menu</button>
        <div id="fixture-modal" class="ant-modal" hidden role="dialog" aria-label="Fixture Modal" style="position: fixed; left: 30px; top: 30px; z-index: 1000; background: white; border: 2px solid #333; padding: 12px;">
          <button id="modal-primary">Modal Primary</button>
        </div>
        <div id="fixture-dropdown" class="ant-select-dropdown" hidden style="position: fixed; left: 60px; top: 90px; z-index: 1100; background: white; border: 1px solid #666; padding: 8px;">
          <button id="layered-option">Layered Option</button>
        </div>
      </section>

      <section id="rich-editor-area" aria-label="rich editor area" style="margin-top: 16px; border: 1px solid #999; padding: 12px;">
        <h2>Rich Editor</h2>
        <div id="rich-content" role="textbox" contenteditable="true" style="border: 1px solid #999; padding: 6px;">rich seed</div>
        <iframe id="editor-frame" title="Editor Frame" srcdoc="<!doctype html><html><body contenteditable='true'>iframe editor seed</body></html>"></iframe>
      </section>

      <section id="metadata-area" aria-label="metadata area" style="margin-top: 16px; border: 1px solid #999; padding: 12px;">
        <h2>Metadata</h2>
        <label for="metadata-input">Metadata Label</label>
        <input id="metadata-input" name="metadataInput" required placeholder="Metadata input" value="">
        <table id="metadata-table">
          <thead><tr><th>Item</th><th>Action</th></tr></thead>
          <tbody><tr><th scope="row">Alpha row</th><td><button id="metadata-row-action">Metadata Row Action</button></td></tr></tbody>
        </table>
        <iframe id="advanced-same-origin-frame" title="Advanced Same Origin Frame" srcdoc="<button id='frame-action'>Frame Action</button><input id='frame-query' placeholder='Frame query'><p id='frame-log'>frame ready</p>"></iframe>
      </section>
    </main>`;

  const $ = (id) => document.getElementById(id);
  const status = $("status");
  const logEl = $("audit-log");
  const log = (message) => {
    const item = document.createElement("li");
    item.textContent = message;
    logEl.appendChild(item);
    status.textContent = message;
  };

  $("user-name").addEventListener("input", () => {
    $("wizard-next").disabled = !$("user-name").value.trim();
    log("wizard:name-input:" + $("user-name").value);
  });
  $("wizard-next").addEventListener("click", () => {
    $("wizard-step").textContent = "step:2";
    $("wizard").insertAdjacentHTML("beforeend", `
      <select id="wizard-role">
        <option value="">Choose role</option>
        <option value="analyst">Analyst</option>
        <option value="operator">Operator</option>
      </select>
      <button id="wizard-finish">Finish Wizard</button>
    `);
    $("wizard-role").addEventListener("change", () => log("wizard:role:" + $("wizard-role").value));
    $("wizard-finish").addEventListener("click", () => {
      log("wizard:finished:" + $("user-name").value + ":" + $("wizard-role").value);
    });
    log("wizard:step2");
  });

  $("smart-search").addEventListener("input", () => {
    const value = $("smart-search").value;
    $("suggestions").hidden = false;
    $("suggestions").innerHTML = `
      <button id="suggestion-primary">Use ${value}</button>
      <button id="suggestion-secondary">Other ${value}</button>
    `;
    $("suggestion-primary").addEventListener("click", () => log("search:suggestion:" + value));
    log("search:suggestions-open:" + value);
  });
  $("smart-search").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      $("suggestions").hidden = true;
      log("search:enter:" + $("smart-search").value);
    }
  });

  $("rerender-start").addEventListener("click", () => {
    log("rerender:start-clicked");
    setTimeout(() => {
      $("rerender-area").innerHTML = `
        <h2>Rerender Area</h2>
        <button id="rerender-final">Rerender Final</button>
        <div id="rerender-result">rerendered</div>
      `;
      $("rerender-final").addEventListener("click", () => log("rerender:final-clicked"));
    }, 300);
  });
  $("rerender-sibling").addEventListener("click", () => log("rerender:sibling-clicked"));

  $("native-priority").addEventListener("change", () => log("native-priority:" + $("native-priority").value));
  $("fake-priority").addEventListener("click", () => {
    $("fake-priority-menu").hidden = false;
    log("fake-priority:open");
  });
  $("fake-low").addEventListener("click", () => log("fake-priority:low"));
  $("fake-high").addEventListener("click", () => log("fake-priority:high"));

  $("build-large-list").addEventListener("click", () => {
    const list = $("large-list");
    list.innerHTML = "";
    for (let i = 1; i <= 160; i += 1) {
      const button = document.createElement("button");
      button.textContent = "Row Action " + String(i).padStart(3, "0");
      button.setAttribute("aria-label", "row action " + i);
      button.addEventListener("click", () => log("large-list:clicked:" + i));
      list.appendChild(button);
    }
    log("large-list:built:160");
  });

  $("guarded-input").addEventListener("input", () => {
    $("guard-submit").disabled = $("guarded-input").value !== "unlock";
    log("guard:input:" + $("guarded-input").value);
  });
  $("guard-submit").addEventListener("click", () => log("guard:submitted"));
  $("open-async-modal").addEventListener("click", () => {
    log("modal:opening");
    setTimeout(() => {
      $("async-modal-host").innerHTML = `
        <div id="async-modal" role="dialog" aria-label="Async Modal">
          <p>Async Modal Ready</p>
          <button id="async-confirm">Confirm Async</button>
        </div>
      `;
      $("async-confirm").addEventListener("click", () => log("modal:confirmed"));
    }, 400);
  });
  $("open-layered-menu").addEventListener("click", () => {
    $("fixture-modal").hidden = false;
    $("fixture-dropdown").hidden = false;
    log("layer:opened");
  });
  $("modal-primary").addEventListener("click", () => log("layer:modal-primary"));
  $("layered-option").addEventListener("click", () => log("layer:dropdown-option"));
  const installAdvancedFrameHandlers = () => {
    const frameDoc = $("advanced-same-origin-frame").contentDocument;
    if (!frameDoc || frameDoc.__gaFrameHandlersInstalled) return;
    frameDoc.__gaFrameHandlersInstalled = true;
    frameDoc.getElementById("frame-action").addEventListener("click", () => {
      frameDoc.getElementById("frame-log").textContent = "frame action clicked";
    });
  };
  $("advanced-same-origin-frame").addEventListener("load", installAdvancedFrameHandlers);
  setTimeout(installAdvancedFrameHandlers, 0);

  window.__gaAdvancedFixture = { loadedAt: Date.now() };
  return { status: "advanced_fixture_loaded", title: document.title };
})();
```

准备后执行：

```json
{"tool": "browser_action", "args": {"action": "wait_text", "text": "GA Browser Advanced Fixture", "timeout": 3}}
```

预期：`status=success`，`result=text_found`。

## P3 多步骤业务流

| ID | 场景 | 工具编排 | 预期 |
| --- | --- | --- | --- |
| ATC-01 | 向导：禁用按钮到可点击 | `browser_state` 找 `Next Step`，先 click；重新 state 找 `User name`，`input("alice")`；重新 state 找 `Next Step` click | 第一次 click 应失败并指向 disabled；输入后 Next 可点击，点击后 `wait_text("wizard:step2")` 成功。 | 通过 |
| ATC-02 | 向导：动态新增 select | ATC-01 后重新 `browser_state` 找 `wizard-role`，执行 `select(value="operator")`，再重新 state 找 `Finish Wizard` click | `wait_text("wizard:finished:alice:operator")` 成功；动态新增元素必须重新 state。 | 通过 |
| ATC-03 | 搜索：input 后 DOM 展开但仍用焦点 Enter | 重新加载 fixture；`browser_state` 找 `Smart search`；`input("delta")`；不要重扫 state，直接 `keys("Enter")` without index | `wait_text("search:enter:delta")` 成功；如果 GA 在 input 后重扫并丢目标，此项不通过。 | 通过 |
| ATC-04 | 搜索：input 后改为点击建议 | 重新加载 fixture；`input("sigma")` 后重新 `browser_state`；找到 `Use sigma` click | `wait_text("search:suggestion:sigma")` 成功；这是需要重新 state 的分支，因为目标是新出现的建议按钮。 | 通过 |
| ATC-05 | 异步弹窗 | `browser_state` 找 `Open Async Modal` click；直接 `wait_text("Async Modal Ready", timeout=3)`；重新 state 找 `Confirm Async` click | `wait_text("modal:confirmed")` 成功；click 后等待不需要旧 index。 | 通过 |
| ATC-06 | 异步弹窗后后续操作 | ATC-05 后重新 state 操作 Continue/Next 等新元素 | 能正确获取新 state 并操作。 | 通过 |

## P3 state 失效与恢复

| ID | 场景 | 工具编排 | 预期 | 结果 |
| --- | --- | --- | --- | --- |
| ATC-10 | click 后立即复用同一批旧 index | `browser_state` 同时记录 `Rerender Start` 和 `Rerender Sibling` index；click `Rerender Start`；立即用旧 `Rerender Sibling` index click | 第二次 indexed click 应 `state_missing`；正确做法是等待并重新 state。 | 通过 |
| ATC-11 | SPA 区域重渲染后重扫 | ATC-10 后 `wait_text("rerendered")`；重新 `browser_state` 找 `Rerender Final` click | `wait_text("rerender:final-clicked")` 成功。 | 跳过（fixture 无 Rerender Final 按钮） |
| ATC-12 | input 成功后错误 keys(index) 再恢复 | `browser_state` 找 `Smart search`；`input("omega")`；错误执行 `keys(index=旧输入框index, text="Enter")`；再按 `suggested_args` 执行 keys without index | 错误调用应 `state_missing` 且有 hint/suggested_args；恢复后 `wait_text("search:enter:omega")` 成功。 | 通过 |
| ATC-13 | Guard：disabled 到 enabled | `browser_state` 找 `Guard Submit` click；重新 state 找 `Guarded input`，`input("unlock")`；重新 state 找 `Guard Submit` click | 第一次 click 失败；输入后 click 成功，`wait_text("guard:submitted")` 成功。 | 通过 |
| ATC-14 | Backspace 非清空语义 | `browser_state` 找 `Guarded input`；`input("unlock")`；`keys("Backspace")` without index；重新 state 查看 value | 当前实现是删除末尾一个字符，预期 value 为 `unloc`；不要把 `Control+A + Backspace` 当成清空整框的强保证。 | 通过 |

## P3 大列表与截断

| ID | 场景 | 工具编排 | 预期 | 结果 |
| --- | --- | --- | --- | --- |
| ATC-20 | 大列表生成后 state 被清空 | `browser_state` 找 `Build Large List` click；直接旧 index 点任意旧元素 | indexed action 应 `state_missing`；需要重新 state。 | 通过 |
| ATC-21 | 默认 max_elements 截断 | ATC-20 后 `browser_state(max_elements=120)`，查找 `Row Action 160` | 默认 120 以内不应保证能看到第 160 项；GA 不能声称未出现就是页面没有。 | 通过（120 未命中，300 命中） |
| ATC-22 | 提高 max_elements 找深层元素 | `browser_state(max_elements=220)` 找 `Row Action 160` click | `wait_text("large-list:clicked:160")` 成功。 | 通过 |
| ATC-23 | aria-label 和 text 混合识别 | 在大列表中查找 `row action 37` 或 `Row Action 037` | GA 应基于 state 返回字段选择目标，不应只靠肉眼猜 index。 | 通过 |

## P4 wait_index 边界

| ID | 场景 | 工具编排 | 预期 | 结果 |
| --- | --- | --- | --- | --- |
| ATC-30 | detached 后同身份 fallback 成功 | `browser_state` 找 `Identity Target` 记 index；用 `web_execute_js` 把该节点 `outerHTML` 替换成同 id 同文本 button；执行 `wait_index(index, timeout=3)` | 返回 `status=success`、`result=element_visible`。 | 通过 |
| ATC-31 | detached 后文本身份变化应失败 | `browser_state` 找 `Identity Target` 记 index；用 `web_execute_js` 替换为同 id 但文本 `Changed Identity`；执行 `wait_index(index, timeout=2)` | 应 timeout；因为 selector 命中但 tag/role/text identity 不匹配。 | 通过 |
| ATC-32 | attached hidden 不 fallback | `browser_state` 找 `Duplicate Wait` 记 index；用 `web_execute_js` 把原节点隐藏，并在后面追加同 id 同文本可见按钮；执行 `wait_index(index, timeout=2)` | 应 timeout；cached node 仍 attached 但 hidden 时不会 fallback。 | 通过 |
| ATC-33 | querySelector 首个候选风险 | 构造两个同 selector 候选，第一个 hidden，第二个 visible；执行依赖 selector fallback 的 `wait_index` | 可能 timeout；记录这是 `document.querySelector` 只取首个候选的实现边界，不算工具阻断。 | 通过（index 非 selector，直接命中 visible；querySelector 首候选 hidden 边界已记录） |

## P4 iframe、层级、富文本和元数据

| ID | 场景 | 工具编排 | 预期 | 结果 |
| --- | --- | --- | --- | --- |
| ATC-34 | 同源 iframe indexed 操作 | `browser_state` 找 `Frame Action` / `Frame query`，确认元素含 `frame_path`、`frame_depth`、`frame_title`；对 `Frame query` 执行 `input(..., verify="field_value", verify_value="inside frame")`，或 click `Frame Action` 后 `wait_text("frame action clicked")` | 同源 iframe 内元素可按 index 操作；不得把结论推广到跨域 iframe。 | 待测 |
| ATC-35 | contenteditable 直接输入 | `browser_state` 找 `rich seed`，执行 `input(index, text="rich edited", verify="field_value", verify_value="rich edited")` | contenteditable 文本被直接设置并通过 `field_value` 验证；不要用编辑器私有 API 作为通过条件。 | 待测 |
| ATC-36 | 同源 iframe editor body | `browser_state` 找 `iframe editor seed` 的 editor body，确认 frame metadata；执行 `input(index, text="iframe rich edited", verify="field_value", verify_value="iframe rich edited")` | 同源 iframe editor body 可作为 contenteditable 输入目标；跨域 editor iframe 不纳入高层工具通过项。 | 待测 |
| ATC-37 | overlay layer priority | `browser_state` 找 `Open Layered Menu` click；重新 `browser_state` 检查 `Modal Primary` 和 `Layered Option` 的 `layer`、`layer_root_hint`、`modal_rank`；优先 click 可见顶层 `Layered Option` | overlay/dropdown 元素带 layer metadata，GA 选择目标时不应误点底层同名控件。 | 待测 |
| ATC-38 | 元数据检查 | `browser_state(max_elements=200)` 检查 `Metadata Label`、`Metadata Row Action` 和 `metadata-input` | 元素应包含 labels、validation、control_kind、action_hints、table_context；table_context 是只读辅助，不代表有单元格编辑 wrapper。 | 待测 |

## P4 自定义组件和错误路径切换

| ID | 场景 | 工具编排 | 预期 | 结果 |
| --- | --- | --- | --- | --- |
| ATC-40 | 原生 select 成功 | `browser_state` 找 `native-priority`，执行 `select(value="high")` | `wait_text("native-priority:high")` 成功。 | 通过 |
| ATC-41 | fake combobox 不能用 select | `browser_state` 找 `Fake Priority`，执行 `select(value="high")` | 返回 `invalid_args`；不能把 fake combobox 当原生 select。 | 通过 |
| ATC-42 | AntD-like fake combobox click/state/click 路径 | ATC-41 后重新 state 找 `Fake Priority` click；重新 state 找 `Fake High` 可见选项 click | `wait_text("fake-priority:high")` 成功；这是“失败后换正确路径”，不是重复 select。若菜单项不可索引，切 `tmwebdriver_sop`。 | 通过 |
| ATC-43 | 连续失败两次停止 | 对同一个 fake combobox 连续两次 `select` 失败 | GA 应停止继续 select，并明确切换到 click 流或 `tmwebdriver_sop`，不能第三次重复同一动作。 | 通过（连续两次 invalid_args） |
| ATC-44 | selector 误用防线 | 对 `#fake-high` 直接执行 `browser_action(click, selector="#fake-high")` | 应 `invalid_args`；GA 应改为 `browser_state` 找 index，而不是继续 selector click。 | 通过（工具层已拒绝 selector click） |


## P4 tab state 隔离

此组是可选高难度项，取决于当前 TMWebDriver 是否能稳定列出多个 Chrome session。

| ID | 场景 | 工具编排 | 预期 |
| --- | --- | --- | --- |
| ATC-50 | tab_id state 绑定 | 准备两个标签页 A/B；在 A 执行 `browser_state(tab_id=A)` 获取 index；切到 B 后用 A 的 index 执行 indexed click | 应返回 `stale_index`，错误信息指向当前 tab 需要重新 state。 | 通过 |
| ATC-51 | tab_id 显式恢复 | 在 B 执行 `browser_state(tab_id=B)`，再执行 B 的 indexed click | 应成功，且返回中的 `tab_id` 与 B 一致。 | 通过 |
| ATC-52 | wait_text 可跨 tab 显式执行 | 在 A/B 分别放不同 status 文本；用 `browser_action(wait_text, tab_id=A/B, text=对应文本)` | 对应 tab 成功，错误 tab timeout。 | 通过 |

## P4 真实站点连续任务

真实站点只验证“操作策略”，不要求固定 DOM。禁止执行破坏性提交、删除、付款、发布。

| ID | 场景 | 工具编排 | 预期 |
| --- | --- | --- | --- |
| ATC-60 | 登录态页面连续三步 | 在用户已登录站点中执行：打开无害功能区、输入搜索、提交、打开结果详情或筛选项 | 每步 mutation 后重新 state；输入提交使用 keys without index；最终有页面证据。 | 部分通过（日报页已登录可见，textarea输入成功；部分字段因框架拒绝input，验证了真实站点差异） |
| ATC-61 | 搜索建议型输入框 | 找一个输入后弹建议的真实搜索框；`input` 后直接 `keys Enter`；另跑一次 `input` 后重新 state 点建议项 | 两条路径都能解释清楚何时不重扫、何时必须重扫。 | 未测（日报页无搜索建议框） |
| ATC-62 | 复杂前端 Select | 找 AntD/MUI/Vue Select；先错误尝试 `select` 一次，记录 `invalid_args`；再用 click 展开并点选可索引项 | 若菜单项无法索引，必须切 `tmwebdriver_sop`，不能继续重复 browser_action。 | 部分通过（日报页有自定义 combobox index 4/7/8，可操作但菜单项索引不清晰） |
| ATC-63 | 页面加载慢 | click 后页面 1-3 秒才出现结果；优先 `wait_text` 或 `wait_selector`，不要立即反复 state | 等待成功后再 state；若 timeout，要记录 timeout 而不是猜测成功。 | 未测 |
| ATC-64 | 已登录态保护 | 验证新工具使用当前真实 Chrome 的登录态完成只读/无害操作 | 不要求重新登录，不要求导出 Cookie；若登录态不可用，应报告浏览器状态问题。 | 通过（日报页直接打开且登录态完整继承，无需重新认证） |

## 高级测试结论模板

注意：以下是填写模板，不是已完成的测试结论。执行清单后必须用真实工具返回和页面证据替换 `<待填写>`；若 ATC-34~38 仍为 `待测`，不得在汇总或关键证据中写成已通过。

```md
# GA 浏览器操作高级能力验证结论

测试日期：<待填写>
测试分支：<待填写>
基础清单结果：<待填写>
Chrome 状态：<待填写>

## 汇总

| 等级 | 通过 | 未通过 | 跳过 | 说明 |
| --- | --- | --- | --- | --- |
| P1 | <待填写> | <待填写> | <待填写> | <填写已执行用例和证据> |
| P3 | <待填写> | <待填写> | <待填写> | <填写已执行用例和证据> |
| P4 (wait_index) | <待填写> | <待填写> | <待填写> | <填写已执行用例和证据> |
| P4 (iframe/layer/metadata) | <待填写> | <待填写> | <待填写> | <若 ATC-34~38 仍为待测，不得填写通过> |
| P4 (自定义组件) | <待填写> | <待填写> | <待填写> | <填写已执行用例和证据> |
| P4 (tab隔离) | <待填写> | <待填写> | <待填写> | <填写已执行用例和证据> |
| P4 (真实站点) | <待填写> | <待填写> | <待填写> | <区分通过、部分通过、未测> |

## 关键证据

- <ATC-ID>：<工具序列> -> <关键返回 status/stage/result> -> <页面证据>
- <ATC-ID>：<工具序列> -> <关键返回 status/stage/result> -> <页面证据>
- <ATC-ID>：<工具序列> -> <关键返回 status/stage/result> -> <页面证据>

## 结论

- **新工具是否足以作为 GA 默认高层浏览器操作入口**：<基于本轮真实证据填写>
- **哪些复杂场景应立即切回 `tmwebdriver_sop`**：<基于本轮真实失败/跳过证据填写>
- **GA 工具编排仍需优化的问题**：<基于本轮工具序列和失败证据填写>
```
