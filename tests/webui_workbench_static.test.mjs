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
  assert.match(appSource, /aria-label="工作上下文"/);
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
