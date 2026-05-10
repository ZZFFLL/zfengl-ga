import type { ExecutionTurn, RuntimeState } from "../types";

type WorkbenchContextTab = "activity" | "status";

export function chooseWorkbenchContextTab(
  requestedTab: WorkbenchContextTab,
  turns: ExecutionTurn[],
  running: boolean,
): WorkbenchContextTab {
  if (running && turns.length > 0) return "activity";
  if (turns.length === 0) return "status";
  if (requestedTab === "activity" || requestedTab === "status") return requestedTab;
  return "status";
}

export function countToolCalls(turns: ExecutionTurn[]) {
  return turns.reduce((total, turn) => total + (turn.tool_calls?.length ?? 0), 0);
}

export function buildTurnMeta(turn: ExecutionTurn) {
  const toolCount = turn.tool_calls?.length ?? 0;

  return {
    title: turn.title || `Turn ${turn.turn}`,
    statusLabel: turn.state === "active" ? "执行中" : "已完成",
    toolCallLabel: `${toolCount} 个工具调用`,
  };
}

export function buildRuntimeSummary(state: RuntimeState | null) {
  return {
    configuredLabel: state?.configured ? "已配置" : "未配置",
    runningLabel: state?.running ? "任务执行中" : "空闲",
    modelLabel: state?.current_llm?.name ?? "未选择模型",
    autonomousLabel: state?.autonomous_enabled ? "自主行动开启" : "自主行动关闭",
  };
}
