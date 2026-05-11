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
  assert.match(appSource, /\bchooseActiveInspectorTarget\b/);
  assert.match(appSource, /\bDrawer\b/);
  assert.match(appSource, /\bSplitter\b/);
  assert.match(appSource, /ga-workbench-main-panel/);
  assert.match(appSource, /ga-workbench-inspector-panel/);
  assert.match(appSource, /rootClassName="ga-run-inspector-drawer-root xl:hidden"/);
  assert.match(appSource, /className="ga-run-inspector-drawer"/);
  assert.match(appSource, /aria-label="运行详情"/);
  assert.match(appSource, /INSPECTOR_DRAWER_DESKTOP_QUERY\s*=\s*"\(min-width: 1280px\)"/);
  assert.match(appSource, /window\.matchMedia\(INSPECTOR_DRAWER_DESKTOP_QUERY\)/);
  assert.match(appSource, /open=\{inspectorOpen && !inspectorDrawerDesktop\}/);
  assert.match(appSource, /const inspectorOpen = autoSelectInspector \|\| Boolean\(activeInspectorTarget\)/);
  assert.match(appSource, /width="min\(92vw, 360px\)"/);
  assert.match(appSource, /setSelectedInspectorTarget\(null\)/);
  assert.match(appSource, /if \(running\) \{\s*setAutoInspectorDismissed\(true\);/s);
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

  assert.match(workbenchCss, /@media\s*\(max-width:\s*1279px\)/);
  assert.match(workbenchCss, /\.ga-workbench-inspector-panel\s*\{[^}]*display:\s*none\s*!important;/s);
  assert.match(workbenchCss, /\.ga-workbench-main-panel\s*\{[^}]*width:\s*100%\s*!important;/s);
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

test("run inspector is on-demand and context panel is not permanent low-value chrome", async () => {
  const [appSource, taskStreamSource, inspectorSource, turnSource, toolCardSource, contextCss] = await Promise.all([
    readSource("frontends/webui/src/App.tsx"),
    readSource("frontends/webui/src/components/chat/TaskStream.tsx"),
    readSource("frontends/webui/src/components/context/RunInspector.tsx"),
    readSource("frontends/webui/src/components/execution/InlineExecutionTurn.tsx"),
    readSource("frontends/webui/src/components/execution/ExecutionToolCallCard.tsx"),
    readSource("frontends/webui/src/styles/context.css"),
  ]);

  assert.match(appSource, /\bRunInspector\b/);
  assert.match(appSource, /chooseActiveInspectorTarget/);
  assert.doesNotMatch(appSource, /\bWorkbenchContextPanel\b/);
  assert.doesNotMatch(appSource, /contextOpen/);
  assert.match(taskStreamSource, /onSelectInspectorTarget/);
  assert.match(inspectorSource, /ga-run-inspector/);
  assert.match(inspectorSource, /selectedToolCall/);
  assert.match(inspectorSource, /任务正在启动，等待执行步骤/);
  assert.match(inspectorSource, /停止当前任务/);
  assert.match(turnSource, /aria-label=\{`检查 Turn \$\{turn\.turn\} 执行步骤`\}/);
  assert.match(toolCardSource, /onInspect/);
  assert.match(toolCardSource, /aria-label=\{`检查 \$\{toolCall\.tool\} 工具调用`\}/);
  assert.doesNotMatch(toolCardSource, /event\.stopPropagation/);
  assert.match(contextCss, /\.ga-run-inspector/);
  assert.match(contextCss, /\.ga-run-inspector \.text-app-textStrong/);
  assert.match(contextCss, /\.ga-run-inspector \.text-app-muted/);
});
