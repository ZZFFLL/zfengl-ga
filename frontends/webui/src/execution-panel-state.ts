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

// 中文注释：工具执行阶段可能没有正文流动画，胶囊运行态需要同时参考消息 pending。
export function resolveExecutionChipRunning(pending: boolean, streaming: boolean) {
  return pending || streaming;
}

// 中文注释：右侧执行过程面板始终保留在布局里，通过 class 切换来做展开/收起动画。
export function buildExecutionPanelStateClassName(open: boolean) {
  return [
    "hidden",
    "relative",
    "h-full",
    "min-h-0",
    "min-w-0",
    "overflow-hidden",
    "border-l",
    "border-app-line",
    "bg-white",
    "xl:flex",
    "xl:flex-col",
    "xl:transition-[width,opacity,transform]",
    "xl:duration-300",
    "xl:ease-out",
    "xl:will-change-[width,opacity,transform]",
    open
      ? "xl:w-[380px] xl:opacity-100 xl:translate-x-0"
      : "xl:w-0 xl:opacity-0 xl:translate-x-4 xl:pointer-events-none",
  ].join(" ");
}

export function resolveExecutionPanelToggle(
  currentMessageId: string | null,
  open: boolean,
  clickedMessageId: string,
) {
  // 中文注释：再次点击同一条思考胶囊时关闭面板；点击另一条时切换到新消息并打开。
  if (open && currentMessageId === clickedMessageId) {
    return { open: false, messageId: currentMessageId };
  }
  return { open: true, messageId: clickedMessageId };
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
