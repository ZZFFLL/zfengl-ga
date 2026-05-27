import type { SopEntry } from "./api";

export type SopReference = Pick<SopEntry, "id" | "name" | "path" | "title">;

export function buildPromptWithSopReferences(content: string, references: SopReference[]): string {
  if (references.length === 0) {
    return content;
  }
  const body = content.trim();
  const lines = references.map((sop) => `- ${sop.path}${sop.title ? `（${sop.title}）` : ""}`);
  return [
    "用户引用了以下 SOP：",
    ...lines,
    "",
    "请先读取这些 SOP，再按用户正文意图处理：",
    "- 如果正文是在询问、比较、解释 SOP，只做说明，不执行任务。",
    "- 如果正文包含明确任务，就遵循 SOP 执行任务。",
    "- 如果正文为空，只概括该 SOP 的适用场景、关键步骤和注意事项。",
    "",
    "用户正文：",
    body || "(空)",
  ].join("\n");
}

export function buildDisplayPromptWithSopReferences(content: string, references: SopReference[]): string {
  if (references.length === 0) {
    return content;
  }
  const sopNames = references.map((sop) => `@${sop.id}`).join(" ");
  const body = content.trim();
  return body ? `${sopNames}\n\n${body}` : sopNames;
}

export function removeTrailingSopTrigger(content: string): string {
  return content.replace(/\s?@$/, "").trimEnd();
}
