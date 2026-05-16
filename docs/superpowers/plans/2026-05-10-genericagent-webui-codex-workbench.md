# GenericAgent WebUI Codex Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the existing GenericAgent WebUI into a Codex-style professional workbench using Ant Design interactions, without adding subagent, run, artifact, or checkpoint backend support.

**Architecture:** Keep `frontends/webui_server.py` unchanged and treat existing WebUI APIs as the contract. The frontend becomes a three-area workbench: conversation navigation, central chat/composer, and an optional context panel based only on `RuntimeState` and `ExecutionTurn`. Shared decisions live in small state helpers so layout and execution summary behavior can be tested without a browser.

**Tech Stack:** React 18, TypeScript, Ant Design 5, lucide-react, framer-motion, existing CSS/Tailwind pipeline, Node `--experimental-strip-types` tests, Python unittest for WebUI backend regression coverage.

---

## Scope Lock

This plan must not modify:

- `frontends/webui_server.py`
- GA core runtime files
- Any dependency project
- Any contract for subagent, run, artifact, or checkpoint entities

This plan may modify:

- `frontends/webui/src/App.tsx`
- `frontends/webui/src/theme.ts`
- `frontends/webui/src/styles.css`
- `frontends/webui/src/styles/*`
- `frontends/webui/src/components/app/*`
- `frontends/webui/src/components/chat/*`
- `frontends/webui/src/components/composer/*`
- `frontends/webui/src/components/context/*`
- `frontends/webui/src/components/execution/*`
- `frontends/webui/src/components/shell/*`
- `frontends/webui/src/components/sidebar/*`
- `frontends/webui/src/state/*`
- `tests/*.test.mjs`

## File Structure

- `frontends/webui/src/state/workbench-context-state.ts`
  - Pure helpers for context panel tab selection, turn summary, tool-call counts, and runtime label building.
- `tests/webui_workbench_context_state.test.mjs`
  - Node tests for context panel helper behavior.
- `tests/webui_workbench_static.test.mjs`
  - Static regression tests that the workbench uses the intended frontend-only integration points and does not reintroduce subagent inspector surfaces.
- `frontends/webui/src/components/context/WorkbenchContextPanel.tsx`
  - Right-side desktop panel and mobile drawer content based on `RuntimeState` and `ExecutionTurn`.
- `frontends/webui/src/components/context/RuntimeSummaryPanel.tsx`
  - Status summary for configured/running/model/autonomous state.
- `frontends/webui/src/components/context/ExecutionActivityPanel.tsx`
  - Compact activity list based on existing `ExecutionTurn[]`.
- `frontends/webui/src/components/context/ContextPanelHeader.tsx`
  - Header actions for close/collapse and active tab labels.
- `frontends/webui/src/components/shell/TopBar.tsx`
  - Add context panel toggle, clearer workbench status grouping, and tighter action hierarchy.
- `frontends/webui/src/components/sidebar/ConversationSidebar.tsx`
  - Improve row hierarchy, counts, active state, empty state, and action separation.
- `frontends/webui/src/components/chat/ChatHome.tsx`
  - Replace current centered hero feel with compact workbench empty state and input anchor.
- `frontends/webui/src/components/chat/ChatMessageView.tsx`
  - Improve assistant/user message hierarchy and integrate execution block more calmly.
- `frontends/webui/src/components/composer/Composer.tsx`
  - Improve input panel states, helper text, send/stop affordance, and disabled feedback.
- `frontends/webui/src/components/execution/InlineExecutionTurns.tsx`
- `frontends/webui/src/components/execution/InlineExecutionTurn.tsx`
- `frontends/webui/src/components/execution/ExecutionToolCallCard.tsx`
  - Keep inline execution, refine scanability, and share helper labels from `workbench-context-state.ts`.
- `frontends/webui/src/styles/context.css`
  - Styles for the context panel.
- `frontends/webui/src/styles/workbench.css`
  - Desktop layout, Splitter panel, and shell-level responsive rules.
- `frontends/webui/src/styles/sidebar.css`
  - Sidebar polish separated from `shell.css`.
- `frontends/webui/src/styles/chat.css`
  - Message, markdown, and composer refinements.
- `frontends/webui/src/styles/execution.css`
  - Execution block refinements.
- `frontends/webui/src/styles/antd-overrides.css`
  - AntD-specific overrides only.
- `frontends/webui/src/theme.ts`
  - Token tuning for Codex-style workbench.
- `frontends/webui/src/styles.css`
  - Add imports for new CSS files.

---

### Task 1: Add Workbench Context State Helpers

**Files:**
- Create: `frontends/webui/src/state/workbench-context-state.ts`
- Create: `tests/webui_workbench_context_state.test.mjs`

- [ ] **Step 1: Write the failing tests**

Create `tests/webui_workbench_context_state.test.mjs`:

```js
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL } from "node:url";

const moduleUrl = pathToFileURL(
  path.resolve("frontends/webui/src/state/workbench-context-state.ts"),
).href;
const {
  buildRuntimeSummary,
  buildTurnMeta,
  chooseWorkbenchContextTab,
  countToolCalls,
} = await import(moduleUrl);

const runningState = {
  configured: true,
  current_llm: { index: 1, name: "gpt-5.4", current: true },
  llms: [{ index: 1, name: "gpt-5.4", current: true }],
  running: true,
  autonomous_enabled: false,
  last_reply_time: 0,
  active_conversation_id: "conv-1",
  execution_log: [],
};

const idleState = {
  ...runningState,
  running: false,
  autonomous_enabled: true,
  current_llm: null,
};

const activeTurn = {
  turn: 2,
  title: "Inspect files",
  content: "Inspect files",
  state: "active",
  tool_calls: [
    { tool: "rg", args: "query", result: "ok", action: "search", status: "completed" },
    { tool: "sed", args: "file", result: "ok", action: "read", status: "completed" },
  ],
};

const completedTurn = {
  turn: 1,
  title: "",
  content: "Draft answer",
  state: "completed",
  tool_calls: [],
};

test("chooseWorkbenchContextTab prefers activity while work is running", () => {
  assert.equal(chooseWorkbenchContextTab("status", [activeTurn], true), "activity");
});

test("chooseWorkbenchContextTab preserves a valid user tab when idle", () => {
  assert.equal(chooseWorkbenchContextTab("status", [completedTurn], false), "status");
});

test("chooseWorkbenchContextTab falls back to status without execution turns", () => {
  assert.equal(chooseWorkbenchContextTab("activity", [], false), "status");
});

test("chooseWorkbenchContextTab sanitizes an invalid requested tab when idle", () => {
  assert.equal(chooseWorkbenchContextTab("stale", [completedTurn], false), "status");
});

test("countToolCalls sums all turn tool calls", () => {
  assert.equal(countToolCalls([activeTurn, completedTurn]), 2);
});

test("buildTurnMeta exposes compact execution labels", () => {
  assert.deepEqual(buildTurnMeta(activeTurn), {
    title: "Inspect files",
    statusLabel: "执行中",
    toolCallLabel: "2 个工具调用",
  });
  assert.deepEqual(buildTurnMeta(completedTurn), {
    title: "Turn 1",
    statusLabel: "已完成",
    toolCallLabel: "0 个工具调用",
  });
});

test("buildRuntimeSummary reports model and autonomous state", () => {
  assert.deepEqual(buildRuntimeSummary(runningState), {
    configuredLabel: "已配置",
    runningLabel: "任务执行中",
    modelLabel: "gpt-5.4",
    autonomousLabel: "自主行动关闭",
  });
  assert.deepEqual(buildRuntimeSummary(idleState), {
    configuredLabel: "已配置",
    runningLabel: "空闲",
    modelLabel: "未选择模型",
    autonomousLabel: "自主行动开启",
  });
});
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```powershell
node --experimental-strip-types --test tests\webui_workbench_context_state.test.mjs
```

Expected: FAIL with a module-not-found error for `frontends/webui/src/state/workbench-context-state.ts`.

- [ ] **Step 3: Add the helper implementation**

Create `frontends/webui/src/state/workbench-context-state.ts`:

```ts
import type { ExecutionTurn, RuntimeState } from "../types";

type WorkbenchContextTab = "activity" | "status";

export function chooseWorkbenchContextTab(
  requestedTab: WorkbenchContextTab,
  turns: ExecutionTurn[],
  running: boolean,
): WorkbenchContextTab {
  if (running && turns.length > 0) return "activity";
  if (turns.length === 0) return "status";
  if (requestedTab === "activity" || requestedTab === "status") return requestedTab;
  return "status";
}

export function countToolCalls(turns: ExecutionTurn[]): number {
  return turns.reduce((total, turn) => total + (turn.tool_calls?.length ?? 0), 0);
}

export function buildTurnMeta(turn: ExecutionTurn) {
  const toolCount = turn.tool_calls?.length ?? 0;
  return {
    title: turn.title || `Turn ${turn.turn}`,
    statusLabel: turn.state === "active" ? "执行中" : "已完成",
    toolCallLabel: `${toolCount} 个工具调用`,
  };
}

export function buildRuntimeSummary(state: RuntimeState | null) {
  return {
    configuredLabel: state?.configured ? "已配置" : "未配置",
    runningLabel: state?.running ? "任务执行中" : "空闲",
    modelLabel: state?.current_llm?.name ?? "未选择模型",
    autonomousLabel: state?.autonomous_enabled ? "自主行动开启" : "自主行动关闭",
  };
}
```

- [ ] **Step 4: Run the new test and verify it passes**

Run:

```powershell
node --experimental-strip-types --test tests\webui_workbench_context_state.test.mjs
```

Expected: PASS, 6 tests.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add -- frontends/webui/src/state/workbench-context-state.ts tests/webui_workbench_context_state.test.mjs
git commit -m "test: add webui workbench context helpers"
```

---

### Task 2: Add Frontend-Only Context Panel Components

**Files:**
- Create: `frontends/webui/src/components/context/ContextPanelHeader.tsx`
- Create: `frontends/webui/src/components/context/RuntimeSummaryPanel.tsx`
- Create: `frontends/webui/src/components/context/ExecutionActivityPanel.tsx`
- Create: `frontends/webui/src/components/context/WorkbenchContextPanel.tsx`
- Create: `frontends/webui/src/styles/context.css`
- Modify: `frontends/webui/src/styles.css`

- [ ] **Step 1: Create the panel header**

Create `frontends/webui/src/components/context/ContextPanelHeader.tsx`:

```tsx
import { Button, Segmented, Tooltip } from "antd";
import { PanelRightClose } from "lucide-react";
type WorkbenchContextTab = "activity" | "status";

export function ContextPanelHeader({
  activeTab,
  onTabChange,
  onClose,
}: {
  activeTab: WorkbenchContextTab;
  onTabChange: (tab: WorkbenchContextTab) => void;
  onClose?: () => void;
}) {
  return (
    <div className="ga-context-header">
      <div className="min-w-0">
        <div className="text-sm font-semibold text-app-textStrong">工作上下文</div>
        <div className="mt-0.5 text-xs text-app-muted">基于当前会话和执行日志</div>
      </div>
      <Segmented
        size="small"
        value={activeTab}
        options={[
          { label: "执行", value: "activity" },
          { label: "状态", value: "status" },
        ]}
        onChange={(value) => onTabChange(value as WorkbenchContextTab)}
      />
      {onClose ? (
        <Tooltip title="收起上下文面板">
          <Button
            type="text"
            size="small"
            aria-label="收起上下文面板"
            icon={<PanelRightClose className="h-4 w-4" aria-hidden="true" />}
            onClick={onClose}
          />
        </Tooltip>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 2: Create the runtime summary panel**

Create `frontends/webui/src/components/context/RuntimeSummaryPanel.tsx`:

```tsx
import type { ReactNode } from "react";
import { Badge, Tag } from "antd";
import { Activity, Bot, BrainCircuit, Power } from "lucide-react";
import type { RuntimeState } from "../../types";
import { buildRuntimeSummary } from "../../state/workbench-context-state";

function SummaryRow({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="ga-context-summary-row">
      <div className="ga-context-summary-icon">{icon}</div>
      <div className="min-w-0">
        <div className="text-[11px] font-medium uppercase text-app-muted">{label}</div>
        <div className="mt-0.5 truncate text-sm font-medium text-app-text">{value}</div>
      </div>
    </div>
  );
}

export function RuntimeSummaryPanel({ state }: { state: RuntimeState | null }) {
  const summary = buildRuntimeSummary(state);
  return (
    <section className="ga-context-section">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="text-sm font-semibold text-app-textStrong">运行状态</div>
        <Tag bordered={false} color={state?.running ? "processing" : "default"} className="m-0">
          <Badge status={state?.running ? "processing" : "default"} text={summary.runningLabel} />
        </Tag>
      </div>
      <div className="space-y-2">
        <SummaryRow
          icon={<Power className="h-4 w-4" aria-hidden="true" />}
          label="配置"
          value={summary.configuredLabel}
        />
        <SummaryRow
          icon={<Bot className="h-4 w-4" aria-hidden="true" />}
          label="模型"
          value={summary.modelLabel}
        />
        <SummaryRow
          icon={<BrainCircuit className="h-4 w-4" aria-hidden="true" />}
          label="自主行动"
          value={summary.autonomousLabel}
        />
        <SummaryRow
          icon={<Activity className="h-4 w-4" aria-hidden="true" />}
          label="任务"
          value={summary.runningLabel}
        />
      </div>
    </section>
  );
}
```

- [ ] **Step 3: Create the execution activity panel**

Create `frontends/webui/src/components/context/ExecutionActivityPanel.tsx`:

```tsx
import { Empty, Timeline, Tag } from "antd";
import { CircleDot, Wrench } from "lucide-react";
import type { ExecutionTurn } from "../../types";
import { buildTurnMeta, countToolCalls } from "../../state/workbench-context-state";

export function ExecutionActivityPanel({
  turns,
  running,
}: {
  turns: ExecutionTurn[];
  running: boolean;
}) {
  if (turns.length === 0) {
    return (
      <section className="ga-context-section">
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="当前会话还没有执行记录"
        />
      </section>
    );
  }

  return (
    <section className="ga-context-section">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-app-textStrong">执行活动</div>
          <div className="mt-0.5 text-xs text-app-muted">
            {turns.length} 轮 · {countToolCalls(turns)} 个工具调用
          </div>
        </div>
        <Tag bordered={false} color={running ? "processing" : "success"} className="m-0">
          {running ? "执行中" : "已完成"}
        </Tag>
      </div>
      <Timeline
        className="ga-context-timeline"
        items={turns.map((turn) => {
          const meta = buildTurnMeta(turn);
          const active = turn.state === "active";
          return {
            color: active ? "blue" : "green",
            dot: active ? (
              <CircleDot className="h-4 w-4 text-app-primary" aria-hidden="true" />
            ) : undefined,
            children: (
              <div className="ga-context-activity-item">
                <div className="flex min-w-0 items-center justify-between gap-2">
                  <div className="truncate text-sm font-medium text-app-text">{meta.title}</div>
                  <span className="shrink-0 text-[11px] text-app-muted">{meta.statusLabel}</span>
                </div>
                <div className="mt-1 flex items-center gap-1.5 text-xs text-app-muted">
                  <Wrench className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{meta.toolCallLabel}</span>
                </div>
              </div>
            ),
          };
        })}
      />
    </section>
  );
}
```

- [ ] **Step 4: Create the combined panel**

Create `frontends/webui/src/components/context/WorkbenchContextPanel.tsx`:

```tsx
import type { ExecutionTurn, RuntimeState } from "../../types";
type WorkbenchContextTab = "activity" | "status";
import { ContextPanelHeader } from "./ContextPanelHeader";
import { ExecutionActivityPanel } from "./ExecutionActivityPanel";
import { RuntimeSummaryPanel } from "./RuntimeSummaryPanel";

export function WorkbenchContextPanel({
  state,
  turns,
  activeTab,
  onTabChange,
  onClose,
}: {
  state: RuntimeState | null;
  turns: ExecutionTurn[];
  activeTab: WorkbenchContextTab;
  onTabChange: (tab: WorkbenchContextTab) => void;
  onClose?: () => void;
}) {
  return (
    <aside className="ga-context-panel">
      <ContextPanelHeader
        activeTab={activeTab}
        onTabChange={onTabChange}
        onClose={onClose}
      />
      <div className="operation-scroll min-h-0 flex-1 overflow-y-auto px-3 pb-4 pt-3">
        {activeTab === "activity" ? (
          <ExecutionActivityPanel turns={turns} running={Boolean(state?.running)} />
        ) : (
          <RuntimeSummaryPanel state={state} />
        )}
      </div>
    </aside>
  );
}
```

- [ ] **Step 5: Add context panel styles**

Create `frontends/webui/src/styles/context.css`:

```css
.ga-context-panel {
  display: flex;
  min-width: 0;
  min-height: 0;
  height: 100%;
  flex-direction: column;
  border-left: 1px solid #d9e0e8;
  background: #f8fafb;
}

.ga-context-header {
  display: flex;
  min-height: 58px;
  align-items: center;
  gap: 0.75rem;
  border-bottom: 1px solid #d9e0e8;
  padding: 0.75rem;
}

.ga-context-section {
  border: 1px solid #d9e0e8;
  border-radius: 10px;
  background: #ffffff;
  padding: 0.875rem;
}

.ga-context-summary-row {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 0.75rem;
  border-radius: 8px;
  background: #f7f9fb;
  padding: 0.625rem 0.75rem;
}

.ga-context-summary-icon {
  display: inline-flex;
  width: 2rem;
  height: 2rem;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: #0f766e;
  background: #e7f5f2;
}

.ga-context-timeline.ant-timeline {
  margin-top: 0.75rem;
}

.ga-context-timeline .ant-timeline-item {
  padding-bottom: 0.875rem;
}

.ga-context-activity-item {
  min-width: 0;
  border-radius: 8px;
  background: #f7f9fb;
  padding: 0.625rem 0.75rem;
}
```

Modify `frontends/webui/src/styles.css` and insert this import after `execution.css`:

```css
@import "./styles/context.css";
```

- [ ] **Step 6: Run build**

Run:

```powershell
npm --prefix frontends/webui run build
```

Expected: PASS. Existing Vite large chunk warning may appear.

- [ ] **Step 7: Commit Task 2**

Run:

```powershell
git add -- frontends/webui/src/components/context frontends/webui/src/styles/context.css frontends/webui/src/styles.css
git commit -m "feat: add webui context panel components"
```

---

### Task 3: Integrate AntD Workbench Shell

**Files:**
- Modify: `frontends/webui/src/App.tsx`
- Modify: `frontends/webui/src/components/shell/TopBar.tsx`
- Create: `frontends/webui/src/styles/workbench.css`
- Modify: `frontends/webui/src/styles.css`
- Create: `tests/webui_workbench_static.test.mjs`

- [ ] **Step 1: Write static regression tests**

Create `tests/webui_workbench_static.test.mjs`:

```js
import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";

test("workbench integrates the frontend-only context panel", async () => {
  const appSource = await readFile(path.resolve("frontends/webui/src/App.tsx"), "utf8");

  assert.match(appSource, /\bWorkbenchContextPanel\b/);
  assert.match(appSource, /\bchooseWorkbenchContextTab\b/);
  assert.match(appSource, /\bDrawer\b/);
  assert.match(appSource, /\bSplitter\b/);
});

test("workbench does not reintroduce subagent inspector surfaces", async () => {
  const appSource = await readFile(path.resolve("frontends/webui/src/App.tsx"), "utf8");
  const apiSource = await readFile(path.resolve("frontends/webui/src/api.ts"), "utf8");

  assert.doesNotMatch(appSource, /Subagent|subagent|RunInspector|Checkpoint/i);
  assert.doesNotMatch(apiSource, /subagents|runs|checkpoints/i);
});

test("topbar exposes context panel controls", async () => {
  const topBarSource = await readFile(path.resolve("frontends/webui/src/components/shell/TopBar.tsx"), "utf8");

  assert.match(topBarSource, /\bonOpenContext\b/);
  assert.match(topBarSource, /上下文/);
});
```

- [ ] **Step 2: Run the static test and verify it fails**

Run:

```powershell
node --experimental-strip-types --test tests\webui_workbench_static.test.mjs
```

Expected: FAIL because `App.tsx` does not yet import `WorkbenchContextPanel`, `Splitter`, or `Drawer`.

- [ ] **Step 3: Update `TopBar` props and context button**

Modify `frontends/webui/src/components/shell/TopBar.tsx`.

Add imports:

```tsx
import {
  Menu,
  MessageSquareText,
  MoreHorizontal,
  PanelRight,
  PauseCircle,
  PlayCircle,
  RefreshCcw,
  RotateCcw,
  Square,
} from "lucide-react";
```

Add props to the function signature type:

```tsx
  contextOpen: boolean;
  onOpenContext: () => void;
  onToggleContext: () => void;
```

Add these destructured values in the parameter list:

```tsx
  contextOpen,
  onOpenContext,
  onToggleContext,
```

Insert this button before the `StatusBadge`:

```tsx
          <Tooltip title={contextOpen ? "收起上下文面板" : "打开上下文面板"}>
            <Button
              type="text"
              className="hidden xl:inline-flex"
              aria-label={contextOpen ? "收起上下文面板" : "打开上下文面板"}
              icon={<PanelRight className="h-5 w-5" aria-hidden="true" />}
              onClick={onToggleContext}
            />
          </Tooltip>

          <Tooltip title="打开上下文面板">
            <Button
              type="text"
              className="xl:hidden"
              aria-label="打开上下文面板"
              icon={<PanelRight className="h-5 w-5" aria-hidden="true" />}
              onClick={onOpenContext}
            />
          </Tooltip>
```

- [ ] **Step 4: Integrate context panel and Splitter in `App.tsx`**

Modify imports in `frontends/webui/src/App.tsx`:

```tsx
import { App as AntApp, ConfigProvider, Drawer, Input, Layout, Splitter } from "antd";
import { WorkbenchContextPanel } from "./components/context/WorkbenchContextPanel";
import { chooseWorkbenchContextTab } from "./state/workbench-context-state";
```

Add state near existing sidebar state:

```tsx
  type WorkbenchContextTab = "activity" | "status";

  const [contextOpen, setContextOpen] = useState(true);
  const [contextDrawerOpen, setContextDrawerOpen] = useState(false);
  const [contextTab, setContextTab] = useState<WorkbenchContextTab>("status");
```

Add derived values after `hasThread`:

```tsx
  const contextTurns = turns.length > 0 ? turns : activeConversation?.execution_log ?? [];
  const resolvedContextTab = chooseWorkbenchContextTab(contextTab, contextTurns, running);
```

Update `TopBar` usage with:

```tsx
          contextOpen={contextOpen}
          onOpenContext={() => setContextDrawerOpen(true)}
          onToggleContext={() => setContextOpen((current) => !current)}
```

Replace the outer shell structure with AntD `Layout` and `Splitter` in four concrete edits:

1. Change the root element returned by `GenericAgentWebUI` from the current `div.ga-shell` to `Layout.ga-shell.ga-workbench-shell`.
2. Change the desktop sidebar wrapper from `div.hidden xl:block` to `Layout.Sider` with `width={sidebarCollapsed ? 76 : 280}`, `collapsedWidth={76}`, `collapsed={sidebarCollapsed}`, `trigger={null}`, and `className="ga-workbench-sider hidden xl:block"`.
3. Wrap the current main chat area in `Splitter`. The first panel contains the current error banner, chat scroll section, and `Composer`. The second panel renders `WorkbenchContextPanel` only when `contextOpen` is true.
4. Keep the current `SidebarDialog`, `ContinueCompatDialog`, and hidden `last-reply-time` node as siblings after the `Layout` content. Do not move or alter `handleSubmit`, streaming logic, conversation handlers, or API calls.

Use this exact `Splitter.Panel` block for the right context panel:

```tsx
          {contextOpen ? (
            <Splitter.Panel min={280} max={420} defaultSize={340} collapsible={{ start: true }}>
              <WorkbenchContextPanel
                state={state}
                turns={contextTurns}
                activeTab={resolvedContextTab}
                onTabChange={setContextTab}
                onClose={() => setContextOpen(false)}
              />
            </Splitter.Panel>
          ) : null}
```

Add the mobile context drawer before `ContinueCompatDialog`:

```tsx
      <Drawer
        className="ga-context-drawer"
        placement="right"
        width={360}
        title={null}
        closable={false}
        open={contextDrawerOpen}
        onClose={() => setContextDrawerOpen(false)}
      >
        <WorkbenchContextPanel
          state={state}
          turns={contextTurns}
          activeTab={resolvedContextTab}
          onTabChange={setContextTab}
          onClose={() => setContextDrawerOpen(false)}
        />
      </Drawer>
```

- [ ] **Step 5: Add workbench layout styles**

Create `frontends/webui/src/styles/workbench.css`:

```css
.ga-workbench-shell {
  width: 100%;
}

.ga-workbench-sider.ant-layout-sider {
  background: transparent;
}

.ga-workbench-sider .ant-layout-sider-children {
  height: 100%;
}

.ga-workbench-splitter {
  background: transparent;
}

.ga-workbench-splitter .ant-splitter-panel {
  min-height: 0;
}

.ga-context-drawer .ant-drawer-body {
  height: 100%;
  padding: 0;
}

.ga-context-drawer .ant-drawer-content {
  background: #f8fafb;
}

@media (max-width: 1279px) {
  .ga-workbench-splitter .ant-splitter-bar {
    display: none;
  }
}
```

Modify `frontends/webui/src/styles.css` and insert this import after `shell.css`:

```css
@import "./styles/workbench.css";
```

- [ ] **Step 6: Run tests and build**

Run:

```powershell
node --experimental-strip-types --test tests\webui_workbench_static.test.mjs
npm --prefix frontends/webui run build
```

Expected: static test PASS and build PASS.

- [ ] **Step 7: Commit Task 3**

Run:

```powershell
git add -- frontends/webui/src/App.tsx frontends/webui/src/components/shell/TopBar.tsx frontends/webui/src/styles/workbench.css frontends/webui/src/styles.css tests/webui_workbench_static.test.mjs
git commit -m "feat: integrate webui workbench shell"
```

---

### Task 4: Polish Sidebar and Top Bar Interaction Density

**Files:**
- Modify: `frontends/webui/src/components/sidebar/ConversationSidebar.tsx`
- Modify: `frontends/webui/src/components/sidebar/ConversationActions.tsx`
- Modify: `frontends/webui/src/components/shell/TopBar.tsx`
- Create: `frontends/webui/src/styles/sidebar.css`
- Modify: `frontends/webui/src/styles.css`

- [ ] **Step 1: Add sidebar styles**

Create `frontends/webui/src/styles/sidebar.css`:

```css
.ga-sidebar {
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.48), transparent 12rem),
    #edf1f5;
  border-right: 1px solid #d9e0e8;
}

.ga-sidebar-brand {
  border-radius: 10px;
  padding: 0.375rem;
}

.ga-sidebar-row {
  position: relative;
  border-radius: 10px;
}

.ga-sidebar-row::before {
  content: "";
  position: absolute;
  left: 0.35rem;
  top: 0.5rem;
  bottom: 0.5rem;
  width: 2px;
  border-radius: 999px;
  background: transparent;
}

.ga-sidebar-row.is-active {
  background: #ffffff;
  border-color: #cfd8e3;
  box-shadow: 0 1px 0 rgba(17, 24, 39, 0.04);
}

.ga-sidebar-row.is-active::before {
  background: #0f766e;
}

.ga-sidebar-row:hover {
  background: rgba(255, 255, 255, 0.74);
}

.ga-sidebar-meta {
  color: #5b6678;
  font-size: 0.75rem;
}
```

Modify `frontends/webui/src/styles.css` and insert after `shell.css`:

```css
@import "./styles/sidebar.css";
```

- [ ] **Step 2: Update sidebar row class names**

In `ConversationSidebar.tsx`, replace `conversationRowClass` with:

```tsx
  const conversationRowClass = (conversationId: string) =>
    `ga-sidebar-row group flex min-h-[40px] w-full items-center gap-2 border px-2.5 py-2 text-left transition ${
      activeConversationId === conversationId
        ? "is-active border-app-line text-app-textStrong"
        : "border-transparent text-app-text"
    }`;
```

Add section counts to section titles by changing section title content:

```tsx
<div className="sidebar-section-title mb-1.5">
  置顶对话 · {pinned.length}
</div>
```

For group titles, replace the group name line with:

```tsx
<div className="flex min-w-0 items-center gap-2 text-[13px] font-medium text-app-text/90">
  <Folder className="h-3.5 w-3.5 shrink-0 text-app-muted" />
  <span className="truncate">{group.name}</span>
  <span className="ga-sidebar-meta shrink-0">{group.conversations.length}</span>
</div>
```

For recent title, replace:

```tsx
<div className="sidebar-section-title px-0">最近对话</div>
```

with:

```tsx
<div className="sidebar-section-title px-0">最近对话 · {ungrouped.length}</div>
```

- [ ] **Step 3: Improve top bar action hierarchy**

In `TopBar.tsx`, keep current behavior but make the status group more explicit. Replace the subtitle block under conversation title with:

```tsx
            <div className="mt-0.5 flex min-w-0 items-center gap-2 text-xs text-app-muted">
              <span className="truncate">{running ? "任务执行中" : state?.configured ? "准备就绪" : "未配置"}</span>
              <span aria-hidden="true">/</span>
              <span className="truncate">{state?.current_llm?.name ?? "未选择模型"}</span>
            </div>
```

Ensure the mobile sidebar button and context button both have `Tooltip` and `aria-label`.

- [ ] **Step 4: Run build**

Run:

```powershell
npm --prefix frontends/webui run build
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

Run:

```powershell
git add -- frontends/webui/src/components/sidebar/ConversationSidebar.tsx frontends/webui/src/components/sidebar/ConversationActions.tsx frontends/webui/src/components/shell/TopBar.tsx frontends/webui/src/styles/sidebar.css frontends/webui/src/styles.css
git commit -m "style: refine webui navigation density"
```

---

### Task 5: Upgrade Chat Surface and Composer States

**Files:**
- Modify: `frontends/webui/src/components/chat/ChatHome.tsx`
- Modify: `frontends/webui/src/components/chat/ChatMessageView.tsx`
- Modify: `frontends/webui/src/components/composer/Composer.tsx`
- Modify: `frontends/webui/src/styles/chat.css`

- [ ] **Step 1: Make ChatHome a workbench empty state**

In `ChatHome.tsx`, keep the existing props. Replace the centered paragraph copy with compact workbench copy:

```tsx
          <h2 className="mt-5 text-2xl font-semibold text-app-textStrong sm:text-3xl">
            开始一个 GA 工作流
          </h2>
          <p className="mx-auto mt-2 max-w-xl text-sm leading-7 text-app-muted">
            输入任务、问题或代码修改目标。WebUI 会保留回答和执行过程，便于复查当前会话。
          </p>
```

Replace the helper text row inside the composer surface with:

```tsx
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-app-muted">
              <span>{state?.configured ? "当前后端已就绪" : "请先配置模型后再发送"}</span>
              <span>Shift+Enter 换行，Enter 发送</span>
            </div>
```

- [ ] **Step 2: Improve message role labels**

In `ChatMessageView.tsx`, add a role label constant before return:

```tsx
  const roleLabel = isUser ? "You" : message.role === "system" ? "System" : "GenericAgent";
```

Replace the message meta line with:

```tsx
          <div className={`mb-2 flex items-center justify-between gap-3 text-[11px] font-medium ${isUser ? "text-white/62" : "text-app-muted"}`}>
            <span>{roleLabel}</span>
            <span className="shrink-0">{message.time}</span>
          </div>
```

- [ ] **Step 3: Improve composer feedback states**

In `Composer.tsx`, add this derived helper before return:

```tsx
  const helperText = !state?.configured
    ? "请先配置模型后再发送。"
    : running
      ? "任务运行中，可以停止当前任务。"
      : "Shift+Enter 换行，Enter 发送。";
```

Replace the current helper text div with:

```tsx
          <div className="text-xs text-app-muted">{helperText}</div>
```

Change the form class to use a workbench-specific composer layer:

```tsx
    <form className="ga-composer-bar shrink-0 border-t border-app-line px-3 py-3 backdrop-blur md:px-4 md:py-4" onSubmit={onSubmit}>
```

- [ ] **Step 4: Update chat CSS**

Modify `frontends/webui/src/styles/chat.css` by replacing the top composer and message styles with:

```css
.ga-composer-bar {
  background: rgba(248, 250, 251, 0.9);
}

.ga-composer-surface {
  border: 1px solid #cfd8e3;
  background: #ffffff;
  box-shadow: 0 14px 32px rgba(17, 24, 39, 0.11);
}

.ga-message-card {
  border-radius: 10px;
  border: 1px solid #d9e0e8;
  box-shadow: none;
}

.ga-message-assistant {
  background: rgba(255, 255, 255, 0.98);
}

.ga-message-user {
  border-color: rgba(23, 32, 51, 0.18);
  background: #172033;
  box-shadow: 0 8px 18px rgba(17, 24, 39, 0.13);
}
```

Keep the existing markdown rules below these definitions.

- [ ] **Step 5: Run build**

Run:

```powershell
npm --prefix frontends/webui run build
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

Run:

```powershell
git add -- frontends/webui/src/components/chat/ChatHome.tsx frontends/webui/src/components/chat/ChatMessageView.tsx frontends/webui/src/components/composer/Composer.tsx frontends/webui/src/styles/chat.css
git commit -m "style: upgrade webui chat surface"
```

---

### Task 6: Refine Existing Inline Execution Presentation

**Files:**
- Modify: `frontends/webui/src/components/execution/InlineExecutionTurns.tsx`
- Modify: `frontends/webui/src/components/execution/InlineExecutionTurn.tsx`
- Modify: `frontends/webui/src/components/execution/ExecutionToolCallCard.tsx`
- Modify: `frontends/webui/src/styles/execution.css`
- Modify: `tests/execution_panel_state.test.mjs`

- [ ] **Step 1: Extend execution state test coverage**

Modify `tests/execution_panel_state.test.mjs` and add:

```js
test("execution labels stay compact for completed and active turns", () => {
  assert.equal(buildExecutionChipLabel([{ turn: 1, title: "", content: "" }], false), "执行过程 · 1 轮");
  assert.equal(buildExecutionChipLabel([{ turn: 2, title: "Tool pass", content: "", state: "active" }], true), "正在执行 · Tool pass");
});
```

- [ ] **Step 2: Run execution state tests**

Run:

```powershell
node --experimental-strip-types --test tests\execution_panel_state.test.mjs
```

Expected: PASS. This is a guard before visual refactoring.

- [ ] **Step 3: Refine `InlineExecutionTurns` header**

In `InlineExecutionTurns.tsx`, replace the header container with:

```tsx
      <div className="flex min-w-0 items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2 text-sm font-semibold text-app-text">
          <Tag
            bordered={false}
            color={streaming ? "processing" : "success"}
            className="m-0 ga-execution-status-tag"
          >
            {streaming ? "执行中" : "已完成"}
          </Tag>
          <span className="truncate">{label}</span>
        </div>
        <span className="shrink-0 text-xs text-app-muted">{turns.length} 轮</span>
      </div>
```

- [ ] **Step 4: Refine `InlineExecutionTurn` and `ExecutionToolCallCard` density**

In `InlineExecutionTurn.tsx`, change the outer section class to:

```tsx
      className={`ga-run-rail rounded-[10px] border bg-white ${
        active ? "border-app-primary/45 shadow-soft" : "border-app-line"
      }`}
```

In `ExecutionToolCallCard.tsx`, change the outer section class to:

```tsx
    <section className="rounded-[10px] border border-app-line bg-app-surface">
```

Keep existing expand/collapse behavior unchanged.

- [ ] **Step 5: Update execution CSS**

Modify `frontends/webui/src/styles/execution.css`:

```css
.ga-execution-status-tag.ant-tag-success {
  color: #126c4d;
  background: #e9f6ef;
}

.ga-execution-status-tag.ant-tag-processing {
  color: #0b6f86;
  background: #e7f7fb;
}

.ga-run-rail {
  position: relative;
}

.ga-run-rail::before {
  content: "";
  position: absolute;
  left: 0.66rem;
  top: 2.55rem;
  bottom: 1rem;
  width: 1px;
  background: #d9e0e8;
  pointer-events: none;
}
```

- [ ] **Step 6: Run tests and build**

Run:

```powershell
node --experimental-strip-types --test tests\execution_panel_state.test.mjs
npm --prefix frontends/webui run build
```

Expected: tests PASS and build PASS.

- [ ] **Step 7: Commit Task 6**

Run:

```powershell
git add -- frontends/webui/src/components/execution/InlineExecutionTurns.tsx frontends/webui/src/components/execution/InlineExecutionTurn.tsx frontends/webui/src/components/execution/ExecutionToolCallCard.tsx frontends/webui/src/styles/execution.css tests/execution_panel_state.test.mjs
git commit -m "style: refine webui inline execution"
```

---

### Task 7: Consolidate Theme Tokens and Run Full Verification

**Files:**
- Modify: `frontends/webui/src/theme.ts`
- Modify: `frontends/webui/src/styles/base.css`
- Modify: `frontends/webui/src/styles/antd-overrides.css`
- Modify: `frontends/webui/src/styles/shell.css`
- Modify: `frontends/webui/src/styles.css`

- [ ] **Step 1: Tune AntD theme tokens**

Modify `frontends/webui/src/theme.ts` token values:

```ts
    borderRadius: 8,
    borderRadiusLG: 10,
    borderRadiusSM: 6,
    controlHeight: 38,
    controlHeightLG: 42,
    controlHeightSM: 32,
    boxShadow: "0 18px 42px rgba(17, 24, 39, 0.13)",
    boxShadowSecondary: "0 8px 20px rgba(17, 24, 39, 0.08)",
```

Add component tokens:

```ts
    Segmented: {
      itemSelectedBg: "#ffffff",
      itemSelectedColor: gaPalette.textStrong,
      trackBg: "#eef3f6",
    },
    Card: {
      borderRadiusLG: 10,
      headerBg: "#ffffff",
    },
```

- [ ] **Step 2: Tighten base focus styles**

Modify `frontends/webui/src/styles/base.css` focus rule:

```css
button:focus-visible,
select:focus-visible,
textarea:focus-visible,
input:focus-visible {
  outline: 3px solid rgba(15, 118, 110, 0.22);
  outline-offset: 2px;
}
```

- [ ] **Step 3: Keep AntD overrides scoped**

Modify `frontends/webui/src/styles/antd-overrides.css` and add:

```css
.ga-context-panel .ant-segmented {
  flex-shrink: 0;
}

.ga-context-panel .ant-empty {
  margin: 1rem 0;
}

.ga-workbench-splitter .ant-splitter-bar-dragger::before {
  background: #cfd8e3;
}
```

- [ ] **Step 4: Run full frontend state tests**

Run:

```powershell
node --experimental-strip-types --test tests\execution_panel_state.test.mjs tests\chat_scroll_state.test.mjs tests\sidebar_selection.test.mjs tests\webui_inline_execution.test.mjs tests\webui_workbench_context_state.test.mjs tests\webui_workbench_static.test.mjs
```

Expected: all listed Node tests PASS.

- [ ] **Step 5: Run backend WebUI regression tests**

Run:

```powershell
py -3 -m unittest tests.test_webui_server -v
```

Expected: PASS. This verifies the implementation did not need backend contract changes.

- [ ] **Step 6: Run production build and diff checks**

Run:

```powershell
npm --prefix frontends/webui run build
git diff --check
```

Expected: build PASS and `git diff --check` prints no output. Existing Vite large chunk warning is acceptable.

- [ ] **Step 7: Commit Task 7**

Run:

```powershell
git add -- frontends/webui/src/theme.ts frontends/webui/src/styles/base.css frontends/webui/src/styles/antd-overrides.css frontends/webui/src/styles/shell.css frontends/webui/src/styles.css
git commit -m "style: tune webui workbench theme"
```

---

## Final Verification

After Task 7, run:

```powershell
git status --short
git log --oneline -n 8
node --experimental-strip-types --test tests\execution_panel_state.test.mjs tests\chat_scroll_state.test.mjs tests\sidebar_selection.test.mjs tests\webui_inline_execution.test.mjs tests\webui_workbench_context_state.test.mjs tests\webui_workbench_static.test.mjs
py -3 -m unittest tests.test_webui_server -v
npm --prefix frontends/webui run build
git diff --check
```

Expected:

- Working tree only contains intentional files before final commits.
- Node tests pass.
- `tests.test_webui_server` passes.
- WebUI build passes.
- `git diff --check` has no output.

No step requires opening a local URL. Browser QA can be added later as a separate visual verification task if requested.

## Self-Review

Spec coverage:

- Existing backend-only scope is covered by the scope lock and Task 7 backend regression test.
- AntD workbench layout is covered by Tasks 2 and 3.
- Sidebar/topbar polish is covered by Task 4.
- Chat/composer polish is covered by Task 5.
- Inline execution and right-side context based on existing `execution_log` are covered by Tasks 2, 3, and 6.
- Theme and accessibility polish are covered by Task 7.

Open-slot scan:

- The plan contains no unresolved markers and no open-ended implementation slots.

Type consistency:

- The `activity` / `status` union is defined locally in the files that need it and used consistently by Tasks 2 and 3.
- Context panel uses existing `RuntimeState` and `ExecutionTurn` only.
- No task references subagent, run, artifact, or checkpoint APIs.
