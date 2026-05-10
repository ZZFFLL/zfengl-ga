import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL } from "node:url";

const moduleUrl = pathToFileURL(
  path.resolve("frontends/webui/src/state/workbench-context-state.ts"),
).href;
const {
  chooseWorkbenchContextTab,
  countToolCalls,
  buildTurnMeta,
  buildRuntimeSummary,
} = await import(moduleUrl);

const activeTurn = {
  turn: 7,
  title: "Inspect files",
  content: "Inspect files",
  state: "active",
  tool_calls: [
    { tool: "rg", args: "query", result: "ok", action: "search", status: "completed" },
    { tool: "sed", args: "file", result: "ok", action: "read", status: "completed" },
  ],
};

const completedTurn = {
  turn: 1,
  title: "",
  content: "Draft answer",
  state: "completed",
  tool_calls: [],
};

const runningState = {
  configured: true,
  current_llm: { index: 0, name: "gpt-5.4", current: true },
  llms: [],
  running: true,
  autonomous_enabled: false,
  last_reply_time: 0,
  active_conversation_id: null,
  execution_log: [],
};

const idleState = {
  configured: true,
  current_llm: null,
  llms: [],
  running: false,
  autonomous_enabled: true,
  last_reply_time: 0,
  active_conversation_id: null,
  execution_log: [],
};

test("chooseWorkbenchContextTab prefers activity while work is running", () => {
  assert.equal(chooseWorkbenchContextTab("status", [activeTurn], true), "activity");
});

test("chooseWorkbenchContextTab keeps a valid requested tab while idle", () => {
  assert.equal(chooseWorkbenchContextTab("status", [completedTurn], false), "status");
});

test("chooseWorkbenchContextTab falls back to status without turns", () => {
  assert.equal(chooseWorkbenchContextTab("activity", [], false), "status");
});

test("chooseWorkbenchContextTab sanitizes an invalid requested tab when idle", () => {
  assert.equal(chooseWorkbenchContextTab("stale", [completedTurn], false), "status");
});

test("countToolCalls sums all turn tool call counts", () => {
  assert.equal(countToolCalls([activeTurn, completedTurn]), 2);
});

test("buildTurnMeta returns compact turn labels", () => {
  assert.deepEqual(buildTurnMeta(activeTurn), {
    title: "Inspect files",
    statusLabel: "执行中",
    toolCallLabel: "2 个工具调用",
  });
  assert.deepEqual(buildTurnMeta(completedTurn), {
    title: "Turn 1",
    statusLabel: "已完成",
    toolCallLabel: "0 个工具调用",
  });
});

test("buildRuntimeSummary returns configured, running, model, and autonomous labels", () => {
  assert.deepEqual(buildRuntimeSummary(runningState), {
    configuredLabel: "已配置",
    runningLabel: "任务执行中",
    modelLabel: "gpt-5.4",
    autonomousLabel: "自主行动关闭",
  });
  assert.deepEqual(buildRuntimeSummary(idleState), {
    configuredLabel: "已配置",
    runningLabel: "空闲",
    modelLabel: "未选择模型",
    autonomousLabel: "自主行动开启",
  });
});
