import type { ExecutionTurn } from "./types";

export type ExecutionMessageLike = {
  id: string;
  role: "user" | "assistant" | "system";
  executionLog: ExecutionTurn[];
};

// 中文注释：流式回复期间优先展示实时摘要，否则回退到消息持久化的 execution_log。
export function resolveExecutionTurns(
  message: ExecutionMessageLike,
  liveTurns: ExecutionTurn[],
  streaming: boolean,
) {
  if (message.role !== "assistant") return [];
  if (streaming && liveTurns.length > 0) {
    return liveTurns;
  }
  return message.executionLog ?? [];
}

// 中文注释：思考胶囊只表达“正在思考/已完成思考”两种消息级状态。
export function buildExecutionChipLabel(turns: ExecutionTurn[], streaming: boolean) {
  if (turns.length === 0) return null;
  return streaming ? "正在思考" : "已完成思考";
}

// 中文注释：assistant 正在执行但正文尚未到达时，也要稳定显示占位提示。
export function shouldShowPendingAssistant(
  pending: boolean,
  content: string,
  _executionLog: ExecutionTurn[],
) {
  return pending && !content.trim();
}

// 中文注释：打开执行过程面板时，默认定位到最后一条带执行摘要的 assistant 回复。
export function findLatestExecutionMessageId(messages: ExecutionMessageLike[]) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role === "assistant" && message.executionLog.length > 0) {
      return message.id;
    }
  }
  return null;
}
