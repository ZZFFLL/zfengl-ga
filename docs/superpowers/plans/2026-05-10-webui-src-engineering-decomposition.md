# WebUI Src Engineering Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `frontends/webui/src/App.tsx` and the single global stylesheet into focused modules without changing the visible WebUI behavior, so the next Agent workbench UI upgrade can be implemented safely.

**Architecture:** Keep `GenericAgentWebUI` in `App.tsx` as the stateful application container during this refactor, and move pure helpers plus presentational components outward first. Extract state hooks only after components have stable props; do not redesign layout, add a right rail, or alter the SSE/backend contract in this plan.

**Tech Stack:** React 18, TypeScript strict mode, Vite, Ant Design 5, Tailwind CSS, lucide-react, react-markdown, remark-gfm, existing Node/Python regression checks.

---

## Non-Negotiables

- Preserve current user-visible behavior: conversation list, grouped sidebar, inline execution display, streaming text reveal, continue dialog, model switcher, autonomous toggle, and mobile sidebar drawer.
- Do not reintroduce the old execution detail drawer. `tests/webui_inline_execution.test.mjs` must continue to reject `onOpenExecution`, `function ExecutionPanel`, `ExecutionPanelDialog`, and `--execution-width`.
- Do not touch backend code unless a verification failure proves the frontend extraction exposed a real contract issue.
- Do not broaden dependencies. Use existing React, AntD, lucide, Tailwind, and local utility files.
- Keep commits narrow. Each task should be independently buildable and reviewable.
- Use ASCII in new files unless preserving existing UI copy requires Chinese text already present in the component.

## Target File Structure

Create this structure under `frontends/webui/src`:

```text
frontends/webui/src/
  App.tsx
  api.ts
  main.tsx
  theme.ts
  types.ts
  state/
    chat-scroll-state.ts
    execution-panel-state.ts
    sidebar-selection.ts
  domain/
    conversation-groups.ts
    message-text.ts
    streaming-text.ts
    time.ts
  components/
    app/
      StatusBadge.tsx
    chat/
      ChatHome.tsx
      ChatMessageView.tsx
      MarkdownContent.tsx
    composer/
      Composer.tsx
    dialogs/
      ContinueCompatDialog.tsx
      SidebarDialog.tsx
    execution/
      ExecutionToolCallCard.tsx
      InlineExecutionTurn.tsx
      InlineExecutionTurns.tsx
    shell/
      TopBar.tsx
    sidebar/
      ConversationActions.tsx
      ConversationSidebar.tsx
  styles/
    antd-overrides.css
    base.css
    chat.css
    execution.css
    shell.css
    motion.css
  styles.css
```

Responsibility boundaries:

- `App.tsx`: orchestration only. Owns top-level state, effects, API calls, streaming task lifecycle, and composes extracted components.
- `domain/*`: framework-light helpers for message cleanup, time labels, streaming reveal, and conversation grouping.
- `state/*`: existing UI state reducers/helpers that can be tested without React.
- `components/*`: presentational or locally interactive components. They may use AntD/lucide, but should not call `fetch*`, `startChat`, `streamTask`, or `switchLlm` directly.
- `styles/*`: CSS grouped by surface. `styles.css` becomes an import manifest plus Tailwind directives.

## Verification Commands

Use these commands after each task unless the task says otherwise:

```powershell
npm --prefix frontends/webui run build
node --experimental-strip-types --test tests\execution_panel_state.test.mjs tests\chat_scroll_state.test.mjs tests\sidebar_selection.test.mjs tests\webui_inline_execution.test.mjs
git diff --check
```

Expected results:

- `npm --prefix frontends/webui run build`: exits 0. A Vite/AntD large chunk warning is acceptable.
- Node tests: all listed tests pass. If a listed test file does not exist in the current checkout, run the existing subset and note the missing file in the task review before continuing.
- `git diff --check`: no whitespace errors.

Run the Python WebUI server suite after Task 8:

```powershell
py -3 -m unittest tests.test_webui_server -v
```

Expected result: all tests pass.

---

### Task 1: Move Existing State Helpers Into `src/state`

**Files:**
- Create directory: `frontends/webui/src/state/`
- Move: `frontends/webui/src/chat-scroll-state.ts` -> `frontends/webui/src/state/chat-scroll-state.ts`
- Move: `frontends/webui/src/execution-panel-state.ts` -> `frontends/webui/src/state/execution-panel-state.ts`
- Move: `frontends/webui/src/sidebar-selection.ts` -> `frontends/webui/src/state/sidebar-selection.ts`
- Modify: `frontends/webui/src/App.tsx`
- Modify if present: `tests/execution_panel_state.test.mjs`, `tests/chat_scroll_state.test.mjs`, `tests/sidebar_selection.test.mjs`

- [ ] **Step 1: Move the helper files without changing their contents**

Use normal file moves, then inspect the diff to confirm the bodies are unchanged:

```powershell
New-Item -ItemType Directory -Force frontends\webui\src\state
Move-Item frontends\webui\src\chat-scroll-state.ts frontends\webui\src\state\chat-scroll-state.ts
Move-Item frontends\webui\src\execution-panel-state.ts frontends\webui\src\state\execution-panel-state.ts
Move-Item frontends\webui\src\sidebar-selection.ts frontends\webui\src\state\sidebar-selection.ts
git diff -- frontends/webui/src/state
```

Expected: Git shows the three files as renames or delete/add pairs with no logic edits.

- [ ] **Step 2: Update imports in `App.tsx`**

Replace:

```ts
import {
  buildExecutionChipLabel,
  resolveExecutionChipRunning,
  resolveExecutionTurns,
  shouldShowPendingAssistant,
} from "./execution-panel-state";
import { isNearScrollBottom } from "./chat-scroll-state";
import {
  buildBulkDeleteLabel,
  pruneSelectedConversations,
  toggleSelectedConversation,
} from "./sidebar-selection";
```

With:

```ts
import {
  buildExecutionChipLabel,
  resolveExecutionChipRunning,
  resolveExecutionTurns,
  shouldShowPendingAssistant,
} from "./state/execution-panel-state";
import { isNearScrollBottom } from "./state/chat-scroll-state";
import {
  buildBulkDeleteLabel,
  pruneSelectedConversations,
  toggleSelectedConversation,
} from "./state/sidebar-selection";
```

- [ ] **Step 3: Update test imports if the test files exist**

In existing Node tests, replace imports such as:

```js
import { isNearScrollBottom } from "../frontends/webui/src/chat-scroll-state.ts";
```

With:

```js
import { isNearScrollBottom } from "../frontends/webui/src/state/chat-scroll-state.ts";
```

Apply the same path pattern for:

```js
../frontends/webui/src/state/execution-panel-state.ts
../frontends/webui/src/state/sidebar-selection.ts
```

- [ ] **Step 4: Verify**

Run:

```powershell
npm --prefix frontends/webui run build
node --experimental-strip-types --test tests\execution_panel_state.test.mjs tests\chat_scroll_state.test.mjs tests\sidebar_selection.test.mjs tests\webui_inline_execution.test.mjs
git diff --check
```

Expected: build and tests pass; no whitespace errors.

- [ ] **Step 5: Commit**

```powershell
git add frontends/webui/src/App.tsx frontends/webui/src/state tests
git commit -m "refactor: group webui state helpers"
```

Review before committing: staged diff should only contain helper file moves plus import path updates.

---

### Task 2: Extract Message Text, Time, Streaming, and Grouping Helpers

**Files:**
- Create: `frontends/webui/src/domain/message-text.ts`
- Create: `frontends/webui/src/domain/time.ts`
- Create: `frontends/webui/src/domain/streaming-text.ts`
- Create: `frontends/webui/src/domain/conversation-groups.ts`
- Modify: `frontends/webui/src/App.tsx`

- [ ] **Step 1: Create `domain/message-text.ts`**

Move the message cleanup helpers out of `App.tsx`. The new file should export the functions used by `App.tsx` and later components:

```ts
const FINAL_INFO_BLOCK_RE = /\n*`{3,}\s*\n?\[Info\]\s*Final response to user\.\s*\n?`{3,}\s*$/i;
const FINAL_INFO_TRAIL_RE = /\n*\[Info\]\s*Final response to user\.\s*(?:`{3,}\s*)*$/i;
const TOOL_START_RE = /🛠️ Tool:\s*`([^`]+)`\s*📥 args:\s*/g;

function consumeFencedBlock(text: string) {
  const match = /^\s*(`{3,})([^\n]*)\n/.exec(text);
  if (!match) return { body: "", remainder: text };
  const fence = match[1];
  const start = match[0].length;
  const endMarker = `\n${fence}`;
  const end = text.indexOf(endMarker, start);
  if (end < 0) return { body: "", remainder: text };
  return {
    body: text.slice(start, end).trim(),
    remainder: text.slice(end + endMarker.length),
  };
}

export function stripToolTraceBlocks(text: string) {
  const source = text || "";
  const parts: string[] = [];
  let cursor = 0;

  while (cursor < source.length) {
    TOOL_START_RE.lastIndex = cursor;
    const match = TOOL_START_RE.exec(source);
    if (!match) {
      parts.push(source.slice(cursor));
      break;
    }
    parts.push(source.slice(cursor, match.index));
    cursor = TOOL_START_RE.lastIndex;

    const argsBlock = consumeFencedBlock(source.slice(cursor));
    if (argsBlock.remainder !== source.slice(cursor)) {
      cursor = source.length - argsBlock.remainder.length;
    }

    while (cursor < source.length) {
      const leading = source.slice(cursor);
      const trimmed = leading.replace(/^\s+/, "");
      const consumedWs = leading.length - trimmed.length;
      cursor += consumedWs;
      const block = consumeFencedBlock(source.slice(cursor));
      if (block.remainder === source.slice(cursor)) {
        break;
      }
      cursor = source.length - block.remainder.length;
    }

    while (cursor < source.length && /[\r\n]/.test(source[cursor])) {
      cursor += 1;
    }
  }

  return parts.join("");
}

export function sanitizeDisplayText(text: string) {
  let cleaned = text || "";
  cleaned = stripToolTraceBlocks(cleaned);
  cleaned = cleaned.replace(FINAL_INFO_BLOCK_RE, "");
  cleaned = cleaned.replace(FINAL_INFO_TRAIL_RE, "");
  cleaned = cleaned.replace(/\n{3,}/g, "\n\n");
  return cleaned.trim();
}

export function previewText(text: string) {
  const cleaned = sanitizeDisplayText(text || "");
  return cleaned.replace(/\s+/g, " ").trim() || "暂无消息";
}
```

Keep `consumeFencedBlock` private because no component should depend on that parsing detail.

- [ ] **Step 2: Create `domain/time.ts`**

```ts
export const nowLabel = () => new Date().toLocaleString();

export function formatMessageTime(raw: string) {
  if (!raw) return nowLabel();
  return raw;
}
```

- [ ] **Step 3: Create `domain/streaming-text.ts`**

```ts
const STREAM_STEP_INTERVAL_MS = 40;
const STREAM_DONE_CATCHUP_INTERVAL_MS = 8;

type GraphemeSegment = { segment: string };
type GraphemeSegmenter = { segment(input: string): Iterable<GraphemeSegment> };
type GraphemeSegmenterConstructor = new (
  locales?: string | string[],
  options?: { granularity: "grapheme" },
) => GraphemeSegmenter;

const graphemeSegmenter = (() => {
  const Segmenter = (Intl as typeof Intl & { Segmenter?: GraphemeSegmenterConstructor }).Segmenter;
  return Segmenter ? new Segmenter(undefined, { granularity: "grapheme" }) : null;
})();

export function splitGraphemes(text: string) {
  if (!text) return [];
  if (graphemeSegmenter) {
    return Array.from(graphemeSegmenter.segment(text), (item) => item.segment);
  }
  return Array.from(text);
}

export function streamStepInterval(remainingChars: number, done: boolean) {
  if (!done) return STREAM_STEP_INTERVAL_MS;
  if (remainingChars > 480) return 0;
  if (remainingChars > 160) return 2;
  return STREAM_DONE_CATCHUP_INTERVAL_MS;
}

export function nextSmoothContent(displayed: string, target: string, done = false) {
  const remaining = splitGraphemes(target.slice(displayed.length));
  if (remaining.length === 0) return target;
  const step = done ? Math.min(28, remaining.length) : Math.min(3, remaining.length);
  return displayed + remaining.slice(0, step).join("");
}

export function prefersReducedMotion() {
  return Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
}
```

- [ ] **Step 4: Create `domain/conversation-groups.ts`**

Move `buildGroups` here and keep its return shape unchanged:

```ts
import type { ConversationSummary, GroupSummary } from "../types";

export function buildGroups(groups: GroupSummary[], conversations: ConversationSummary[]) {
  const groupMap = new Map<string, ConversationSummary[]>();
  for (const conversation of conversations) {
    if (!conversation.group_id) continue;
    if (!groupMap.has(conversation.group_id)) {
      groupMap.set(conversation.group_id, []);
    }
    groupMap.get(conversation.group_id)?.push(conversation);
  }

  return groups
    .slice()
    .sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name))
    .map((group) => ({
      group,
      conversations: groupMap.get(group.id) ?? [],
    }));
}
```

If the current `App.tsx` implementation has extra sorting inside `buildGroups`, preserve it exactly when moving.

- [ ] **Step 5: Update `App.tsx` imports and delete moved helper definitions**

Add:

```ts
import { buildGroups } from "./domain/conversation-groups";
import { previewText, sanitizeDisplayText } from "./domain/message-text";
import { formatMessageTime, nowLabel } from "./domain/time";
import {
  nextSmoothContent,
  prefersReducedMotion,
  streamStepInterval,
} from "./domain/streaming-text";
```

Remove from `App.tsx`:

```ts
const nowLabel = () => new Date().toLocaleString();
const STREAM_STEP_INTERVAL_MS = 40;
const STREAM_DONE_CATCHUP_INTERVAL_MS = 8;
type GraphemeSegment = { segment: string };
type GraphemeSegmenter = { segment(input: string): Iterable<GraphemeSegment> };
type GraphemeSegmenterConstructor = new (
  locales?: string | string[],
  options?: { granularity: "grapheme" },
) => GraphemeSegmenter;
const FINAL_INFO_BLOCK_RE = /\n*`{3,}\s*\n?\[Info\]\s*Final response to user\.\s*\n?`{3,}\s*$/i;
const FINAL_INFO_TRAIL_RE = /\n*\[Info\]\s*Final response to user\.\s*(?:`{3,}\s*)*$/i;
const TOOL_START_RE = /🛠️ Tool:\s*`([^`]+)`\s*📥 args:\s*/g;
const graphemeSegmenter = (() => {
  const Segmenter = (Intl as typeof Intl & { Segmenter?: GraphemeSegmenterConstructor }).Segmenter;
  return Segmenter ? new Segmenter(undefined, { granularity: "grapheme" }) : null;
})();
function splitGraphemes(text: string) { /* moved to domain/streaming-text.ts */ }
function streamStepInterval(remainingChars: number, done: boolean) { /* moved to domain/streaming-text.ts */ }
function nextSmoothContent(displayed: string, target: string, done = false) { /* moved to domain/streaming-text.ts */ }
function prefersReducedMotion() { /* moved to domain/streaming-text.ts */ }
function formatMessageTime(raw: string) { /* moved to domain/time.ts */ }
function sanitizeDisplayText(text: string) { /* moved to domain/message-text.ts */ }
function consumeFencedBlock(text: string) { /* stays private in domain/message-text.ts */ }
function stripToolTraceBlocks(text: string) { /* moved to domain/message-text.ts */ }
function previewText(text: string) { /* moved to domain/message-text.ts */ }
function buildGroups(groups: GroupSummary[], conversations: ConversationSummary[]) { /* moved to domain/conversation-groups.ts */ }
```

Keep `id`, `DEFAULT_CONTINUE_COMMAND`, `UiMessage`, `ContinueCompatResult`, and `toUiMessages` in `App.tsx` for now because they are still coupled to the application state shape.

- [ ] **Step 6: Verify**

Run:

```powershell
npm --prefix frontends/webui run build
node --experimental-strip-types --test tests\execution_panel_state.test.mjs tests\chat_scroll_state.test.mjs tests\sidebar_selection.test.mjs tests\webui_inline_execution.test.mjs
git diff --check
```

Expected: build and tests pass.

- [ ] **Step 7: Commit**

```powershell
git add frontends/webui/src/App.tsx frontends/webui/src/domain
git commit -m "refactor: extract webui domain helpers"
```

Review before committing: no JSX moved in this task; only helper extraction and import cleanup.

---

### Task 3: Extract Markdown Rendering

**Files:**
- Create: `frontends/webui/src/components/chat/MarkdownContent.tsx`
- Modify: `frontends/webui/src/App.tsx`

- [ ] **Step 1: Create the chat component directory**

```powershell
New-Item -ItemType Directory -Force frontends\webui\src\components\chat
```

- [ ] **Step 2: Move `MarkdownContent` into its own file**

Create `frontends/webui/src/components/chat/MarkdownContent.tsx`:

```tsx
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type MarkdownContentProps = {
  content: string;
  streaming?: boolean;
};

export function MarkdownContent({ content, streaming = false }: MarkdownContentProps) {
  return (
    <div className={`markdown-content ${streaming ? "is-streaming" : ""}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      {streaming ? <span className="streaming-cursor" aria-hidden="true" /> : null}
    </div>
  );
}
```

If the current `MarkdownContent` implementation has different wrapper markup or class names, preserve the current JSX exactly and only change the file boundary.

- [ ] **Step 3: Update `App.tsx`**

Remove:

```ts
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
```

Add:

```ts
import { MarkdownContent } from "./components/chat/MarkdownContent";
```

Delete the in-file `MarkdownContent` function from `App.tsx`.

- [ ] **Step 4: Verify**

Run:

```powershell
npm --prefix frontends/webui run build
node --experimental-strip-types --test tests\execution_panel_state.test.mjs tests\chat_scroll_state.test.mjs tests\sidebar_selection.test.mjs tests\webui_inline_execution.test.mjs
git diff --check
```

Expected: build and tests pass; no visual behavior intentionally changes.

- [ ] **Step 5: Commit**

```powershell
git add frontends/webui/src/App.tsx frontends/webui/src/components/chat/MarkdownContent.tsx
git commit -m "refactor: extract markdown renderer"
```

---

### Task 4: Extract Inline Execution Components

**Files:**
- Create: `frontends/webui/src/components/execution/ExecutionToolCallCard.tsx`
- Create: `frontends/webui/src/components/execution/InlineExecutionTurn.tsx`
- Create: `frontends/webui/src/components/execution/InlineExecutionTurns.tsx`
- Modify: `frontends/webui/src/App.tsx`

- [ ] **Step 1: Create the execution component directory**

```powershell
New-Item -ItemType Directory -Force frontends\webui\src\components\execution
```

- [ ] **Step 2: Move `ExecutionToolCallCard`**

Create `frontends/webui/src/components/execution/ExecutionToolCallCard.tsx` by moving the complete current `function ExecutionToolCallCard` block from `frontends/webui/src/App.tsx` lines 265-327.

Add these imports at the top of the new file:

```tsx
import { ChevronDown, Wrench } from "lucide-react";
import { useState } from "react";
import type { ExecutionTurn } from "../../types";
```

Keep the current inline prop type:

```tsx
{
  toolCall: ExecutionTurn["tool_calls"][number];
  resultMode?: "preview" | "full";
}
```

Do not alter any JSX, class names, aria labels, result preview logic, Chinese copy, or local `open` state.

- [ ] **Step 3: Move `InlineExecutionTurn`**

Create `frontends/webui/src/components/execution/InlineExecutionTurn.tsx` by moving the complete current `function InlineExecutionTurn` block from `frontends/webui/src/App.tsx` lines 328-402.

Add these imports at the top of the new file:

```tsx
import { Tag } from "antd";
import { ChevronDown } from "lucide-react";
import { useEffect, useState } from "react";
import type { ExecutionTurn } from "../../types";
import { MarkdownContent } from "../chat/MarkdownContent";
import { ExecutionToolCallCard } from "./ExecutionToolCallCard";
```

Keep the current inline prop type:

```tsx
{
  turn: ExecutionTurn;
  defaultOpen: boolean;
}
```

Do not alter `useEffect`, default-open behavior, summary rendering, content rendering, tool-call rendering, or class names.

- [ ] **Step 4: Move `InlineExecutionTurns`**

Create `frontends/webui/src/components/execution/InlineExecutionTurns.tsx` by moving the complete current `function InlineExecutionTurns` block from `frontends/webui/src/App.tsx` lines 403-440.

Add these imports at the top of the new file:

```tsx
import type { ExecutionTurn } from "../../types";
import {
  buildExecutionChipLabel,
  resolveExecutionChipRunning,
} from "../../state/execution-panel-state";
import { InlineExecutionTurn } from "./InlineExecutionTurn";
```

Keep the current inline prop type:

```tsx
{
  turns: ExecutionTurn[];
  streaming: boolean;
  pending: boolean;
}
```

Do not alter the empty-state return, chip label logic, running-state classes, or per-turn default-open calculation.

- [ ] **Step 5: Update `App.tsx`**

Add:

```ts
import { InlineExecutionTurns } from "./components/execution/InlineExecutionTurns";
```

Delete these function declarations from `App.tsx`:

```ts
function ExecutionToolCallCard(...)
function InlineExecutionTurn(...)
function InlineExecutionTurns(...)
```

Keep `resolveExecutionTurns` and `shouldShowPendingAssistant` imported in `App.tsx` because `ChatMessageView` still lives there after this task.

- [ ] **Step 6: Verify**

Run:

```powershell
npm --prefix frontends/webui run build
node --experimental-strip-types --test tests\execution_panel_state.test.mjs tests\chat_scroll_state.test.mjs tests\sidebar_selection.test.mjs tests\webui_inline_execution.test.mjs
git diff --check
```

Expected: build and tests pass. The inline execution drawer regression test still passes.

- [ ] **Step 7: Commit**

```powershell
git add frontends/webui/src/App.tsx frontends/webui/src/components/execution
git commit -m "refactor: extract inline execution components"
```

---

### Task 5: Extract Chat Message and Empty State Components

**Files:**
- Create: `frontends/webui/src/components/chat/ChatMessageView.tsx`
- Create: `frontends/webui/src/components/chat/ChatHome.tsx`
- Modify: `frontends/webui/src/App.tsx`
- Modify: `frontends/webui/src/types.ts`

- [ ] **Step 1: Add shared UI message type**

Move the `UiMessage` type from `App.tsx` into `frontends/webui/src/types.ts`:

```ts
export type UiMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  time: string;
  executionLog: ExecutionTurn[];
  pending?: boolean;
};
```

Place it after `ConversationMessage` or near other frontend message types. `ExecutionTurn` is already defined above it in `types.ts`.

- [ ] **Step 2: Move `ChatMessageView`**

Create `frontends/webui/src/components/chat/ChatMessageView.tsx` by moving the complete current `function ChatMessageView` block from `frontends/webui/src/App.tsx` lines 441-491.

Add these imports at the top of the new file:

```tsx
import type { ExecutionTurn, UiMessage } from "../../types";
import {
  resolveExecutionTurns,
  shouldShowPendingAssistant,
} from "../../state/execution-panel-state";
import { InlineExecutionTurns } from "../execution/InlineExecutionTurns";
import { MarkdownContent } from "./MarkdownContent";
```

Keep the current inline prop type:

```tsx
{
  message: UiMessage;
  liveTurns: ExecutionTurn[];
  streaming: boolean;
}
```

Do not alter the pending assistant placeholder, `MarkdownContent` streaming prop, `InlineExecutionTurns` placement, or message card class names.

- [ ] **Step 3: Move `ChatHome`**

Create `frontends/webui/src/components/chat/ChatHome.tsx` by moving the complete current `function ChatHome` block from `frontends/webui/src/App.tsx` lines 492-560.

Add this import at the top of the new file:

```tsx
import { Sparkles } from "lucide-react";
```

Keep the current inline prop type:

```tsx
{
  configured: boolean;
}
```

Do not alter empty-home copy, layout, icons, or class names.

- [ ] **Step 4: Update `App.tsx`**

Import:

```ts
import { ChatHome } from "./components/chat/ChatHome";
import { ChatMessageView } from "./components/chat/ChatMessageView";
```

Change the type import:

```ts
import type {
  ConversationDetail,
  ConversationSummary,
  ExecutionTurn,
  GroupSummary,
  RuntimeState,
  StreamEvent,
  UiMessage,
} from "./types";
```

Delete local `UiMessage`, `ChatMessageView`, and `ChatHome` declarations from `App.tsx`.

- [ ] **Step 5: Remove now-unused imports from `App.tsx`**

After the move, remove any imports that were only needed by chat components, such as `Sparkles`, `MarkdownContent`, or execution chip helpers if TypeScript reports them unused.

- [ ] **Step 6: Verify**

Run:

```powershell
npm --prefix frontends/webui run build
node --experimental-strip-types --test tests\execution_panel_state.test.mjs tests\chat_scroll_state.test.mjs tests\sidebar_selection.test.mjs tests\webui_inline_execution.test.mjs
git diff --check
```

Expected: build and tests pass.

- [ ] **Step 7: Commit**

```powershell
git add frontends/webui/src/App.tsx frontends/webui/src/types.ts frontends/webui/src/components/chat
git commit -m "refactor: extract chat presentation components"
```

---

### Task 6: Extract Composer, TopBar, and Dialog Components

**Files:**
- Create: `frontends/webui/src/components/composer/Composer.tsx`
- Create: `frontends/webui/src/components/shell/TopBar.tsx`
- Create: `frontends/webui/src/components/app/StatusBadge.tsx`
- Create: `frontends/webui/src/components/dialogs/ContinueCompatDialog.tsx`
- Create: `frontends/webui/src/components/dialogs/SidebarDialog.tsx`
- Modify: `frontends/webui/src/App.tsx`

- [ ] **Step 1: Create directories**

```powershell
New-Item -ItemType Directory -Force frontends\webui\src\components\composer
New-Item -ItemType Directory -Force frontends\webui\src\components\shell
New-Item -ItemType Directory -Force frontends\webui\src\components\app
New-Item -ItemType Directory -Force frontends\webui\src\components\dialogs
```

- [ ] **Step 2: Move `StatusBadge`**

Create `frontends/webui/src/components/app/StatusBadge.tsx` by moving both complete blocks from `frontends/webui/src/App.tsx`:

- `function statusTone` from lines 230-235
- `function StatusBadge` from lines 236-247

Add these imports at the top of the new file:

```tsx
import { Tag } from "antd";
import type { RuntimeState } from "../../types";
```

Do not alter status labels, `Tag` props, status color mapping, or class names.

- [ ] **Step 3: Move `Composer`**

Create `frontends/webui/src/components/composer/Composer.tsx` by moving the complete current `function Composer` block from `frontends/webui/src/App.tsx` lines 561-618.

Add these imports at the top of the new file:

```tsx
import type { FormEvent, KeyboardEvent } from "react";
import { Button } from "antd";
import { Send, Square } from "lucide-react";
import type { RuntimeState } from "../../types";
```

Keep the current inline prop type:

```tsx
{
  state: RuntimeState | null;
  draft: string;
  running: boolean;
  onDraftChange: (value: string) => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onSubmit: (event?: FormEvent) => void;
  onAbort: () => void;
}
```

Do not move keyboard handling into `Composer`; `App.tsx` currently owns `onKeyDown`, and this task should preserve that boundary.

- [ ] **Step 4: Move `TopBar`**

Create `frontends/webui/src/components/shell/TopBar.tsx` by moving the complete current `function TopBar` block from `frontends/webui/src/App.tsx` lines 619-757.

Add these imports at the top of the new file:

```tsx
import { Button, Select, Tooltip } from "antd";
import {
  Menu,
  PauseCircle,
  PlayCircle,
  Plus,
  RefreshCcw,
  RotateCcw,
} from "lucide-react";
import type { RuntimeState } from "../../types";
import { StatusBadge } from "../app/StatusBadge";
```

Keep the current inline prop type from `App.tsx` exactly. Do not introduce new controls, remove menu items, or change model/autonomous/abort/reinject behavior.

- [ ] **Step 5: Move `ContinueCompatDialog`**

Create `frontends/webui/src/components/dialogs/ContinueCompatDialog.tsx` by moving the complete current `type ContinueCompatResult` from `App.tsx` lines 91-94 and the complete current `function ContinueCompatDialog` block from `frontends/webui/src/App.tsx` lines 758-854.

Add these imports at the top of the new file:

```tsx
import { Button, Input, Modal } from "antd";
```

After this move, delete the local `ContinueCompatResult` type from `App.tsx` if it is no longer used there. Do not alter dialog copy, form behavior, result rendering, or loading/error states.

- [ ] **Step 6: Move `SidebarDialog`**

Create `frontends/webui/src/components/dialogs/SidebarDialog.tsx` by moving the complete current `function SidebarDialog` block from `frontends/webui/src/App.tsx` lines 1278-1305.

Add this import at the top of the new file:

```tsx
import { Drawer } from "antd";
```

Keep the current inline prop type exactly:

```tsx
{
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}
```

Because this prop type references `React.ReactNode`, either import `React` or change the prop type to an imported `ReactNode` while keeping runtime behavior unchanged.

- [ ] **Step 7: Update `App.tsx` imports and delete moved functions**

Add imports:

```ts
import { Composer } from "./components/composer/Composer";
import { ContinueCompatDialog } from "./components/dialogs/ContinueCompatDialog";
import { SidebarDialog } from "./components/dialogs/SidebarDialog";
import { TopBar } from "./components/shell/TopBar";
```

Delete these function declarations from `App.tsx`:

```ts
function statusTone(...)
function StatusBadge(...)
function Composer(...)
function TopBar(...)
function ContinueCompatDialog(...)
function SidebarDialog(...)
```

- [ ] **Step 8: Verify**

Run:

```powershell
npm --prefix frontends/webui run build
node --experimental-strip-types --test tests\execution_panel_state.test.mjs tests\chat_scroll_state.test.mjs tests\sidebar_selection.test.mjs tests\webui_inline_execution.test.mjs
git diff --check
```

Expected: build and tests pass.

- [ ] **Step 9: Commit**

```powershell
git add frontends/webui/src/App.tsx frontends/webui/src/components/app frontends/webui/src/components/composer frontends/webui/src/components/dialogs frontends/webui/src/components/shell
git commit -m "refactor: extract webui shell controls"
```

---

### Task 7: Extract Conversation Sidebar Components

**Files:**
- Create: `frontends/webui/src/components/sidebar/ConversationActions.tsx`
- Create: `frontends/webui/src/components/sidebar/ConversationSidebar.tsx`
- Modify: `frontends/webui/src/App.tsx`

- [ ] **Step 1: Create the sidebar component directory**

```powershell
New-Item -ItemType Directory -Force frontends\webui\src\components\sidebar
```

- [ ] **Step 2: Move `ConversationActions`**

Create `frontends/webui/src/components/sidebar/ConversationActions.tsx` by moving the complete current `function ConversationActions` block from `frontends/webui/src/App.tsx` lines 855-952.

Add these imports at the top of the new file:

```tsx
import { Button, Dropdown } from "antd";
import type { MenuProps } from "antd";
import {
  Folder,
  MessageSquareText,
  MoreHorizontal,
  Pin,
  PinOff,
  Trash2,
} from "lucide-react";
import type { ConversationSummary, GroupSummary } from "../../types";
```

Keep the current inline prop type from `App.tsx` exactly. Do not alter menu item keys, pin/unpin behavior, move-to-group options, destructive labels, disabled handling, or icon usage.

- [ ] **Step 3: Move `ConversationSidebar`**

Create `frontends/webui/src/components/sidebar/ConversationSidebar.tsx` by moving the complete current `function ConversationSidebar` block from `frontends/webui/src/App.tsx` lines 953-1277.

Add these imports at the top of the new file:

```tsx
import { Button, Tooltip } from "antd";
import {
  Circle,
  Folder,
  FolderPlus,
  MessageSquareText,
  PanelLeft,
  Pin,
  Plus,
  Trash2,
} from "lucide-react";
import type { RuntimeState, ConversationSummary, GroupSummary } from "../../types";
import { buildGroups } from "../../domain/conversation-groups";
import { previewText } from "../../domain/message-text";
import { buildBulkDeleteLabel } from "../../state/sidebar-selection";
import { ConversationActions } from "./ConversationActions";
```

Keep the current inline prop type from `App.tsx` exactly. Do not alter pinned/recent/grouped sections, collapsed behavior, selecting-recent controls, mobile compatibility, active item classes, or create/rename/delete flows.

- [ ] **Step 4: Keep selection helper ownership clear**

Inside the extracted sidebar, use the existing state helpers from `src/state/sidebar-selection.ts`. Do not duplicate the helper logic in JSX. For example:

```ts
const nextSelectedIds = toggleSelectedConversation(selectedRecentIds, conversation.id);
onSelectedRecentIdsChange(nextSelectedIds);
```

- [ ] **Step 5: Update `App.tsx`**

Import:

```ts
import { ConversationSidebar } from "./components/sidebar/ConversationSidebar";
```

Delete local `ConversationActions` and `ConversationSidebar` declarations from `App.tsx`.

Remove sidebar-only imports from `App.tsx`, including icons and AntD types that are no longer used there.

- [ ] **Step 6: Verify**

Run:

```powershell
npm --prefix frontends/webui run build
node --experimental-strip-types --test tests\execution_panel_state.test.mjs tests\chat_scroll_state.test.mjs tests\sidebar_selection.test.mjs tests\webui_inline_execution.test.mjs
git diff --check
```

Expected: build and tests pass.

- [ ] **Step 7: Commit**

```powershell
git add frontends/webui/src/App.tsx frontends/webui/src/components/sidebar
git commit -m "refactor: extract conversation sidebar"
```

---

### Task 8: Thin `App.tsx` and Split CSS by Surface

**Files:**
- Create: `frontends/webui/src/styles/base.css`
- Create: `frontends/webui/src/styles/antd-overrides.css`
- Create: `frontends/webui/src/styles/shell.css`
- Create: `frontends/webui/src/styles/chat.css`
- Create: `frontends/webui/src/styles/execution.css`
- Create: `frontends/webui/src/styles/motion.css`
- Modify: `frontends/webui/src/styles.css`
- Modify: `frontends/webui/src/App.tsx`

- [ ] **Step 1: Create the styles directory**

```powershell
New-Item -ItemType Directory -Force frontends\webui\src\styles
```

- [ ] **Step 2: Split AntD overrides**

Move these selectors from `frontends/webui/src/styles.css` into `frontends/webui/src/styles/antd-overrides.css`:

```css
.ant-app
.ga-model-select .ant-select-selector
.ga-dropdown .ant-dropdown-menu
.ga-dropdown
.ga-dropdown .ant-dropdown-menu-item,
.ga-dropdown .ant-dropdown-menu-submenu-title
.ga-modal .ant-modal-content
.ga-modal .ant-modal-header
.ga-sidebar-drawer .ant-drawer-content
.ga-sidebar-drawer .ant-drawer-body
```

Move exact current rule bodies. Do not edit visual values in this task.

- [ ] **Step 3: Split shell rules**

Move these selectors into `frontends/webui/src/styles/shell.css`:

```css
.ga-shell
.ga-topbar
.ga-sidebar
.ga-sidebar-active
.ga-composer-surface
```

Keep exact current rule bodies.

- [ ] **Step 4: Split execution rules**

Move these selectors into `frontends/webui/src/styles/execution.css`:

```css
.ga-execution-status-tag.ant-tag-success
.ga-execution-status-tag.ant-tag-processing
.ga-run-rail
.ga-run-rail::before
.operation-scroll
.thought-chip
.thought-chip.is-thinking::after
.thought-chip > *
```

Keep exact current rule bodies and related keyframes if they only support execution chips.

- [ ] **Step 5: Split chat and markdown rules**

Move these selectors into `frontends/webui/src/styles/chat.css`:

```css
.ga-message-card
.ga-message-assistant
.ga-message-user
.message-content
.markdown-content
.markdown-content > :first-child,
.markdown-content > div > :first-child
.markdown-content > :last-child,
.markdown-content > div > :last-child
.markdown-content p,
.markdown-content ul,
.markdown-content ol,
.markdown-content blockquote,
.markdown-content pre,
.markdown-content table
.markdown-content ul,
.markdown-content ol
.markdown-content ul
.markdown-content ol
.markdown-content li
.markdown-content a
.markdown-content blockquote
.markdown-content code
.markdown-content pre
.markdown-content pre code
.markdown-content table
.markdown-content th,
.markdown-content td
.markdown-content th
```

Keep exact current rule bodies.

- [ ] **Step 6: Split motion rules**

Move streaming cursor and animation rules into `frontends/webui/src/styles/motion.css`:

```css
.panel-animate
.streaming-cursor
@keyframes stream-sheen
@keyframes stream-cursor-blink
@keyframes stream-cursor-glow
@media (prefers-reduced-motion: reduce)
```

If the reduced-motion block references classes now split across files, keep the whole media block in `motion.css` so the motion policy remains centralized.

- [ ] **Step 7: Keep `styles.css` as the manifest**

After moving rule bodies, `frontends/webui/src/styles.css` should look like:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@import "./styles/base.css";
@import "./styles/antd-overrides.css";
@import "./styles/shell.css";
@import "./styles/chat.css";
@import "./styles/execution.css";
@import "./styles/motion.css";

@layer components {
  /* Keep existing Tailwind component-layer utilities here if they currently exist. */
}
```

If Vite/PostCSS rejects `@import` after Tailwind directives, use the valid PostCSS order instead:

```css
@import "./styles/base.css";
@import "./styles/antd-overrides.css";
@import "./styles/shell.css";
@import "./styles/chat.css";
@import "./styles/execution.css";
@import "./styles/motion.css";

@tailwind base;
@tailwind components;
@tailwind utilities;
```

Run the build immediately after this step to confirm the order.

- [ ] **Step 8: Clean `App.tsx` imports**

After all component extractions, `App.tsx` should no longer import component-only icons or AntD controls. Keep only imports needed for the container, likely:

```ts
import { CSSProperties, useEffect, useRef, useState } from "react";
import { App as AntApp, ConfigProvider } from "antd";
import {
  abortTask,
  activateConversation,
  continueConversation,
  createConversation,
  createGroup,
  deleteConversation,
  deleteGroup,
  fetchConversation,
  fetchState,
  pinConversation,
  reinject,
  renameConversation,
  renameGroup,
  setAutonomous,
  startChat,
  streamTask,
  switchLlm,
} from "./api";
```

Do not change state names or streaming logic in this task.

- [ ] **Step 9: Verify complete refactor**

Run:

```powershell
npm --prefix frontends/webui run build
node --experimental-strip-types --test tests\execution_panel_state.test.mjs tests\chat_scroll_state.test.mjs tests\sidebar_selection.test.mjs tests\webui_inline_execution.test.mjs
py -3 -m unittest tests.test_webui_server -v
git diff --check
```

Expected:

- WebUI build passes.
- Inline execution regression test still passes.
- WebUI server test suite passes.
- No whitespace errors.

- [ ] **Step 10: Optional browser smoke if a WebUI server is available**

If `http://127.0.0.1:18610` is already running, open it and verify:

- Desktop: sidebar, topbar, chat scroll area, and composer render.
- Mobile width: sidebar is opened via drawer, not permanently visible.
- Sending a prompt still shows inline execution updates inside assistant messages.
- No console runtime errors.

If no server is running, do not start new backend services solely for this refactor unless the reviewer asks for browser evidence.

- [ ] **Step 11: Commit**

```powershell
git add frontends/webui/src/App.tsx frontends/webui/src/styles.css frontends/webui/src/styles
git commit -m "refactor: split webui styles by surface"
```

---

## Final Review Checklist

After all tasks are complete:

- [ ] `frontends/webui/src/App.tsx` is substantially smaller and primarily contains application state/effects/API orchestration.
- [ ] Extracted components do not import from `api.ts` and do not own backend calls.
- [ ] Extracted domain helpers do not import React or AntD.
- [ ] Existing inline execution behavior remains inline only.
- [ ] No task introduced new layout concepts, new UI surfaces, new dependencies, or backend contract changes.
- [ ] Final verification commands pass:

```powershell
npm --prefix frontends/webui run build
node --experimental-strip-types --test tests\execution_panel_state.test.mjs tests\chat_scroll_state.test.mjs tests\sidebar_selection.test.mjs tests\webui_inline_execution.test.mjs
py -3 -m unittest tests.test_webui_server -v
git diff --check
```

## Handoff To UI Upgrade

Only after this refactor lands should the Agent workbench UI upgrade start. The next plan can then operate on:

- `components/shell/TopBar.tsx` and future shell layout files for information architecture.
- `components/sidebar/ConversationSidebar.tsx` for task/session navigation.
- `components/chat/ChatMessageView.tsx` for conversation hierarchy.
- `components/execution/*` for a future run monitor or execution rail.
- `components/composer/Composer.tsx` for command-bar interactions.
- `styles/*` and `theme.ts` for visual tokens, density, elevation, and motion.
