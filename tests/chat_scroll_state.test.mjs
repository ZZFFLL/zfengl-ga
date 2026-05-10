import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL } from "node:url";

const moduleUrl = pathToFileURL(
  path.resolve("frontends/webui/src/chat-scroll-state.ts"),
).href;
const {
  isNearScrollBottom,
} = await import(moduleUrl);

test("isNearScrollBottom stays sticky when the viewport is already near the end", () => {
  assert.equal(isNearScrollBottom(676, 300, 1000), true);
  assert.equal(isNearScrollBottom(700, 300, 1000), true);
});

test("isNearScrollBottom releases sticky mode once the user scrolls meaningfully upward", () => {
  assert.equal(isNearScrollBottom(620, 300, 1000), false);
  assert.equal(isNearScrollBottom(0, 300, 1000), false);
});
