import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";

async function readSource(relativePath) {
  return readFile(path.resolve(relativePath), "utf8");
}

test("App wires the workbench context shell surfaces", async () => {
  const appSource = await readSource("frontends/webui/src/App.tsx");

  assert.match(appSource, /\bWorkbenchContextPanel\b/);
  assert.match(appSource, /\bchooseWorkbenchContextTab\b/);
  assert.match(appSource, /\bDrawer\b/);
  assert.match(appSource, /\bSplitter\b/);
  assert.match(appSource, /ga-workbench-main-panel/);
  assert.match(appSource, /ga-workbench-context-panel/);
  assert.match(appSource, /rootClassName="ga-context-drawer-root xl:hidden"/);
  assert.match(appSource, /className="ga-context-drawer"/);
  assert.match(appSource, /aria-label="工作上下文"/);
  assert.match(appSource, /CONTEXT_DRAWER_DESKTOP_QUERY\s*=\s*"\(min-width: 1280px\)"/);
  assert.match(appSource, /window\.matchMedia\(CONTEXT_DRAWER_DESKTOP_QUERY\)/);
  assert.match(appSource, /open=\{contextDrawerOpen && !contextDrawerDesktop\}/);
  assert.match(appSource, /width="min\(92vw, 360px\)"/);
  assert.match(appSource, /setContextDrawerOpen\(false\)/);
  assert.doesNotMatch(
    appSource,
    /turns\.length > 0 \? turns : activeConversation\?\.execution_log \?\? \[\]/,
  );
  assert.match(appSource, /running \? \[\] : activeConversation\?\.execution_log/);
});

test("workbench does not add subagent or inspector API surfaces", async () => {
  const [appSource, apiSource] = await Promise.all([
    readSource("frontends/webui/src/App.tsx"),
    readSource("frontends/webui/src/api.ts"),
  ]);

  assert.doesNotMatch(
    appSource,
    /\bSubagent(?:Inspector|Panel|Drawer)?\b|\bsubagent\b|\bRunInspector\b|\bCheckpoint(?:Inspector|Panel|Drawer)?\b|\bArtifactInspector\b/i,
  );
  assert.doesNotMatch(apiSource, /\/api\/(?:subagents|runs|checkpoints|artifacts)\b/i);
});

test("TopBar exposes the context entry points", async () => {
  const topBarSource = await readSource("frontends/webui/src/components/shell/TopBar.tsx");

  assert.match(topBarSource, /\bonOpenContext\b/);
  assert.match(topBarSource, /上下文/);
});

test("workbench hides inline context panel below desktop breakpoint", async () => {
  const workbenchCss = await readSource("frontends/webui/src/styles/workbench.css");

  assert.match(workbenchCss, /@media\s*\(max-width:\s*1279px\)/);
  assert.match(workbenchCss, /\.ga-workbench-context-panel\s*\{[^}]*display:\s*none\s*!important;/s);
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
