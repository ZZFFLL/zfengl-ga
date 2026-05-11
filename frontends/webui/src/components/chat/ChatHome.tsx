import type { FormEvent, KeyboardEvent } from "react";
import { Button } from "antd";
import { MessageSquareText, Send, Sparkles } from "lucide-react";

import type { RuntimeState } from "../../types";

export function ChatHome({
  state,
  draft,
  running,
  onDraftChange,
  onKeyDown,
  onSubmit,
}: {
  state: RuntimeState | null;
  draft: string;
  running: boolean;
  onDraftChange: (value: string) => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onSubmit: (event?: FormEvent) => void;
}) {
  return (
    <section className="ga-chat-home flex min-h-full flex-col justify-center px-4 pb-10 pt-6 sm:px-6">
      <div className="mx-auto w-full max-w-[51.25rem]">
        <div className="text-center">
          <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-lg bg-app-primarySoft text-app-primary ring-1 ring-app-line/70">
            <Sparkles className="h-5 w-5" aria-hidden="true" />
          </div>
          <h2 className="mt-5 text-2xl font-semibold text-app-textStrong sm:text-3xl">
            开始一个 GA 工作流
          </h2>
          <p className="mx-auto mt-2 max-w-xl text-sm leading-7 text-app-muted">
            输入任务、问题或代码修改目标。WebUI 会保留回答和执行过程，便于复查当前会话。
          </p>
        </div>

        <form className="mx-auto mt-12 max-w-[51.25rem]" onSubmit={onSubmit}>
          <div className="ga-home-command-dock">
            <div className="flex items-start gap-4">
              <div className="mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-app-primarySoft text-app-primary">
                <MessageSquareText className="h-5 w-5" aria-hidden="true" />
              </div>
              <textarea
                id="chat-home-draft"
                name="chat-home-draft"
                className="ga-home-command-input"
                placeholder={running ? "任务运行中..." : "有什么我能帮您的吗？"}
                value={draft}
                disabled={running || !state?.configured}
                onChange={(event) => onDraftChange(event.target.value)}
                onKeyDown={onKeyDown}
                rows={2}
              />
              <Button
                type="primary"
                htmlType="submit"
                shape="circle"
                className="mt-1 shrink-0"
                disabled={!draft.trim() || running || !state?.configured}
                aria-label="发送"
                icon={<Send className="h-4 w-4" aria-hidden="true" />}
              >
              </Button>
            </div>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-app-muted">
              <span>{state?.configured ? "当前后端已就绪" : "请先配置模型后再发送"}</span>
              <span>Shift+Enter 换行，Enter 发送</span>
            </div>
          </div>
        </form>
      </div>
    </section>
  );
}
