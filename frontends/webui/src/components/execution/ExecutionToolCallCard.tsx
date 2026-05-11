import { Wrench } from "lucide-react";

import type { ExecutionTurn } from "../../types";

export function ExecutionToolCallCard({
  toolCall,
  onInspect,
}: {
  toolCall: ExecutionTurn["tool_calls"][number];
  onInspect?: () => void;
}) {
  return (
    <section className="rounded-[0.625rem] border border-app-line bg-app-surface">
      <div className="flex w-full items-center justify-between gap-3 px-3.5 py-2.5">
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2 text-sm font-medium text-app-text">
            <Wrench className="h-4 w-4 shrink-0 text-app-primary" aria-hidden="true" />
            <span className="truncate">{toolCall.tool}</span>
          </div>
          <div className="mt-1 truncate text-xs text-app-muted">
            {toolCall.status || toolCall.action || "查看工具调用详情"}
          </div>
        </div>
        {onInspect ? (
          <button
            type="button"
            className="shrink-0 text-xs font-medium text-app-primary transition hover:text-app-primaryHover"
            aria-label={`查看 ${toolCall.tool} 工具调用详情`}
            onClick={onInspect}
          >
            详情
          </button>
        ) : null}
      </div>
    </section>
  );
}
