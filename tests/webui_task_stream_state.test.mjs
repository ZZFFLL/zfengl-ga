import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL } from "node:url";

const moduleUrl = pathToFileURL(
  path.resolve("frontends/webui/src/state/task-stream-state.ts"),
).href;
const {
  buildTaskStreamItems,
  chooseActiveInspectorTarget,
} = await import(moduleUrl);

const command = {
  id: "u-1",
  role: "user",
  content: "Refactor the WebUI",
  time: "10:00",
  executionLog: [],
};

const executionTurn = {
  turn: 1,
  title: "Inspect files",
  content: "Inspect files",
  state: "completed",
  tool_calls: [
    {
      tool: "rg",
      args: "query",
      result: "ok",
      result_preview: "ok",
      action: "search",
      status: "completed",
    },
  ],
};

const response = {
  id: "a-1",
  role: "assistant",
  content: "Done",
  time: "10:01",
  executionLog: [executionTurn],
};

test("buildTaskStreamItems groups a user command with the following assistant response", () => {
  assert.deepEqual(buildTaskStreamItems([command, response], [], false), [
    {
      id: "task-u-1",
      command,
      response,
      executionLog: [executionTurn],
      pending: false,
    },
  ]);
});

test("buildTaskStreamItems keeps assistant-only legacy replies readable", () => {
  const items = buildTaskStreamItems([response], [], false);

  assert.equal(items.length, 1);
  assert.equal(items[0].id, "task-a-1");
  assert.equal(items[0].command, null);
  assert.equal(items[0].response, response);
  assert.deepEqual(items[0].executionLog, [executionTurn]);
});

test("buildTaskStreamItems prefers live execution log for the streaming assistant", () => {
  const liveTurn = { ...executionTurn, turn: 2, title: "Live turn", state: "active" };
  const pendingResponse = { ...response, id: "a-2", pending: true, executionLog: [] };
  const items = buildTaskStreamItems([command, pendingResponse], [liveTurn], true);

  assert.deepEqual(items[0].executionLog, [liveTurn]);
  assert.equal(items[0].pending, true);
});

test("buildTaskStreamItems starts a new task for each user command", () => {
  const secondCommand = { ...command, id: "u-2", content: "Run tests", time: "10:02" };
  const items = buildTaskStreamItems([command, response, secondCommand], [], false);

  assert.equal(items.length, 2);
  assert.equal(items[0].command.id, "u-1");
  assert.equal(items[0].response.id, "a-1");
  assert.equal(items[1].command.id, "u-2");
  assert.equal(items[1].response, null);
});

test("chooseActiveInspectorTarget opens only for running or explicitly selected execution", () => {
  assert.equal(chooseActiveInspectorTarget([], false, null), null);
  assert.deepEqual(chooseActiveInspectorTarget([executionTurn], true, null), {
    turnIndex: 0,
    toolIndex: null,
  });
  assert.deepEqual(chooseActiveInspectorTarget([executionTurn], false, { turnIndex: 0, toolIndex: 0 }), {
    turnIndex: 0,
    toolIndex: 0,
  });
});
