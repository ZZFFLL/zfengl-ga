import { useEffect, useState } from "react";
import { ChevronDown, Search } from "lucide-react";

import { MarkdownContent } from "../chat/MarkdownContent";
import type { ExecutionTurn } from "../../types";
import { ExecutionToolCallCard } from "./ExecutionToolCallCard";

export function InlineExecutionTurn({
  turn,
  defaultOpen,
  onSelectInspectorTarget,
}: {
  turn: ExecutionTurn;
  defaultOpen: boolean;
  onSelectInspectorTarget?: (toolIndex: number | null) => void;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [manualOpen, setManualOpen] = useState(false);
  const toolCalls = turn.tool_calls ?? [];
  const summary = turn.summary || turn.content;
  const active = turn.state === "active";

  useEffect(() => {
    if (!manualOpen) {
      setOpen(defaultOpen);
    }
  }, [defaultOpen, manualOpen]);

  return (
    <section
      className={`ga-run-rail rounded-[10px] border bg-white ${
        active ? "border-app-primary/45 shadow-soft" : "border-app-line"
      }`}
    >
      <div className="flex w-full items-start justify-between gap-3 px-4 py-3">
        <button
          type="button"
          className="min-w-0 flex-1 text-left"
          onClick={() => {
            setManualOpen(true);
            setOpen((value) => !value);
          }}
          aria-expanded={open}
        >
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-2 text-sm font-semibold text-app-text">
              <span
                className={`relative z-[1] inline-flex h-3 w-3 shrink-0 rounded-full ring-4 ${
                  active
                    ? "animate-pulse bg-app-primary ring-app-primarySoft"
                    : "bg-app-success ring-[#e9f6ef]"
                }`}
                aria-hidden="true"
              />
              <span className="shrink-0">Turn {turn.turn}</span>
              <span className="truncate text-app-muted">{turn.title || "执行步骤"}</span>
            </div>
            <div className="mt-1 text-xs text-app-muted">
              {active ? "执行中" : "已完成"} · {toolCalls.length} 个工具调用
            </div>
          </div>
        </button>
        <div className="mt-0.5 flex shrink-0 items-center gap-2">
          {onSelectInspectorTarget ? (
            <button
              type="button"
              className="inline-flex h-7 w-7 items-center justify-center rounded-md text-app-primary transition hover:bg-app-primarySubtle"
              aria-label={`检查 Turn ${turn.turn} 执行步骤`}
              onClick={() => onSelectInspectorTarget(null)}
            >
              <Search className="h-4 w-4" aria-hidden="true" />
            </button>
          ) : null}
          <ChevronDown className={`h-4 w-4 text-app-muted transition ${open ? "rotate-180" : ""}`} />
        </div>
      </div>
      {open ? (
        <div className="border-t border-app-line/70 px-4 py-4">
          <div className="text-sm leading-7 text-app-muted">
            {summary ? <MarkdownContent content={summary} /> : "此轮没有 summary。"}
          </div>
          {toolCalls.length > 0 ? (
            <div className="mt-4 space-y-3 border-t border-app-line/70 pt-4">
              {toolCalls.map((toolCall, toolIndex) => (
                <ExecutionToolCallCard
                  key={`${turn.turn}-${toolCall.tool}-${toolIndex}`}
                  toolCall={toolCall}
                  resultMode="preview"
                  onInspect={() => onSelectInspectorTarget?.(toolIndex)}
                />
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
