import assert from "node:assert/strict";
import test from "node:test";
import { parseGenericAgentOutputSteps } from "./ga_output_parser.ts";

test("parses GenericAgent mixed logs into tool cards without final answers", () => {
  const output = `
LLM Running (Turn 1) ...
<summary>Need to inspect files.</summary>
🔧 Tool: code_run
args:
{
  "cmd": "python - <<'PY'\\nprint('hello')\\nPY"
}
[Action] Running python...
[Status] ✅ Exit Code: 0
[stdout]
hello

LLM Running (Turn 2) ...
最终结论：这里应该只显示为正常助手回复，不应该进入执行卡片。
`;

  const steps = parseGenericAgentOutputSteps(output, {
    idPrefix: "resp-1:output:1",
    turnId: "turn-1",
    responseId: "resp-1",
    createdAt: "2026-05-24T00:00:00.000Z",
    gaTurn: 2,
  });

  assert.equal(steps.length, 1);
  assert.equal(steps[0].tool_name, "code_run");
  assert.equal(steps[0].kind, "command");
  assert.equal(steps[0].tool_label, "GA Turn 2");
  assert.match(steps[0].input ?? "", /"cmd"/);
  assert.match(steps[0].output ?? "", /hello/);
  assert.doesNotMatch(steps[0].detail, /最终结论/);
  assert.doesNotMatch(steps[0].output ?? "", /最终结论/);
});

test("parses multiple tool calls from one GenericAgent output", () => {
  const output = `
🔧 Tool: web_scan
args:
{"url":"https://example.test"}
[Status] ✅ ok
[stdout]
page text
🔧 Tool: code_run
args:
{"cmd":"dir"}
[Status] ✅ Exit Code: 0
[stdout]
file.txt
`;

  const steps = parseGenericAgentOutputSteps(output, {
    idPrefix: "resp-2:output:1",
    turnId: "turn-2",
    responseId: "resp-2",
    createdAt: "2026-05-24T00:00:00.000Z",
  });

  assert.deepEqual(
    steps.map((step) => step.tool_name),
    ["web_scan", "code_run"],
  );
  assert.deepEqual(
    steps.map((step) => step.kind),
    ["search", "command"],
  );
});
