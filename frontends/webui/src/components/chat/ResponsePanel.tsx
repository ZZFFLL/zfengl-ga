import { Loader2 } from "lucide-react";
import type { UiMessage } from "../../types";
import { MarkdownContent } from "./MarkdownContent";

export function ResponsePanel({
  message,
  streaming,
  pending,
}: {
  message: UiMessage | null;
  streaming: boolean;
  pending: boolean;
}) {
  if (!message || (pending && !message.content.trim())) {
    return (
      <section className="ga-response-panel is-pending">
        <div className="ga-response-meta">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          <span>GenericAgent is working</span>
        </div>
        <div className="text-sm text-app-muted">正在执行任务，结果会在这里生成。</div>
      </section>
    );
  }

  const roleLabel = message.role === "system" ? "System" : "GenericAgent";

  return (
    <section className="ga-response-panel">
      <div className="ga-response-meta">
        <span>{roleLabel}</span>
        <span aria-hidden="true">/</span>
        <span>{message.time}</span>
      </div>
      <MarkdownContent content={message.content} streaming={streaming} />
    </section>
  );
}
