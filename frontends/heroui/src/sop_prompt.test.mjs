import assert from "node:assert/strict";
import test from "node:test";

import { buildDisplayPromptWithSopReferences, buildPromptWithSopReferences, removeTrailingSopTrigger } from "./sop_prompt.ts";

test("SOP references expand into an instruction that lets GA decide consult versus execute", () => {
  const prompt = buildPromptWithSopReferences("这个适合什么时候用？", [
    { id: "plan_sop", name: "plan_sop.md", path: "memory/plan_sop.md", title: "Plan Mode SOP" },
  ]);

  assert.match(prompt, /用户引用了以下 SOP/);
  assert.match(prompt, /memory\/plan_sop\.md/);
  assert.match(prompt, /请先读取这些 SOP/);
  assert.match(prompt, /如果正文是在询问、比较、解释 SOP/);
  assert.match(prompt, /如果正文包含明确任务/);
  assert.match(prompt, /如果正文为空/);
  assert.match(prompt, /用户正文：\n这个适合什么时候用？/);
});

test("empty content asks GA to summarize the referenced SOP instead of executing work", () => {
  const prompt = buildPromptWithSopReferences("   ", [
    { id: "web_setup_sop", name: "web_setup_sop.md", path: "memory/web_setup_sop.md", title: "Web 工具链初始化执行 SOP" },
  ]);

  assert.match(prompt, /用户正文：\n\(空\)/);
  assert.match(prompt, /只概括该 SOP 的适用场景、关键步骤和注意事项/);
});

test("prompt without SOP references stays as the user's original message", () => {
  assert.equal(buildPromptWithSopReferences("直接聊天", []), "直接聊天");
});

test("display prompt keeps only visible SOP names and the user text", () => {
  const prompt = buildDisplayPromptWithSopReferences("这个适合什么时候用？", [
    { id: "plan_sop", name: "plan_sop.md", path: "memory/plan_sop.md", title: "Plan Mode SOP" },
    { id: "verify_sop", name: "verify_sop.md", path: "memory/verify_sop.md", title: "你的两个失败模式" },
  ]);

  assert.equal(prompt, "@plan_sop @verify_sop\n\n这个适合什么时候用？");
  assert.doesNotMatch(prompt, /请先读取这些 SOP/);
  assert.doesNotMatch(prompt, /如果正文包含明确任务/);
});

test("display prompt can show only SOP chips when the user body is empty", () => {
  const prompt = buildDisplayPromptWithSopReferences(" ", [
    { id: "scheduled_task_sop", name: "scheduled_task_sop.md", path: "memory/scheduled_task_sop.md", title: "定时任务 SOP" },
  ]);

  assert.equal(prompt, "@scheduled_task_sop");
});

test("typing at-sign trigger can be removed after picking a SOP", () => {
  assert.equal(removeTrailingSopTrigger("帮我查一下 @"), "帮我查一下");
  assert.equal(removeTrailingSopTrigger("@"), "");
  assert.equal(removeTrailingSopTrigger("正常任务"), "正常任务");
});
