import { Activity, PanelRightOpen } from "lucide-react";

export function RunInspectorToggle({
  running,
  turnCount,
  onClick,
}: {
  running: boolean;
  turnCount: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`ga-run-inspector-toggle ${running ? "is-running" : ""}`}
      aria-label="展开运行详情"
      onClick={onClick}
    >
      <span className="ga-run-inspector-toggle-icon">
        {running ? (
          <Activity className="h-4 w-4" aria-hidden="true" />
        ) : (
          <PanelRightOpen className="h-4 w-4" aria-hidden="true" />
        )}
      </span>
      <span className="ga-run-inspector-toggle-text">
        <span>{running ? "运行中" : "执行详情"}</span>
        <span>{turnCount > 0 ? `${turnCount} 轮` : "等待步骤"}</span>
      </span>
    </button>
  );
}
