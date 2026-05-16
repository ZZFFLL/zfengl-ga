import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";

import type { ExecutionTurn } from "../../types";
import { buildExecutionChipLabel } from "../../state/execution-panel-state";
import type { InspectorTarget } from "../../state/task-stream-state";
import { InlineExecutionTurn } from "./InlineExecutionTurn";

export function InlineExecutionTurns({
  turns,
  streaming,
  onSelectInspectorTarget,
}: {
  turns: ExecutionTurn[];
  streaming: boolean;
  onSelectInspectorTarget?: (target: InspectorTarget) => void;
}) {
  const label = buildExecutionChipLabel(turns, streaming);
  const [open, setOpen] = useState(streaming);

  useEffect(() => {
    if (streaming) {
      setOpen(true);
    }
  }, [streaming]);

  if (!label) return null;

  return (
    <section className="ga-inline-execution">
      <button
        type="button"
        className={`ga-inline-execution-summary ${streaming ? "is-running" : "is-complete"}`}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span
          className={`ga-execution-dot ${streaming ? "is-running" : "is-complete"}`}
          aria-hidden="true"
        />
        <span className="ga-execution-state">{streaming ? "执行中" : "已完成"}</span>
        <span className="ga-execution-separator" aria-hidden="true" />
        <span className="ga-execution-title">{label}</span>
        <span className="ga-execution-count">{turns.length} 轮</span>
        <ChevronDown
          className={`ga-execution-chevron ${open ? "is-open" : ""}`}
          aria-hidden="true"
        />
      </button>
      {open ? (
        <div className="ga-inline-execution-list">
          {turns.map((turn, index) => {
            const defaultOpen = turn.state === "active";
            return (
              <InlineExecutionTurn
                key={`${turn.turn}-${index}`}
                turn={turn}
                defaultOpen={defaultOpen}
                onSelectInspectorTarget={(toolIndex) =>
                  onSelectInspectorTarget?.({ turnIndex: index, toolIndex })
                }
              />
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
