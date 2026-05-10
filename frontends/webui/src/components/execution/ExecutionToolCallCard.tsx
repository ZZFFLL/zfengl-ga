import { useState } from "react";
import { ChevronDown, Wrench } from "lucide-react";

import type { ExecutionTurn } from "../../types";

export function ExecutionToolCallCard({
  toolCall,
  resultMode = "full",
}: {
  toolCall: ExecutionTurn["tool_calls"][number];
  resultMode?: "preview" | "full";
}) {
  const [open, setOpen] = useState(false);
  const showingPreview = resultMode === "preview" && Boolean(toolCall.result_preview);
  const resultText = showingPreview ? toolCall.result_preview : toolCall.result || toolCall.result_preview;
  const resultLabel = showingPreview
    ? toolCall.result_length
      ? `Result preview · 完整 ${toolCall.result_length} 字符`
      : "Result preview"
    : toolCall.result_length
      ? `Result · ${toolCall.result_length} 字符`
      : "Result";

  return (
    <section className="rounded-[10px] border border-app-line bg-app-surface">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 px-3.5 py-2.5 text-left"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2 text-sm font-medium text-app-text">
            <Wrench className="h-4 w-4 shrink-0 text-app-primary" aria-hidden="true" />
            <span className="truncate">{toolCall.tool}</span>
          </div>
          <div className="mt-1 truncate text-xs text-app-muted">
            {toolCall.status || toolCall.action || "查看工具调用详情"}
          </div>
        </div>
        <ChevronDown className={`h-4 w-4 shrink-0 text-app-muted transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open ? (
        <div className="space-y-3 border-t border-app-line/70 px-4 py-4">
          {toolCall.args ? (
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-app-muted">Args</div>
              <pre className="mt-2 overflow-x-auto rounded-lg bg-app-codeBg px-3.5 py-3 text-xs leading-6 text-app-codeText">
                <code>{toolCall.args}</code>
              </pre>
            </div>
          ) : null}
          {resultText ? (
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-app-muted">
                {resultLabel}
              </div>
              <pre className="mt-2 overflow-x-auto rounded-lg bg-app-codeBg px-3.5 py-3 text-xs leading-6 text-app-codeText">
                <code>{resultText}</code>
              </pre>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
