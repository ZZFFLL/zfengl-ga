import type { ExecutionStep } from "./types";

type ParseGenericAgentOutputOptions = {
  idPrefix: string;
  turnId?: string;
  responseId?: string;
  createdAt?: string;
  gaTurn?: number;
};

type ParsedToolBlock = {
  name: string;
  body: string;
};

const TOOL_HEADER_PATTERN = /(?:^|\n)\s*(?:🔧\s*)?Tool:\s*([A-Za-z0-9_.-]+)/g;
const TOOL_BOUNDARY_PATTERN = /^\s*(?:\[Action\]|\[Status\]|\[stdout\]|\[stderr\]|\[Error\]|LLM Running\b|(?:🔧\s*)?Tool:)/;

export function parseGenericAgentOutputSteps(output: string, options: ParseGenericAgentOutputOptions): ExecutionStep[] {
  const blocks = splitToolBlocks(output);
  return blocks.map((block, index) => {
    const input = readArgs(block.body);
    const stdout = readTaggedSection(block.body, "stdout");
    const stderr = readTaggedSection(block.body, "stderr");
    const statusLines = readPrefixedLines(block.body, "[Status]");
    const actionLines = readPrefixedLines(block.body, "[Action]");
    const errorLines = [...readPrefixedLines(block.body, "[Error]"), stderr].filter(Boolean);
    const failed = errorLines.length > 0 || statusLines.some((line) => /(?:failed|error|exit code:\s*[1-9])/i.test(line));
    const outputText = [statusLines.join("\n"), stdout].filter(Boolean).join("\n\n");
    const detail = [actionLines.join("\n"), outputText, errorLines.join("\n")].filter(Boolean).join("\n\n");

    return {
      id: `${options.idPrefix}:tool:${index + 1}`,
      turn_id: options.turnId,
      response_id: options.responseId,
      kind: readToolKind(block.name),
      title: `调用 ${block.name}`,
      status: failed ? "failed" : "done",
      summary: summarizeToolBlock(block.name, statusLines, actionLines, stdout, errorLines),
      detail,
      input,
      output: outputText,
      error: errorLines.join("\n") || undefined,
      tool_name: block.name,
      tool_label: typeof options.gaTurn === "number" ? `GA Turn ${options.gaTurn}` : "GA 工具调用",
      created_at: options.createdAt,
    };
  });
}

function splitToolBlocks(output: string): ParsedToolBlock[] {
  const matches = Array.from(output.matchAll(TOOL_HEADER_PATTERN));
  return matches.map((match, index) => {
    const next = matches[index + 1];
    const headerEnd = (match.index ?? 0) + match[0].length;
    return {
      name: match[1],
      body: output.slice(headerEnd, next?.index ?? output.length),
    };
  });
}

function readArgs(body: string): string | undefined {
  const match = body.match(/^\s*args:\s*$/im);
  if (!match || match.index === undefined) {
    return undefined;
  }
  const start = match.index + match[0].length;
  const lines = body.slice(start).split(/\r?\n/);
  const argsLines: string[] = [];
  for (const line of lines) {
    if (TOOL_BOUNDARY_PATTERN.test(line)) {
      break;
    }
    argsLines.push(line);
  }
  const text = argsLines.join("\n").trim();
  return text || undefined;
}

function readTaggedSection(body: string, tag: "stdout" | "stderr"): string {
  const pattern = new RegExp(`^\\s*\\[${tag}\\]\\s*$`, "im");
  const match = body.match(pattern);
  if (!match || match.index === undefined) {
    return "";
  }
  const start = match.index + match[0].length;
  const lines = body.slice(start).split(/\r?\n/);
  const sectionLines: string[] = [];
  for (const line of lines) {
    if (TOOL_BOUNDARY_PATTERN.test(line)) {
      break;
    }
    sectionLines.push(line);
  }
  return sectionLines.join("\n").trim();
}

function readPrefixedLines(body: string, prefix: string): string[] {
  return body
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.startsWith(prefix))
    .map((line) => line.slice(prefix.length).trim())
    .filter(Boolean);
}

function readToolKind(toolName: string): ExecutionStep["kind"] {
  const lower = toolName.toLowerCase();
  if (lower.includes("code") || lower.includes("shell") || lower.includes("command")) {
    return "command";
  }
  if (lower.includes("scan") || lower.includes("search") || lower.includes("browse") || lower.includes("web")) {
    return "search";
  }
  if (lower.includes("read")) {
    return "read";
  }
  if (lower.includes("file") || lower.includes("write")) {
    return "file";
  }
  return "tool";
}

function summarizeToolBlock(
  toolName: string,
  statusLines: string[],
  actionLines: string[],
  stdout: string,
  errorLines: string[],
): string {
  const firstError = errorLines.find(Boolean);
  if (firstError) {
    return firstError.length > 80 ? `${firstError.slice(0, 77)}...` : firstError;
  }
  const firstStatus = statusLines.find(Boolean);
  if (firstStatus) {
    return firstStatus.length > 80 ? `${firstStatus.slice(0, 77)}...` : firstStatus;
  }
  const firstAction = actionLines.find(Boolean);
  if (firstAction) {
    return firstAction.length > 80 ? `${firstAction.slice(0, 77)}...` : firstAction;
  }
  const firstOutput = stdout.split(/\r?\n/).find((line) => line.trim());
  if (firstOutput) {
    return firstOutput.length > 80 ? `${firstOutput.slice(0, 77)}...` : firstOutput;
  }
  return `${toolName} 已执行`;
}
