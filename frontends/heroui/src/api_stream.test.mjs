import assert from "node:assert/strict";
import test from "node:test";

test("subscribeTurn prefers EventSource and closes on turn.done", async () => {
  const { subscribeTurn } = await import("./api.ts");
  const events = [];
  const originalEventSource = globalThis.EventSource;
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  const created = [];

  class FakeEventSource {
    constructor(url) {
      this.url = url;
      this.closed = false;
      this.onmessage = null;
      this.onerror = null;
      created.push(this);
    }

    close() {
      this.closed = true;
    }
  }

  globalThis.EventSource = FakeEventSource;
  globalThis.fetch = async () => {
    throw new Error("polling fallback should not run when EventSource exists");
  };
  globalThis.window = { setTimeout: () => 0 };

  try {
    const source = subscribeTurn("ga|sess-1|1", (event) => events.push(event));
    assert.equal(created.length, 1);
    assert.match(created[0].url, /\/session\/sess-1\/events\?/);
    assert.match(created[0].url, /turn_id=ga%7Csess-1%7C1/);

    created[0].onmessage({
      data: JSON.stringify({
        seq: 2,
        type: "turn.done",
        turn_id: "ga|sess-1|1",
        session_id: "sess-1",
        data: { ok: true },
      }),
    });

    assert.equal(events[0].type, "turn.done");
    assert.equal(created[0].closed, true);
    source.close();
  } finally {
    globalThis.EventSource = originalEventSource;
    globalThis.fetch = originalFetch;
    globalThis.window = originalWindow;
  }
});

test("subscribeTurn falls back to polling when EventSource errors before data", async () => {
  const { subscribeTurn } = await import("./api.ts");
  const events = [];
  const requests = [];
  const originalEventSource = globalThis.EventSource;
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  const created = [];

  class FakeEventSource {
    constructor(url) {
      this.url = url;
      this.closed = false;
      this.onmessage = null;
      this.onerror = null;
      created.push(this);
    }

    close() {
      this.closed = true;
    }
  }

  globalThis.EventSource = FakeEventSource;
  globalThis.window = { setTimeout: () => 0 };
  globalThis.fetch = async (url) => {
    requests.push(String(url));
    return {
      ok: true,
      async json() {
        return {
          status: "idle",
          events: [],
          messages: [{ id: 2, role: "assistant", content: "done", ts: 1 }],
        };
      },
    };
  };

  try {
    const source = subscribeTurn("ga|sess-1|1", (event) => events.push(event));
    created[0].onerror(new Event("error"));
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(created[0].closed, true);
    assert.match(requests[0], /\/session\/sess-1\/messages\?/);
    assert.deepEqual(events.map((event) => event.type), ["answer.final", "turn.done"]);
    source.close();
  } finally {
    globalThis.EventSource = originalEventSource;
    globalThis.fetch = originalFetch;
    globalThis.window = originalWindow;
  }
});

test("subscribeTurn leaves EventSource open on errors after data arrives", async () => {
  const { subscribeTurn } = await import("./api.ts");
  const events = [];
  const errors = [];
  const originalEventSource = globalThis.EventSource;
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  const created = [];

  class FakeEventSource {
    constructor(url) {
      this.url = url;
      this.closed = false;
      this.onmessage = null;
      this.onerror = null;
      created.push(this);
    }

    close() {
      this.closed = true;
    }
  }

  globalThis.EventSource = FakeEventSource;
  globalThis.fetch = async () => {
    throw new Error("polling fallback should not run after SSE data arrives");
  };
  globalThis.window = { setTimeout: () => 0 };

  try {
    const source = subscribeTurn("ga|sess-1|1", (event) => events.push(event), (error) => errors.push(error));
    created[0].onmessage({
      data: JSON.stringify({
        seq: 2,
        type: "answer.delta",
        turn_id: "ga|sess-1|1",
        session_id: "sess-1",
        data: { delta: "hel" },
      }),
    });
    created[0].onerror(new Event("error"));

    assert.deepEqual(events.map((event) => event.type), ["answer.delta"]);
    assert.equal(errors.length, 0);
    assert.equal(created[0].closed, false);
    source.close();
    assert.equal(created[0].closed, true);
  } finally {
    globalThis.EventSource = originalEventSource;
    globalThis.fetch = originalFetch;
    globalThis.window = originalWindow;
  }
});

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

test("subscribeTurn polling does not duplicate backend turn.done events", async () => {
  const { subscribeTurn } = await import("./api.ts");
  const events = [];
  const originalEventSource = globalThis.EventSource;
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  globalThis.EventSource = undefined;
  globalThis.window = { setTimeout: () => 0 };
  globalThis.fetch = async () => ({
    ok: true,
    async json() {
      return {
        status: "idle",
        events: [
          {
            seq: 1,
            type: "answer.final",
            turn_id: "ga|sess-1|2",
            session_id: "sess-1",
            data: { text: "完成", response_id: "ga|sess-1|2:response:1" },
          },
          { seq: 2, type: "turn.done", turn_id: "ga|sess-1|2", session_id: "sess-1", data: { ok: true } },
        ],
        messages: [{ id: 3, role: "assistant", content: "完成", ts: 1 }],
      };
    },
  });

  try {
    subscribeTurn("ga|sess-1|2", (event) => events.push(event));
    await new Promise((resolve) => setImmediate(resolve));
  } finally {
    globalThis.EventSource = originalEventSource;
    globalThis.fetch = originalFetch;
    globalThis.window = originalWindow;
  }

  assert.deepEqual(events.map((event) => event.type), ["answer.final", "turn.done"]);
});

test("subscribeTurn polling does not duplicate backend turn.error events", async () => {
  const { subscribeTurn } = await import("./api.ts");
  const events = [];
  const originalEventSource = globalThis.EventSource;
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  globalThis.EventSource = undefined;
  globalThis.window = { setTimeout: () => 0 };
  globalThis.fetch = async () => ({
    ok: true,
    async json() {
      return {
        status: "error",
        lastError: "boom",
        events: [{ seq: 1, type: "turn.error", turn_id: "ga|sess-1|2", session_id: "sess-1", data: { message: "boom" } }],
        messages: [],
      };
    },
  });

  try {
    subscribeTurn("ga|sess-1|2", (event) => events.push(event));
    await new Promise((resolve) => setImmediate(resolve));
  } finally {
    globalThis.EventSource = originalEventSource;
    globalThis.fetch = originalFetch;
    globalThis.window = originalWindow;
  }

  assert.deepEqual(events.map((event) => event.type), ["turn.error"]);
});

test("subscribeTurn polling preserves legacy outputs after backend turn.done replay", async () => {
  const { subscribeTurn } = await import("./api.ts");
  const events = [];
  const originalEventSource = globalThis.EventSource;
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  globalThis.EventSource = undefined;
  globalThis.window = { setTimeout: () => 0 };
  globalThis.fetch = async () => ({
    ok: true,
    async json() {
      return {
        status: "idle",
        events: [
          {
            seq: 1,
            type: "answer.final",
            turn_id: "ga|sess-1|2",
            session_id: "sess-1",
            data: { text: "完成", response_id: "ga|sess-1|2:response:1" },
          },
          { seq: 2, type: "turn.done", turn_id: "ga|sess-1|2", session_id: "sess-1", data: { ok: true } },
        ],
        messages: [
          {
            id: 3,
            role: "assistant",
            content: "完成",
            responseId: "ga|sess-1|2:response:1",
            outputs: ["🔧 Tool: code_run\nargs:\n{\"cmd\":\"dir\"}\n[Status] ok\n[stdout]\nfile.txt\n"],
          },
        ],
      };
    },
  });

  try {
    subscribeTurn("ga|sess-1|2", (event) => events.push(event));
    await new Promise((resolve) => setImmediate(resolve));
  } finally {
    globalThis.EventSource = originalEventSource;
    globalThis.fetch = originalFetch;
    globalThis.window = originalWindow;
  }

  assert.deepEqual(events.map((event) => event.type), ["answer.final", "timeline.step", "turn.done"]);
});

test("subscribeTurn forwards elapsed_ms from backend turn.done events", async () => {
  const { subscribeTurn } = await import("./api.ts");
  const events = [];
  const originalEventSource = globalThis.EventSource;
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  globalThis.EventSource = undefined;
  globalThis.window = { setTimeout: () => 0 };
  globalThis.fetch = async () => ({
    ok: true,
    async json() {
      return {
        status: "idle",
        events: [
          {
            seq: 1,
            type: "answer.final",
            turn_id: "ga|sess-1|2",
            session_id: "sess-1",
            data: { text: "完成", response_id: "ga|sess-1|2:response:1" },
          },
          { seq: 2, type: "turn.done", turn_id: "ga|sess-1|2", session_id: "sess-1", data: { ok: true, elapsed_ms: 3210 } },
        ],
        messages: [{ id: 3, role: "assistant", content: "完成", ts: 1, elapsed_ms: 3210 }],
      };
    },
  });

  try {
    subscribeTurn("ga|sess-1|2", (event) => events.push(event));
    await new Promise((resolve) => setImmediate(resolve));
  } finally {
    globalThis.EventSource = originalEventSource;
    globalThis.fetch = originalFetch;
    globalThis.window = originalWindow;
  }

  assert.equal(events[1].type, "turn.done");
  assert.equal(events[1].data.elapsed_ms, 3210);
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
