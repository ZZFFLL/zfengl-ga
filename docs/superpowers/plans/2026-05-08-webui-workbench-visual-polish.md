# GenericAgent WebUI Workbench Visual Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refine `frontends/webui` into a calmer, more premium Agent workbench by tightening color, layout density, message hierarchy, and execution-process presentation while preserving the existing GA runtime contract.

**Architecture:** Keep Ant Design as the interaction and token layer, and keep GA-specific chat, conversation, and execution rendering as custom React views. This pass is frontend-only: it must not move backend display-routing logic into the browser, must not change SSE payload semantics, and must not reduce execution/tool visibility.

**Tech Stack:** React 18, TypeScript, Vite, Tailwind CSS, Ant Design v5, lucide-react, Chrome DevTools MCP for visual QA, existing Python WebUI server and `tests.test_webui_server`.

---

## Design Direction

Use `ui-ux-pro-max` as the design-quality lens and Ant Design as the component system. The target visual style is **Light Workbench + Graphite Chrome + Signal Accent**:

- Light content canvas for long-form reading.
- Graphite-toned shell surfaces for workbench framing, not a full dark theme.
- Teal/cyan signal accent for active operation, selected state, focus, and primary action.
- Low-shadow, border-led hierarchy. Shadows are reserved for floating layers and the composer.
- Execution turns should feel like a run monitor / timeline rather than nested chat cards.

Product type: AI agent workbench / developer productivity console.

Must preserve:
- Existing streaming text behavior and smooth reveal tuning.
- Visible execution/tool process inside assistant messages.
- Backend display-routing contract from `frontends/webui_server.py`.
- Conversation list, group, pin, rename, delete, continue, abort, reinject, and LLM switching behavior.

Avoid:
- Marketing hero composition.
- Decorative orbs, bokeh, large gradients, or one-note blue/purple palette.
- Card-in-card visual clutter.
- Layout changes that hide execution details or make tool output look like ordinary chat text.
- New UI libraries.

---

## File Structure

**Modify: `frontends/webui/src/theme.ts`**
- Own the upgraded workbench palette and AntD token refinements.
- Add concrete semantic colors for shell, rail, canvas, elevated surface, muted text, accent, active state, and execution status.
- Keep the exported names `gaPalette` and `gaTheme`.
- Do not add dark mode in this pass.

**Modify: `frontends/webui/tailwind.config.ts`**
- Align Tailwind `app.*` colors and shadows with `theme.ts`.
- Keep Tailwind as a bridge for existing class-heavy JSX.
- Do not introduce a second independent palette.

**Modify: `frontends/webui/src/styles.css`**
- Add semantic CSS classes for shell, sidebar, topbar, composer, messages, and execution timeline.
- Reduce global decorative gradients.
- Keep markdown, streaming cursor, reduced-motion, operation-scroll, modal/dropdown/drawer integration.

**Modify: `frontends/webui/src/App.tsx`**
- Update class names and small structural wrappers for:
  - `StatusBadge`
  - `ExecutionToolCallCard`
  - `InlineExecutionTurn`
  - `InlineExecutionTurns`
  - `ChatMessageView`
  - `EmptyState`
  - `ChatComposer`
  - `TopBar`
  - `SidebarContent` / collapsed sidebar
  - root shell layout
- Do not refactor runtime state management, API calls, streaming queue, markdown parsing, conversation actions, or backend contracts.

**Do not modify unless an actual bug is found:**
- `frontends/webui_server.py`
- `agentmain.py`
- GA core / tool handlers
- SSE parsing tests beyond verifying they still pass

---

## Target Tokens

Use this concrete palette as the starting point. The implementer may tune by small increments after screenshots, but must keep the same visual direction.

```ts
export const gaPalette = {
  bg: "#f4f6f8",
  canvas: "#f8fafb",
  shell: "#161a22",
  shellMuted: "#252b35",
  sidebar: "#edf1f5",
  sidebarActive: "#ffffff",
  panel: "#ffffff",
  surface: "#f7f9fb",
  surfaceStrong: "#eef3f6",
  elevated: "#ffffff",
  line: "#d9e0e8",
  lineStrong: "#b8c3cf",
  text: "#1d2430",
  textStrong: "#111827",
  muted: "#667085",
  mutedSoft: "#8a95a5",
  primary: "#0f766e",
  primaryHover: "#0b5f59",
  primarySoft: "#e7f5f2",
  primarySubtle: "#f0faf8",
  info: "#0e7490",
  success: "#16845b",
  danger: "#c2413d",
  warning: "#b26a18",
  codeBg: "#111827",
  codeText: "#eef2ff",
  userBubble: "#172033",
};
```

AntD token intent:

```ts
token: {
  colorPrimary: gaPalette.primary,
  colorInfo: gaPalette.info,
  colorBgBase: gaPalette.bg,
  colorBgLayout: gaPalette.bg,
  colorBgContainer: gaPalette.panel,
  colorBgElevated: gaPalette.elevated,
  colorBorder: gaPalette.line,
  colorBorderSecondary: "#e7ecf2",
  colorText: gaPalette.text,
  colorTextHeading: gaPalette.textStrong,
  colorTextSecondary: gaPalette.muted,
  colorTextTertiary: gaPalette.mutedSoft,
  colorFillSecondary: "#eef2f6",
  colorFillTertiary: "#f4f7fa",
  borderRadius: 8,
  borderRadiusLG: 12,
  borderRadiusSM: 6,
  controlHeight: 38,
  controlHeightLG: 44,
  controlHeightSM: 32,
  boxShadow: "0 16px 36px rgba(17, 24, 39, 0.12)",
  boxShadowSecondary: "0 8px 22px rgba(17, 24, 39, 0.08)",
  motionDurationFast: "0.14s",
  motionDurationMid: "0.2s",
  motionDurationSlow: "0.28s",
}
```

Tailwind should mirror these tokens:

```ts
colors: {
  app: {
    bg: "#f4f6f8",
    canvas: "#f8fafb",
    shell: "#161a22",
    shellMuted: "#252b35",
    sidebar: "#edf1f5",
    panel: "#ffffff",
    surface: "#f7f9fb",
    composer: "#ffffff",
    line: "#d9e0e8",
    lineStrong: "#b8c3cf",
    text: "#1d2430",
    textStrong: "#111827",
    muted: "#667085",
    mutedSoft: "#8a95a5",
    primary: "#0f766e",
    primarySoft: "#e7f5f2",
    primarySubtle: "#f0faf8",
    info: "#0e7490",
    success: "#16845b",
    danger: "#c2413d",
    warning: "#b26a18",
    codeBg: "#111827",
    codeText: "#eef2ff",
    userBubble: "#172033"
  }
}
```

---

### Task 1: Align Theme And Tailwind Tokens

**Files:**
- Modify: `frontends/webui/src/theme.ts`
- Modify: `frontends/webui/tailwind.config.ts`

- [ ] **Step 1: Replace `gaPalette` in `theme.ts`**

Open `frontends/webui/src/theme.ts` and replace the existing `gaPalette` object with the palette from **Target Tokens**.

Expected:
- `gaPalette.primary` is `#0f766e`.
- `gaPalette.shell` and `gaPalette.shellMuted` exist.
- `gaPalette.userBubble` is `#172033`.

- [ ] **Step 2: Update AntD global tokens**

In the same file, update `gaTheme.token` to use the token block from **Target Tokens** while preserving the existing `fontFamily`, `fontSize`, and `lineHeight` choices.

Expected:
- AntD uses a tighter radius scale: `borderRadius: 8`, `borderRadiusLG: 12`, `borderRadiusSM: 6`.
- `colorTextHeading` is explicitly set.
- `colorBgElevated` uses `gaPalette.elevated`.
- Shadows are graphite-neutral rather than blue-gray.

- [ ] **Step 3: Tune AntD component tokens**

Keep the current component keys but update values as follows:

```ts
components: {
  Button: {
    borderRadius: 8,
    controlHeight: 38,
    fontWeight: 600,
    defaultShadow: "none",
    primaryShadow: "none",
    textHoverBg: "rgba(15, 118, 110, 0.08)",
  },
  Select: {
    borderRadius: 8,
    selectorBg: "#ffffff",
    optionSelectedBg: gaPalette.primarySoft,
    optionActiveBg: "#f2f6f7",
    activeBorderColor: gaPalette.primary,
    hoverBorderColor: "#8fa0ad",
  },
  Input: {
    borderRadius: 10,
    activeBorderColor: gaPalette.primary,
    hoverBorderColor: "#8fa0ad",
    activeShadow: "0 0 0 3px rgba(15, 118, 110, 0.14)",
  },
  Dropdown: {
    paddingBlock: 6,
    zIndexPopup: 1200,
  },
  Modal: {
    borderRadiusLG: 12,
    contentBg: "#ffffff",
    headerBg: "#ffffff",
    footerBg: "#ffffff",
    titleColor: gaPalette.textStrong,
    titleFontSize: 17,
  },
  Drawer: {
    zIndexPopup: 1200,
  },
  Tag: {
    borderRadiusSM: 999,
  },
}
```

- [ ] **Step 4: Mirror tokens in Tailwind**

In `frontends/webui/tailwind.config.ts`, replace the `app` color block with the Tailwind block from **Target Tokens**.

Update shadows:

```ts
boxShadow: {
  panel: "0 14px 34px rgba(17, 24, 39, 0.075)",
  soft: "0 5px 16px rgba(17, 24, 39, 0.045)",
  composer: "0 12px 34px rgba(17, 24, 39, 0.10)"
}
```

- [ ] **Step 5: Verify token compile**

Run:

```powershell
npm --prefix frontends/webui run build
```

Expected:
- TypeScript passes.
- Vite build exits `0`.
- A chunk-size warning is acceptable because AntD is already in the bundle.

---

### Task 2: Refine Global Shell, Floating Layers, And Base Surfaces

**Files:**
- Modify: `frontends/webui/src/styles.css`
- Modify: `frontends/webui/src/App.tsx`

- [ ] **Step 1: Replace global root/body surfaces**

In `frontends/webui/src/styles.css`, update the top-level surface rules to remove decorative radial emphasis:

```css
:root {
  color: #1d2430;
  background: #f4f6f8;
  font-family:
    "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", system-ui,
    -apple-system, BlinkMacSystemFont, sans-serif;
}

body {
  margin: 0;
  min-width: 320px;
  min-height: 100%;
  background: #f4f6f8;
}
```

Expected:
- No radial-gradient on `body`.
- The app reads as an operational surface, not a decorated page.

- [ ] **Step 2: Replace shell class**

In `styles.css`, replace `.ga-shell` with:

```css
.ga-shell {
  background:
    linear-gradient(90deg, rgba(22, 26, 34, 0.04), transparent 18rem),
    #f4f6f8;
}
```

Expected:
- Desktop shell gets a subtle graphite framing cue.
- Mobile remains light and readable.

- [ ] **Step 3: Tighten floating layer styles**

Update existing AntD integration rules:

```css
.ga-dropdown .ant-dropdown-menu {
  min-width: 220px;
  border: 1px solid #d9e0e8;
  box-shadow: 0 16px 36px rgba(17, 24, 39, 0.12);
}

.ga-modal .ant-modal-content {
  border: 1px solid #d9e0e8;
  box-shadow: 0 18px 48px rgba(17, 24, 39, 0.16);
}

.ga-sidebar-drawer .ant-drawer-content {
  background: #edf1f5;
}
```

Expected:
- Dropdown/Modal feel elevated without blue-tinted shadows.
- Drawer background matches the sidebar system.

- [ ] **Step 4: Add reusable workbench classes**

Append these classes near the shell/message rules:

```css
.ga-topbar {
  background: rgba(255, 255, 255, 0.92);
  border-bottom: 1px solid #d9e0e8;
  box-shadow: 0 1px 0 rgba(17, 24, 39, 0.02);
  backdrop-filter: blur(12px);
}

.ga-sidebar {
  background: #edf1f5;
  border-right: 1px solid #d9e0e8;
}

.ga-sidebar-active {
  background: #ffffff;
  box-shadow: inset 3px 0 0 #0f766e;
}

.ga-composer-surface {
  border: 1px solid #d9e0e8;
  background: #ffffff;
  box-shadow: 0 12px 34px rgba(17, 24, 39, 0.10);
}

.ga-run-rail {
  position: relative;
}

.ga-run-rail::before {
  content: "";
  position: absolute;
  left: 0.66rem;
  top: 2.6rem;
  bottom: 1rem;
  width: 1px;
  background: #d9e0e8;
}
```

Expected:
- Later JSX can reference semantic classes instead of scattering new raw values.

- [ ] **Step 5: Verify CSS compile**

Run:

```powershell
npm --prefix frontends/webui run build
```

Expected:
- Build exits `0`.

---

### Task 3: Rework Top Bar Into A Quiet Workbench Toolbar

**Files:**
- Modify: `frontends/webui/src/App.tsx`
- Modify: `frontends/webui/src/styles.css`

- [ ] **Step 1: Update topbar container class**

In `TopBar`, replace:

```tsx
<header className="shrink-0 border-b border-app-line/80 bg-white/90 backdrop-blur">
```

with:

```tsx
<header className="ga-topbar shrink-0">
```

- [ ] **Step 2: Tighten topbar height and spacing**

In the next wrapper, replace:

```tsx
<div className="flex min-h-[54px] items-center gap-3 px-4 py-2 md:px-6">
```

with:

```tsx
<div className="flex min-h-[52px] items-center gap-2.5 px-3 py-2 md:px-5">
```

Expected:
- Toolbar feels denser and more like a workbench header.
- Touch targets remain controlled by AntD button heights.

- [ ] **Step 3: Make title block less decorative**

Find the conversation title block inside `TopBar` and make sure the title line uses:

```tsx
<div className="truncate text-[15px] font-semibold text-app-textStrong">
```

and the subtitle/status line uses:

```tsx
<div className="mt-0.5 flex min-w-0 items-center gap-2 text-xs text-app-muted">
```

Expected:
- Title hierarchy is clear without large type.

- [ ] **Step 4: Make model selector visually subordinate**

Ensure the model select wrapper keeps `ga-model-select`, but set width to a stable compact size:

```tsx
className="ga-model-select min-w-[168px]"
```

If the existing select already uses responsive hiding, preserve those responsive classes and only adjust the visual width.

Expected:
- Model selection stays available but does not compete with primary work actions.

- [ ] **Step 5: Verify interactions still compile**

Run:

```powershell
npm --prefix frontends/webui run build
```

Expected:
- Build exits `0`.

---

### Task 4: Reframe Sidebar As Navigation, Not Cards

**Files:**
- Modify: `frontends/webui/src/App.tsx`
- Modify: `frontends/webui/src/styles.css`

- [ ] **Step 1: Apply semantic sidebar class**

In collapsed sidebar, replace:

```tsx
<aside className="flex h-full min-h-0 flex-col items-center border-r border-app-line/80 bg-app-sidebar px-2 py-3">
```

with:

```tsx
<aside className="ga-sidebar flex h-full min-h-0 flex-col items-center px-2 py-3">
```

In expanded sidebar, replace:

```tsx
<aside className="flex h-full min-h-0 flex-col border-r border-app-line/80 bg-app-sidebar">
```

with:

```tsx
<aside className="ga-sidebar flex h-full min-h-0 flex-col">
```

- [ ] **Step 2: Tighten sidebar brand block**

Update the expanded sidebar header icon container from rounded `15px` to a quieter radius:

```tsx
className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white text-app-primary ring-1 ring-app-line"
```

Expected:
- The app mark reads as part of the workbench chrome, not a decorative badge.

- [ ] **Step 3: Change active conversation styling**

Find the conversation row class construction. For the active row, use:

```tsx
isActive
  ? "ga-sidebar-active border-app-line text-app-textStrong"
  : "border-transparent text-app-text hover:border-app-line hover:bg-white/64"
```

The row base class should include:

```tsx
"group flex min-h-[42px] w-full items-center gap-2 rounded-xl border px-2.5 py-2 text-left transition"
```

Expected:
- Active state is communicated by a left rail and text weight.
- Inactive rows stay flatter.

- [ ] **Step 4: Reduce action button visual weight**

For per-conversation action buttons inside the row, keep AntD `Button type="text"` but ensure the class includes:

```tsx
className="shrink-0 text-app-muted opacity-0 transition group-hover:opacity-100 focus:opacity-100"
```

Expected:
- Rows scan cleanly until hovered/focused.
- Keyboard access still reveals the action button.

- [ ] **Step 5: Verify sidebar does not regress mobile drawer**

Run:

```powershell
npm --prefix frontends/webui run build
```

Expected:
- Build exits `0`.
- No TypeScript errors around sidebar props or class names.

---

### Task 5: Turn Execution Rendering Into A Run Timeline

**Files:**
- Modify: `frontends/webui/src/App.tsx`
- Modify: `frontends/webui/src/styles.css`

- [ ] **Step 1: Tighten execution section wrapper**

In `InlineExecutionTurns`, replace:

```tsx
<section className="mb-5 border-b border-app-line/70 pb-4">
```

with:

```tsx
<section className="mb-5 border-b border-app-line pb-4">
```

Expected:
- Execution process is still separated from assistant final text.

- [ ] **Step 2: Add timeline rail to each execution turn**

In `InlineExecutionTurn`, replace the section class:

```tsx
<section className={`rounded-[18px] border bg-white/90 ${active ? "border-app-primary/30" : "border-app-line/70"}`}>
```

with:

```tsx
<section
  className={`ga-run-rail rounded-xl border bg-white ${
    active ? "border-app-primary/45 shadow-soft" : "border-app-line"
  }`}
>
```

Expected:
- Active execution turn gets a subtle active border, not a large colored block.

- [ ] **Step 3: Replace status dot with timeline node**

Inside the execution turn header, replace the existing status dot span with:

```tsx
<span
  className={`relative z-[1] inline-flex h-3 w-3 shrink-0 rounded-full ring-4 ${
    active
      ? "animate-pulse bg-app-primary ring-app-primarySoft"
      : "bg-app-success ring-[#e9f6ef]"
  }`}
/>
```

Expected:
- Running state is visible through a small signal node.

- [ ] **Step 4: Tighten tool call cards**

In `ExecutionToolCallCard`, replace:

```tsx
<section className="rounded-[18px] border border-app-line/70 bg-white">
```

with:

```tsx
<section className="rounded-xl border border-app-line bg-app-surface">
```

Update the header button padding from `px-4 py-3` to:

```tsx
className="flex w-full items-center justify-between gap-3 px-3.5 py-2.5 text-left"
```

Expected:
- Tool calls feel like rows in a run monitor.

- [ ] **Step 5: Update code/result block styling**

In `ExecutionToolCallCard`, update both `pre` elements from rounded `2xl` to:

```tsx
className="mt-2 overflow-x-auto rounded-lg bg-app-codeBg px-3.5 py-3 text-xs leading-6 text-app-codeText"
```

Expected:
- Code/result output is still inspectable, but visually more compact.

- [ ] **Step 6: Verify backend display contract tests**

Run:

```powershell
py -3 -m unittest tests.test_webui_server -v
```

Expected:
- `Ran 62 tests ... OK`.
- Existing `ResourceWarning` from `agentmain.py` is acceptable if tests pass.

---

### Task 6: Make Chat Messages More Workbench-Like

**Files:**
- Modify: `frontends/webui/src/App.tsx`
- Modify: `frontends/webui/src/styles.css`

- [ ] **Step 1: Replace message card CSS**

In `styles.css`, replace message rules with:

```css
.ga-message-card {
  border-radius: 12px;
  border: 1px solid #d9e0e8;
  box-shadow: 0 4px 14px rgba(17, 24, 39, 0.045);
}

.ga-message-assistant {
  background: rgba(255, 255, 255, 0.96);
}

.ga-message-user {
  border-color: rgba(23, 32, 51, 0.16);
  background: #172033;
  box-shadow: 0 8px 20px rgba(17, 24, 39, 0.14);
}
```

Expected:
- Assistant output reads like a work document.
- User prompt remains distinct but not bright-blue.

- [ ] **Step 2: Reduce message max widths**

In `ChatMessageView`, replace:

```tsx
<div className={isUser ? "max-w-[88%]" : "w-full max-w-[92%]"}>
```

with:

```tsx
<div className={isUser ? "max-w-[78%]" : "w-full max-w-[94%]"}>
```

Expected:
- User messages stop dominating the work area.
- Assistant remains broad enough for tool execution and markdown.

- [ ] **Step 3: Tighten message padding**

In `ChatMessageView`, replace:

```tsx
className={`ga-message-card px-5 py-4 ${
```

with:

```tsx
className={`ga-message-card px-4 py-3.5 ${
```

Expected:
- Conversation density improves without hurting readability.

- [ ] **Step 4: Update metadata color and weight**

In the message metadata line, use:

```tsx
<div className={`mb-2 text-[11px] font-medium ${isUser ? "text-white/62" : "text-app-muted"}`}>
```

Expected:
- Metadata is legible but no longer visually loud.

- [ ] **Step 5: Verify markdown readability**

Run:

```powershell
npm --prefix frontends/webui run build
```

Expected:
- Build exits `0`.

---

### Task 7: Redesign Empty State And Composer As Command Surface

**Files:**
- Modify: `frontends/webui/src/App.tsx`
- Modify: `frontends/webui/src/styles.css`

- [ ] **Step 1: Make empty state less like a landing page**

In `EmptyState`, replace the outer section class:

```tsx
<section className="flex min-h-full flex-col justify-center px-4 pb-12 pt-8 sm:px-6">
```

with:

```tsx
<section className="flex min-h-full flex-col justify-center px-4 pb-10 pt-6 sm:px-6">
```

Replace heading classes:

```tsx
<h2 className="mt-6 text-3xl font-semibold text-app-text sm:text-4xl">
```

with:

```tsx
<h2 className="mt-5 text-2xl font-semibold text-app-textStrong sm:text-3xl">
```

Expected:
- The first screen feels like a ready workbench, not a hero page.

- [ ] **Step 2: Tighten empty state text**

Keep existing Chinese copy if desired, but change paragraph classes to:

```tsx
<p className="mx-auto mt-2 max-w-xl text-sm leading-7 text-app-muted">
```

Expected:
- Supporting text stays secondary.

- [ ] **Step 3: Apply command surface class to empty composer**

In `EmptyState`, replace the input surface class:

```tsx
className="rounded-2xl border border-app-line bg-white/95 px-5 py-4 shadow-[0_10px_30px_rgba(31,41,55,0.08)] backdrop-blur"
```

with:

```tsx
className="ga-composer-surface rounded-xl px-4 py-3.5"
```

Expected:
- Composer becomes the primary command surface.

- [ ] **Step 4: Apply command surface class to bottom composer**

In `ChatComposer`, replace the form class:

```tsx
<form className="shrink-0 border-t border-app-line/70 bg-white/82 px-3 py-3 backdrop-blur md:px-4 md:py-4" onSubmit={onSubmit}>
```

with:

```tsx
<form className="shrink-0 border-t border-app-line bg-white/86 px-3 py-3 backdrop-blur md:px-4 md:py-4" onSubmit={onSubmit}>
```

Replace the inner surface class:

```tsx
className="mx-auto max-w-[900px] rounded-2xl border border-app-line bg-white px-4 py-3 shadow-[0_10px_30px_rgba(31,41,55,0.08)]"
```

with:

```tsx
className="ga-composer-surface mx-auto max-w-[900px] rounded-xl px-4 py-3"
```

Expected:
- The input surface is premium, restrained, and visually consistent.

- [ ] **Step 5: Verify composer states**

Run:

```powershell
npm --prefix frontends/webui run build
```

Expected:
- Build exits `0`.
- No JSX class replacement mistakes.

---

### Task 8: Browser Visual QA And Responsive Acceptance

**Files:**
- No source edits unless QA finds a visual bug.
- Save screenshots under `temp/`.

- [ ] **Step 1: Start WebUI server**

Run:

```powershell
py -3 launch.pyw --webui --port 18610
```

If port `18610` is already in use, use the existing running server if it serves the current workspace. If it is stale, stop only the verified process using that port, then restart.

Expected:
- WebUI is reachable at `http://127.0.0.1:18610`.

- [ ] **Step 2: Desktop screenshot QA**

Using Chrome DevTools MCP:

1. Navigate to `http://127.0.0.1:18610`.
2. Set viewport to `1440x960`.
3. Capture screenshot to:

```text
temp/webui-workbench-desktop.png
```

Acceptance:
- Topbar is quiet and dense.
- Sidebar scans as navigation, not stacked cards.
- Composer is the primary command surface.
- Assistant messages are document-like.
- User bubble is dark graphite, not bright blue.
- No text overlap.
- No horizontal scroll.

- [ ] **Step 3: Mobile drawer screenshot QA**

Using Chrome DevTools MCP:

1. Set viewport to `500x900`.
2. Open the sidebar drawer.
3. Capture screenshot to:

```text
temp/webui-workbench-mobile.png
```

Acceptance:
- Drawer background matches sidebar.
- Conversation row action button does not trigger conversation switch.
- Dropdowns and modals appear above the drawer.
- Touch targets are at least 38px visual height and practical 44px hit area through AntD spacing.
- No horizontal scroll.

- [ ] **Step 4: Execution-state screenshot QA**

Use an existing conversation with execution logs or start a small prompt that produces tool execution. Capture:

```text
temp/webui-workbench-execution.png
```

Acceptance:
- Execution turns render as a timeline/run monitor.
- Tool calls remain visible and expandable.
- Active running state is noticeable through a small signal node.
- Tool result/code blocks remain readable.
- Final assistant answer is visually separated from execution process.

- [ ] **Step 5: Console and accessibility smoke**

Using Chrome DevTools MCP:

1. Check console messages.
2. Run Lighthouse snapshot or accessibility audit if available.

Expected:
- No runtime console errors.
- No obvious missing accessible names for icon-only buttons.
- Existing text inputs keep `id` / `name`.

- [ ] **Step 6: Stop temporary server**

If this task started a new temporary server, stop only that verified process.

Expected:
- No stray WebUI process remains from QA.

---

### Task 9: Final Verification And Commit

**Files:**
- Modified files from prior tasks only.

- [ ] **Step 1: Run frontend build**

Run:

```powershell
npm --prefix frontends/webui run build
```

Expected:
- Build exits `0`.
- AntD chunk-size warning is acceptable.

- [ ] **Step 2: Run backend WebUI contract tests**

Run:

```powershell
py -3 -m unittest tests.test_webui_server -v
```

Expected:
- `Ran 62 tests ... OK`.
- Existing `ResourceWarning` from `agentmain.py` is acceptable if tests pass.

- [ ] **Step 3: Run Python compile check**

Run:

```powershell
py -3 -m py_compile frontends\webui_server.py launch.pyw
```

Expected:
- Exit code `0`.

- [ ] **Step 4: Review git diff**

Run:

```powershell
git diff --stat -- frontends/webui docs/superpowers/plans/2026-05-08-webui-workbench-visual-polish.md
git diff -- frontends/webui/src/theme.ts frontends/webui/tailwind.config.ts frontends/webui/src/styles.css --check
```

Expected:
- Only planned frontend files and this plan are changed.
- No whitespace errors.
- No changes to `frontends/webui_server.py` unless a real bug was discovered and explicitly justified.

- [ ] **Step 5: Exclude unrelated dirty files**

Run:

```powershell
git status --short
```

Expected:
- Existing unrelated files such as `memory/file_access_stats.json`, `AGENTS.main.backup.md`, and `assets/sys_prompt.2026-04-22` remain unstaged if present.

- [ ] **Step 6: Commit planned changes**

Stage only the planned files:

```powershell
git add -- frontends/webui/src/theme.ts frontends/webui/tailwind.config.ts frontends/webui/src/styles.css frontends/webui/src/App.tsx docs/superpowers/plans/2026-05-08-webui-workbench-visual-polish.md
git commit -m "Refine webui workbench visual design"
```

Expected:
- Commit succeeds.
- Unrelated dirty files remain uncommitted.

---

## Self-Review Checklist

- Spec coverage: The plan covers color tokens, AntD token alignment, Tailwind palette, shell, topbar, sidebar, messages, composer, execution timeline, responsive QA, and final verification.
- Contract boundary: No task changes backend display parsing, SSE behavior, GA core, or tool handlers.
- Accessibility: Touch targets remain AntD-backed; icon-only buttons keep existing labels/tooltips; browser QA includes accessible-name smoke.
- Visual quality: The plan reduces decorative gradients, lowers radius, reduces random shadows, introduces graphite shell structure, and shifts active state to a restrained signal accent.
- Testing: Each implementation group has `npm --prefix frontends/webui run build`; execution-related changes also run `py -3 -m unittest tests.test_webui_server -v`.
- No placeholders: All steps include exact file paths, exact class/token targets, commands, and expected results.
