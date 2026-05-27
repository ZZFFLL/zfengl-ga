import { Button, Tabs, TextArea } from "@heroui/react";
import { AnimatePresence, motion } from "motion/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Loader2, RefreshCw, Save, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from "react";
import { getSopDetail, listSops, saveSopDetail, type SopDetail, type SopEntry } from "../api";
import { SopWorkspaceItem } from "./SopWorkspaceItem";

const SOP_LIST_RATIO_STORAGE_KEY = "genericagent.heroui.sopListRatio";
const LEGACY_SOP_LIST_WIDTH_STORAGE_KEY = "genericagent.heroui.sopListWidth";
const DEFAULT_SOP_LIST_RATIO = 0.38;
const MIN_SOP_LIST_RATIO = 0.34;
const MAX_SOP_LIST_RATIO = 0.5;

function clampSopListRatio(ratio: number) {
  return Math.max(MIN_SOP_LIST_RATIO, Math.min(MAX_SOP_LIST_RATIO, ratio));
}

function readStoredSopListRatio() {
  if (typeof window === "undefined") {
    return DEFAULT_SOP_LIST_RATIO;
  }
  try {
    const storedRatio = Number(window.localStorage.getItem(SOP_LIST_RATIO_STORAGE_KEY));
    // 旧版本曾保存固定像素宽度；现在改为比例后主动清理，避免旧值造成误判。
    window.localStorage.removeItem(LEGACY_SOP_LIST_WIDTH_STORAGE_KEY);
    return Number.isFinite(storedRatio) ? clampSopListRatio(storedRatio) : DEFAULT_SOP_LIST_RATIO;
  } catch {
    return DEFAULT_SOP_LIST_RATIO;
  }
}

export function SopWorkspace() {
  const [sops, setSops] = useState<SopEntry[]>([]);
  const [query, setQuery] = useState("");
  const [selectedSopId, setSelectedSopId] = useState("");
  const [detail, setDetail] = useState<SopDetail | null>(null);
  const [draft, setDraft] = useState("");
  const [activeTab, setActiveTab] = useState("preview");
  const [error, setError] = useState("");
  const [isLoadingList, setIsLoadingList] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveState, setSaveState] = useState<"idle" | "saved">("idle");
  const [sopListRatio, setSopListRatio] = useState(() => readStoredSopListRatio());
  const [isListResizing, setIsListResizing] = useState(false);
  const workspaceRef = useRef<HTMLElement | null>(null);
  const resizeCleanupRef = useRef<(() => void) | null>(null);
  const selectedSop = detail?.item ?? sops.find((sop) => sop.id === selectedSopId) ?? null;
  const hasPreview = Boolean(selectedSopId);
  const isDirty = Boolean(detail && draft !== detail.content);

  const filteredSops = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return sops;
    }
    return sops.filter((sop) => `${sop.name} ${sop.title} ${sop.path} ${sop.summary}`.toLowerCase().includes(normalized));
  }, [query, sops]);

  useEffect(() => {
    void loadSops();
    return () => {
      resizeCleanupRef.current?.();
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    try {
      window.localStorage.setItem(SOP_LIST_RATIO_STORAGE_KEY, sopListRatio.toFixed(4));
    } catch {
      // localStorage 不可用时只影响列表比例记忆，不影响 SOP 页面使用。
    }
  }, [sopListRatio]);

  async function loadSops() {
    setIsLoadingList(true);
    try {
      const items = await listSops();
      setSops(items);
      setError("");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "SOP 列表读取失败");
    } finally {
      setIsLoadingList(false);
    }
  }

  async function openSop(sop: SopEntry) {
    setSelectedSopId(sop.id);
    setIsLoadingDetail(true);
    setSaveState("idle");
    try {
      const nextDetail = await getSopDetail(sop.id);
      setDetail(nextDetail);
      setDraft(nextDetail.content);
      setActiveTab("preview");
      setError("");
    } catch (loadError) {
      setDetail(null);
      setDraft("");
      setError(loadError instanceof Error ? loadError.message : "SOP 内容读取失败");
    } finally {
      setIsLoadingDetail(false);
    }
  }

  async function saveCurrentSop() {
    if (!selectedSopId || !detail || isSaving || !isDirty) {
      return;
    }
    setIsSaving(true);
    try {
      const nextDetail = await saveSopDetail(selectedSopId, draft);
      setDetail(nextDetail);
      setDraft(nextDetail.content);
      setSops((current) => current.map((sop) => (sop.id === nextDetail.item.id ? nextDetail.item : sop)));
      setSaveState("saved");
      setError("");
    } catch (saveError) {
      setSaveState("idle");
      setError(saveError instanceof Error ? saveError.message : "SOP 保存失败");
    } finally {
      setIsSaving(false);
    }
  }

  function clearPreview() {
    setSelectedSopId("");
    setDetail(null);
    setDraft("");
    setSaveState("idle");
  }

  function handleListResizePointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (!hasPreview || event.button !== 0) {
      return;
    }
    const workspace = workspaceRef.current;
    if (!workspace) {
      return;
    }
    const rect = workspace.getBoundingClientRect();
    event.preventDefault();
    resizeCleanupRef.current?.();
    setIsListResizing(true);

    const handlePointerMove = (moveEvent: PointerEvent) => {
      setSopListRatio(clampSopListRatio((moveEvent.clientX - rect.left) / rect.width));
    };

    const cleanup = () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", cleanup);
      window.removeEventListener("pointercancel", cleanup);
      setIsListResizing(false);
      resizeCleanupRef.current = null;
    };

    resizeCleanupRef.current = cleanup;
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", cleanup);
    window.addEventListener("pointercancel", cleanup);
  }

  return (
    <section
      aria-label="SOP 库"
      className={`sop-workspace ${hasPreview ? "has-preview" : ""} ${isListResizing ? "is-list-resizing" : ""}`}
      ref={workspaceRef}
      style={{ "--sop-list-ratio": String(sopListRatio) } as CSSProperties}
    >
      <motion.aside className="sop-library-panel" layout transition={{ damping: 26, stiffness: 280, type: "spring" }}>
        <div className="sop-library-head">
          <div>
            <h2>SOP 库</h2>
            <span>{sops.length} 个 SOP</span>
          </div>
          <Button
            aria-label="刷新 SOP 列表"
            className={`sop-refresh-button ${isLoadingList ? "is-loading" : ""}`}
            isIconOnly
            onPress={() => void loadSops()}
            size="sm"
            variant="ghost"
          >
            {isLoadingList ? <Loader2 size={15} /> : <RefreshCw size={15} />}
          </Button>
        </div>
        <div className="sop-library-search">
          <Search size={15} />
          <input
            aria-label="搜索 SOP"
            id="sop-library-search"
            name="sop-library-search"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索 SOP"
            value={query}
          />
        </div>
        {error ? <div className="sop-library-error">{error}</div> : null}
        {/* 这里使用原生列表，保证可变高度的 SOP 摘要按自然文档流排布。 */}
        <div aria-label="SOP 页面列表" className="sop-library-list" role="list">
          {filteredSops.map((sop) => (
            <motion.div
              animate={{ opacity: 1, y: 0 }}
              className="sop-library-row"
              exit={{ opacity: 0, y: 8 }}
              initial={{ opacity: 0, y: 8 }}
              key={sop.id}
              layout="position"
              role="listitem"
              transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            >
              <SopWorkspaceItem
                isSelected={sop.id === selectedSopId}
                onOpen={(nextSop) => void openSop(nextSop)}
                onPreview={(nextSop) => void openSop(nextSop)}
                sop={sop}
              />
            </motion.div>
          ))}
        </div>
        {filteredSops.length === 0 && !isLoadingList ? <div className="sop-library-empty">没有匹配的 SOP</div> : null}
      </motion.aside>

      <div
        aria-label="调整 SOP 列表宽度"
        aria-orientation="vertical"
        className="sop-list-resize-handle"
        onPointerDown={handleListResizePointerDown}
        role="separator"
      />

      <AnimatePresence mode="popLayout">
        {hasPreview ? (
          <motion.section
            animate={{ opacity: 1, x: 0 }}
            aria-label="SOP 预览内容"
            className="sop-editor-panel"
            exit={{ opacity: 0, x: 22 }}
            initial={{ opacity: 0, x: 28 }}
            key={selectedSopId}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          >
            <header className="sop-editor-head">
              <div className="sop-editor-title">
                <strong>{selectedSop?.title || selectedSop?.name || "SOP"}</strong>
                <code>{selectedSop?.path || ""}</code>
              </div>
              <div className="sop-editor-actions">
                {saveState === "saved" ? (
                  <span className="sop-save-state">
                    <Check size={13} />
                    已保存
                  </span>
                ) : null}
                <Button
                  className={`sop-save-button ${isSaving ? "is-loading" : ""}`}
                  isDisabled={!isDirty || isSaving || isLoadingDetail}
                  onPress={() => void saveCurrentSop()}
                  size="sm"
                  variant="secondary"
                >
                  {isSaving ? <Loader2 size={14} /> : <Save size={14} />}
                  保存
                </Button>
                <Button aria-label="关闭 SOP 预览" isIconOnly onPress={clearPreview} size="sm" variant="ghost">
                  <X size={15} />
                </Button>
              </div>
            </header>
            {isLoadingDetail ? (
              <div className="sop-editor-loading">
                <Loader2 size={16} />
                正在读取 SOP
              </div>
            ) : (
              <Tabs className="sop-editor-tabs" onSelectionChange={(key) => setActiveTab(String(key))} selectedKey={activeTab} variant="secondary">
                <Tabs.ListContainer>
                  <Tabs.List aria-label="SOP 查看模式">
                    <Tabs.Tab id="preview">
                      预览
                      <Tabs.Indicator />
                    </Tabs.Tab>
                    <Tabs.Tab id="edit">
                      编辑
                      <Tabs.Indicator />
                    </Tabs.Tab>
                  </Tabs.List>
                </Tabs.ListContainer>
                <Tabs.Panel className="sop-tab-panel" id="preview">
                  <div className="sop-markdown-preview">
                    <ReactMarkdown
                      components={{
                        a: ({ children, ...props }) => (
                          <a {...props} rel="noreferrer" target="_blank">
                            {children}
                          </a>
                        ),
                      }}
                      remarkPlugins={[remarkGfm]}
                    >
                      {draft || "这个 SOP 暂无内容。"}
                    </ReactMarkdown>
                  </div>
                </Tabs.Panel>
                <Tabs.Panel className="sop-tab-panel" id="edit">
                  <TextArea
                    aria-label="编辑 SOP Markdown"
                    className="sop-editor-textarea"
                    fullWidth
                    onChange={(event) => {
                      setDraft(event.target.value);
                      setSaveState("idle");
                    }}
                    rows={20}
                    value={draft}
                    variant="secondary"
                  />
                </Tabs.Panel>
              </Tabs>
            )}
          </motion.section>
        ) : (
          <motion.section
            animate={{ opacity: 1, scale: 1 }}
            aria-label="SOP 空状态"
            className="sop-empty-preview"
            exit={{ opacity: 0, scale: 0.98 }}
            initial={{ opacity: 0, scale: 0.98 }}
            key="empty"
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
          >
            <strong>选择一个 SOP</strong>
            <span>左侧列表支持搜索，打开后可在预览和编辑之间切换。</span>
          </motion.section>
        )}
      </AnimatePresence>
    </section>
  );
}
