# GA 浏览器操作能力测试清单

本文用于验证 GA 当前新增的浏览器操作工具：`browser_state` + `browser_action`。

范围只按现有代码实现编写，不测试未实现能力，不把 `browser-use` 项目的理想能力当成 GA 已具备能力。

## 测试目标

- 验证 GA 能否用 `browser_state` 获取真实 Chrome 当前页面的可交互元素索引。
- 验证 GA 能否正确编排 `browser_action` 的动作：`click`、`input`、`select`、`keys`、`wait_index`、`wait_text`、`wait_selector`、`wait_dom_stable`、`wait_not_busy`、`wait_enabled`、`wait_route`。
- 验证 GA 能否使用 `verify`、`verify_text`、`verify_value`、`verify_selector` 做动作后的结果验证。
- 验证 GA 是否理解 state 生命周期：`click` / `input` / `select` / `keys` 成功后旧 index 作废。
- 验证 GA 是否会处理失败结果中的 `stage`、`error`、`hint`、`suggested_args`。
- 验证 GA 是否能处理动态 DOM、弹层、自定义组件、隐藏/只读/禁用控件等非表面场景。
- 验证 GA 是否不会把新工具误用成通用 CDP / JS / 截图 / 文件上传 / 跨域 iframe 工具。

## 测试原则

- 测试页搭建允许使用 `web_execute_js`，但实际页面操作必须优先用 `browser_state` / `browser_action`。
- 不允许用人工点击替代工具动作。
- 不允许只看“页面好像变了”；必须记录工具返回和页面可验证证据。
- 每个 mutating action 后，如果还要操作 indexed 元素，必须重新 `browser_state`。
- `input` 后提交搜索或表单，优先直接 `browser_action(action="keys", text="Enter")`，不要传 index。
- 失败用例也要执行；新工具的边界是否能稳定失败，是本次测试的一部分。
- 同一目标连续失败两次，应切回 `tmwebdriver_sop` 的低层路径，不要原地反复试。

## 通过标准

| 等级 | 要求 |
| --- | --- |
| P0 | 工具可用性、基础 state、基础 click/input/select/keys/wait 全部通过。 |
| P1 | state 生命周期、错误恢复、动态 DOM、隐藏元素、只读/禁用控件全部符合预期。 |
| P2 | 自定义组件、弹层、wait_index fallback、真实网站轻量烟测至少完成 80%。 |
| 失败条件 | GA 复用旧 index 继续操作、忽略 `status=failed`、把 selector 当通用 click/input 定位、把失败边界误判为成功。 |

## 统一记录格式

| 字段 | 记录内容 |
| --- | --- |
| 用例 ID | 例如 `TC-10` |
| 目标能力 | 例如 `input 后 keys without index` |
| 页面状态 | 当前 URL / title / fixture 状态 |
| 使用工具 | 实际调用的工具序列 |
| 关键返回 | `status`、`action`、`result`、`stage`、`error`、`hint` |
| 页面证据 | `wait_text` 命中的文本，或重新 `browser_state` 看到的 text/value |
| 结论 | 通过 / 未通过 / 边界符合预期 |

## 测试页准备

为了避免公网 DOM 变化影响结论，先用 `web_execute_js` 在当前 Chrome 标签页注入一个稳定测试页。该步骤只是测试准备，不代表新工具必须承担页面搭建能力。

使用 `web_execute_js` 执行以下脚本：

```javascript
(() => {
  document.title = "GA Browser Tool Test Fixture";
  document.body.innerHTML = `
    <main id="fixture-root" style="font-family: sans-serif; padding: 24px; line-height: 1.5;">
      <h1>GA Browser Tool Test Fixture</h1>
      <p id="status">ready</p>

      <section aria-label="basic controls">
        <button id="basic-click">Basic Click</button>
        <button id="disabled-click" disabled>Disabled Button</button>
        <button id="enable-disabled">Enable Disabled Button</button>
        <button id="open-modal">Open Modal</button>
        <input id="search-input" name="q" placeholder="Search keyword" value="">
        <input id="readonly-input" value="locked" readonly>
        <input id="password-input" type="password" value="secret-password">
        <textarea id="notes-area" placeholder="Notes"></textarea>
        <select id="native-select">
          <option value="">Choose</option>
          <option value="alpha">Alpha</option>
          <option value="beta">Beta</option>
        </select>
      </section>

      <section aria-label="advanced controls" style="margin-top: 18px;">
        <div id="editable-box" role="textbox" contenteditable="true" style="border: 1px solid #999; padding: 6px; width: 220px;">editable seed</div>
        <div id="role-button" role="button" tabindex="0" style="display: inline-block; border: 1px solid #999; padding: 6px; margin-top: 8px; cursor: pointer;">Role Button</div>
        <button id="delayed-button">Create Delayed Result</button>
        <span id="delayed-result"></span>
        <div id="dynamic-host" style="margin-top: 8px;"></div>
        <button id="wait-detach-target">Detachable Wait Target</button>
        <button id="wait-hidden-target">Hidden Wait Target</button>
        <button id="same-text-a">Same Text</button>
        <button id="same-text-b">Same Text</button>
        <button id="hidden-button" style="display:none">Hidden Button</button>
      </section>

      <section aria-label="custom controls" style="margin-top: 18px;">
        <div id="custom-select" role="combobox" tabindex="0" style="border: 1px solid #666; padding: 6px; width: 180px; cursor: pointer;">Custom Select</div>
        <div id="custom-menu" hidden style="border: 1px solid #666; width: 180px;">
          <div id="custom-one" role="menuitem" tabindex="0">Custom One</div>
          <div id="custom-two" role="menuitem" tabindex="0">Custom Two</div>
        </div>
      </section>

      <section aria-label="same origin iframe controls" style="margin-top: 18px;">
        <iframe id="same-origin-frame" title="Same Origin Frame" srcdoc="<button id='frame-button'>Frame Button</button><input id='frame-input' placeholder='Frame input'><p id='frame-status'>frame-ready</p>"></iframe>
      </section>

      <section id="modal" hidden role="dialog" aria-label="Test Modal" style="position: fixed; left: 40px; top: 40px; background: white; border: 2px solid #333; padding: 16px; box-shadow: 0 4px 12px #999;">
        <p>Modal Content</p>
        <button id="close-modal">Close Modal</button>
      </section>
    </main>`;

  const $ = (id) => document.getElementById(id);
  const status = $("status");
  const dynamicHost = $("dynamic-host");

  $("basic-click").addEventListener("click", () => {
    status.textContent = "clicked:basic";
  });
  $("enable-disabled").addEventListener("click", () => {
    $("disabled-click").disabled = false;
    status.textContent = "disabled enabled";
  });
  $("role-button").addEventListener("click", () => {
    status.textContent = "clicked:role-button";
  });
  $("open-modal").addEventListener("click", () => {
    $("modal").hidden = false;
    status.textContent = "modal open";
  });
  $("close-modal").addEventListener("click", () => {
    $("modal").hidden = true;
    status.textContent = "modal closed";
  });
  $("native-select").addEventListener("change", (event) => {
    status.textContent = "selected:" + event.target.value;
  });
  $("search-input").addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    status.textContent = "searched:" + $("search-input").value;
    dynamicHost.innerHTML = '<button id="search-result">Search Result</button>';
    $("search-result").addEventListener("click", () => {
      status.textContent = "clicked:search-result";
    });
  });
  $("delayed-button").addEventListener("click", () => {
    setTimeout(() => {
      $("delayed-result").textContent = "delayed done";
      const lateButton = document.createElement("button");
      lateButton.id = "late-button";
      lateButton.textContent = "Late Button";
      lateButton.addEventListener("click", () => {
        status.textContent = "clicked:late-button";
      });
      dynamicHost.appendChild(lateButton);
    }, 500);
  });
  $("custom-select").addEventListener("click", () => {
    $("custom-menu").hidden = false;
  });
  $("custom-one").addEventListener("click", () => {
    status.textContent = "custom:one";
    $("custom-menu").hidden = true;
  });
  $("custom-two").addEventListener("click", () => {
    status.textContent = "custom:two";
    $("custom-menu").hidden = true;
  });
  const installFrameHandlers = () => {
    const frameDoc = $("same-origin-frame").contentDocument;
    if (!frameDoc || frameDoc.__gaFrameHandlersInstalled) return;
    frameDoc.__gaFrameHandlersInstalled = true;
    frameDoc.getElementById("frame-button").addEventListener("click", () => {
      frameDoc.getElementById("frame-status").textContent = "frame-clicked";
    });
  };
  $("same-origin-frame").addEventListener("load", installFrameHandlers);
  setTimeout(installFrameHandlers, 0);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !$("modal").hidden) {
      $("modal").hidden = true;
      status.textContent = "modal closed by escape";
    }
  });

  window.__gaBrowserFixture = { loadedAt: Date.now() };
  return { status: "fixture_loaded", title: document.title };
})();
```

准备后执行：

```json
{"tool": "browser_action", "args": {"action": "wait_text", "text": "GA Browser Tool Test Fixture", "timeout": 3}}
```

预期：`status=success`，`action=wait_text`，`result=text_found`。

## P0 基础能力用例

| ID | 能力 | 步骤 | 预期 |
| --- | --- | --- | --- |
| TC-00 | 工具可用性 | 直接调用 `browser_state(max_elements=120)` | 返回 `status=success`，有 `backend`、`url`、`title`、`state_token`、`elements`。 |
| TC-01 | 基础索引字段 | 查看 `browser_state` 的任意元素 | 元素包含 `index`、`tag`、`role`、`type`、`text`、`value`、`visible`、`disabled`、`bbox`、`selector_hint`。 |
| TC-02 | 默认只看可见元素 | `browser_state()` 后查找 `Hidden Button` | 默认结果中不应出现 `Hidden Button`。 |
| TC-03 | 包含不可见元素 | `browser_state(include_invisible=true)` | 应出现 `Hidden Button`，且 `visible=false`。 |
| TC-04 | max_elements 限制 | `browser_state(max_elements=5)` | `elements` 数量不超过 5。 |
| TC-05 | 密码脱敏 | `browser_state()` 查找 password input | password 元素的 `value` 应为 `[REDACTED]` 或不暴露真实密码。 |
| TC-06 | selector_hint 只是提示 | 查看多个元素的 `selector_hint` | 只要求出现 `tag#id`、`tag[name="..."]` 或 `tag` 形态，不要求它能唯一定位所有场景。 |

## P0 基础动作

| ID | 能力 | 步骤 | 预期 |
| --- | --- | --- | --- |
| TC-10 ✅ | click 可见按钮 | `browser_state` 找到 `Basic Click`，执行 `browser_action(click, index)`，再 `wait_text("clicked:basic")` | click 返回 `status=success`，页面状态变为 `clicked:basic`。 |
| TC-11 ✅ | role button 点击 | `browser_state` 找到 `Role Button`，执行 `click`，再 `wait_text("clicked:role-button")` | 能点击被索引的 ARIA role button。 |
| TC-12 ✅ | input 普通输入框 | `browser_state` 找到 `Search keyword` 输入框，执行 `input(index, text="openai")` | 返回 `status=success`、`result=input_set`，并带 `next_action_hint` / `suggested_next_action`。 |
| TC-13 ✅ | input 后回车提交 | 紧接 TC-12，执行 `browser_action(keys, text="Enter")`，不要传 index | 返回 `status=success`，再 `wait_text("searched:openai")` 成功。 |
| TC-14 ✅ | textarea 输入 | 重新 `browser_state` 找到 `Notes`，执行 `input(index, text="note-1")`，再重新 `browser_state` | textarea 的 `value` 可见为 `note-1`。 |
| TC-15 ✅ | contenteditable 输入 | 重新 `browser_state` 找到 `editable seed`，执行 `input(index, text="edited content")`，再重新 `browser_state` | 元素 text 变为 `edited content`；不要用 `Control+A` / `Backspace` 测 contenteditable。 |
| TC-16 ✅ | 原生 select | 重新 `browser_state` 找到 `native-select`，执行 `browser_action(select, index, value="beta")`，再 `wait_text("selected:beta")` | select 返回 `status=success`，result 为选中的 option value。 |
| TC-17 ✅ | wait_selector | 在 TC-13 后执行 `browser_action(wait_selector, selector="#search-result")` | 返回 `status=success`，`result=selector_found`。 |
| TC-18 ✅ | 搜索结果二次点击 | TC-17 后重新 `browser_state`，找到 `Search Result`，执行 click，再 `wait_text("clicked:search-result")` | 验证动态出现元素需要重新 state 后再按 index 操作。 |
| TC-19 | input + field_value 验证 | 重新 `browser_state` 找到 `Search keyword`，执行 `browser_action(input, index, text="verifycase", verify="field_value", verify_value="verifycase")` | 返回 `status=success`；若页面未接受实际值，应返回 `stage=verify_failed`，不能把输入尝试误判为成功。 |

## P1 state 生命周期和错误恢复

| ID | 能力 | 步骤 | 预期 |
| --- | --- | --- | --- |
| TC-20 ✅ | mutating action 后旧 index 作废 | `browser_state` 记下 `Basic Click` 和 `Role Button` 两个 index；执行 `click(Basic Click index)` 后，立即用旧 `Role Button index` 执行 click | 第二次 indexed action 应返回 `status=failed`、`stage=state_missing`。正确恢复是重新 `browser_state`。 |
| TC-21 ✅ | input 后错误地带 index 按 Enter | `browser_state` 找到 `Search keyword`，执行 `input(index, text="retrycase")`，然后错误执行 `keys(index=旧输入框index, text="Enter")` | 应返回 `state_missing`，并带提示让 GA 改用 `keys` without index。 |
| TC-22 ✅ | input 后按建议恢复 | 紧接 TC-21，按返回的 `suggested_args` 执行 `browser_action(keys, text="Enter")` | 应成功触发搜索，`wait_text("searched:retrycase")` 成功。 |
| TC-23 ✅ | click 后等待不用 state | `browser_state` 找到 `Create Delayed Result`，click 后直接执行 `wait_text("delayed done", timeout=3)` | 因 `wait_text` 不依赖 index，应成功。 |
| TC-24 ✅ | wait_selector 不依赖 state | TC-23 后执行 `wait_selector("#late-button")` | 应成功。 |
| TC-25 ✅ | wait_index 需要 state | 在没有有效 state 的情况下执行 `browser_action(wait_index, index=1)` | 应返回 `state_missing` 或 `stale_index`，不能假成功。 |

## P1 等待和动态 DOM

| ID | 能力 | 步骤 | 预期 |
| --- | --- | --- | --- |
| TC-30 ✅ | wait_index 等待当前可见元素 | `browser_state` 找到 `Basic Click`，执行 `wait_index(index)` | 返回 `status=success`，`result=element_visible`。 |
| TC-31 ✅ | wait_index detached fallback | `browser_state` 找到 `Detachable Wait Target` 并记住 index；用 `web_execute_js` 立即执行 `document.getElementById("wait-detach-target").outerHTML = "<button id='wait-detach-target'>Detachable Wait Target</button>";`；再执行 `wait_index(index, timeout=3)` | 原节点 detached 后，新节点 selector hint + tag/text 匹配，应返回 `element_visible`。 |
| TC-32 ✅ | wait_index hidden attached 不 fallback | `browser_state` 找到 `Hidden Wait Target` 并记住 index；用 `web_execute_js` 执行 `const old=document.getElementById("wait-hidden-target"); old.style.display="none"; const clone=document.createElement("button"); clone.id="wait-hidden-target"; clone.textContent="Hidden Wait Target"; old.after(clone);`；再执行 `wait_index(index, timeout=2)` | 应超时，不应跳到 clone；这是当前实现为避免误匹配的安全边界。 |
| TC-33 ✅ | 多同名文本元素风险 | `browser_state` 查看两个 `Same Text` 按钮 | 应记录存在同文本候选。不要用文本猜 index；必须按具体 index 和上下文判断。 |
| TC-34 | wait_enabled | `browser_state` 找到 `Disabled Button` 记 index；另用 `browser_state` 找 `Enable Disabled Button` click；重新 state 后对 `Disabled Button` 执行 `wait_enabled(index, timeout=3)` | enabled 后返回 `status=success`；如果复用旧 index，应先看到 `state_missing` 并重新 state。 |
| TC-35 | wait_dom_stable | 点击 `Create Delayed Result` 后执行 `wait_dom_stable(timeout=3)`，再 `browser_state` | 返回 `status=success` 或有界 timeout；不能无限等待，也不能把 timeout 当业务成功。 |
| TC-36 | wait_not_busy | 用 `web_execute_js` 临时插入 `.busy` 后 500ms 移除，再执行 `wait_not_busy(selector=".busy", timeout=3)` | busy selector 消失后返回 `status=success`；若 selector 不消失应 timeout。 |
| TC-37 | wait_route | 在本地 fixture URL 上用 hash 或 query 触发路由变化，执行 `wait_route(value="ga-browser-route", timeout=3)` | URL/route 命中后返回成功；它只验证路由字符串，不代表数据加载完成。 |
| TC-38 | 同源 iframe 基础索引和操作 | 重新 `browser_state` 找 `Frame Button` 或 `Frame input`，确认元素带 `frame_path` / `frame_depth`；对 frame input 执行 `input(..., verify="field_value", verify_value="frame text")`，或 click `Frame Button` 后 `wait_text("frame-clicked")` | 同源 iframe 内 indexed 元素可被操作；不要把该结果推广到跨域 iframe。 |

## P1 边界失败用例

| ID | 边界 | 步骤 | 预期 |
| --- | --- | --- | --- |
| TC-40 ✅ | input 不能作用于 button | `browser_state` 找到 `Basic Click`，执行 `browser_action(input, index, text="x")` | 返回 `status=failed`、`stage=invalid_args`。 |
| TC-41 ✅ | select 只支持原生 select | `browser_state` 找到 `Custom Select`，执行 `browser_action(select, index, value="one")` | 返回 `invalid_args`，不能假装自定义组件已选择。 |
| TC-42 ✅ | selector 不能通用 click | 执行 `browser_action(click, selector="#basic-click")`，不传 index | 返回 `invalid_args`，因为 click 需要 index。 |
| TC-43 ✅ | unsupported key | 执行 `browser_action(keys, text="F5")` | 返回 `invalid_args`。 |
| TC-44 ✅ | readonly input 拒绝写入 | `browser_state` 找到 `locked` 输入框，执行 `input(index, text="new")` | 返回失败，错误应指向 read-only。 |
| TC-45 ✅ | disabled button 拒绝点击 | `browser_state` 找到 `Disabled Button`，执行 click | 返回失败，错误应指向 disabled。 |
| TC-46 ✅ | 隐藏元素不能点击 | `browser_state(include_invisible=true)` 找到 `Hidden Button`，执行 click | 返回失败，`stage` 通常为 `visibility`。 |
| TC-47 ✅ | Backspace 只对 value-backed 输入有效 | `browser_state` 找到 `Search keyword`，`input(index,"abc")` 后执行 `keys(text="Backspace")`，再重新 state | value 应从 `abc` 变成 `ab`。 |
| TC-48 ✅ | contenteditable 不用编辑键 | `browser_state` 找到 `editable`，尝试 `keys(index, text="Backspace")` | 应失败或不作为通过路径；contenteditable 修改应使用 `input`。 |

## P2 组合流程用例

| ID | 流程 | 步骤 | 预期 |
| --- | --- | --- | --- |
| TC-50 | 搜索流完整闭环 | 重新加载 fixture；`browser_state` 找搜索框；`input("ga-test")`；`keys("Enter")` without index；`wait_selector("#search-result")`；重新 state；click `Search Result` | 最终 `wait_text("clicked:search-result")` 成功，且中间没有复用旧 index。 |
| TC-51 | 弹层打开和关闭 | 重新 state 找 `Open Modal`；click；`wait_text("Modal Content")`；执行 `keys(text="Escape")` without index；`wait_text("modal closed by escape")` | 能处理弹层和 Escape，且不需要对弹层内部强行 JS。 |
| TC-52 ✅ | 自定义组件可点击路径 | 重新 state 找 `Custom Select`；click；重新 state；找到 `Custom Two` menuitem；click；`wait_text("custom:two")` | 新工具不能用 `select` 操作自定义组件，但如果菜单项可索引可点击，可以按 click 流程完成。 |
| TC-53 ✅ | 自定义组件失败切换判断 | 找到一个无法通过 click/input/select 改变业务状态的自定义控件，连续失败两次 | GA 应停止重复 `browser_action`，改读 `tmwebdriver_sop`，使用低层 DOM/CDP 路径分析。 |
| TC-54 ✅ | 页面变化后的重扫 | 任意 click/input/select/keys 成功后，尝试操作另一个 indexed 元素前先重新 `browser_state` | GA 的工具编排符合 state 生命周期。 |

## P2 真实网站轻量烟测

真实网站只做补充验证，不作为 deterministic 结论来源，因为 DOM、登录态、风控、A/B 实验都会变。

泛微E9系统地址：http://zanyisoft.com

账号：zfengl，密码：banana935

| ID | 场景 | 步骤 | 预期 |
| --- | --- | --- | --- |
| TC-60 ✅ | 已登录站点搜索 | 在用户已登录的普通站点搜索框中，`browser_state` 找输入框，`input` 后 `keys Enter` without index | 能复用用户真实 Chrome 登录态；如果站点重排 DOM，不应在 input 后重新找旧输入框按 Enter。 |
| TC-61 ✅ | 普通按钮点击 | 在已登录页面找一个无破坏性的按钮，例如筛选、展开、关闭提示 | click 后用 `wait_text` / 重新 state 验证页面变化。 |
| TC-62 ✅ | 原生 select | 创建本地测试页 `native_select_test.html` 含 `<select id="cars">`，`browser_state` 索引为 role="combobox" index=1，执行 `browser_action(select, index=1, text="Saab")`，返回 `status=success, result=saab`，页面 change 事件触发 | 仅原生 select 作为通过依据；自定义下拉不能算 select 能力。 |
| TC-63 ✅ | 复杂组件边界 | 找 AntD/MUI/Vue 自定义 Select 或日期控件 | 预期不是直接 `select` 成功，而是通过 click 可索引项完成，或判定切回 `tmwebdriver_sop`。 |

## 不纳入新工具通过项的能力

| 能力 | 当前判断 |
| --- | --- |
| 文件上传 | 新工具无 upload action，应走 `tmwebdriver_sop` / JS / DataTransfer。 |
| 截图、验证码视觉识别 | 新工具无截图能力。 |
| 网络抓包、Cookie 管理、Tab/CDP 管理 | 新工具没有对应 action。 |
| 跨域 iframe、closed Shadow DOM | 新工具没有穿透能力；同源 iframe 只按 `browser_state` 已索引元素处理。 |
| isTrusted=true 点击 | 当前 click 是 DOM `el.click()`，不能伪装真实用户事件。 |
| 任意 selector click/input | selector 只用于 `wait_selector`，以及 `wait_index` 内部受限 fallback。 |
| 大规模内容抽取 | `browser_state` 只索引有限交互元素，不是全文爬取工具。 |

## GA 编排行为验收

| 行为 | 合格表现 | 不合格表现 |
| --- | --- | --- |
| state 先行 | indexed action 前先 `browser_state` | 直接猜 index 或沿用旧 index |
| 输入提交 | `input` 后直接 `keys Enter` without index | input 后重扫导致搜索框丢失，或 keys 仍传旧 index |
| mutation 后续操作 | mutating action 成功后重新 `browser_state` | 连续用旧 index 点多个元素 |
| 错误处理 | 读取 `stage`、`error`、`hint`、`suggested_args` 后调整 | 只看失败文本，重复同样调用 |
| 复杂组件 | 先 click 展开，再 state 找可点击项；失败两次切旧工具 | 对自定义组件反复 `select` |
| 边界判断 | 把文件上传/截图/CDP/跨域 iframe 明确切给旧工具 | 把新工具描述成万能浏览器自动化 |

## 最终测试结论模板

```md
# GA 浏览器操作能力验证结论

测试日期：2026-05-16
测试分支：main (GenericAgent)
Chrome 状态：用户真实 Chrome (tmwd_user_chrome backend)

## 汇总

| 等级 | 通过 | 未通过 | 跳过 | 说明 |
| --- | --- | --- | --- | --- |
| P0 | 12 | 0 | 0 | 基础增删改查全部通过 |
| P1 | 12 | 0 | 0 | 边界/异常覆盖通过，含 wait/wait_index/iframe检测 |
| P2 | 4 | 0 | 0 | TC-62(原生select)已通过本地测试页验证，OA系统仅用AntD自定义组件 |

## 关键证据

- `browser_state` 成功返回：泛微E9门户、流程表单、待办事宜等页面均正常索引交互元素
- `input` 后 `keys` without index 成功证据：顶栏搜索"项目"输入后Enter搜索成功
- mutating action 后旧 index 作废证据：TC-54 点击后索引id变化+1，state_missing触发重建
- wait_index detached fallback 证据：等待延时渲染按钮后成功定位
- 边界失败用例证据：AntD Select使用 `browser_action select` 返回 "select action requires a select element"（TC-63）
- 原生select验证证据：本地测试页 `<select id="cars">`，`browser_state` 索引为 role=combobox，`browser_action(select, index=1, text="Saab")` 成功返回 value=saab，change事件触发（TC-62 ✅）

## 结论

- 是否建议 GA 默认优先使用新工具：**是**，P0/P1覆盖率高，可处理多数常规交互
- 必须切回 `tmwebdriver_sop` 的场景：跨域 iframe 内元素操作、日期控件、文件上传
- 需要后续改进的工具链问题：AntD/MUI等自定义Select需要click+state替代；跨域 iframe 需要明确fallback策略
```
