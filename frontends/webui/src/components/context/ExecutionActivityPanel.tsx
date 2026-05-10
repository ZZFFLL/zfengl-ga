import { Empty, Tag, Timeline } from "antd";
import { CircleDot, Wrench } from "lucide-react";

import { buildTurnMeta, countToolCalls } from "../../state/workbench-context-state";
import type { ExecutionTurn } from "../../types";

export function ExecutionActivityPanel({
  turns,
  running,
}: {
  turns: ExecutionTurn[];
  running: boolean;
}) {
  if (turns.length === 0) {
    return (
      <section className="ga-context-section">
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="当前会话还没有执行记录"
          className="my-2"
        />
      </section>
    );
  }

  return (
    <section className="ga-context-section">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-app-text">执行活动</div>
          <div className="mt-1 text-xs text-app-muted">
            {turns.length} 轮 · {countToolCalls(turns)} 个工具调用
          </div>
        </div>
        <Tag bordered={false} color={running ? "processing" : "success"} className="m-0">
          {running ? "执行中" : "已完成"}
        </Tag>
      </div>
      <Timeline
        className="ga-context-timeline"
        items={turns.map((turn, index) => {
          const meta = buildTurnMeta(turn);
          return {
            key: `${turn.turn}-${index}`,
            dot: (
              <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-[#e7f5f2] text-[#0f766e]">
                <CircleDot className="h-3.5 w-3.5" />
              </span>
            ),
            children: (
              <div className="ga-context-activity-item">
                <div className="flex min-w-0 items-center justify-between gap-3">
                  <div className="truncate text-sm font-medium text-app-text">{meta.title}</div>
                  <Tag bordered={false} className="m-0 shrink-0">
                    {meta.statusLabel}
                  </Tag>
                </div>
                <div className="mt-2 flex items-center gap-2 text-xs text-app-muted">
                  <Wrench className="h-3.5 w-3.5" />
                  <span>{meta.toolCallLabel}</span>
                </div>
              </div>
            ),
          };
        })}
      />
    </section>
  );
}
