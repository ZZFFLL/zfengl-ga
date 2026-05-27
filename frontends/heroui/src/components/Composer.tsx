import { Button, Chip, ListBox, Popover, Select, Surface, TextArea, type Key } from "@heroui/react";
import { AnimatePresence, motion } from "motion/react";
import { ArrowUp, BookOpen, Paperclip, Search, Square, X } from "lucide-react";
import type { ChangeEvent, FormEvent, KeyboardEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { getSopDetail, listSops, type ModelProfile, type SopEntry } from "../api";
import { buildDisplayPromptWithSopReferences, buildPromptWithSopReferences, removeTrailingSopTrigger } from "../sop_prompt";
import type { ImageAttachment } from "../types";
import { SopPickerItem } from "./SopPickerItem";

type ComposerProps = {
  disabled: boolean;
  modelProfiles: ModelProfile[];
  onCancel: () => void;
  onModelProfileSelect: (profileId: string) => void;
  onSubmit: (content: string, images: ImageAttachment[], displayContent?: string) => void;
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
  const [sopPickerOpen, setSopPickerOpen] = useState(false);
  const [sops, setSops] = useState<SopEntry[]>([]);
  const [selectedSops, setSelectedSops] = useState<SopEntry[]>([]);
  const [sopQuery, setSopQuery] = useState("");
  const [previewSop, setPreviewSop] = useState<SopEntry | null>(null);
  const [previewContent, setPreviewContent] = useState("");
  const [sopError, setSopError] = useState("");
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const selectedProfile = modelProfiles.find((profile) => String(profile.id) === selectedProfileId);
  const selectedSopIds = useMemo(() => new Set(selectedSops.map((sop) => sop.id)), [selectedSops]);
  const filteredSops = useMemo(() => {
    const query = sopQuery.trim().toLowerCase();
    if (!query) {
      return sops;
    }
    return sops.filter((sop) => `${sop.name} ${sop.title} ${sop.summary}`.toLowerCase().includes(query));
  }, [sopQuery, sops]);

  useEffect(() => {
    if (!sopPickerOpen || sops.length > 0) {
      return;
    }
    let cancelled = false;
    listSops()
      .then((items) => {
        if (!cancelled) {
          setSops(items);
          setSopError("");
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setSopError(error instanceof Error ? error.message : "SOP 列表读取失败");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [sopPickerOpen, sops.length]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = content.trim();
    if (disabled) {
      onCancel();
      return;
    }
    if (!trimmed && selectedImages.length === 0 && selectedSops.length === 0) {
      return;
    }
    const finalContent = buildPromptWithSopReferences(trimmed, selectedSops);
    const displayContent = buildDisplayPromptWithSopReferences(trimmed, selectedSops);
    setContent("");
    setSelectedImages([]);
    setSelectedSops([]);
    onSubmit(finalContent, selectedImages, displayContent === finalContent ? undefined : displayContent);
  }

  function updateContent(next: string) {
    setContent(next);
    if (next.endsWith("@")) {
      setSopPickerOpen(true);
      setSopQuery("");
    }
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

  function addSopReference(sop: SopEntry) {
    setSelectedSops((current) => (current.some((item) => item.id === sop.id) ? current : [...current, sop]));
    setContent((current) => removeTrailingSopTrigger(current));
    setSopPickerOpen(false);
    setSopQuery("");
  }

  function removeSopReference(sopId: string) {
    setSelectedSops((current) => current.filter((sop) => sop.id !== sopId));
  }

  async function showSopPreview(sop: SopEntry) {
    setPreviewSop(sop);
    setPreviewContent("正在读取 SOP...");
    try {
      const detail = await getSopDetail(sop.id);
      setPreviewContent(detail.content);
    } catch (error) {
      setPreviewContent(error instanceof Error ? error.message : "SOP 读取失败");
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
            onChange={(event) => updateContent(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="你想了解什么？"
            rows={2}
            value={content}
            variant="secondary"
          />
          <AnimatePresence>
            {selectedSops.length > 0 ? (
              <motion.div
                animate={{ opacity: 1, y: 0 }}
                className="composer-sop-chips"
                exit={{ opacity: 0, y: -4 }}
                initial={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
              >
                {selectedSops.map((sop) => (
                  <Chip className="composer-sop-chip" color="accent" key={sop.id} size="sm" variant="soft">
                    <BookOpen size={13} />
                    <Chip.Label>@{sop.id}</Chip.Label>
                    <button aria-label={`移除 ${sop.name}`} className="composer-sop-chip-remove" onClick={() => removeSopReference(sop.id)} type="button">
                      <X size={12} />
                    </button>
                  </Chip>
                ))}
              </motion.div>
            ) : null}
          </AnimatePresence>
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
              <Popover isOpen={sopPickerOpen} onOpenChange={setSopPickerOpen}>
                <Popover.Trigger>
                  <Button
                    aria-label="引用 SOP"
                    className="composer-icon-button"
                    isDisabled={disabled}
                    onPress={() => setSopPickerOpen(true)}
                    size="sm"
                    variant="tertiary"
                  >
                    <BookOpen size={17} />
                    SOP
                  </Button>
                </Popover.Trigger>
                <Popover.Content className="sop-picker-popover" placement="top start">
                  <Popover.Dialog className="sop-picker">
                    <div className="sop-picker-search">
                      <Search size={15} />
                      <input
                        aria-label="搜索 SOP"
                        autoFocus
                        id="sop-picker-search"
                        name="sop-picker-search"
                        onChange={(event) => setSopQuery(event.target.value)}
                        placeholder="搜索 SOP"
                        value={sopQuery}
                      />
                    </div>
                    {sopError ? <div className="sop-picker-error">{sopError}</div> : null}
                    {/* SOP 弹窗行高由自定义卡片决定，避免 ListBox collection 布局压缩列表项。 */}
                    <div aria-label="SOP 列表" className="sop-picker-list" role="listbox">
                      {filteredSops.map((sop) => (
                        <div
                          aria-selected={selectedSopIds.has(sop.id)}
                          className="sop-picker-row"
                          key={sop.id}
                          role="option"
                        >
                          <SopPickerItem
                            isSelected={selectedSopIds.has(sop.id)}
                            onOpen={addSopReference}
                            onPreview={(nextSop) => void showSopPreview(nextSop)}
                            sop={sop}
                          />
                        </div>
                      ))}
                    </div>
                    {filteredSops.length === 0 && !sopError ? <div className="sop-picker-empty">没有匹配的 SOP</div> : null}
                    <AnimatePresence>
                      {previewSop ? (
                        <motion.div
                          animate={{ opacity: 1, height: "auto" }}
                          className="sop-preview"
                          exit={{ opacity: 0, height: 0 }}
                          initial={{ opacity: 0, height: 0 }}
                          transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
                        >
                          <div className="sop-preview-head">
                            <strong>{previewSop.name}</strong>
                            <Button aria-label="关闭 SOP 预览" isIconOnly onPress={() => setPreviewSop(null)} size="sm" variant="ghost">
                              <X size={13} />
                            </Button>
                          </div>
                          <pre>{previewContent}</pre>
                        </motion.div>
                      ) : null}
                    </AnimatePresence>
                  </Popover.Dialog>
                </Popover.Content>
              </Popover>
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
              isDisabled={!disabled && !content.trim() && selectedImages.length === 0 && selectedSops.length === 0}
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
