import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";

import { MarkdownContent } from "../chat/MarkdownContent";
import type { ExecutionTurn } from "../../types";
import { ExecutionToolCallCard } from "./ExecutionToolCallCard";

export function InlineExecutionTurn({
  turn,
  defaultOpen,
}: {
  turn: ExecutionTurn;
  defaultOpen: boolean;
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
      <button
        type="button"
        className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left"
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
        <ChevronDown className={`mt-0.5 h-4 w-4 shrink-0 text-app-muted transition ${open ? "rotate-180" : ""}`} />
      </button>
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
                />
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
