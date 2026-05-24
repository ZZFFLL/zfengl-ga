import assert from "node:assert/strict";
import test from "node:test";
import {
  applyStreamEvent,
  appendFinalAssistantMessage,
  buildTurnRounds,
  createInitialTurnState,
  mergeCompletedTurnIntoHistory,
  buildThreadItems,
} from "./state.ts";

const baseEvent = {
  turn_id: "turn-1",
  session_id: "web:local",
};

test("answer.delta appends streaming text and marks state streaming", () => {
  let state = createInitialTurnState("turn-1");
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "answer.delta",
    data: { delta: "hel" },
  });
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "answer.delta",
    data: { delta: "lo" },
  });

  assert.equal(state.answer, "hello");
  assert.equal(state.status, "streaming");
});

test("phase.update replaces current phase", () => {
  const state = applyStreamEvent(createInitialTurnState("turn-1"), {
    ...baseEvent,
    type: "phase.update",
    data: { phase: "calling_tool", label: "Calling tool" },
  });

  assert.deepEqual(state.phase, { phase: "calling_tool", label: "正在调用工具" });
});

test("phase.update localizes legacy English status labels", () => {
  const state = applyStreamEvent(createInitialTurnState("turn-1"), {
    ...baseEvent,
    type: "phase.update",
    data: { phase: "understanding", label: "Understanding request" },
  });

  assert.deepEqual(state.phase, { phase: "understanding", label: "正在理解请求" });
});

test("tool.start and tool.end maintain tool cards", () => {
  let state = createInitialTurnState("turn-1");
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "tool.start",
    data: { id: "tool-1", name: "Search" },
  });
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "tool.end",
    data: { id: "tool-1", name: "Search", status: "done", summary: "Found result", elapsed_ms: 42 },
  });

  assert.deepEqual(state.tools, [
    {
      id: "tool-1",
      name: "Search",
      status: "done",
      summary: "Found result",
      elapsedMs: 42,
    },
  ]);
});

test("timeline.step updates execution steps and artifact.created stores artifacts", () => {
  let state = createInitialTurnState("turn-1");
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "timeline.step",
    data: {
      id: "thought-1",
      kind: "thought",
      title: "已完成思考",
      status: "done",
      summary: "分析任务",
      detail: "需要查询天气并写入文件。",
    },
  });
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "timeline.step",
    data: {
      id: "tool-1",
      kind: "command",
      title: "执行命令",
      status: "running",
      summary: "python script.py",
      detail: "参数：script.py",
    },
  });
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "timeline.step",
    data: {
      id: "tool-1",
      kind: "command",
      title: "执行命令",
      status: "done",
      summary: "写入完成",
      detail: "结果：ok",
      input: "{'cmd': 'python script.py'}",
      output: "ok",
      elapsed_ms: 1530,
    },
  });
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "artifact.created",
    data: { id: "artifact-1", name: "长沙天气.txt", kind: "file", path: "长沙天气.txt" },
  });

  assert.deepEqual(state.steps.map((step) => [step.id, step.kind, step.status]), [
    ["thought-1", "thought", "done"],
    ["tool-1", "command", "done"],
  ]);
  assert.deepEqual(state.steps.map((step) => step.turn_id), ["turn-1", "turn-1"]);
  assert.equal(state.steps[1].detail, "结果：ok");
  assert.equal(state.steps[1].input, "{'cmd': 'python script.py'}");
  assert.equal(state.steps[1].output, "ok");
  assert.equal(state.steps[1].elapsed_ms, 1530);
  assert.deepEqual(state.artifacts, [
    { id: "artifact-1", turn_id: "turn-1", name: "长沙天气.txt", kind: "file", path: "长沙天气.txt" },
  ]);
});

test("timeline.step preserves Bub tool display metadata", () => {
  const state = applyStreamEvent(createInitialTurnState("turn-1"), {
    ...baseEvent,
    type: "timeline.step",
    data: {
      id: "turn-1:call-1",
      kind: "tape",
      title: "正在搜索记忆",
      status: "running",
      summary: "query: bb-browser",
      detail: "参数：{\"query\":\"bb-browser\"}",
      tool_name: "tape.search",
      tool_label: "搜索记忆",
    },
  });

  assert.equal(state.steps[0].kind, "tape");
  assert.equal(state.steps[0].tool_name, "tape.search");
  assert.equal(state.steps[0].tool_label, "搜索记忆");
});

test("timeline.step output_delta appends to an existing tool card", () => {
  let state = createInitialTurnState("turn-1");
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "timeline.step",
    data: {
      id: "turn-1:tool:1",
      response_id: "turn-1:response:1",
      kind: "command",
      title: "调用 code_run",
      status: "running",
      summary: "正在执行 code_run",
      detail: "",
      input: "{}",
    },
  });
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "timeline.step",
    data: {
      id: "turn-1:tool:1",
      response_id: "turn-1:response:1",
      kind: "command",
      title: "调用 code_run",
      status: "running",
      summary: "正在执行 code_run",
      detail: "",
      output_delta: "line 1\n",
    },
  });
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "timeline.step",
    data: {
      id: "turn-1:tool:1",
      response_id: "turn-1:response:1",
      kind: "command",
      title: "调用 code_run",
      status: "done",
      summary: "执行完成",
      detail: "",
      output_delta: "line 2\n",
    },
  });

  assert.equal(state.steps[0].output, "line 1\nline 2\n");
  assert.equal(state.steps[0].status, "done");
});

test("timeline.step hides round start/end phases and preserves model output default open state", () => {
  let state = createInitialTurnState("turn-1");
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "timeline.step",
    data: {
      id: "turn-1:response:1:phase:1:start",
      response_id: "turn-1:response:1",
      kind: "phase",
      title: "第 1 轮开始",
      status: "done",
      detail: "",
    },
  });
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "timeline.step",
    data: {
      id: "turn-1:response:1:phase:1:llm",
      response_id: "turn-1:response:1",
      kind: "phase",
      title: "用户请求今日AI新闻，调用搜索获取",
      status: "done",
      detail: "我需要先调用搜索工具。",
      elapsed_ms: 987,
      default_open: false,
    },
  });
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "timeline.step",
    data: {
      id: "turn-1:response:1:phase:1:end",
      response_id: "turn-1:response:1",
      kind: "phase",
      title: "第 1 轮结束",
      status: "done",
      detail: "",
    },
  });

  assert.deepEqual(state.steps.map((step) => step.title), ["用户请求今日AI新闻，调用搜索获取"]);
  assert.equal(state.steps[0].detail, "我需要先调用搜索工具。");
  assert.equal(state.steps[0].elapsed_ms, 987);
  assert.equal(state.steps[0].default_open, false);
});

test("turn.error records the error and turn.done preserves error status", () => {
  let state = createInitialTurnState("turn-1");
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "turn.error",
    data: { message: "boom" },
  });
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "turn.done",
    data: {},
  });

  assert.equal(state.error, "boom");
  assert.equal(state.status, "error");
});

test("answer.final stores a completed response and turn.done marks successful turns done", () => {
  let state = createInitialTurnState("turn-1");
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "answer.delta",
    data: { delta: "draft" },
  });
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "answer.final",
    data: { text: "final answer" },
  });
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "turn.done",
    data: {},
  });

  assert.equal(state.answer, "");
  assert.equal(state.finalAnswer, "final answer");
  assert.deepEqual(state.responses, [{ id: "turn-1:response:1", content: "final answer" }]);
  assert.equal(state.status, "done");
  assert.deepEqual(state.phase, { phase: "done", label: "本轮执行完成" });
});

test("turn.done closes any still-running execution steps without adding a completion node", () => {
  let state = createInitialTurnState("turn-1");
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "timeline.step",
    data: {
      id: "turn-1:tool:1",
      kind: "search",
      title: "正在搜索",
      status: "running",
      summary: "查询资料",
      detail: "参数：长沙天气",
    },
  });
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "answer.final",
    data: { text: "最终回答" },
  });
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "turn.done",
    data: { ok: true },
  });

  assert.equal(state.status, "done");
  assert.deepEqual(
    state.steps.map((step) => [step.id, step.status]),
    [["turn-1:tool:1", "done"]],
  );
});

test("turn.error marks any still-running execution steps as failed", () => {
  let state = createInitialTurnState("turn-1");
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "timeline.step",
    data: {
      id: "turn-1:tool:1",
      kind: "command",
      title: "正在执行命令",
      status: "running",
      summary: "执行本地命令",
      detail: "",
    },
  });
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "turn.error",
    data: { message: "boom" },
  });

  assert.equal(state.status, "error");
  assert.deepEqual(state.steps.map((step) => [step.id, step.status]), [
    ["turn-1:tool:1", "failed"],
    ["turn-1:complete", "failed"],
  ]);
});

test("answer.final supports multiple completed responses inside one turn", () => {
  let state = createInitialTurnState("turn-1");
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "answer.delta",
    data: { delta: "第一段" },
  });
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "answer.final",
    data: { text: "第一段" },
  });
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "answer.delta",
    data: { delta: "第二段" },
  });
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "answer.final",
    data: { text: "第二段", response_id: "custom-response" },
  });

  assert.equal(state.answer, "");
  assert.deepEqual(state.responses, [
    { id: "turn-1:response:1", content: "第一段" },
    { id: "custom-response", content: "第二段" },
  ]);
});

test("answer.delta binds streaming draft to the response round used by tools and final text", () => {
  let state = createInitialTurnState("turn-1");
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "answer.delta",
    data: { delta: "我先查一下。", response_id: "turn-1:response:1" },
  });
  assert.equal(state.currentResponseId, "turn-1:response:1");
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "timeline.step",
    data: {
      id: "turn-1:call-1",
      turn_id: "turn-1",
      response_id: "turn-1:response:1",
      kind: "search",
      title: "抓取网页已完成",
      status: "done",
      summary: "ok",
      detail: "",
    },
  });
  state = applyStreamEvent(state, {
    ...baseEvent,
    type: "answer.final",
    data: { text: "我先查一下。", response_id: "turn-1:response:1" },
  });

  assert.equal(state.currentResponseId, "");
  assert.deepEqual(state.responses, [{ id: "turn-1:response:1", content: "我先查一下。" }]);
  assert.deepEqual(
    buildTurnRounds(
      [{ role: "assistant", content: "我先查一下。", created_at: "2026-05-23T00:00:01.000Z", turn_id: "turn-1", response_id: "turn-1:response:1" }],
      state.steps,
      [],
    )[0].items.map((item) => item.type),
    ["step", "message"],
  );
});

test("appendFinalAssistantMessage appends completed answer without refetch replacement", () => {
  const messages = [{ role: "user", content: "你好", created_at: "2026-05-23T00:00:00.000Z" }];
  const turn = {
    ...createInitialTurnState("turn-1"),
    finalAnswer: "最终回答",
    responses: [{ id: "turn-1:response:1", content: "最终回答" }],
    status: "done",
  };

  const next = appendFinalAssistantMessage(messages, turn, "2026-05-23T00:00:01.000Z");

  assert.deepEqual(next, [
    { role: "user", content: "你好", created_at: "2026-05-23T00:00:00.000Z" },
    {
      role: "assistant",
      content: "最终回答",
      turn_id: "turn-1",
      response_id: "turn-1:response:1",
      created_at: "2026-05-23T00:00:01.000Z",
    },
  ]);
});

test("appendFinalAssistantMessage appends every completed response", () => {
  const messages = [{ role: "user", content: "执行", created_at: "2026-05-23T00:00:00.000Z" }];
  const turn = {
    ...createInitialTurnState("turn-1"),
    responses: [
      { id: "r1", content: "先说明计划" },
      { id: "r2", content: "最终结果" },
    ],
    status: "done",
  };

  const next = appendFinalAssistantMessage(messages, turn, "2026-05-23T00:00:01.000Z");

  assert.deepEqual(next.map((message) => message.content), ["执行", "先说明计划", "最终结果"]);
  assert.deepEqual(next.slice(1).map((message) => message.turn_id), ["turn-1", "turn-1"]);
});

test("appendFinalAssistantMessage skips errored or empty turns", () => {
  const messages = [{ role: "user", content: "你好", created_at: "2026-05-23T00:00:00.000Z" }];
  const errored = { ...createInitialTurnState("turn-1"), answer: "失败回答", status: "error" };
  const empty = { ...createInitialTurnState("turn-2"), status: "done" };

  assert.equal(appendFinalAssistantMessage(messages, errored, "now"), messages);
  assert.equal(appendFinalAssistantMessage(messages, empty, "now"), messages);
});

test("mergeCompletedTurnIntoHistory keeps completed timeline and artifacts for later turns", () => {
  const messages = [{ role: "user", content: "第一轮", created_at: "2026-05-23T00:00:00.000Z" }];
  const turn = {
    ...createInitialTurnState("turn-1"),
    responses: [{ id: "r1", content: "第一轮回答" }],
    steps: [
      {
        id: "turn-1:tool:1",
        turn_id: "turn-1",
        kind: "search",
        title: "web_fetch 已完成",
        status: "done",
        summary: "ok",
        detail: "",
      },
    ],
    artifacts: [{ id: "turn-1:artifact:1", turn_id: "turn-1", name: "result.txt", kind: "file", path: "result.txt" }],
    status: "done",
  };

  const next = mergeCompletedTurnIntoHistory(messages, [], [], turn);

  assert.deepEqual(next.messages.map((message) => message.content), ["第一轮", "第一轮回答"]);
  assert.deepEqual(next.timeline.map((step) => step.id), ["turn-1:tool:1"]);
  assert.deepEqual(next.artifacts.map((artifact) => artifact.name), ["result.txt"]);
});

test("buildThreadItems keeps refreshed turn messages and timeline together", () => {
  const items = buildThreadItems(
    [
      { role: "user", content: "解释 Bub", created_at: "2026-05-23T00:00:00.000Z", turn_id: "turn-1" },
      { role: "assistant", content: "最终回复", created_at: "2026-05-23T00:00:02.000Z", turn_id: "turn-1" },
    ],
    [
      {
        id: "turn-1:tool:1",
        turn_id: "turn-1",
        kind: "command",
        title: "执行 JavaScript 已完成",
        status: "done",
        summary: "ok",
        detail: "",
      },
    ],
    [],
  );

  assert.equal(items.length, 1);
  assert.equal(items[0].type, "turn");
  assert.deepEqual(items[0].messages.map((message) => message.role), ["user", "assistant"]);
  assert.deepEqual(items[0].steps.map((step) => step.id), ["turn-1:tool:1"]);
});

test("buildThreadItems splits execution steps by assistant response", () => {
  const items = buildThreadItems(
    [
      { role: "user", content: "分析账单", created_at: "2026-05-23T00:00:00.000Z", turn_id: "turn-1" },
      {
        role: "assistant",
        content: "好的，我来读取并分析您的账单文件。",
        created_at: "2026-05-23T00:00:01.000Z",
        turn_id: "turn-1",
        response_id: "turn-1:response:1",
      },
      {
        role: "assistant",
        content: "找到了！账单目录下有多个文件。让我逐一分析。",
        created_at: "2026-05-23T00:00:03.000Z",
        turn_id: "turn-1",
        response_id: "turn-1:response:2",
      },
    ],
    [
      {
        id: "turn-1:tool:1",
        turn_id: "turn-1",
        response_id: "turn-1:response:1",
        kind: "read",
        title: "读取文件已完成",
        status: "done",
        summary: "账单A",
        detail: "",
      },
      {
        id: "turn-1:tool:2",
        turn_id: "turn-1",
        response_id: "turn-1:response:2",
        kind: "command",
        title: "执行命令已完成",
        status: "done",
        summary: "parsed",
        detail: "",
      },
    ],
    [],
  );

  assert.equal(items.length, 1);
  assert.equal(items[0].type, "turn");
  assert.deepEqual(
    items[0].rounds.map((round) => ({
      message: round.message?.content,
      steps: round.steps.map((step) => step.id),
    })),
    [
      { message: "好的，我来读取并分析您的账单文件。", steps: ["turn-1:tool:1"] },
      { message: "找到了！账单目录下有多个文件。让我逐一分析。", steps: ["turn-1:tool:2"] },
    ],
  );
});

test("buildThreadItems places execution steps above each assistant response round", () => {
  const items = buildThreadItems(
    [
      { role: "user", content: "分析项目", created_at: "2026-05-23T00:00:00.000Z", turn_id: "turn-1" },
      {
        role: "assistant",
        content: "我会先查看目录。",
        created_at: "2026-05-23T00:00:03.000Z",
        turn_id: "turn-1",
        response_id: "turn-1:response:1",
      },
      {
        role: "assistant",
        content: "目录结构如下。",
        created_at: "2026-05-23T00:00:05.000Z",
        turn_id: "turn-1",
        response_id: "turn-1:response:2",
      },
    ],
    [
      {
        id: "turn-1:thought:1",
        turn_id: "turn-1",
        response_id: "turn-1:response:1",
        kind: "thought",
        title: "已完成思考",
        status: "done",
        summary: "需要确认目录",
        detail: "需要确认目录",
        created_at: "2026-05-23T00:00:01.000Z",
      },
      {
        id: "turn-1:tool:1",
        turn_id: "turn-1",
        response_id: "turn-1:response:2",
        kind: "command",
        title: "执行命令已完成",
        status: "done",
        summary: "dir",
        detail: "",
        created_at: "2026-05-23T00:00:06.000Z",
      },
    ],
    [],
  );

  assert.equal(items[0].type, "turn");
  assert.deepEqual(
    items[0].rounds.flatMap((round) => round.items.map((item) => item.type)),
    ["step", "message", "step", "message"],
  );
});

test("buildThreadItems places legacy unowned timeline before the following assistant message", () => {
  const items = buildThreadItems(
    [
      { role: "user", content: "解释 Bub", created_at: "2026-05-23T00:00:00.000Z" },
      { role: "assistant", content: "最终回复", created_at: "2026-05-23T00:00:02.000Z" },
    ],
    [
      {
        id: "turn-legacy:tool:1",
        turn_id: "turn-legacy",
        kind: "command",
        title: "执行 JavaScript 已完成",
        status: "done",
        summary: "ok",
        detail: "",
        created_at: "2026-05-23T00:00:01.000Z",
      },
    ],
    [],
  );

  assert.deepEqual(
    items.map((item) => (item.type === "message" ? item.message.role : "timeline")),
    ["user", "timeline", "assistant"],
  );
});
