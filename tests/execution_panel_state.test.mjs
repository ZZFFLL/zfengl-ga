import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL } from "node:url";

const moduleUrl = pathToFileURL(
  path.resolve("frontends/webui/src/execution-panel-state.ts"),
).href;
const {
  buildExecutionChipLabel,
  resolveExecutionChipRunning,
  shouldShowPendingAssistant,
  resolveExecutionTurns,
} = await import(moduleUrl);

const persistedTurns = [
  { turn: 1, title: "Inspect files", content: "Inspect files" },
  { turn: 2, title: "Draft answer", content: "Draft answer" },
];

const messages = [
  { id: "u-1", role: "user", executionLog: [] },
  { id: "a-1", role: "assistant", executionLog: persistedTurns },
];

test("resolveExecutionTurns prefers live turns for the streaming assistant reply", () => {
  const liveTurns = [{ turn: 9, title: "Live turn", content: "Live turn" }];

  const resolved = resolveExecutionTurns(messages[1], liveTurns, true);

  assert.deepEqual(resolved, liveTurns);
});

test("resolveExecutionTurns falls back to persisted turns for completed replies", () => {
  const resolved = resolveExecutionTurns(messages[1], [], false);

  assert.deepEqual(resolved, persistedTurns);
});

test("buildExecutionChipLabel reflects running and completed states", () => {
  assert.equal(buildExecutionChipLabel(persistedTurns, true), "正在执行 · Draft answer");
  assert.equal(buildExecutionChipLabel(persistedTurns, false), "执行过程 · 2 轮");
  assert.equal(buildExecutionChipLabel([], false), null);
});

test("resolveExecutionChipRunning stays active for tool-only pending updates", () => {
  assert.equal(resolveExecutionChipRunning(true, false), true);
  assert.equal(resolveExecutionChipRunning(false, true), true);
  assert.equal(resolveExecutionChipRunning(false, false), false);
});

test("shouldShowPendingAssistant stays visible while streaming even before turns arrive", () => {
  assert.equal(shouldShowPendingAssistant(true, "", []), true);
  assert.equal(shouldShowPendingAssistant(true, "最终答复", []), false);
  assert.equal(shouldShowPendingAssistant(false, "", persistedTurns), false);
});
