import type { ExecutionStep } from "./types";

export type ToolDetailSection = {
  kind: "input" | "output" | "error" | "detail";
  label: string;
  content: string;
};

export function buildToolDetailSections(step: ExecutionStep): ToolDetailSection[] {
  const sections: ToolDetailSection[] = [];
  const input = readToolInputDisplay(step);
  const output = readNonEmptyText(step.output);
  const error = readNonEmptyText(step.error);
  const detail = readNonEmptyText(step.detail);

  if (input) {
    sections.push({ kind: "input", label: "入参", content: input });
  }
  if (output) {
    sections.push({ kind: "output", label: "结果", content: output });
  }
  if (error) {
    sections.push({ kind: "error", label: "错误", content: error });
  }
  if (sections.length === 0) {
    const parsedSections = splitToolDetail(step.detail);
    if (parsedSections.length > 0) {
      return parsedSections;
    }
  }

  if (detail && !sections.some((section) => section.content === detail)) {
    sections.push({ kind: "detail", label: sections.length > 0 ? "过程" : "详情", content: detail });
  }

  return sections;
}

function readToolInputDisplay(step: ExecutionStep) {
  const input = readNonEmptyText(step.input);
  if (!isEmptyJsonObject(input)) {
    return input;
  }
  const toolName = normalizeToolName(step.tool_name);
  if (toolName.includes("web_scan")) {
    return "默认：扫描当前浏览器标签页";
  }
  if (toolName.includes("code_run")) {
    return "默认：执行本轮回复中的代码块";
  }
  if (toolName.includes("web_execute_js")) {
    return "默认：执行本轮回复中的 JavaScript 代码块";
  }
  return "";
}

function splitToolDetail(detail: string): ToolDetailSection[] {
  return detail
    .split("\n")
    .map((line) => {
      const match = line.match(/^(参数|结果|输出|错误)：([\s\S]*)$/);
      return match ? { kind: readDetailSectionKind(match[1]), label: match[1], content: match[2] } : null;
    })
    .filter((section): section is ToolDetailSection => Boolean(section));
}

function readDetailSectionKind(label: string): ToolDetailSection["kind"] {
  if (label === "参数") {
    return "input";
  }
  if (label === "结果" || label === "输出") {
    return "output";
  }
  if (label === "错误") {
    return "error";
  }
  return "detail";
}

function isEmptyJsonObject(value: string) {
  if (!value) {
    return false;
  }
  try {
    const parsed = JSON.parse(value);
    return Boolean(parsed) && typeof parsed === "object" && !Array.isArray(parsed) && Object.keys(parsed).length === 0;
  } catch {
    return false;
  }
}

function normalizeToolName(toolName?: string) {
  return toolName?.trim().toLowerCase().replace(/[\s-]+/g, "_") ?? "";
}

function readNonEmptyText(value?: string) {
  const text = value?.trim();
  return text ? text : "";
}
