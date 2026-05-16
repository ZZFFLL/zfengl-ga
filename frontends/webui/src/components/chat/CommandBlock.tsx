import { TerminalSquare } from "lucide-react";
import type { UiMessage } from "../../types";

export function CommandBlock({ message }: { message: UiMessage }) {
  return (
    <section className="ga-command-block">
      <div className="ga-command-meta">
        <span className="ga-command-icon">
          <TerminalSquare className="h-4 w-4" aria-hidden="true" />
        </span>
        <span>Command</span>
        <span aria-hidden="true">/</span>
        <span>{message.time}</span>
      </div>
      <div className="ga-command-content">{message.content}</div>
    </section>
  );
}
