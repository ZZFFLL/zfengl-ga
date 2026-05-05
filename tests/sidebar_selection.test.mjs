import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL } from "node:url";

const moduleUrl = pathToFileURL(
  path.resolve("frontends/webui/src/sidebar-selection.ts"),
).href;
const {
  buildBulkDeleteLabel,
  pruneSelectedConversations,
  toggleSelectedConversation,
} = await import(moduleUrl);

test("toggleSelectedConversation adds and removes ids", () => {
  assert.deepEqual(toggleSelectedConversation([], "a"), ["a"]);
  assert.deepEqual(toggleSelectedConversation(["a", "b"], "a"), ["b"]);
});

test("pruneSelectedConversations keeps only visible recent conversations", () => {
  assert.deepEqual(pruneSelectedConversations(["a", "b", "c"], ["b", "c", "d"]), ["b", "c"]);
});

test("buildBulkDeleteLabel includes selected count", () => {
  assert.equal(buildBulkDeleteLabel(0), "删除");
  assert.equal(buildBulkDeleteLabel(3), "删除 3");
});
