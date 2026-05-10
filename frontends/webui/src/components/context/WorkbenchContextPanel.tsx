import type { RuntimeState, ExecutionTurn } from "../../types";
import { ContextPanelHeader } from "./ContextPanelHeader";
import { ExecutionActivityPanel } from "./ExecutionActivityPanel";
import { RuntimeSummaryPanel } from "./RuntimeSummaryPanel";

type WorkbenchContextTab = "activity" | "status";

export function WorkbenchContextPanel({
  state,
  turns,
  activeTab,
  onTabChange,
  onClose,
  closeLabel,
}: {
  state: RuntimeState | null;
  turns: ExecutionTurn[];
  activeTab: WorkbenchContextTab;
  onTabChange: (tab: WorkbenchContextTab) => void;
  onClose?: () => void;
  closeLabel?: string;
}) {
  return (
    <aside className="ga-context-panel">
      <ContextPanelHeader
        activeTab={activeTab}
        onTabChange={onTabChange}
        onClose={onClose}
        closeLabel={closeLabel}
      />
      <div className="operation-scroll min-h-0 flex-1 overflow-y-auto px-3 pb-4 pt-3">
        {activeTab === "activity" ? (
          <ExecutionActivityPanel turns={turns} running={state?.running ?? false} />
        ) : (
          <RuntimeSummaryPanel state={state} />
        )}
      </div>
    </aside>
  );
}
