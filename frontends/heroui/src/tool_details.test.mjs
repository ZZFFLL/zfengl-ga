import assert from "node:assert/strict";
import test from "node:test";
import { buildToolDetailSections } from "./tool_details.ts";

test("renders web_scan empty args as current-tab default behavior", () => {
  const sections = buildToolDetailSections({
    id: "step-1",
    kind: "search",
    title: "第5轮 调用了 web_scan",
    status: "done",
    summary: "第5轮 调用了 web_scan",
    detail: "",
    input: "{}",
    output: '{"status":"success"}',
    tool_name: "web_scan",
  });

  assert.equal(sections[0].label, "入参");
  assert.equal(sections[0].content, "默认：扫描当前浏览器标签页");
  assert.equal(sections[1].label, "结果");
});

test("keeps normal tool args instead of replacing them", () => {
  const sections = buildToolDetailSections({
    id: "step-2",
    kind: "read",
    title: "调用 file_read",
    status: "done",
    summary: "调用 file_read",
    detail: "",
    input: '{"path":"frontends/heroui/src/App.tsx","start":10}',
    output: "10| export function App() {}",
    tool_name: "file_read",
  });

  assert.match(sections[0].content, /"path"/);
  assert.doesNotMatch(sections[0].content, /默认/);
});

test("distinguishes code and browser tools that use reply code blocks", () => {
  const codeRunSections = buildToolDetailSections({
    id: "step-3",
    kind: "command",
    title: "调用 code_run",
    status: "done",
    summary: "调用 code_run",
    detail: "",
    input: "{}",
    output: "ok",
    tool_name: "code_run",
  });
  const jsSections = buildToolDetailSections({
    id: "step-4",
    kind: "command",
    title: "调用 web_execute_js",
    status: "done",
    summary: "调用 web_execute_js",
    detail: "",
    input: "{}",
    output: "ok",
    tool_name: "web_execute_js",
  });

  assert.equal(codeRunSections[0].content, "默认：执行本轮回复中的代码块");
  assert.equal(jsSections[0].content, "默认：执行本轮回复中的 JavaScript 代码块");
});

test("hides empty args for truly no-argument tools", () => {
  const sections = buildToolDetailSections({
    id: "step-5",
    kind: "tool",
    title: "调用 start_long_term_update",
    status: "done",
    summary: "调用 start_long_term_update",
    detail: "",
    input: "{}",
    output: '{"ok":true}',
    tool_name: "start_long_term_update",
  });

  assert.equal(sections[0].label, "结果");
  assert.doesNotMatch(sections.map((section) => section.content).join("\n"), /\{\}/);
});

test("keeps legacy detail parsing when no structured fields exist", () => {
  const sections = buildToolDetailSections({
    id: "step-6",
    kind: "tool",
    title: "调用 legacy_tool",
    status: "done",
    summary: "调用 legacy_tool",
    detail: "参数：旧参数\n结果：旧结果",
    tool_name: "legacy_tool",
  });

  assert.deepEqual(
    sections.map((section) => [section.kind, section.label, section.content]),
    [
      ["input", "参数", "旧参数"],
      ["output", "结果", "旧结果"],
    ],
  );
});
