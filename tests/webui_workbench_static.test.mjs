import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";

async function readSource(relativePath) {
  return readFile(path.resolve(relativePath), "utf8");
}

test("App wires on-demand run inspector without permanent context chrome", async () => {
  const appSource = await readSource("frontends/webui/src/App.tsx");

  assert.match(appSource, /\bRunInspector\b/);
  assert.match(appSource, /\bRunInspectorToggle\b/);
  assert.match(appSource, /\bchooseActiveInspectorTarget\b/);
  assert.match(appSource, /\bDrawer\b/);
  assert.match(appSource, /ga-workbench-main-panel/);
  assert.match(appSource, /ga-workbench-inspector-panel/);
  assert.match(appSource, /ga-workbench-content-frame/);
  assert.match(appSource, /rootClassName="ga-run-inspector-drawer-root/);
  assert.match(appSource, /className="ga-run-inspector-drawer"/);
  assert.match(appSource, /aria-label="运行详情"/);
  assert.match(appSource, /INSPECTOR_DRAWER_DESKTOP_QUERY\s*=\s*"\(min-width: 80rem\)"/);
  assert.match(appSource, /window\.matchMedia\(INSPECTOR_DRAWER_DESKTOP_QUERY\)/);
  assert.match(appSource, /const inspectorOpen = inspectorVisible && \(running \|\| Boolean\(activeInspectorTarget\)\)/);
  assert.match(appSource, /openLatestInspector/);
  assert.match(appSource, /if \(wasRunningRef\.current && !running\) \{\s*closeInspector\(\);/s);
  assert.match(appSource, /width="min\(92vw, 22\.5rem\)"/);
  assert.match(appSource, /setSelectedInspectorTarget\(null\)/);
  assert.doesNotMatch(appSource, /autoSelectInspector|autoInspectorDismissed/);
  assert.doesNotMatch(appSource, /\bSplitter\b/);
  assert.doesNotMatch(appSource, /defaultSize=\{|min=\{300\}|max=\{460\}|360px|1280px|1279px|max-w-\[920px\]/);
  assert.doesNotMatch(appSource, /\bWorkbenchContextPanel\b/);
  assert.doesNotMatch(appSource, /\bchooseWorkbenchContextTab\b/);
  assert.doesNotMatch(appSource, /contextOpen/);
  assert.doesNotMatch(
    appSource,
    /turns\.length > 0 \? turns : activeConversation\?\.execution_log \?\? \[\]/,
  );
  assert.match(appSource, /running \? \[\] : activeConversation\?\.execution_log/);
});

test("workbench does not add subagent or backend inspector API surfaces", async () => {
  const [appSource, apiSource] = await Promise.all([
    readSource("frontends/webui/src/App.tsx"),
    readSource("frontends/webui/src/api.ts"),
  ]);

  assert.doesNotMatch(
    appSource,
    /\bSubagent(?:Inspector|Panel|Drawer)?\b|\bsubagent\b|\bCheckpoint(?:Inspector|Panel|Drawer)?\b|\bArtifactInspector\b/i,
  );
  assert.doesNotMatch(apiSource, /\/api\/(?:subagents|runs|checkpoints|artifacts)\b/i);
});

test("TopBar does not expose permanent context entry points", async () => {
  const topBarSource = await readSource("frontends/webui/src/components/shell/TopBar.tsx");

  assert.doesNotMatch(topBarSource, /\bonOpenContext\b/);
  assert.doesNotMatch(topBarSource, /\bonToggleContext\b/);
  assert.doesNotMatch(topBarSource, /上下文面板/);
});

test("workbench hides inline inspector below desktop breakpoint", async () => {
  const workbenchCss = await readSource("frontends/webui/src/styles/workbench.css");

  assert.match(workbenchCss, /@media\s*\(max-width:\s*79\.999rem\)/);
  assert.match(workbenchCss, /\.ga-workbench-inspector-panel\s*\{[^}]*display:\s*none\s*!important;/s);
  assert.match(workbenchCss, /\.ga-workbench-main-panel\s*\{[^}]*width:\s*100%\s*!important;/s);
  assert.match(workbenchCss, /\.ga-workbench-inspector-panel[\s\S]*transition:/);
  assert.match(workbenchCss, /\.ga-run-inspector-toggle/);
  assert.match(workbenchCss, /clamp\(/);
  assert.doesNotMatch(workbenchCss, /1279px|1280px|300px|360px|460px/);
});

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
  assert.match(chatCss, /\.ga-task-item \.text-app-muted/);
  assert.match(chatCss, /\.ga-task-item \.markdown-content/);
  assert.match(chatCss, /\.ga-response-panel \.markdown-content/);
});

test("composer is a command dock", async () => {
  const [composerSource, chatHomeSource, chatCss, themeSource, baseStyles] = await Promise.all([
    readSource("frontends/webui/src/components/composer/Composer.tsx"),
    readSource("frontends/webui/src/components/chat/ChatHome.tsx"),
    readSource("frontends/webui/src/styles/chat.css"),
    readSource("frontends/webui/src/theme.ts"),
    readSource("frontends/webui/src/styles.css"),
  ]);

  assert.match(composerSource, /ga-command-dock/);
  assert.match(composerSource, /ga-command-input/);
  assert.doesNotMatch(composerSource, /ga-composer-surface/);
  assert.match(chatHomeSource, /ga-chat-home/);
  assert.match(chatHomeSource, /ga-home-command-dock/);
  assert.match(chatHomeSource, /ga-home-command-input/);
  assert.doesNotMatch(chatHomeSource, /ga-composer-surface|rounded-xl|rounded-2xl/);
  assert.match(chatCss, /\.ga-command-dock/);
  assert.match(chatCss, /\.ga-command-input/);
  assert.match(chatCss, /\.ga-home-command-dock[\s\S]*border:\s*0\.0625rem solid #c9c5bd/);
  assert.match(chatCss, /\.ga-home-command-dock[\s\S]*border-radius:\s*0\.625rem/);
  assert.match(chatCss, /\.ga-home-command-dock[\s\S]*box-shadow:\s*0 1\.125rem 3rem rgba\(15, 23, 42, 0\.12\)/);
  assert.match(
    chatCss,
    /\.ga-home-command-input:focus-visible,\s*\.ga-command-input:focus-visible[\s\S]*outline:\s*none;/,
  );
  assert.match(chatCss, /\.ga-home-command-input:focus[\s\S]*box-shadow:\s*none;/);
  assert.match(themeSource, /borderRadius:\s*6/);
  assert.match(themeSource, /borderRadiusLG:\s*8/);
  assert.match(themeSource, /borderRadiusSM:\s*4/);
  assert.doesNotMatch(themeSource, /borderRadius:\s*8|borderRadiusLG:\s*10|borderRadiusSM:\s*999/);
  assert.doesNotMatch(baseStyles, /rounded-\[1\.125rem\]|rounded-xl|rounded-full/);
});

test("new conversation action stays a local draft until first send", async () => {
  const appSource = await readSource("frontends/webui/src/App.tsx");
  const handleStart = appSource.indexOf("const handleCreateConversation");
  const handleEnd = appSource.indexOf("const handleRenameConversation");
  const handleCreateSource = appSource.slice(handleStart, handleEnd);

  assert.match(appSource, /draftConversationActive/);
  assert.match(
    appSource,
    /const activeConversationId = draftConversationActive\s*\?\s*null\s*:\s*activeConversation\?\.summary\.id \?\? state\?\.active_conversation_id \?\? null;/,
  );
  assert.match(handleCreateSource, /setDraftConversationActive\(true\)/);
  assert.match(handleCreateSource, /setActiveConversation\(null\)/);
  assert.match(handleCreateSource, /setMessages\(\[\]\)/);
  assert.match(handleCreateSource, /setDraft\(""\)/);
  assert.doesNotMatch(handleCreateSource, /createConversation\(|fetchConversation\(|fetchState\(|syncConversationList/);
  assert.match(appSource, /if \(!conversationId\) \{[\s\S]*setDraftConversationActive\(false\);[\s\S]*createConversation\(prompt\)/);
});

test("run inspector is manually opened, localized, and not permanent low-value chrome", async () => {
  const [appSource, taskStreamSource, inspectorSource, toggleSource, turnSource, toolCardSource, contextCss] = await Promise.all([
    readSource("frontends/webui/src/App.tsx"),
    readSource("frontends/webui/src/components/chat/TaskStream.tsx"),
    readSource("frontends/webui/src/components/context/RunInspector.tsx"),
    readSource("frontends/webui/src/components/context/RunInspectorToggle.tsx"),
    readSource("frontends/webui/src/components/execution/InlineExecutionTurn.tsx"),
    readSource("frontends/webui/src/components/execution/ExecutionToolCallCard.tsx"),
    readSource("frontends/webui/src/styles/context.css"),
  ]);

  assert.match(appSource, /\bRunInspector\b/);
  assert.match(appSource, /chooseActiveInspectorTarget/);
  assert.doesNotMatch(appSource, /\bWorkbenchContextPanel\b/);
  assert.doesNotMatch(appSource, /contextOpen/);
  assert.match(taskStreamSource, /onSelectInspectorTarget/);
  assert.match(toggleSource, /展开运行详情/);
  assert.match(toggleSource, /运行中/);
  assert.match(toggleSource, /执行详情/);
  assert.match(inspectorSource, /ga-run-inspector/);
  assert.match(inspectorSource, /selectedToolCall/);
  assert.match(inspectorSource, /任务正在启动，等待执行步骤/);
  assert.match(inspectorSource, /停止当前任务/);
  assert.match(inspectorSource, /运行详情/);
  assert.match(inspectorSource, /步骤/);
  assert.match(inspectorSource, /已选工具/);
  assert.match(inspectorSource, /此步骤暂无摘要/);
  assert.doesNotMatch(inspectorSource, /Run Inspector|Selected Tool|>Step<|>Summary</);
  assert.match(turnSource, /aria-label=\{`\$\{open \? "收起" : "展开"\} Turn \$\{turn\.turn\} 执行步骤`\}/);
  assert.doesNotMatch(turnSource, /\bSearch\b/);
  assert.doesNotMatch(turnSource, /onSelectInspectorTarget\(null\)/);
  assert.doesNotMatch(turnSource, /检查 Turn/);
  assert.match(toolCardSource, /onInspect/);
  assert.match(toolCardSource, /aria-label=\{`查看 \$\{toolCall\.tool\} 工具调用详情`\}/);
  assert.match(toolCardSource, /详情/);
  assert.doesNotMatch(toolCardSource, /\buseState\b/);
  assert.doesNotMatch(toolCardSource, /\bChevronDown\b/);
  assert.doesNotMatch(toolCardSource, /aria-expanded/);
  assert.doesNotMatch(toolCardSource, /\bresultMode\b/);
  assert.doesNotMatch(toolCardSource, /<pre|<code>|参数|结果预览|执行结果/);
  assert.doesNotMatch(toolCardSource, />\s*Inspect\s*</);
  assert.doesNotMatch(toolCardSource, />\s*Args\s*</);
  assert.doesNotMatch(toolCardSource, /`Result preview|>\s*Result preview\s*</);
  assert.doesNotMatch(toolCardSource, /`Result ·|>\s*Result\s*</);
  assert.doesNotMatch(toolCardSource, /event\.stopPropagation/);
  assert.match(contextCss, /\.ga-run-inspector/);
  assert.match(contextCss, /\.ga-run-inspector \.text-app-textStrong/);
  assert.match(contextCss, /\.ga-run-inspector \.text-app-muted/);
});

test("workbench visual system follows Codex-like light shell", async () => {
  const [
    themeSource,
    tailwindSource,
    baseCss,
    shellCss,
    sidebarCss,
    chatCss,
    contextCss,
    topBarSource,
    statusBadgeSource,
    sidebarSource,
  ] =
    await Promise.all([
      readSource("frontends/webui/src/theme.ts"),
      readSource("frontends/webui/tailwind.config.ts"),
      readSource("frontends/webui/src/styles/base.css"),
      readSource("frontends/webui/src/styles/shell.css"),
      readSource("frontends/webui/src/styles/sidebar.css"),
      readSource("frontends/webui/src/styles/chat.css"),
      readSource("frontends/webui/src/styles/context.css"),
      readSource("frontends/webui/src/components/shell/TopBar.tsx"),
      readSource("frontends/webui/src/components/app/StatusBadge.tsx"),
      readSource("frontends/webui/src/components/sidebar/ConversationSidebar.tsx"),
    ]);

  assert.match(themeSource, /bg:\s*"#f7f7f5"/);
  assert.doesNotMatch(themeSource, /darkAlgorithm/);
  assert.match(tailwindSource, /sidebar:\s*"#f3f3f1"/);
  assert.match(baseCss, /background:\s*#f7f7f5/);
  assert.match(shellCss, /background:\s*#f7f7f5/);
  assert.match(sidebarCss, /background:\s*#f3f3f1/);
  assert.match(chatCss, /\.ga-task-item[\s\S]*background:\s*#ffffff/);
  assert.match(chatCss, /\.ga-command-dock-inner[\s\S]*background:\s*#ffffff/);
  assert.match(contextCss, /\.ga-run-inspector[\s\S]*background:\s*#f8f8f6/);
  assert.match(topBarSource, /rounded-md border border-app-line bg-white/);
  assert.doesNotMatch(topBarSource, /rounded-xl/);
  assert.match(statusBadgeSource, /rounded-md/);
  assert.doesNotMatch(statusBadgeSource, /rounded-full/);
  assert.match(sidebarSource, /rounded-lg bg-white text-app-primary/);
  assert.match(sidebarSource, /rounded-md bg-white\/75/);
  assert.doesNotMatch(sidebarSource, /rounded-\[0\.9375rem\]|rounded-xl|rounded-full bg-white\/75/);
});
