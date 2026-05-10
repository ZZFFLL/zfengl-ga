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
