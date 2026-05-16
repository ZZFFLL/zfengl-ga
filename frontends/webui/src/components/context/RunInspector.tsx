import { Button, Empty, Tag } from "antd";
import { PanelRightClose, Square } from "lucide-react";
import type { InspectorTarget } from "../../state/task-stream-state";
import type { ExecutionTurn } from "../../types";

export function RunInspector({
  turns,
  target,
  running,
  onClose,
  onAbort,
}: {
  turns: ExecutionTurn[];
  target: InspectorTarget | null;
  running: boolean;
  onClose: () => void;
  onAbort: () => void;
}) {
  const selectedTurn = target ? turns[target.turnIndex] : null;
  const selectedToolCall =
    selectedTurn && target?.toolIndex !== null && target?.toolIndex !== undefined
      ? selectedTurn.tool_calls?.[target.toolIndex]
      : null;

  return (
    <aside className="ga-run-inspector">
      <div className="ga-run-inspector-header">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-app-textStrong">运行详情</div>
          <div className="mt-1 truncate text-xs text-app-muted">
            {selectedTurn ? selectedTurn.title || `Turn ${selectedTurn.turn}` : "没有选中的执行步骤"}
          </div>
        </div>
        <Button
          type="text"
          aria-label="关闭运行详情"
          icon={<PanelRightClose className="h-4 w-4" aria-hidden="true" />}
          onClick={onClose}
        />
      </div>

      <div className="operation-scroll min-h-0 flex-1 overflow-y-auto p-4">
        {!selectedTurn ? (
          <div className="space-y-4">
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={running ? "任务正在启动，等待执行步骤..." : "选择执行步骤后查看细节"}
            />
            {running ? (
              <Button danger icon={<Square className="h-4 w-4" aria-hidden="true" />} onClick={onAbort}>
                停止当前任务
              </Button>
            ) : null}
          </div>
        ) : (
          <div className="space-y-4">
            <section className="ga-run-inspector-section">
              <div className="mb-2 flex items-center justify-between gap-3">
                <div className="text-xs font-semibold text-app-muted">步骤</div>
                <Tag bordered={false} color={selectedTurn.state === "active" ? "processing" : "success"}>
                  {selectedTurn.state === "active" ? "执行中" : "已完成"}
                </Tag>
              </div>
              <div className="text-sm font-semibold text-app-textStrong">
                {selectedTurn.title || `Turn ${selectedTurn.turn}`}
              </div>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-app-muted">
                {selectedTurn.summary || selectedTurn.content || "此步骤暂无摘要。"}
              </p>
            </section>

            {selectedToolCall ? (
              <section className="ga-run-inspector-section">
                <div className="mb-2 text-xs font-semibold text-app-muted">已选工具</div>
                <div className="text-sm font-semibold text-app-textStrong">{selectedToolCall.tool}</div>
                <div className="mt-1 text-xs text-app-muted">
                  {selectedToolCall.status || selectedToolCall.action || "工具调用"}
                </div>
                {selectedToolCall.args ? (
                  <pre className="mt-3 overflow-x-auto rounded-lg bg-app-codeBg p-3 text-xs leading-6 text-app-codeText">
                    <code>{selectedToolCall.args}</code>
                  </pre>
                ) : null}
                {selectedToolCall.result_preview || selectedToolCall.result ? (
                  <pre className="mt-3 overflow-x-auto rounded-lg bg-app-codeBg p-3 text-xs leading-6 text-app-codeText">
                    <code>{selectedToolCall.result_preview || selectedToolCall.result}</code>
                  </pre>
                ) : null}
              </section>
            ) : null}
          </div>
        )}
      </div>
    </aside>
  );
}
