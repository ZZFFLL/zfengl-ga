import type { ExecutionTurn, UiMessage } from "../../types";
import {
  resolveExecutionChipRunning,
  resolveExecutionTurns,
  shouldShowPendingAssistant,
} from "../../state/execution-panel-state";
import { InlineExecutionTurns } from "../execution/InlineExecutionTurns";
import { MarkdownContent } from "./MarkdownContent";

export function ChatMessageView({
  message,
  streaming = false,
  liveExecutionLog = [],
}: {
  message: UiMessage;
  streaming?: boolean;
  liveExecutionLog?: ExecutionTurn[];
}) {
  const isUser = message.role === "user";
  const roleLabel = isUser ? "You" : message.role === "system" ? "System" : "GenericAgent";
  const effectiveExecutionLog = resolveExecutionTurns(message, liveExecutionLog, streaming);
  const executionChipRunning = resolveExecutionChipRunning(Boolean(message.pending), streaming);
  const isPendingAssistant =
    message.role === "assistant" &&
    shouldShowPendingAssistant(Boolean(message.pending), message.content, effectiveExecutionLog);

  return (
    <article className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={isUser ? "max-w-[78%]" : "w-full max-w-[94%]"}>
        <div
          className={`ga-message-card px-4 py-3.5 ${
            isUser
              ? "ga-message-user text-white"
              : "ga-message-assistant text-app-text"
          }`}
        >
          <div className={`mb-2 flex items-center justify-between gap-3 text-[11px] font-medium ${isUser ? "text-white/62" : "text-app-muted"}`}>
            <span>{roleLabel}</span>
            <span className="shrink-0">{message.time}</span>
          </div>
          {!isUser ? (
            <InlineExecutionTurns
              turns={effectiveExecutionLog}
              streaming={executionChipRunning}
            />
          ) : null}
          {isPendingAssistant ? (
            <div className="flex items-center gap-3 text-sm text-app-muted">
              <span className="inline-flex h-2.5 w-2.5 rounded-full bg-app-primary animate-pulse" />
              <span>任务执行中...</span>
            </div>
          ) : isUser ? (
            <div className="message-content text-sm leading-7">{message.content}</div>
          ) : (
            <MarkdownContent content={message.content} streaming={streaming} />
          )}
        </div>
      </div>
    </article>
  );
}
