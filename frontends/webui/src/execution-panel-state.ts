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

// 中文注释：内联执行折叠区顶部用一句话概括当前执行状态。
export function buildExecutionChipLabel(turns: ExecutionTurn[], streaming: boolean) {
  if (turns.length === 0) return null;
  const latest = turns[turns.length - 1];
  const title = latest?.title || `Turn ${latest?.turn ?? turns.length}`;
  return streaming ? `正在执行 · ${title}` : `执行过程 · ${turns.length} 轮`;
}

// 中文注释：工具执行阶段可能没有正文流动画，胶囊运行态需要同时参考消息 pending。
export function resolveExecutionChipRunning(pending: boolean, streaming: boolean) {
  return pending || streaming;
}

// 中文注释：assistant 正在执行但正文尚未到达时，也要稳定显示占位提示。
export function shouldShowPendingAssistant(
  pending: boolean,
  content: string,
  _executionLog: ExecutionTurn[],
) {
  return pending && !content.trim();
}
