import type { ExecutionTurn, UiMessage } from "../types";

export type InspectorTarget = {
  turnIndex: number;
  toolIndex: number | null;
};

export type TaskStreamItem = {
  id: string;
  command: UiMessage | null;
  response: UiMessage | null;
  executionLog: ExecutionTurn[];
  pending: boolean;
};

function executionForResponse(
  response: UiMessage | null,
  liveExecutionLog: ExecutionTurn[],
  streaming: boolean,
) {
  if (!response) return [];
  if (streaming && response.pending && liveExecutionLog.length > 0) {
    return liveExecutionLog;
  }
  return response.executionLog ?? [];
}

export function buildTaskStreamItems(
  messages: UiMessage[],
  liveExecutionLog: ExecutionTurn[],
  streaming: boolean,
): TaskStreamItem[] {
  const items: TaskStreamItem[] = [];

  for (const message of messages) {
    if (message.role === "user") {
      items.push({
        id: `task-${message.id}`,
        command: message,
        response: null,
        executionLog: [],
        pending: Boolean(message.pending),
      });
      continue;
    }

    if (message.role === "system") {
      items.push({
        id: `task-${message.id}`,
        command: null,
        response: message,
        executionLog: executionForResponse(message, liveExecutionLog, streaming),
        pending: Boolean(message.pending),
      });
      continue;
    }

    const pendingCommand = [...items].reverse().find((item) => item.command && !item.response);
    if (pendingCommand) {
      pendingCommand.response = message;
      pendingCommand.executionLog = executionForResponse(message, liveExecutionLog, streaming);
      pendingCommand.pending = Boolean(message.pending);
      continue;
    }

    items.push({
      id: `task-${message.id}`,
      command: null,
      response: message,
      executionLog: executionForResponse(message, liveExecutionLog, streaming),
      pending: Boolean(message.pending),
    });
  }

  return items.map((item) => ({
    ...item,
    executionLog: item.response
      ? executionForResponse(item.response, liveExecutionLog, streaming)
      : item.executionLog,
    pending: Boolean(item.response?.pending ?? item.pending),
  }));
}

export function chooseActiveInspectorTarget(
  executionLog: ExecutionTurn[],
  running: boolean,
  selectedTarget: InspectorTarget | null,
) {
  if (selectedTarget) {
    const selectedTurn = executionLog[selectedTarget.turnIndex];
    if (selectedTurn) {
      const selectedToolIndex =
        selectedTarget.toolIndex !== null && selectedTurn.tool_calls?.[selectedTarget.toolIndex]
          ? selectedTarget.toolIndex
          : null;
      return {
        turnIndex: selectedTarget.turnIndex,
        toolIndex: selectedToolIndex,
      };
    }
  }
  if (!running || executionLog.length === 0) {
    return null;
  }
  return {
    turnIndex: executionLog.length - 1,
    toolIndex: null,
  };
}
