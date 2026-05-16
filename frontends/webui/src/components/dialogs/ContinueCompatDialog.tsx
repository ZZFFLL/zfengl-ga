import type { FormEvent } from "react";
import { Button, Input, Modal, Tag } from "antd";

const DEFAULT_CONTINUE_COMMAND = "/continue 1";

export type ContinueCompatResult = {
  message: string;
  history: Array<{ role: "user" | "assistant"; content: string }>;
};

export function ContinueCompatDialog({
  open,
  command,
  loading,
  error,
  result,
  onOpenChange,
  onCommandChange,
  onSubmit,
}: {
  open: boolean;
  command: string;
  loading: boolean;
  error: string;
  result: ContinueCompatResult | null;
  onOpenChange: (open: boolean) => void;
  onCommandChange: (value: string) => void;
  onSubmit: (event?: FormEvent) => void;
}) {
  return (
    <Modal
      open={open}
      title="恢复旧会话（兼容入口）"
      width="min(92vw, 45rem)"
      centered
      destroyOnClose={false}
      onCancel={() => onOpenChange(false)}
      footer={null}
      className="ga-modal"
    >
      <p className="mt-1 text-sm leading-7 text-app-muted">
        这里保留 `/continue` 兼容能力，但不会把旧日志体系改成新会话真相源。
      </p>

      <form className="mt-6 space-y-4" onSubmit={onSubmit}>
        <div className="rounded-2xl border border-app-line bg-app-surface px-4 py-4">
          <label className="mb-2 block text-sm font-medium text-app-text" htmlFor="continue-command">
            兼容命令
          </label>
          <Input
            id="continue-command"
            value={command}
            onChange={(event) => onCommandChange(event.target.value)}
            placeholder={DEFAULT_CONTINUE_COMMAND}
          />
          <p className="mt-2 text-xs leading-6 text-app-muted">示例：`/continue 1`。接口仍走现有后端兼容逻辑。</p>
        </div>

        {error ? (
          <div className="rounded-2xl border border-app-danger/20 bg-app-danger/10 px-4 py-3 text-sm text-app-danger">
            {error}
          </div>
        ) : null}

        {result ? (
          <div className="space-y-4">
            <section className="rounded-2xl border border-app-line bg-app-surface px-4 py-4">
              <div className="text-sm font-semibold text-app-text">执行结果</div>
              <div className="mt-3 whitespace-pre-wrap text-sm leading-7 text-app-text">{result.message}</div>
            </section>

            <section className="rounded-2xl border border-app-line bg-app-surface px-4 py-4">
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm font-semibold text-app-text">兼容历史预览</div>
                <Tag bordered={false}>{result.history.length}</Tag>
              </div>
              <div className="mt-3 max-h-[17.5rem] space-y-3 overflow-y-auto">
                {result.history.length === 0 ? (
                  <div className="text-sm text-app-muted">这次兼容恢复没有返回可展示的历史记录。</div>
                ) : (
                  result.history.map((message, index) => (
                    <div key={`${message.role}-${index}`} className="rounded-xl bg-white px-4 py-3 ring-1 ring-app-line/70">
                      <div className="text-xs font-medium text-app-muted">
                        {message.role === "user" ? "用户" : "GA"}
                      </div>
                      <div className="mt-2 whitespace-pre-wrap text-sm leading-7 text-app-text">
                        {message.content}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </section>
          </div>
        ) : null}

        <div className="flex items-center justify-end gap-3">
          <Button onClick={() => onOpenChange(false)}>关闭</Button>
          <Button type="primary" htmlType="submit" loading={loading} disabled={!command.trim()}>
            执行兼容恢复
          </Button>
        </div>
      </form>
    </Modal>
  );
}
