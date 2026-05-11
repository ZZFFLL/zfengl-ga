import type { InspectorTarget, TaskStreamItem } from "../../state/task-stream-state";
import { InlineExecutionTurns } from "../execution/InlineExecutionTurns";
import { CommandBlock } from "./CommandBlock";
import { ResponsePanel } from "./ResponsePanel";

export function TaskStream({
  items,
  streaming,
  onSelectInspectorTarget,
}: {
  items: TaskStreamItem[];
  streaming: boolean;
  onSelectInspectorTarget?: (taskId: string, target: InspectorTarget) => void;
}) {
  return (
    <div className="ga-task-stream">
      {items.map((item, index) => {
        const isLatest = index === items.length - 1;
        const itemStreaming = streaming && isLatest;
        return (
          <article key={item.id} className="ga-task-item">
            {item.command ? <CommandBlock message={item.command} /> : null}
            <InlineExecutionTurns
              turns={item.executionLog}
              streaming={Boolean(item.pending || itemStreaming)}
              onSelectInspectorTarget={(target) =>
                onSelectInspectorTarget?.(item.id, target)
              }
            />
            <ResponsePanel
              message={item.response}
              streaming={itemStreaming}
              pending={Boolean(item.pending)}
            />
          </article>
        );
      })}
    </div>
  );
}
