# GenericAgent WebUI Workbench Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current chat-bubble WebUI presentation with a visibly different Agent workbench: task stream, command blocks, response panels, command dock, execution trace, and only-on-demand run inspector.

**Architecture:** Keep the WebUI backend contract unchanged. Project existing `UiMessage[]` into frontend-only task items, render those task items through new focused components, and make the inspector a selected/running execution detail surface instead of a permanent low-value right panel. Update AntD tokens, Tailwind tokens, and custom CSS together so the actual page changes, not only AntD controls.

**Tech Stack:** React 18, TypeScript, Ant Design 5, lucide-react, existing Tailwind/CSS pipeline, Node `--experimental-strip-types` tests, Python unittest for WebUI backend regressions.

---

## Scope Lock

Do not modify:

- `frontends/webui_server.py`
- GA core runtime files
- External dependency projects
- Backend contracts for subagent, run, artifact, or checkpoint entities

This plan intentionally removes the old main chat-bubble presentation. It may keep compatibility class names only when they are not used as the primary visual model.

## File Structure

- `frontends/webui/src/state/task-stream-state.ts`
  - Pure projection from `UiMessage[]` plus live execution state into frontend task items.
- `tests/webui_task_stream_state.test.mjs`
  - Regression tests for task item projection.
- `frontends/webui/src/components/chat/TaskStream.tsx`
  - Renders the center task stream.
- `frontends/webui/src/components/chat/CommandBlock.tsx`
  - Renders user command blocks.
- `frontends/webui/src/components/chat/ResponsePanel.tsx`
  - Renders assistant/system response panels.
- `frontends/webui/src/components/chat/ChatMessageView.tsx`
  - Removed from the primary task stream path or converted into a thin compatibility wrapper that no longer contains bubble layout.
- `frontends/webui/src/components/composer/Composer.tsx`
  - Converted to command dock.
- `frontends/webui/src/components/context/RunInspector.tsx`
  - On-demand inspector for selected/current execution details.
- `frontends/webui/src/App.tsx`
  - Wires task stream and inspector state without changing chat API logic.
- `frontends/webui/src/styles/chat.css`
  - Task stream, command block, response panel, command dock, markdown readability.
- `frontends/webui/src/styles/context.css`
  - Run inspector styles.
- `frontends/webui/src/styles/workbench.css`
  - Center workbench canvas and on-demand inspector layout.
- `frontends/webui/src/styles/shell.css`
  - Dark workbench shell and topbar.
- `frontends/webui/src/styles/sidebar.css`
  - Dark sidebar/resource rail polish.
- `frontends/webui/src/styles/base.css`
  - Global dark background, focus, body defaults.
- `frontends/webui/src/styles/antd-overrides.css`
  - Scoped AntD dark workbench overrides.
- `frontends/webui/src/theme.ts`
  - AntD dark workbench tokens.
- `frontends/webui/tailwind.config.ts`
  - Tailwind app tokens matching the dark workbench.
- `tests/webui_workbench_static.test.mjs`
  - Structural tests that prevent returning to the old bubble UI and low-value permanent context panel.

---

### Task 1: Add Frontend Task Stream Projection

**Files:**
- Create: `frontends/webui/src/state/task-stream-state.ts`
- Create: `tests/webui_task_stream_state.test.mjs`

- [ ] **Step 1: Write the failing task stream tests**

Create `tests/webui_task_stream_state.test.mjs`:

```js
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL } from "node:url";

const moduleUrl = pathToFileURL(
  path.resolve("frontends/webui/src/state/task-stream-state.ts"),
).href;
const {
  buildTaskStreamItems,
  chooseActiveInspectorTarget,
} = await import(moduleUrl);

const command = {
  id: "u-1",
  role: "user",
  content: "Refactor the WebUI",
  time: "10:00",
  executionLog: [],
};

const executionTurn = {
  turn: 1,
  title: "Inspect files",
  content: "Inspect files",
  state: "completed",
  tool_calls: [
    {
      tool: "rg",
      args: "query",
      result: "ok",
      result_preview: "ok",
      action: "search",
      status: "completed",
    },
  ],
};

const response = {
  id: "a-1",
  role: "assistant",
  content: "Done",
  time: "10:01",
  executionLog: [executionTurn],
};

test("buildTaskStreamItems groups a user command with the following assistant response", () => {
  assert.deepEqual(buildTaskStreamItems([command, response], [], false), [
    {
      id: "task-u-1",
      command,
      response,
      executionLog: [executionTurn],
      pending: false,
    },
  ]);
});

test("buildTaskStreamItems keeps assistant-only legacy replies readable", () => {
  const items = buildTaskStreamItems([response], [], false);

  assert.equal(items.length, 1);
  assert.equal(items[0].id, "task-a-1");
  assert.equal(items[0].command, null);
  assert.equal(items[0].response, response);
  assert.deepEqual(items[0].executionLog, [executionTurn]);
});

test("buildTaskStreamItems prefers live execution log for the streaming assistant", () => {
  const liveTurn = { ...executionTurn, turn: 2, title: "Live turn", state: "active" };
  const pendingResponse = { ...response, id: "a-2", pending: true, executionLog: [] };
  const items = buildTaskStreamItems([command, pendingResponse], [liveTurn], true);

  assert.deepEqual(items[0].executionLog, [liveTurn]);
  assert.equal(items[0].pending, true);
});

test("buildTaskStreamItems starts a new task for each user command", () => {
  const secondCommand = { ...command, id: "u-2", content: "Run tests", time: "10:02" };
  const items = buildTaskStreamItems([command, response, secondCommand], [], false);

  assert.equal(items.length, 2);
  assert.equal(items[0].command.id, "u-1");
  assert.equal(items[0].response.id, "a-1");
  assert.equal(items[1].command.id, "u-2");
  assert.equal(items[1].response, null);
});

test("chooseActiveInspectorTarget opens only for running or explicitly selected execution", () => {
  assert.equal(chooseActiveInspectorTarget([], false, null), null);
  assert.deepEqual(chooseActiveInspectorTarget([executionTurn], true, null), {
    turnIndex: 0,
    toolIndex: null,
  });
  assert.deepEqual(chooseActiveInspectorTarget([executionTurn], false, { turnIndex: 0, toolIndex: 0 }), {
    turnIndex: 0,
    toolIndex: 0,
  });
});
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```powershell
node --experimental-strip-types --test tests\webui_task_stream_state.test.mjs
```

Expected: FAIL because `frontends/webui/src/state/task-stream-state.ts` does not exist.

- [ ] **Step 3: Add the task stream helper implementation**

Create `frontends/webui/src/state/task-stream-state.ts`:

```ts
import type { ExecutionTurn, UiMessage } from "../types";

export type InspectorTarget = {
  turnIndex: number;
  toolIndex: number | null;
};

export type TaskStreamItem = {
  id: string;
  command: UiMessage | null;
  response: UiMessage | null;
  executionLog: ExecutionTurn[];
  pending: boolean;
};

function executionForResponse(
  response: UiMessage | null,
  liveExecutionLog: ExecutionTurn[],
  streaming: boolean,
) {
  if (!response) return [];
  if (streaming && response.pending && liveExecutionLog.length > 0) {
    return liveExecutionLog;
  }
  return response.executionLog ?? [];
}

export function buildTaskStreamItems(
  messages: UiMessage[],
  liveExecutionLog: ExecutionTurn[],
  streaming: boolean,
): TaskStreamItem[] {
  const items: TaskStreamItem[] = [];

  for (const message of messages) {
    if (message.role === "user") {
      items.push({
        id: `task-${message.id}`,
        command: message,
        response: null,
        executionLog: [],
        pending: Boolean(message.pending),
      });
      continue;
    }

    const latest = items[items.length - 1];
    if (latest && latest.command && !latest.response) {
      latest.response = message;
      latest.executionLog = executionForResponse(message, liveExecutionLog, streaming);
      latest.pending = Boolean(message.pending);
      continue;
    }

    items.push({
      id: `task-${message.id}`,
      command: null,
      response: message,
      executionLog: executionForResponse(message, liveExecutionLog, streaming),
      pending: Boolean(message.pending),
    });
  }

  return items.map((item) => ({
    ...item,
    executionLog: item.response ? executionForResponse(item.response, liveExecutionLog, streaming) : item.executionLog,
    pending: Boolean(item.response?.pending ?? item.pending),
  }));
}

export function chooseActiveInspectorTarget(
  executionLog: ExecutionTurn[],
  running: boolean,
  selectedTarget: InspectorTarget | null,
) {
  if (selectedTarget && executionLog[selectedTarget.turnIndex]) {
    return selectedTarget;
  }
  if (!running || executionLog.length === 0) {
    return null;
  }
  return {
    turnIndex: executionLog.length - 1,
    toolIndex: null,
  };
}
```

- [ ] **Step 4: Run the new test and verify it passes**

Run:

```powershell
node --experimental-strip-types --test tests\webui_task_stream_state.test.mjs
```

Expected: PASS, 5 tests.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add -- frontends/webui/src/state/task-stream-state.ts tests/webui_task_stream_state.test.mjs
git commit -m "test: add webui task stream projection"
```

---

### Task 2: Replace Bubble Message Rendering With Task Stream Components

**Files:**
- Create: `frontends/webui/src/components/chat/TaskStream.tsx`
- Create: `frontends/webui/src/components/chat/CommandBlock.tsx`
- Create: `frontends/webui/src/components/chat/ResponsePanel.tsx`
- Modify: `frontends/webui/src/components/chat/ChatMessageView.tsx`
- Modify: `frontends/webui/src/App.tsx`
- Modify: `frontends/webui/src/styles/chat.css`
- Modify: `tests/webui_workbench_static.test.mjs`

- [ ] **Step 1: Add static tests that reject the old bubble-first model**

Modify `tests/webui_workbench_static.test.mjs` and add:

```js
test("chat workbench uses task stream instead of chat bubbles", async () => {
  const [appSource, chatMessageSource, taskStreamSource, commandSource, responseSource, chatCss] =
    await Promise.all([
      readSource("frontends/webui/src/App.tsx"),
      readSource("frontends/webui/src/components/chat/ChatMessageView.tsx"),
      readSource("frontends/webui/src/components/chat/TaskStream.tsx"),
      readSource("frontends/webui/src/components/chat/CommandBlock.tsx"),
      readSource("frontends/webui/src/components/chat/ResponsePanel.tsx"),
      readSource("frontends/webui/src/styles/chat.css"),
    ]);

  assert.match(appSource, /\bTaskStream\b/);
  assert.doesNotMatch(appSource, /\bChatMessageView\b/);
  assert.doesNotMatch(chatMessageSource, /justify-end|max-w-\[78%\]|ga-message-user/);
  assert.match(taskStreamSource, /ga-task-stream/);
  assert.match(commandSource, /ga-command-block/);
  assert.match(responseSource, /ga-response-panel/);
  assert.match(chatCss, /\.ga-task-stream/);
  assert.match(chatCss, /\.ga-command-block/);
  assert.match(chatCss, /\.ga-response-panel/);
});
```

- [ ] **Step 2: Run the static test and verify it fails**

Run:

```powershell
node --experimental-strip-types --test tests\webui_workbench_static.test.mjs
```

Expected: FAIL because the new task stream components do not exist and `App.tsx` still uses `ChatMessageView`.

- [ ] **Step 3: Create `CommandBlock.tsx`**

Create `frontends/webui/src/components/chat/CommandBlock.tsx`:

```tsx
import { TerminalSquare } from "lucide-react";
import type { UiMessage } from "../../types";

export function CommandBlock({ message }: { message: UiMessage }) {
  return (
    <section className="ga-command-block">
      <div className="ga-command-meta">
        <span className="ga-command-icon">
          <TerminalSquare className="h-4 w-4" aria-hidden="true" />
        </span>
        <span>Command</span>
        <span aria-hidden="true">/</span>
        <span>{message.time}</span>
      </div>
      <div className="ga-command-content">{message.content}</div>
    </section>
  );
}
```

- [ ] **Step 4: Create `ResponsePanel.tsx`**

Create `frontends/webui/src/components/chat/ResponsePanel.tsx`:

```tsx
import { Loader2 } from "lucide-react";
import type { UiMessage } from "../../types";
import { MarkdownContent } from "./MarkdownContent";

export function ResponsePanel({
  message,
  streaming,
  pending,
}: {
  message: UiMessage | null;
  streaming: boolean;
  pending: boolean;
}) {
  if (!message || (pending && !message.content.trim())) {
    return (
      <section className="ga-response-panel is-pending">
        <div className="ga-response-meta">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          <span>GenericAgent is working</span>
        </div>
        <div className="text-sm text-app-muted">正在执行任务，结果会在这里生成。</div>
      </section>
    );
  }

  const roleLabel = message.role === "system" ? "System" : "GenericAgent";

  return (
    <section className="ga-response-panel">
      <div className="ga-response-meta">
        <span>{roleLabel}</span>
        <span aria-hidden="true">/</span>
        <span>{message.time}</span>
      </div>
      <MarkdownContent content={message.content} streaming={streaming} />
    </section>
  );
}
```

- [ ] **Step 5: Create `TaskStream.tsx`**

Create `frontends/webui/src/components/chat/TaskStream.tsx`:

```tsx
import type { InspectorTarget, TaskStreamItem } from "../../state/task-stream-state";
import type { ExecutionTurn } from "../../types";
import { InlineExecutionTurns } from "../execution/InlineExecutionTurns";
import { CommandBlock } from "./CommandBlock";
import { ResponsePanel } from "./ResponsePanel";

export function TaskStream({
  items,
  streaming,
  onSelectInspectorTarget,
}: {
  items: TaskStreamItem[];
  streaming: boolean;
  onSelectInspectorTarget: (turns: ExecutionTurn[], target: InspectorTarget) => void;
}) {
  return (
    <div className="ga-task-stream">
      {items.map((item, index) => {
        const isLatest = index === items.length - 1;
        const itemStreaming = streaming && isLatest;
        return (
          <article key={item.id} className="ga-task-item">
            {item.command ? <CommandBlock message={item.command} /> : null}
            <InlineExecutionTurns
              turns={item.executionLog}
              streaming={Boolean(item.pending || itemStreaming)}
              onSelectInspectorTarget={(target) => onSelectInspectorTarget(item.executionLog, target)}
            />
            <ResponsePanel
              message={item.response}
              streaming={itemStreaming}
              pending={Boolean(item.pending)}
            />
          </article>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 6: Convert `ChatMessageView.tsx` into a compatibility wrapper without bubble layout**

Replace `frontends/webui/src/components/chat/ChatMessageView.tsx` with:

```tsx
import type { ExecutionTurn, UiMessage } from "../../types";
import { ResponsePanel } from "./ResponsePanel";

export function ChatMessageView({
  message,
  streaming = false,
}: {
  message: UiMessage;
  streaming?: boolean;
  liveExecutionLog?: ExecutionTurn[];
}) {
  return (
    <ResponsePanel
      message={message}
      streaming={streaming}
      pending={Boolean(message.pending)}
    />
  );
}
```

- [ ] **Step 7: Wire `TaskStream` in `App.tsx`**

Modify imports:

```tsx
import { TaskStream } from "./components/chat/TaskStream";
import type { InspectorTarget } from "./state/task-stream-state";
import { buildTaskStreamItems } from "./state/task-stream-state";
```

Remove the `ChatMessageView` import.

Add state near context state:

```tsx
  const [selectedInspectorTurns, setSelectedInspectorTurns] = useState<ExecutionTurn[]>([]);
  const [selectedInspectorTarget, setSelectedInspectorTarget] = useState<InspectorTarget | null>(null);
```

Add derived task items after `resolvedContextTab`:

```tsx
  const taskItems = buildTaskStreamItems(messages, turns, streamAnimating);
```

Add helper before render:

```tsx
  const selectInspectorTarget = (nextTurns: ExecutionTurn[], target: InspectorTarget) => {
    setSelectedInspectorTurns(nextTurns);
    setSelectedInspectorTarget(target);
    setContextDrawerOpen(false);
  };
```

Replace the current `messages.map(...ChatMessageView...)` block with:

```tsx
                      <TaskStream
                        items={taskItems}
                        streaming={streamAnimating}
                        onSelectInspectorTarget={selectInspectorTarget}
                      />
```

- [ ] **Step 8: Add task stream styles**

Modify the top of `frontends/webui/src/styles/chat.css` to include:

```css
.ga-task-stream {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.ga-task-item {
  border: 1px solid #263246;
  border-radius: 14px;
  background: #111827;
  box-shadow: 0 18px 46px rgba(0, 0, 0, 0.22);
  overflow: hidden;
}

.ga-command-block {
  border-bottom: 1px solid #263246;
  background: #0b1120;
  padding: 0.875rem 1rem;
}

.ga-command-meta,
.ga-response-meta {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 0.5rem;
  color: #8ea0b8;
  font-size: 0.75rem;
  font-weight: 600;
}

.ga-command-icon {
  display: inline-flex;
  color: #34d399;
}

.ga-command-content {
  margin-top: 0.625rem;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: #e5eefb;
  font-size: 0.95rem;
  line-height: 1.75;
}

.ga-response-panel {
  padding: 1rem;
  color: #dbe7f5;
}

.ga-response-panel.is-pending {
  display: grid;
  gap: 0.75rem;
}
```

Remove or stop relying on `.ga-message-user` as the user command surface. Keep markdown rules but update their colors in Task 5.

- [ ] **Step 9: Run tests and build**

Run:

```powershell
node --experimental-strip-types --test tests\webui_task_stream_state.test.mjs tests\webui_workbench_static.test.mjs tests\execution_panel_state.test.mjs
npm --prefix frontends/webui run build
git diff --check
```

Expected: all tests PASS, build PASS with existing Vite chunk warning allowed, `git diff --check` no output.

- [ ] **Step 10: Commit Task 2**

Run:

```powershell
git add -- frontends/webui/src/components/chat/TaskStream.tsx frontends/webui/src/components/chat/CommandBlock.tsx frontends/webui/src/components/chat/ResponsePanel.tsx frontends/webui/src/components/chat/ChatMessageView.tsx frontends/webui/src/App.tsx frontends/webui/src/styles/chat.css tests/webui_workbench_static.test.mjs
git commit -m "feat: replace webui chat bubbles with task stream"
```

---

### Task 3: Convert Composer Into Command Dock

**Files:**
- Modify: `frontends/webui/src/components/composer/Composer.tsx`
- Modify: `frontends/webui/src/styles/chat.css`
- Modify: `tests/webui_workbench_static.test.mjs`

- [ ] **Step 1: Add static command dock assertions**

Modify `tests/webui_workbench_static.test.mjs` and add:

```js
test("composer is a command dock", async () => {
  const [composerSource, chatCss] = await Promise.all([
    readSource("frontends/webui/src/components/composer/Composer.tsx"),
    readSource("frontends/webui/src/styles/chat.css"),
  ]);

  assert.match(composerSource, /ga-command-dock/);
  assert.match(composerSource, /ga-command-input/);
  assert.doesNotMatch(composerSource, /ga-composer-surface/);
  assert.match(chatCss, /\.ga-command-dock/);
  assert.match(chatCss, /\.ga-command-input/);
});
```

- [ ] **Step 2: Run the static test and verify it fails**

Run:

```powershell
node --experimental-strip-types --test tests\webui_workbench_static.test.mjs
```

Expected: FAIL because `Composer.tsx` still uses `ga-composer-surface`.

- [ ] **Step 3: Replace composer markup with command dock**

Replace the return block in `frontends/webui/src/components/composer/Composer.tsx` with:

```tsx
  return (
    <form className="ga-command-dock" onSubmit={onSubmit}>
      <div className="ga-command-dock-inner">
        <div className="ga-command-dock-status">
          <span>{state?.current_llm?.name ?? "未选择模型"}</span>
          <span aria-hidden="true">/</span>
          <span>{running ? "运行中" : state?.configured ? "准备就绪" : "未配置"}</span>
        </div>
        <textarea
          id="chat-composer-draft"
          name="chat-composer-draft"
          className="ga-command-input"
          placeholder={running ? "任务运行中..." : "输入任务、修改目标或问题"}
          value={draft}
          disabled={running || !state?.configured}
          onChange={(event) => onDraftChange(event.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
        />
        <div className="ga-command-dock-footer">
          <div className="text-xs text-app-muted">{helperText}</div>
          <div className="flex items-center gap-2">
            {running ? (
              <Button
                icon={<Square className="h-4 w-4" aria-hidden="true" />}
                onClick={onAbort}
              >
                停止
              </Button>
            ) : null}
            <Button
              type="primary"
              htmlType="submit"
              disabled={!draft.trim() || running || !state?.configured}
              aria-label="发送任务"
              icon={<Send className="h-4 w-4" aria-hidden="true" />}
            >
              运行
            </Button>
          </div>
        </div>
      </div>
    </form>
  );
```

- [ ] **Step 4: Add command dock CSS**

Modify `frontends/webui/src/styles/chat.css` and add:

```css
.ga-command-dock {
  flex-shrink: 0;
  border-top: 1px solid #263246;
  background: rgba(7, 12, 22, 0.92);
  padding: 0.875rem 1rem 1rem;
  backdrop-filter: blur(14px);
}

.ga-command-dock-inner {
  max-width: 940px;
  margin: 0 auto;
  border: 1px solid #334155;
  border-radius: 14px;
  background: #0f172a;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.32);
  padding: 0.875rem;
}

.ga-command-dock-status {
  display: flex;
  gap: 0.5rem;
  color: #8ea0b8;
  font-size: 0.75rem;
  font-weight: 600;
}

.ga-command-input {
  margin-top: 0.625rem;
  min-height: 4.5rem;
  width: 100%;
  resize: none;
  border: 0;
  outline: none;
  background: transparent;
  color: #e5eefb;
  font-size: 0.96rem;
  line-height: 1.75;
}

.ga-command-input::placeholder {
  color: #64748b;
}

.ga-command-input:disabled {
  cursor: not-allowed;
  opacity: 0.62;
}

.ga-command-dock-footer {
  margin-top: 0.75rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}
```

Remove obsolete `.ga-composer-bar` and `.ga-composer-surface` if no longer used.

- [ ] **Step 5: Run tests and build**

Run:

```powershell
node --experimental-strip-types --test tests\webui_workbench_static.test.mjs
npm --prefix frontends/webui run build
git diff --check
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

Run:

```powershell
git add -- frontends/webui/src/components/composer/Composer.tsx frontends/webui/src/styles/chat.css tests/webui_workbench_static.test.mjs
git commit -m "feat: convert webui composer to command dock"
```

---

### Task 4: Replace Permanent Context Panel With On-Demand Run Inspector

**Files:**
- Create: `frontends/webui/src/components/context/RunInspector.tsx`
- Modify: `frontends/webui/src/App.tsx`
- Modify: `frontends/webui/src/components/execution/InlineExecutionTurns.tsx`
- Modify: `frontends/webui/src/components/execution/InlineExecutionTurn.tsx`
- Modify: `frontends/webui/src/components/execution/ExecutionToolCallCard.tsx`
- Modify: `frontends/webui/src/styles/context.css`
- Modify: `frontends/webui/src/styles/workbench.css`
- Modify: `tests/webui_workbench_static.test.mjs`

- [ ] **Step 1: Add static tests for on-demand inspector**

Modify `tests/webui_workbench_static.test.mjs`:

```js
test("run inspector is on-demand and context panel is not permanent low-value chrome", async () => {
  const [appSource, inspectorSource, contextCss] = await Promise.all([
    readSource("frontends/webui/src/App.tsx"),
    readSource("frontends/webui/src/components/context/RunInspector.tsx"),
    readSource("frontends/webui/src/styles/context.css"),
  ]);

  assert.match(appSource, /\bRunInspector\b/);
  assert.match(appSource, /chooseActiveInspectorTarget/);
  assert.doesNotMatch(appSource, /\bWorkbenchContextPanel\b/);
  assert.doesNotMatch(appSource, /contextOpen/);
  assert.match(inspectorSource, /ga-run-inspector/);
  assert.match(inspectorSource, /selectedToolCall/);
  assert.match(contextCss, /\.ga-run-inspector/);
});
```

- [ ] **Step 2: Run the static test and verify it fails**

Run:

```powershell
node --experimental-strip-types --test tests\webui_workbench_static.test.mjs
```

Expected: FAIL because `RunInspector.tsx` does not exist and `App.tsx` still uses `WorkbenchContextPanel`.

- [ ] **Step 3: Add selection props to execution components**

Update `InlineExecutionTurns.tsx` props:

```tsx
import type { InspectorTarget } from "../../state/task-stream-state";

export function InlineExecutionTurns({
  turns,
  streaming,
  onSelectInspectorTarget,
}: {
  turns: ExecutionTurn[];
  streaming: boolean;
  onSelectInspectorTarget?: (target: InspectorTarget) => void;
}) {
```

Pass target to each turn:

```tsx
              onSelectInspectorTarget={(toolIndex) =>
                onSelectInspectorTarget?.({ turnIndex: index, toolIndex })
              }
```

Update `InlineExecutionTurn.tsx` props:

```tsx
  onSelectInspectorTarget?: (toolIndex: number | null) => void;
```

Add a secondary button or click handler on the turn header:

```tsx
        onDoubleClick={() => onSelectInspectorTarget?.(null)}
```

Pass tool selection into `ExecutionToolCallCard`:

```tsx
                  onInspect={() => onSelectInspectorTarget?.(toolIndex)}
```

Update `ExecutionToolCallCard.tsx` props:

```tsx
  onInspect,
}: {
  toolCall: ExecutionTurn["tool_calls"][number];
  resultMode?: "preview" | "full";
  onInspect?: () => void;
}) {
```

Add an inspect button beside the chevron:

```tsx
        {onInspect ? (
          <button
            type="button"
            className="text-xs font-medium text-app-primary transition hover:text-app-primaryHover"
            onClick={(event) => {
              event.stopPropagation();
              onInspect();
            }}
          >
            Inspect
          </button>
        ) : null}
```

- [ ] **Step 4: Create `RunInspector.tsx`**

Create `frontends/webui/src/components/context/RunInspector.tsx`:

```tsx
import { Button, Empty, Tag } from "antd";
import { PanelRightClose, Square } from "lucide-react";
import type { InspectorTarget } from "../../state/task-stream-state";
import type { ExecutionTurn } from "../../types";

export function RunInspector({
  turns,
  target,
  running,
  onClose,
  onAbort,
}: {
  turns: ExecutionTurn[];
  target: InspectorTarget | null;
  running: boolean;
  onClose: () => void;
  onAbort: () => void;
}) {
  const selectedTurn = target ? turns[target.turnIndex] : null;
  const selectedToolCall =
    selectedTurn && target?.toolIndex !== null && target?.toolIndex !== undefined
      ? selectedTurn.tool_calls?.[target.toolIndex]
      : null;

  return (
    <aside className="ga-run-inspector">
      <div className="ga-run-inspector-header">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-app-textStrong">Run Inspector</div>
          <div className="mt-1 truncate text-xs text-app-muted">
            {selectedTurn ? selectedTurn.title || `Turn ${selectedTurn.turn}` : "没有选中的执行步骤"}
          </div>
        </div>
        <Button
          type="text"
          aria-label="关闭 Inspector"
          icon={<PanelRightClose className="h-4 w-4" aria-hidden="true" />}
          onClick={onClose}
        />
      </div>

      <div className="operation-scroll min-h-0 flex-1 overflow-y-auto p-4">
        {!selectedTurn ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择执行步骤后查看细节" />
        ) : (
          <div className="space-y-4">
            <section className="ga-run-inspector-section">
              <div className="mb-2 flex items-center justify-between gap-3">
                <div className="text-xs font-semibold uppercase text-app-muted">Step</div>
                <Tag bordered={false} color={selectedTurn.state === "active" ? "processing" : "success"}>
                  {selectedTurn.state === "active" ? "执行中" : "已完成"}
                </Tag>
              </div>
              <div className="text-sm font-semibold text-app-textStrong">
                {selectedTurn.title || `Turn ${selectedTurn.turn}`}
              </div>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-app-muted">
                {selectedTurn.summary || selectedTurn.content || "此步骤没有 summary。"}
              </p>
            </section>

            {selectedToolCall ? (
              <section className="ga-run-inspector-section">
                <div className="mb-2 text-xs font-semibold uppercase text-app-muted">Selected Tool</div>
                <div className="text-sm font-semibold text-app-textStrong">{selectedToolCall.tool}</div>
                <div className="mt-1 text-xs text-app-muted">
                  {selectedToolCall.status || selectedToolCall.action || "tool call"}
                </div>
                {selectedToolCall.args ? (
                  <pre className="mt-3 overflow-x-auto rounded-lg bg-app-codeBg p-3 text-xs leading-6 text-app-codeText">
                    <code>{selectedToolCall.args}</code>
                  </pre>
                ) : null}
                {selectedToolCall.result_preview || selectedToolCall.result ? (
                  <pre className="mt-3 overflow-x-auto rounded-lg bg-app-codeBg p-3 text-xs leading-6 text-app-codeText">
                    <code>{selectedToolCall.result_preview || selectedToolCall.result}</code>
                  </pre>
                ) : null}
              </section>
            ) : null}

            {running ? (
              <Button
                danger
                icon={<Square className="h-4 w-4" aria-hidden="true" />}
                onClick={onAbort}
              >
                停止当前任务
              </Button>
            ) : null}
          </div>
        )}
      </div>
    </aside>
  );
}
```

- [ ] **Step 5: Wire inspector in `App.tsx`**

Remove imports and state for `WorkbenchContextPanel`, `chooseWorkbenchContextTab`, `contextOpen`, `contextTab`, and `resolvedContextTab`.

Add imports:

```tsx
import { RunInspector } from "./components/context/RunInspector";
import { chooseActiveInspectorTarget } from "./state/task-stream-state";
```

Add derived target:

```tsx
  const inspectorTurns = selectedInspectorTurns.length > 0 ? selectedInspectorTurns : contextTurns;
  const activeInspectorTarget = chooseActiveInspectorTarget(
    inspectorTurns,
    running,
    selectedInspectorTarget,
  );
  const inspectorOpen = Boolean(activeInspectorTarget);
```

Replace the permanent `WorkbenchContextPanel` `Splitter.Panel` with:

```tsx
            {inspectorOpen ? (
              <Splitter.Panel
                min={300}
                max={460}
                defaultSize={360}
                collapsible={{ start: true }}
                className="ga-workbench-inspector-panel"
              >
                <RunInspector
                  turns={inspectorTurns}
                  target={activeInspectorTarget}
                  running={running}
                  onClose={() => {
                    setSelectedInspectorTarget(null);
                    setSelectedInspectorTurns([]);
                  }}
                  onAbort={() => void abortTask().then(refreshState)}
                />
              </Splitter.Panel>
            ) : null}
```

Replace the mobile context drawer content with `RunInspector`, and open it only when `inspectorOpen` is true.

Update `TopBar` props in Task 6 so context panel buttons are removed or renamed to inspector only if useful.

- [ ] **Step 6: Add inspector styles**

Modify `frontends/webui/src/styles/context.css`:

```css
.ga-run-inspector {
  display: flex;
  height: 100%;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  border-left: 1px solid #263246;
  background: #0b1120;
}

.ga-run-inspector-header {
  display: flex;
  min-height: 4rem;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  border-bottom: 1px solid #263246;
  padding: 0.875rem 1rem;
}

.ga-run-inspector-section {
  border: 1px solid #263246;
  border-radius: 12px;
  background: #111827;
  padding: 0.875rem;
}
```

Update `frontends/webui/src/styles/workbench.css` responsive rules to hide `.ga-workbench-inspector-panel` below `xl`.

- [ ] **Step 7: Run tests and build**

Run:

```powershell
node --experimental-strip-types --test tests\webui_workbench_static.test.mjs tests\webui_task_stream_state.test.mjs tests\execution_panel_state.test.mjs
npm --prefix frontends/webui run build
git diff --check
```

Expected: PASS.

- [ ] **Step 8: Commit Task 4**

Run:

```powershell
git add -- frontends/webui/src/components/context/RunInspector.tsx frontends/webui/src/App.tsx frontends/webui/src/components/execution/InlineExecutionTurns.tsx frontends/webui/src/components/execution/InlineExecutionTurn.tsx frontends/webui/src/components/execution/ExecutionToolCallCard.tsx frontends/webui/src/styles/context.css frontends/webui/src/styles/workbench.css tests/webui_workbench_static.test.mjs
git commit -m "feat: add on-demand webui run inspector"
```

---

### Task 5: Apply Dark Workbench Visual System Across Real Tokens

**Files:**
- Modify: `frontends/webui/src/theme.ts`
- Modify: `frontends/webui/tailwind.config.ts`
- Modify: `frontends/webui/src/styles/base.css`
- Modify: `frontends/webui/src/styles/shell.css`
- Modify: `frontends/webui/src/styles/sidebar.css`
- Modify: `frontends/webui/src/styles/workbench.css`
- Modify: `frontends/webui/src/styles/chat.css`
- Modify: `frontends/webui/src/styles/execution.css`
- Modify: `frontends/webui/src/styles/context.css`
- Modify: `frontends/webui/src/styles/antd-overrides.css`
- Modify: `tests/webui_workbench_static.test.mjs`

- [ ] **Step 1: Add static visual-token assertions**

Modify `tests/webui_workbench_static.test.mjs`:

```js
test("workbench visual system is applied to Tailwind, AntD, and custom CSS", async () => {
  const [themeSource, tailwindSource, shellCss, chatCss, contextCss] = await Promise.all([
    readSource("frontends/webui/src/theme.ts"),
    readSource("frontends/webui/tailwind.config.ts"),
    readSource("frontends/webui/src/styles/shell.css"),
    readSource("frontends/webui/src/styles/chat.css"),
    readSource("frontends/webui/src/styles/context.css"),
  ]);

  assert.match(themeSource, /colorBgBase:\s*gaPalette\.bg/);
  assert.match(tailwindSource, /bg:\s*"#070c16"/);
  assert.match(tailwindSource, /panel:\s*"#111827"/);
  assert.match(shellCss, /#070c16/);
  assert.match(chatCss, /\.ga-command-dock/);
  assert.match(contextCss, /\.ga-run-inspector/);
});
```

- [ ] **Step 2: Run the static test and verify it fails**

Run:

```powershell
node --experimental-strip-types --test tests\webui_workbench_static.test.mjs
```

Expected: FAIL until token files are updated.

- [ ] **Step 3: Update `tailwind.config.ts` tokens**

Replace the `app` colors with:

```ts
        app: {
          bg: "#070c16",
          canvas: "#0b1120",
          shell: "#070c16",
          shellMuted: "#111827",
          sidebar: "#0b1120",
          panel: "#111827",
          surface: "#172033",
          composer: "#0f172a",
          line: "#263246",
          lineStrong: "#334155",
          text: "#dbe7f5",
          textStrong: "#f8fafc",
          muted: "#8ea0b8",
          mutedSoft: "#64748b",
          primary: "#34d399",
          primaryHover: "#6ee7b7",
          primarySoft: "#12352f",
          primarySubtle: "#0f2a27",
          info: "#38bdf8",
          success: "#22c55e",
          danger: "#fb7185",
          warning: "#fbbf24",
          codeBg: "#020617",
          codeText: "#dbeafe",
          userBubble: "#0b1120"
        }
```

Update shadows:

```ts
        panel: "0 18px 46px rgba(0, 0, 0, 0.24)",
        soft: "0 10px 28px rgba(0, 0, 0, 0.18)",
        composer: "0 24px 60px rgba(0, 0, 0, 0.32)"
```

- [ ] **Step 4: Update `theme.ts` palette and AntD tokens**

Update `gaPalette` to match the dark tokens from Step 3.

Set token values:

```ts
    colorBgBase: gaPalette.bg,
    colorBgLayout: gaPalette.bg,
    colorBgContainer: gaPalette.panel,
    colorBgElevated: gaPalette.surface,
    colorBorder: gaPalette.line,
    colorBorderSecondary: gaPalette.line,
    colorText: gaPalette.text,
    colorTextHeading: gaPalette.textStrong,
    colorTextSecondary: gaPalette.muted,
    colorTextTertiary: gaPalette.mutedSoft,
    colorFillSecondary: "#172033",
    colorFillTertiary: "#111827",
    boxShadow: "0 24px 60px rgba(0, 0, 0, 0.32)",
    boxShadowSecondary: "0 14px 34px rgba(0, 0, 0, 0.22)",
```

Update component token backgrounds for `Select`, `Input`, `Modal`, `Segmented`, and `Card` so they use dark surfaces.

- [ ] **Step 5: Update base and shell CSS**

Modify `frontends/webui/src/styles/base.css`:

```css
:root {
  color: #dbe7f5;
  background: #070c16;
  font-family:
    "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", system-ui,
    -apple-system, BlinkMacSystemFont, sans-serif;
}

body {
  margin: 0;
  min-width: 320px;
  min-height: 100%;
  background: #070c16;
}
```

Modify `frontends/webui/src/styles/shell.css`:

```css
.ga-shell {
  background:
    radial-gradient(circle at 20% 0%, rgba(52, 211, 153, 0.08), transparent 28rem),
    linear-gradient(180deg, #0b1120 0%, #070c16 60%);
}

.ga-topbar {
  background: rgba(7, 12, 22, 0.86);
  border-bottom: 1px solid #263246;
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.03);
  backdrop-filter: blur(14px);
}
```

- [ ] **Step 6: Update sidebar, workbench, execution, context, and AntD CSS**

Use the dark tokens already introduced in previous tasks. Replace remaining light backgrounds `#ffffff`, `#f8fafb`, `#edf1f5`, `#d9e0e8` in the modified WebUI style files with dark equivalents:

- Background surface: `#0b1120`, `#111827`, `#172033`
- Border: `#263246`, `#334155`
- Text: `#dbe7f5`, `#f8fafc`, `#8ea0b8`
- Accent: `#34d399`

Do not replace markdown code block colors that already use dark surfaces.

- [ ] **Step 7: Run tests and build**

Run:

```powershell
node --experimental-strip-types --test tests\webui_workbench_static.test.mjs
npm --prefix frontends/webui run build
git diff --check
```

Expected: PASS.

- [ ] **Step 8: Commit Task 5**

Run:

```powershell
git add -- frontends/webui/src/theme.ts frontends/webui/tailwind.config.ts frontends/webui/src/styles/base.css frontends/webui/src/styles/shell.css frontends/webui/src/styles/sidebar.css frontends/webui/src/styles/workbench.css frontends/webui/src/styles/chat.css frontends/webui/src/styles/execution.css frontends/webui/src/styles/context.css frontends/webui/src/styles/antd-overrides.css tests/webui_workbench_static.test.mjs
git commit -m "style: apply dark webui workbench system"
```

---

### Task 6: Final Verification and No-Regression Review

**Files:**
- Modify only if a previous task left a failing test or build error.

- [ ] **Step 1: Run full Node state/static tests**

Run:

```powershell
node --experimental-strip-types --test tests\execution_panel_state.test.mjs tests\chat_scroll_state.test.mjs tests\sidebar_selection.test.mjs tests\webui_inline_execution.test.mjs tests\webui_workbench_context_state.test.mjs tests\webui_workbench_static.test.mjs tests\webui_task_stream_state.test.mjs
```

Expected: all tests PASS.

- [ ] **Step 2: Run backend WebUI regression tests**

Run:

```powershell
py -3 -m unittest tests.test_webui_server -v
```

Expected: PASS. This confirms the backend contract remains unchanged.

- [ ] **Step 3: Run production build**

Run:

```powershell
npm --prefix frontends/webui run build
```

Expected: PASS. Existing Vite large chunk warning is acceptable.

- [ ] **Step 4: Run diff hygiene**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors. Working tree should contain only intentional files if any fix is still pending.

- [ ] **Step 5: Verify hard acceptance with source checks**

Run:

```powershell
Select-String -Path frontends\webui\src\components\chat\ChatMessageView.tsx -Pattern "justify-end|max-w-\[78%\]|ga-message-user"
Select-String -Path frontends\webui\src\App.tsx -Pattern "WorkbenchContextPanel|contextOpen"
Select-String -Path frontends\webui\src\components\composer\Composer.tsx -Pattern "ga-command-dock|ga-composer-surface"
```

Expected:

- First command prints no matches.
- Second command prints no matches.
- Third command prints `ga-command-dock` and no `ga-composer-surface`.

- [ ] **Step 6: Commit only if fixes were needed**

If Step 1-5 required fixes, commit them:

```powershell
git add -- <fixed files>
git commit -m "fix: finalize webui workbench correction"
```

If no fixes were needed, do not create an empty commit.

---

## Final Verification

After Task 6, run:

```powershell
git status --short
git log --oneline -n 10
node --experimental-strip-types --test tests\execution_panel_state.test.mjs tests\chat_scroll_state.test.mjs tests\sidebar_selection.test.mjs tests\webui_inline_execution.test.mjs tests\webui_workbench_context_state.test.mjs tests\webui_workbench_static.test.mjs tests\webui_task_stream_state.test.mjs
py -3 -m unittest tests.test_webui_server -v
npm --prefix frontends/webui run build
git diff --check
```

No step requires starting the local frontend/backend or opening a local URL.

## Self-Review

Spec coverage:

- Task stream projection covers the required frontend-only data reshaping.
- Task 2 removes the old bubble-first center surface.
- Task 3 converts the composer into a command dock.
- Task 4 removes the permanent low-value context panel and replaces it with an on-demand run inspector.
- Task 5 applies the visual system to Tailwind, AntD, and custom CSS.
- Task 6 verifies no backend contract drift and no return to the old bubble UI.

Placeholder scan:

- The plan contains no TBD/TODO placeholders.
- Every code-creating step includes concrete code.

Type consistency:

- `InspectorTarget` is defined in `task-stream-state.ts` and reused by task stream, execution, and inspector components.
- `TaskStreamItem` is frontend-only and uses existing `UiMessage` and `ExecutionTurn` types.

