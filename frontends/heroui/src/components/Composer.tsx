import { Button, Surface, TextArea } from "@heroui/react";
import { ArrowUp, Paperclip, Square, X } from "lucide-react";
import type { ChangeEvent, FormEvent, KeyboardEvent } from "react";
import { useRef, useState } from "react";
import type { ImageAttachment } from "../types";

type ComposerProps = {
  disabled: boolean;
  onCancel: () => void;
  onSubmit: (content: string, images: ImageAttachment[]) => void;
};

export function Composer({ disabled, onCancel, onSubmit }: ComposerProps) {
  const [content, setContent] = useState("");
  const [selectedImages, setSelectedImages] = useState<ImageAttachment[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = content.trim();
    if (disabled) {
      onCancel();
      return;
    }
    if (!trimmed && selectedImages.length === 0) {
      return;
    }
    setContent("");
    setSelectedImages([]);
    onSubmit(trimmed, selectedImages);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      submit(event);
    }
  }

  async function handleImageSelection(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    const images = await Promise.all(files.filter((file) => file.type.startsWith("image/")).map(readImageAttachment));
    setSelectedImages((current) => [...current, ...images]);
    event.target.value = "";
  }

  function removeImage(imageId: string) {
    setSelectedImages((current) => current.filter((image) => image.id !== imageId));
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
              <input
                accept="image/*"
                aria-label="选择图片附件"
                className="composer-file-input"
                multiple
                onChange={handleImageSelection}
                ref={fileInputRef}
                type="file"
              />
              <Button
                aria-label="添加附件"
                className="composer-icon-button"
                isDisabled={disabled}
                isIconOnly
                onPress={() => fileInputRef.current?.click()}
                size="sm"
                variant="tertiary"
              >
                <Paperclip size={19} />
              </Button>
            </div>
            {selectedImages.length > 0 ? (
              <div className="composer-attachment-list" aria-label="已选择图片附件">
                {selectedImages.map((image) => (
                  <span className="composer-attachment-pill" key={image.id}>
                    {image.name}
                    <Button
                      aria-label={`移除 ${image.name}`}
                      className="composer-attachment-remove"
                      isIconOnly
                      onPress={() => removeImage(image.id)}
                      size="sm"
                      variant="ghost"
                    >
                      <X size={12} />
                    </Button>
                  </span>
                ))}
              </div>
            ) : null}
            <Button
              aria-label={disabled ? "停止生成" : "发送消息"}
              className={`send-button ${disabled ? "send-button--stop" : ""}`}
              isDisabled={!disabled && !content.trim() && selectedImages.length === 0}
              isIconOnly
              type="submit"
              variant={disabled ? "danger" : "primary"}
            >
              {disabled ? <Square size={15} /> : <ArrowUp size={20} />}
            </Button>
          </div>
        </form>
      </Surface>
      <p className="composer-disclaimer">AI 可能出错，请核对重要信息。</p>
    </div>
  );
}

function readImageAttachment(file: File): Promise<ImageAttachment> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      resolve({
        id: `img-${crypto.randomUUID()}`,
        name: file.name,
        dataUrl: String(reader.result ?? ""),
      });
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}
