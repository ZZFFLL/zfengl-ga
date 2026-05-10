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

  return (
    <form className="ga-composer-bar shrink-0 border-t border-app-line px-3 py-3 backdrop-blur md:px-4 md:py-4" onSubmit={onSubmit}>
      <div className="ga-composer-surface mx-auto max-w-[900px] rounded-xl px-4 py-3">
        <textarea
          id="chat-composer-draft"
          name="chat-composer-draft"
          className="min-h-[64px] w-full resize-none border-0 bg-transparent text-[15px] leading-7 text-app-text placeholder:text-app-muted focus:outline-none"
          placeholder={running ? "任务运行中..." : "继续补充问题，Shift+Enter 换行"}
          value={draft}
          disabled={running || !state?.configured}
          onChange={(event) => onDraftChange(event.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
        />
        <div className="mt-3 flex items-center justify-between gap-3">
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
              shape="circle"
              disabled={!draft.trim() || running || !state?.configured}
              aria-label="发送"
              icon={<Send className="h-4 w-4" aria-hidden="true" />}
            >
            </Button>
          </div>
        </div>
      </div>
    </form>
  );
}
