import { Button, ListBox, Select, Surface, TextArea, type Key } from "@heroui/react";
import { ArrowUp, Paperclip, Square, X } from "lucide-react";
import type { ChangeEvent, FormEvent, KeyboardEvent } from "react";
import { useRef, useState } from "react";
import type { ModelProfile } from "../api";
import type { ImageAttachment } from "../types";

type ComposerProps = {
  disabled: boolean;
  modelProfiles: ModelProfile[];
  onCancel: () => void;
  onModelProfileSelect: (profileId: string) => void;
  onSubmit: (content: string, images: ImageAttachment[]) => void;
  selectedProfileId: string;
};

export function Composer({
  disabled,
  modelProfiles,
  onCancel,
  onModelProfileSelect,
  onSubmit,
  selectedProfileId,
}: ComposerProps) {
  const [content, setContent] = useState("");
  const [selectedImages, setSelectedImages] = useState<ImageAttachment[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const selectedProfile = modelProfiles.find((profile) => String(profile.id) === selectedProfileId);

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

  function handleProfileChange(value: Key | Key[] | null) {
    const next = Array.isArray(value) ? value[0] : value;
    if (next !== null && next !== undefined) {
      onModelProfileSelect(String(next));
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
          <div className="composer-toolbar">
            <input
              accept="image/*"
              aria-label="选择图片附件"
              className="composer-file-input"
              multiple
              onChange={handleImageSelection}
              ref={fileInputRef}
              type="file"
            />
            <div className="composer-actions-row">
              <Button
                aria-label="添加附件"
                className="composer-icon-button"
                isDisabled={disabled}
                onPress={() => fileInputRef.current?.click()}
                size="sm"
                variant="tertiary"
              >
                <Paperclip size={17} />
                添加附件
              </Button>
              <Select
                aria-label="切换生效模型"
                className="composer-model-switch profile-switch"
                isDisabled={disabled || modelProfiles.length === 0}
                onChange={handleProfileChange}
                placeholder="选择模型"
                value={selectedProfileId || null}
                variant="secondary"
              >
                <Select.Trigger>
                  <Select.Value>{selectedProfile ? formatProfileOption(selectedProfile) : "选择模型"}</Select.Value>
                  <Select.Indicator />
                </Select.Trigger>
                <Select.Popover className="composer-model-popover">
                  <ListBox className="composer-model-listbox">
                    {modelProfiles.map((profile) => (
                      <ListBox.Item
                        className="composer-model-option"
                        id={String(profile.id)}
                        key={profile.id}
                        textValue={formatProfileOption(profile)}
                      >
                        {formatProfileOption(profile)}
                        <ListBox.ItemIndicator />
                      </ListBox.Item>
                    ))}
                  </ListBox>
                </Select.Popover>
              </Select>
            </div>
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

function formatProfileOption(profile: ModelProfile): string {
  return profile.model?.trim() ? profile.model.trim() : profile.name;
}
