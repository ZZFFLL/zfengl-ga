import type { ReactNode } from "react";
import { Badge, Tag } from "antd";
import { Activity, Bot, BrainCircuit, Power } from "lucide-react";

import { buildRuntimeSummary } from "../../state/workbench-context-state";
import type { RuntimeState } from "../../types";

function SummaryRow({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="ga-context-summary-row">
      <span className="ga-context-summary-icon" aria-hidden="true">
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-xs text-app-muted">{label}</div>
        <div className="truncate text-sm font-medium text-app-text">{value}</div>
      </div>
    </div>
  );
}

export function RuntimeSummaryPanel({ state }: { state: RuntimeState | null }) {
  const summary = buildRuntimeSummary(state);

  return (
    <section className="ga-context-section space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-app-text">运行状态</div>
          <div className="text-xs text-app-muted">当前会话前端状态摘要</div>
        </div>
        <Tag bordered={false} color={state?.running ? "processing" : "default"} className="m-0 shrink-0">
          <Badge status={state?.running ? "processing" : "default"} text={summary.runningLabel} />
        </Tag>
      </div>
      <div className="space-y-2">
        <SummaryRow
          icon={<Power className="h-4 w-4" aria-hidden="true" />}
          label="配置"
          value={summary.configuredLabel}
        />
        <SummaryRow
          icon={<Bot className="h-4 w-4" aria-hidden="true" />}
          label="模型"
          value={summary.modelLabel}
        />
        <SummaryRow
          icon={<BrainCircuit className="h-4 w-4" aria-hidden="true" />}
          label="自主行动"
          value={summary.autonomousLabel}
        />
        <SummaryRow
          icon={<Activity className="h-4 w-4" aria-hidden="true" />}
          label="任务"
          value={summary.runningLabel}
        />
      </div>
    </section>
  );
}
