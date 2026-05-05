import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL } from "node:url";

const moduleUrl = pathToFileURL(
  path.resolve("frontends/webui/src/execution-panel-state.ts"),
).href;
const {
  buildExecutionChipLabel,
  buildExecutionPanelStateClassName,
  findLatestExecutionMessageId,
  resolveExecutionPanelToggle,
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
  { id: "a-2", role: "assistant", executionLog: [{ turn: 3, title: "Final polish", content: "Final polish" }] },
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
  assert.equal(buildExecutionChipLabel(persistedTurns, true), "正在思考");
  assert.equal(buildExecutionChipLabel(persistedTurns, false), "已完成思考");
  assert.equal(buildExecutionChipLabel([], false), null);
});

test("resolveExecutionChipRunning stays active for tool-only pending updates", () => {
  assert.equal(resolveExecutionChipRunning(true, false), true);
  assert.equal(resolveExecutionChipRunning(false, true), true);
  assert.equal(resolveExecutionChipRunning(false, false), false);
});

test("buildExecutionPanelStateClassName toggles the desktop panel animation state", () => {
  assert.match(buildExecutionPanelStateClassName(true), /relative/);
  assert.match(buildExecutionPanelStateClassName(true), /w-\[380px\]/);
  assert.match(buildExecutionPanelStateClassName(true), /opacity-100/);
  assert.match(buildExecutionPanelStateClassName(false), /w-0/);
  assert.match(buildExecutionPanelStateClassName(false), /opacity-0/);
  assert.match(buildExecutionPanelStateClassName(false), /pointer-events-none/);
});

test("resolveExecutionPanelToggle closes when clicking the selected message again", () => {
  assert.deepEqual(resolveExecutionPanelToggle("a-1", true, "a-1"), {
    open: false,
    messageId: "a-1",
  });
  assert.deepEqual(resolveExecutionPanelToggle("a-1", true, "a-2"), {
    open: true,
    messageId: "a-2",
  });
  assert.deepEqual(resolveExecutionPanelToggle(null, false, "a-1"), {
    open: true,
    messageId: "a-1",
  });
});

test("shouldShowPendingAssistant stays visible while streaming even before turns arrive", () => {
  assert.equal(shouldShowPendingAssistant(true, "", []), true);
  assert.equal(shouldShowPendingAssistant(true, "最终答复", []), false);
  assert.equal(shouldShowPendingAssistant(false, "", persistedTurns), false);
});

test("findLatestExecutionMessageId returns the latest assistant reply with execution turns", () => {
  const messageId = findLatestExecutionMessageId(messages);

  assert.equal(messageId, "a-2");
});
