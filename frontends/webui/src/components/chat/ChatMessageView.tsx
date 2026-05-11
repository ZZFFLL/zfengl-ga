import type { ExecutionTurn, UiMessage } from "../../types";
import { ResponsePanel } from "./ResponsePanel";

export function ChatMessageView({
  message,
  streaming = false,
}: {
  message: UiMessage;
  streaming?: boolean;
  liveExecutionLog?: ExecutionTurn[];
}) {
  return (
    <ResponsePanel
      message={message}
      streaming={streaming}
      pending={Boolean(message.pending)}
    />
  );
}
