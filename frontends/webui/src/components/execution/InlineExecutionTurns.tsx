import { Tag } from "antd";

import type { ExecutionTurn } from "../../types";
import { buildExecutionChipLabel } from "../../state/execution-panel-state";
import { InlineExecutionTurn } from "./InlineExecutionTurn";

export function InlineExecutionTurns({
  turns,
  streaming,
}: {
  turns: ExecutionTurn[];
  streaming: boolean;
}) {
  const label = buildExecutionChipLabel(turns, streaming);
  if (!label) return null;

  return (
    <section className="mb-5 border-b border-app-line pb-4">
      <div className="flex min-w-0 items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2 text-sm font-semibold text-app-text">
          <Tag
            bordered={false}
            color={streaming ? "processing" : "success"}
            className="m-0 ga-execution-status-tag"
          >
            {streaming ? "执行中" : "已完成"}
          </Tag>
          <span className="truncate">{label}</span>
        </div>
        <span className="shrink-0 text-xs text-app-muted">{turns.length} 轮</span>
      </div>
      <div className="mt-3 space-y-2">
        {turns.map((turn, index) => {
          const defaultOpen = turn.state === "active";
          return (
            <InlineExecutionTurn
              key={`${turn.turn}-${index}`}
              turn={turn}
              defaultOpen={defaultOpen}
            />
          );
        })}
      </div>
    </section>
  );
}
