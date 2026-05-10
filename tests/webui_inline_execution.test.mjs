import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";

test("inline execution does not expose the old detail drawer entry point", async () => {
  const appSource = await readFile(path.resolve("frontends/webui/src/App.tsx"), "utf8");

  assert.doesNotMatch(appSource, /\bonOpenExecution\b/);
  assert.doesNotMatch(appSource, /\bfunction ExecutionPanel\b/);
  assert.doesNotMatch(appSource, /\bExecutionPanelDialog\b/);
  assert.doesNotMatch(appSource, /\b--execution-width\b/);
});
