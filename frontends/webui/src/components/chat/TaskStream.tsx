import type { InspectorTarget, TaskStreamItem } from "../../state/task-stream-state";
import type { ExecutionTurn } from "../../types";
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
  onSelectInspectorTarget: (turns: ExecutionTurn[], target: InspectorTarget) => void;
}) {
  void onSelectInspectorTarget;

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
