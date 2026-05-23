import { Button, Surface, TextArea } from "@heroui/react";
import { ArrowUp, Paperclip } from "lucide-react";
import type { FormEvent, KeyboardEvent } from "react";
import { useState } from "react";

type ComposerProps = {
  disabled: boolean;
  onSubmit: (content: string) => void;
};

export function Composer({ disabled, onSubmit }: ComposerProps) {
  const [content, setContent] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = content.trim();
    if (!trimmed || disabled) {
      return;
    }
    setContent("");
    onSubmit(trimmed);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      submit(event);
    }
  }

  return (
    <div className="composer-dock">
      <Surface className="composer-card" variant="default">
        <form className="composer-form" onSubmit={submit}>
          <TextArea
            aria-label="发送给 GenericAgent 的消息"
            className="composer-input"
            disabled={disabled}
            fullWidth
            id="message-to-genericagent"
            name="message"
            onChange={(event) => setContent(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="你想了解什么？"
            rows={2}
            value={content}
            variant="secondary"
          />
          <div className="composer-toolbar">
            <div className="composer-left-tools">
              <Button aria-label="添加附件" className="composer-icon-button" isIconOnly size="sm" variant="tertiary">
                <Paperclip size={19} />
              </Button>
            </div>
            <Button
              aria-label="发送消息"
              className="send-button"
              isDisabled={disabled || !content.trim()}
              isIconOnly
              type="submit"
            >
              <ArrowUp size={20} />
            </Button>
          </div>
        </form>
      </Surface>
      <p className="composer-disclaimer">AI 可能出错，请核对重要信息。</p>
    </div>
  );
}
