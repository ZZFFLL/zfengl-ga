import type { TaskStreamItem } from "../../state/task-stream-state";
import { InlineExecutionTurns } from "../execution/InlineExecutionTurns";
import { CommandBlock } from "./CommandBlock";
import { ResponsePanel } from "./ResponsePanel";

export function TaskStream({
  items,
  streaming,
}: {
  items: TaskStreamItem[];
  streaming: boolean;
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
