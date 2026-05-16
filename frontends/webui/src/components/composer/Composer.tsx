import type { FormEvent, KeyboardEvent } from "react";
import { Button } from "antd";
import { Send, Square } from "lucide-react";
import type { RuntimeState } from "../../types";

export function Composer({
  state,
  draft,
  running,
  onDraftChange,
  onKeyDown,
  onSubmit,
  onAbort,
}: {
  state: RuntimeState | null;
  draft: string;
  running: boolean;
  onDraftChange: (value: string) => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onSubmit: (event?: FormEvent) => void;
  onAbort: () => void;
}) {
  const helperText = !state?.configured
    ? "请先配置模型后再发送。"
    : running
      ? "任务运行中，可以停止当前任务。"
      : "Shift+Enter 换行，Enter 发送。";
  const statusText = running ? "运行中" : state?.configured ? "准备就绪" : "未配置";

  return (
    <form className="ga-command-dock" onSubmit={onSubmit}>
      <div className="ga-command-dock-inner">
        <div className="ga-command-dock-status">
          <span>{state?.current_llm?.name ?? "未选择模型"}</span>
          <span aria-hidden="true">/</span>
          <span>{statusText}</span>
        </div>
        <textarea
          id="chat-composer-draft"
          name="chat-composer-draft"
          className="ga-command-input"
          placeholder={running ? "任务运行中..." : "输入任务、修改目标或问题"}
          value={draft}
          disabled={running || !state?.configured}
          onChange={(event) => onDraftChange(event.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
        />
        <div className="ga-command-dock-footer">
          <div className="text-xs text-app-muted">{helperText}</div>
          <div className="flex items-center gap-2">
            {running ? (
              <Button
                icon={<Square className="h-4 w-4" aria-hidden="true" />}
                onClick={onAbort}
              >
                停止
              </Button>
            ) : null}
            <Button
              type="primary"
              htmlType="submit"
              disabled={!draft.trim() || running || !state?.configured}
              aria-label="发送任务"
              icon={<Send className="h-4 w-4" aria-hidden="true" />}
            >
              运行
            </Button>
          </div>
        </div>
      </div>
    </form>
  );
}
