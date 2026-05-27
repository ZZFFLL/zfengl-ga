import { Button, ListBox, Select, Surface, type Key } from "@heroui/react";
import { AnimatePresence, motion } from "motion/react";
import { ArrowUp, BookOpen, Paperclip, Search, Square, X } from "lucide-react";
import type { ChangeEvent, FormEvent, KeyboardEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { getSopDetail, listSops, type ModelProfile, type SopEntry } from "../api";
import { buildDisplayPromptWithSopReferences, buildPromptWithSopReferences } from "../sop_prompt";
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

type SopMentionRange = {
  start: number;
  end: number;
  query: string;
};

type SopPickerMode = "button" | "mention";

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
  const [sopPickerMode, setSopPickerMode] = useState<SopPickerMode>("button");
  const [sops, setSops] = useState<SopEntry[]>([]);
  const [selectedSops, setSelectedSops] = useState<SopEntry[]>([]);
  const [sopQuery, setSopQuery] = useState("");
  const [activeSopIndex, setActiveSopIndex] = useState(0);
  const [activeMentionRange, setActiveMentionRange] = useState<SopMentionRange | null>(null);
  const [previewSop, setPreviewSop] = useState<SopEntry | null>(null);
  const [previewContent, setPreviewContent] = useState("");
  const [sopError, setSopError] = useState("");
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const editorRef = useRef<HTMLDivElement | null>(null);
  const editorSelectionRef = useRef<Range | null>(null);
  const activeMentionRangeRef = useRef<Range | null>(null);
  const sopPickerPanelRef = useRef<HTMLDivElement | null>(null);
  const sopPickerSearchRef = useRef<HTMLInputElement | null>(null);
  const activeSopOptionRef = useRef<HTMLDivElement | null>(null);
  const previewRequestSeqRef = useRef(0);
  const selectedProfile = modelProfiles.find((profile) => String(profile.id) === selectedProfileId);
  const selectedSopIds = useMemo(() => new Set(selectedSops.map((sop) => sop.id)), [selectedSops]);
  const filteredSops = useMemo(() => {
    const query = sopQuery.trim().toLowerCase();
    if (!query) {
      return sops;
    }
    return sops.filter((sop) => readSopSearchText(sop).includes(query));
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

  useEffect(() => {
    setActiveSopIndex(0);
  }, [sopQuery]);

  useEffect(() => {
    if (activeSopIndex >= filteredSops.length) {
      setActiveSopIndex(Math.max(0, filteredSops.length - 1));
    }
  }, [activeSopIndex, filteredSops.length]);

  useEffect(() => {
    activeSopOptionRef.current?.scrollIntoView({ block: "nearest" });
  }, [activeSopIndex, filteredSops]);

  useEffect(() => {
    if (!sopPickerOpen || sopPickerMode !== "button") {
      return;
    }
    sopPickerSearchRef.current?.focus();
  }, [sopPickerMode, sopPickerOpen]);

  useEffect(() => {
    if (!sopPickerOpen) {
      return;
    }

    function handlePointerDown(event: PointerEvent) {
      const target = event.target;
      if (!(target instanceof Element)) {
        return;
      }
      if (target.closest(".composer-sop-trigger")) {
        return;
      }
      if (sopPickerPanelRef.current?.contains(target)) {
        return;
      }
      closeSopPicker();
    }

    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [sopPickerOpen]);

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
    clearEditor(editorRef.current);
    onSubmit(finalContent, selectedImages, displayContent === finalContent ? undefined : displayContent);
  }

  function updateEditorContent() {
    const editor = editorRef.current;
    if (!editor) {
      return;
    }
    saveEditorSelection();
    syncSelectedSopsWithEditor();
    setContent(readEditorPlainText(editor));
    const mention = detectActiveSopMention(editor);
    if (mention) {
      activeMentionRangeRef.current = mention.range;
      setActiveMentionRange({ end: mention.end, query: mention.query, start: mention.start });
      setSopPickerMode("mention");
      setSopPickerOpen(true);
      setSopQuery(mention.query);
      return;
    }
    activeMentionRangeRef.current = null;
    setActiveMentionRange(null);
    setSopPickerOpen(false);
    setSopQuery("");
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement | HTMLInputElement>) {
    if (sopPickerOpen) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveSopIndex((current) => Math.min(current + 1, Math.max(0, filteredSops.length - 1)));
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveSopIndex((current) => Math.max(0, current - 1));
        return;
      }
      if ((event.key === "Enter" || event.key === "Tab") && filteredSops[activeSopIndex]) {
        event.preventDefault();
        addSopReference(filteredSops[activeSopIndex]);
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        closeSopPicker();
        return;
      }
      if (event.key === "Enter" || event.key === "Tab") {
        event.preventDefault();
        return;
      }
    }
    if (event.key === "Enter" && !event.shiftKey) {
      submit(event);
    }
  }

  function saveEditorSelection() {
    const editor = editorRef.current;
    const selection = window.getSelection();
    if (!editor || !selection || selection.rangeCount === 0) {
      return;
    }
    const range = selection.getRangeAt(0);
    if (editor.contains(range.commonAncestorContainer)) {
      editorSelectionRef.current = range.cloneRange();
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
    insertSopToken(sop);
    closeSopPicker();
  }

  function removeSopReference(sopId: string) {
    setSelectedSops((current) => current.filter((sop) => sop.id !== sopId));
    editorRef.current?.querySelectorAll(`[data-sop-token="${cssEscape(sopId)}"]`).forEach((node) => node.remove());
    setContent(readEditorPlainText(editorRef.current));
  }

  function openSopPicker() {
    if (sopPickerOpen && sopPickerMode === "button") {
      closeSopPicker();
      return;
    }
    setActiveMentionRange(null);
    setSopPickerMode("button");
    setSopQuery("");
    setSopPickerOpen(true);
  }

  function closeSopPicker() {
    setSopPickerOpen(false);
    setSopPickerMode("button");
    setSopQuery("");
    setActiveMentionRange(null);
    setPreviewSop(null);
  }

  async function showSopPreview(sop: SopEntry) {
    const requestSeq = previewRequestSeqRef.current + 1;
    previewRequestSeqRef.current = requestSeq;
    setPreviewSop(sop);
    setPreviewContent("正在读取 SOP...");
    try {
      const detail = await getSopDetail(sop.id);
      if (requestSeq !== previewRequestSeqRef.current) {
        return;
      }
      setPreviewContent(detail.content);
    } catch (error) {
      if (requestSeq !== previewRequestSeqRef.current) {
        return;
      }
      setPreviewContent(error instanceof Error ? error.message : "SOP 读取失败");
    }
  }

  function syncSelectedSopsWithEditor() {
    const editor = editorRef.current;
    if (!editor) {
      return;
    }
    const visibleIds = new Set(Array.from(editor.querySelectorAll<HTMLElement>("[data-sop-token]")).map((node) => node.dataset.sopToken ?? ""));
    setSelectedSops((current) => current.filter((sop) => visibleIds.has(sop.id)));
  }

  function insertSopToken(sop: SopEntry) {
    const editor = editorRef.current;
    if (!editor) {
      return;
    }
    editor.focus();
    const token = createSopTokenElement(sop, removeSopReference);
    const range = activeMentionRangeRef.current ?? readEditorInsertionRange(editor, editorSelectionRef.current);
    range.deleteContents();
    range.insertNode(document.createTextNode(" "));
    range.insertNode(token);
    range.insertNode(document.createTextNode(" "));
    moveCaretAfterNode(token);
    activeMentionRangeRef.current = null;
    editorSelectionRef.current = null;
    setContent(readEditorPlainText(editor));
  }

  return (
    <div className="composer-dock">
      <Surface className="composer-card" variant="default">
        <form className="composer-form" onSubmit={submit}>
          <AnimatePresence>
            {sopPickerOpen ? (
              <motion.div
                animate={{ opacity: 1, y: 0 }}
                className="sop-picker-popover composer-sop-picker-popover"
                exit={{ opacity: 0, y: 8 }}
                initial={{ opacity: 0, y: 8 }}
                transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
                ref={sopPickerPanelRef}
              >
                <div className="sop-picker">
                  <div className="sop-picker-head">
                    <span>SOP</span>
                    <span>{sopPickerMode === "button" ? "输入关键词搜索 SOP" : "输入 @ 或 @关键词引用 SOP"}</span>
                  </div>
                  {sopPickerMode === "button" ? (
                    <div className="sop-picker-search">
                      <Search size={15} />
                      <input
                        aria-label="搜索 SOP"
                        autoFocus
                        id="sop-picker-search"
                        name="sop-picker-search"
                        onChange={(event) => setSopQuery(event.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="搜索 SOP"
                        ref={sopPickerSearchRef}
                        value={sopQuery}
                      />
                    </div>
                  ) : null}
                  {sopError ? <div className="sop-picker-error">{sopError}</div> : null}
                  {/* SOP 弹窗行高由自定义卡片决定，避免 ListBox collection 布局压缩列表项。 */}
                  <div aria-activedescendant={filteredSops[activeSopIndex] ? `sop-option-${filteredSops[activeSopIndex].id}` : undefined} aria-label="SOP 列表" className="sop-picker-list" role="listbox">
                    {filteredSops.map((sop, index) => (
                      <div
                        aria-selected={selectedSopIds.has(sop.id)}
                        className="sop-picker-row"
                        id={`sop-option-${sop.id}`}
                        key={sop.id}
                        onMouseEnter={() => setActiveSopIndex(index)}
                        ref={index === activeSopIndex ? activeSopOptionRef : null}
                        role="option"
                      >
                        <SopPickerItem
                          isActive={index === activeSopIndex}
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
                </div>
              </motion.div>
            ) : null}
          </AnimatePresence>
          <div className="composer-input-area">
            <div
              aria-label="发送给 GenericAgent 的消息"
              className="composer-input composer-rich-input"
              contentEditable={!disabled}
              data-placeholder="你想了解什么？"
              id="message-to-genericagent"
              onBlur={saveEditorSelection}
              onClick={saveEditorSelection}
              onInput={updateEditorContent}
              onKeyDown={handleKeyDown}
              onKeyUp={saveEditorSelection}
              ref={editorRef}
              role="textbox"
              suppressContentEditableWarning
            />
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
                aria-label="引用 SOP"
                className="composer-icon-button composer-sop-trigger"
                isDisabled={disabled}
                onPress={openSopPicker}
                size="sm"
                variant="tertiary"
              >
                <BookOpen size={17} />
                SOP
              </Button>
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

function detectActiveSopMention(editor: HTMLElement): (SopMentionRange & { range: Range }) | null {
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0 || !selection.isCollapsed) {
    return null;
  }
  const anchorNode = selection.anchorNode;
  if (!anchorNode || anchorNode.nodeType !== Node.TEXT_NODE || !editor.contains(anchorNode)) {
    return null;
  }
  const anchorText = anchorNode.textContent ?? "";
  const caret = selection.anchorOffset;
  const beforeCaret = anchorText.slice(0, caret);
  const match = /(^|\s)@([A-Za-z0-9_.-]*)$/.exec(beforeCaret);
  if (!match) {
    return null;
  }
  const query = match[2] ?? "";
  const start = caret - query.length - 1;
  const range = document.createRange();
  range.setStart(anchorNode, Math.max(0, start));
  range.setEnd(anchorNode, caret);
  return {
    start: Math.max(0, start),
    end: caret,
    query,
    range,
  };
}

function readEditorPlainText(editor: HTMLElement | null): string {
  if (!editor) {
    return "";
  }
  const clone = editor.cloneNode(true) as HTMLElement;
  clone.querySelectorAll("[data-sop-token]").forEach((node) => node.remove());
  return clone.innerText.replace(/\u00a0/g, " ").trim();
}

function clearEditor(editor: HTMLElement | null) {
  if (editor) {
    editor.textContent = "";
  }
}

function readSopSearchText(sop: SopEntry): string {
  return [sop.id, sop.title, sop.summary, fileBaseName(sop.name), fileBaseName(sop.path)].filter(Boolean).join(" ").toLowerCase();
}

function fileBaseName(path: string | undefined): string {
  return (path ?? "").split(/[\\/]/).pop() ?? "";
}

function readEditorInsertionRange(editor: HTMLElement, savedRange: Range | null): Range {
  if (savedRange && editor.contains(savedRange.commonAncestorContainer)) {
    return savedRange.cloneRange();
  }
  const range = document.createRange();
  range.selectNodeContents(editor);
  range.collapse(false);
  return range;
}

function createSopTokenElement(sop: SopEntry, onRemove: (sopId: string) => void): HTMLElement {
  const token = document.createElement("span");
  token.className = "composer-sop-token";
  token.contentEditable = "false";
  token.dataset.sopToken = sop.id;
  token.title = sop.title || sop.name || sop.id;

  const label = document.createElement("span");
  label.className = "composer-sop-token-label";
  label.textContent = `@${sop.id}`;

  const remove = document.createElement("button");
  remove.className = "composer-sop-token-remove";
  remove.type = "button";
  remove.setAttribute("aria-label", `移除 ${sop.name}`);
  remove.textContent = "x";
  remove.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    onRemove(sop.id);
  });

  token.append(label, remove);
  return token;
}

function moveCaretAfterNode(node: Node) {
  const selection = window.getSelection();
  if (!selection) {
    return;
  }
  const range = document.createRange();
  range.setStartAfter(node);
  range.collapse(true);
  selection.removeAllRanges();
  selection.addRange(range);
}

function cssEscape(value: string): string {
  return typeof CSS !== "undefined" && typeof CSS.escape === "function" ? CSS.escape(value) : value.replace(/["\\]/g, "\\$&");
}
