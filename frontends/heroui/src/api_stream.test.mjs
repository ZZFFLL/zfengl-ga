import assert from "node:assert/strict";
import test from "node:test";

test("subscribeTurn ignores structured events from previous turns", async () => {
  const { subscribeTurn } = await import("./api.ts");
  const events = [];
  const requests = [];
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  globalThis.window = { setTimeout: () => 0 };
  globalThis.fetch = async (url) => {
    requests.push(String(url));
    return {
      ok: true,
      async json() {
        return {
          status: "idle",
          events: [
            { seq: 1, type: "turn.done", turn_id: "ga|sess-1|1", session_id: "sess-1", data: { ok: true } },
            {
              seq: 2,
              type: "timeline.step",
              turn_id: "ga|sess-1|2",
              session_id: "sess-1",
              data: { id: "step-2", turn_id: "ga|sess-1|2", title: "当前工具", status: "done" },
            },
            {
              seq: 3,
              type: "answer.final",
              turn_id: "ga|sess-1|2",
              session_id: "sess-1",
              data: { text: "当前回答", response_id: "ga|sess-1|2:response:1" },
            },
          ],
          messages: [],
        };
      },
    };
  };

  try {
    subscribeTurn("ga|sess-1|2", (event) => events.push(event));
    await new Promise((resolve) => setImmediate(resolve));
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.window = originalWindow;
  }

  assert.match(requests[0], /after_event=0/);
  assert.deepEqual(
    events.map((event) => event.turn_id),
    ["ga|sess-1|2", "ga|sess-1|2", "ga|sess-1|2"],
  );
  assert.deepEqual(events.map((event) => event.type), ["timeline.step", "answer.final", "turn.done"]);
});

test("subscribeTurn does not stream raw partial text when structured events are present", async () => {
  const { subscribeTurn } = await import("./api.ts");
  const events = [];
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  globalThis.window = { setTimeout: () => 0 };
  globalThis.fetch = async () => ({
    ok: true,
    async json() {
      return {
        status: "running",
        partial: { content: "**LLM Running**\n\nraw tool log" },
        events: [
          {
            seq: 4,
            type: "timeline.step",
            turn_id: "ga|sess-1|2",
            session_id: "sess-1",
            data: { id: "step-2", turn_id: "ga|sess-1|2", title: "当前工具", status: "running" },
          },
        ],
        messages: [],
      };
    },
  });

  try {
    subscribeTurn("ga|sess-1|2", (event) => events.push(event));
    await new Promise((resolve) => setImmediate(resolve));
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.window = originalWindow;
  }

  assert.deepEqual(events.map((event) => event.type), ["timeline.step"]);
});

test("subscribeTurn does not parse legacy outputs after an earlier structured timeline event", async () => {
  const { subscribeTurn } = await import("./api.ts");
  const events = [];
  const scheduled = [];
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  let pollCount = 0;
  globalThis.window = { setTimeout: (callback) => scheduled.push(callback) };
  globalThis.fetch = async () => {
    pollCount += 1;
    return {
      ok: true,
      async json() {
        if (pollCount === 1) {
          return {
            status: "running",
            events: [
              {
                seq: 10,
                type: "timeline.step",
                turn_id: "ga|sess-1|2",
                session_id: "sess-1",
                data: {
                  id: "ga|sess-1|2:response:1:tool:1:1",
                  turn_id: "ga|sess-1|2",
                  response_id: "ga|sess-1|2:response:1",
                  kind: "command",
                  title: "调用 code_run",
                  status: "running",
                },
              },
            ],
            messages: [],
          };
        }
        return {
          status: "idle",
          events: [],
          messages: [
            {
              id: 3,
              role: "assistant",
              content: "clean final",
              responseId: "ga|sess-1|2:response:1",
              outputs: [
                "🔧 Tool: code_run\nargs:\n{\"cmd\":\"dir\"}\n[Status] ok\n[stdout]\nfile.txt\n",
              ],
            },
          ],
        };
      },
    };
  };

  try {
    subscribeTurn("ga|sess-1|2", (event) => events.push(event));
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(scheduled.length, 1);
    scheduled.shift()();
    await new Promise((resolve) => setImmediate(resolve));
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.window = originalWindow;
  }

  assert.deepEqual(events.map((event) => event.type), ["timeline.step", "answer.final", "turn.done"]);
  assert.equal(events.filter((event) => event.type === "timeline.step").length, 1);
});
