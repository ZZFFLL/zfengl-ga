import { Button, Segmented, Tooltip } from "antd";
import { PanelRightClose } from "lucide-react";

type WorkbenchContextTab = "activity" | "status";

export function ContextPanelHeader({
  activeTab,
  onTabChange,
  onClose,
}: {
  activeTab: WorkbenchContextTab;
  onTabChange: (tab: WorkbenchContextTab) => void;
  onClose?: () => void;
}) {
  return (
    <header className="ga-context-header">
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-app-text">工作上下文</div>
        <div className="text-xs text-app-muted">基于当前会话和执行日志</div>
      </div>
      <Segmented<WorkbenchContextTab>
        size="small"
        value={activeTab}
        onChange={(value) => onTabChange(value)}
        options={[
          { label: "执行", value: "activity" },
          { label: "状态", value: "status" },
        ]}
      />
      {onClose ? (
        <Tooltip title="收起上下文面板">
          <Button
            type="text"
            size="small"
            className="inline-flex items-center justify-center"
            icon={<PanelRightClose className="h-4 w-4" aria-hidden="true" />}
            onClick={onClose}
            aria-label="收起上下文面板"
          />
        </Tooltip>
      ) : null}
    </header>
  );
}
