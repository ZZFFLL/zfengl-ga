import { Button, Chip, ListBox, Select, type Key } from "@heroui/react";
import { FileCode, FolderOpen, Info, Menu, RefreshCcw, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
  cancelSession,
  createSession,
  createTurn,
  deleteSessions,
  getBridgeStatus,
  listModelProfiles,
  listSessions,
  listTranscript,
  openBridgePath,
  subscribeTurn,
  switchModelProfile,
  type BridgeStatus,
  type ModelProfile,
} from "./api";
import { ChatSurface } from "./components/ChatSurface";
import { Composer } from "./components/Composer";
import { ConversationRail } from "./components/ConversationRail";
import {
  applyStreamEvent,
  createInitialTurnState,
  mergeCompletedTurnIntoHistory,
  type TurnState,
} from "./state";
import type { ArtifactRecord, ExecutionStep, ImageAttachment, MessageRecord, SessionRecord } from "./types";

export function App() {
  const [sessions, setSessions] = useState<SessionRecord[]>([]);
  const [activeSessionId, setActiveSessionId] = useState("");
  const [messages, setMessages] = useState<MessageRecord[]>([]);
  const [timeline, setTimeline] = useState<ExecutionStep[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactRecord[]>([]);
  const [activeTurn, setActiveTurn] = useState<TurnState | null>(null);
  const [appError, setAppError] = useState("");
  const [bridgeStatus, setBridgeStatus] = useState<BridgeStatus | null>(null);
  const [modelProfiles, setModelProfiles] = useState<ModelProfile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState("");
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [showBridgeDiagnostics, setShowBridgeDiagnostics] = useState(false);
  const [isBridgeDiagnosticsClosing, setIsBridgeDiagnosticsClosing] = useState(false);
  const [isReloadingBridgeMetadata, setIsReloadingBridgeMetadata] = useState(false);
  const [isSwitchingModelProfile, setIsSwitchingModelProfile] = useState(false);
  const [bridgeMetadataReloadedAt, setBridgeMetadataReloadedAt] = useState("");
  const activeSourceRef = useRef<EventSource | null>(null);
  const activeSessionRef = useRef("");
  const activeTurnRef = useRef("");
  const activeTurnStateRef = useRef<TurnState | null>(null);
  const isMountedRef = useRef(true);
  const bridgeDiagnosticsButtonRef = useRef<HTMLButtonElement | null>(null);
  const bridgeDiagnosticsPanelRef = useRef<HTMLDivElement | null>(null);
  const bridgeDiagnosticsCloseTimerRef = useRef<number | null>(null);

  useEffect(() => {
    activeSessionRef.current = activeSessionId;
  }, [activeSessionId]);

  useEffect(() => {
    isMountedRef.current = true;
    let cancelled = false;

    async function boot() {
      try {
        const existing = await listSessions();
        if (cancelled) {
          return;
        }
        if (existing.length > 0) {
          setSessions(existing);
          setActiveSessionId(existing[0].id);
        } else {
          setSessions([]);
          setActiveSessionId("");
        }
        void refreshBridgeMetadata({ silent: true });
      } catch (error) {
        if (!cancelled) {
          setAppError(readError(error));
        }
      }
    }

    void boot();
    return () => {
      cancelled = true;
      isMountedRef.current = false;
      closeActiveSource(activeSourceRef.current);
    };
  }, []);

  useEffect(() => {
    if (!activeSessionId) {
      setIsLoadingMessages(false);
      return;
    }
    let cancelled = false;

    async function loadTranscript() {
      setIsLoadingMessages(true);
      try {
        const transcript = await listTranscript(activeSessionId);
        if (!cancelled) {
          setMessages(transcript.messages);
          setTimeline(transcript.timeline);
          setArtifacts(transcript.artifacts);
          setIsLoadingMessages(false);
        }
      } catch (error) {
        if (!cancelled) {
          setAppError(readError(error));
          setIsLoadingMessages(false);
        }
      }
    }

    void loadTranscript();
    return () => {
      cancelled = true;
    };
  }, [activeSessionId]);

  useEffect(() => {
    if (!showBridgeDiagnostics || isBridgeDiagnosticsClosing) {
      return;
    }

    function handlePointerDown(event: PointerEvent) {
      const target = event.target;
      if (!(target instanceof Node)) {
        return;
      }
      if (bridgeDiagnosticsPanelRef.current?.contains(target) || bridgeDiagnosticsButtonRef.current?.contains(target)) {
        return;
      }
      closeBridgeDiagnostics();
    }

    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [showBridgeDiagnostics, isBridgeDiagnosticsClosing]);

  useEffect(() => {
    return () => {
      if (bridgeDiagnosticsCloseTimerRef.current !== null) {
        window.clearTimeout(bridgeDiagnosticsCloseTimerRef.current);
      }
    };
  }, []);

  function openBridgeDiagnostics() {
    if (bridgeDiagnosticsCloseTimerRef.current !== null) {
      window.clearTimeout(bridgeDiagnosticsCloseTimerRef.current);
      bridgeDiagnosticsCloseTimerRef.current = null;
    }
    setIsBridgeDiagnosticsClosing(false);
    setShowBridgeDiagnostics(true);
  }

  function closeBridgeDiagnostics() {
    if (!showBridgeDiagnostics || isBridgeDiagnosticsClosing) {
      return;
    }
    setIsBridgeDiagnosticsClosing(true);
    bridgeDiagnosticsCloseTimerRef.current = window.setTimeout(() => {
      setShowBridgeDiagnostics(false);
      setIsBridgeDiagnosticsClosing(false);
      bridgeDiagnosticsCloseTimerRef.current = null;
    }, 160);
  }

  function toggleBridgeDiagnostics() {
    if (showBridgeDiagnostics && !isBridgeDiagnosticsClosing) {
      closeBridgeDiagnostics();
      return;
    }
    openBridgeDiagnostics();
  }

  async function refreshBridgeMetadata({ silent = false }: { silent?: boolean } = {}) {
    try {
      const [status, profiles] = await Promise.all([getBridgeStatus(), listModelProfiles()]);
      if (!isMountedRef.current) {
        return;
      }
      setBridgeStatus(status);
      setModelProfiles(profiles);
      setSelectedProfileId(getActiveProfileId(profiles));
      setBridgeMetadataReloadedAt(formatMetadataReloadTime(new Date()));
      if (!silent) {
        setAppError("");
      }
    } catch (error) {
      if (!silent) {
        throw error;
      }
    }
  }

  async function handleReloadBridgeMetadata() {
    if (isReloadingBridgeMetadata) {
      return;
    }
    setIsReloadingBridgeMetadata(true);
    try {
      await refreshBridgeMetadata();
    } catch (error) {
      setAppError(readError(error));
    } finally {
      setIsReloadingBridgeMetadata(false);
    }
  }

  async function handleSwitchModelProfile(profileId: string) {
    if (!profileId || profileId === selectedProfileId || isSwitchingModelProfile) {
      return;
    }
    setIsSwitchingModelProfile(true);
    try {
      const profiles = await switchModelProfile(profileId, activeSessionId || undefined);
      setModelProfiles(profiles);
      setSelectedProfileId(getActiveProfileId(profiles) || profileId);
      setBridgeMetadataReloadedAt(formatMetadataReloadTime(new Date()));
      setAppError("");
    } catch (error) {
      setAppError(readError(error));
    } finally {
      setIsSwitchingModelProfile(false);
    }
  }

  async function handleCreateSession() {
    if (activeSessionId && messages.length === 0 && (!activeTurn || activeTurn.status !== "streaming")) {
      setAppError("");
      return;
    }
    try {
      const session = await createSession("新会话");
      setSessions((current) => [session, ...current]);
      setActiveSessionId(session.id);
      setMessages([]);
      setTimeline([]);
      setArtifacts([]);
      setActiveTurn(null);
      setIsLoadingMessages(false);
      setAppError("");
      closeActiveSource(activeSourceRef.current);
      activeTurnRef.current = "";
      activeTurnStateRef.current = null;
      activeSourceRef.current = null;
    } catch (error) {
      setAppError(readError(error));
    }
  }

  function handleSelectSession(sessionId: string) {
    if (sessionId === activeSessionId) {
      setAppError("");
      return;
    }
    closeActiveSource(activeSourceRef.current);
    activeTurnRef.current = "";
    activeTurnStateRef.current = null;
    activeSourceRef.current = null;
    setActiveSessionId(sessionId);
    setMessages([]);
    setTimeline([]);
    setArtifacts([]);
    setActiveTurn(null);
    setIsLoadingMessages(true);
    setAppError("");
  }

  async function handleSubmit(content: string, images: ImageAttachment[] = []) {
    const sessionId = activeSessionId || (await createSessionForSubmit()).id;
    const terminalTurn =
      activeTurnStateRef.current?.status === "done" || activeTurnStateRef.current?.status === "error"
        ? activeTurnStateRef.current
        : null;
    const history = terminalTurn
      ? mergeCompletedTurnIntoHistory(messages, timeline, artifacts, terminalTurn)
      : { messages, timeline, artifacts };
    const optimistic: MessageRecord = {
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    setMessages([...history.messages, optimistic]);
    setTimeline(history.timeline);
    setArtifacts(history.artifacts);
    if (terminalTurn) {
      setActiveTurn(null);
      activeTurnStateRef.current = null;
    }
    setAppError("");

    try {
      closeActiveSource(activeSourceRef.current);
      const turnId = await createTurn(sessionId, content, images);
      if (activeSessionRef.current !== sessionId) {
        return;
      }
      setMessages((current) =>
        current.map((message) =>
          message.created_at === optimistic.created_at && message.role === "user" && message.content === optimistic.content
            ? { ...message, turn_id: turnId }
            : message,
        ),
      );
      activeTurnRef.current = turnId;
      activeTurnStateRef.current = createInitialTurnState(turnId);
      setActiveTurn(activeTurnStateRef.current);
      activeSourceRef.current = subscribeTurn(turnId, (event) => {
        if (activeSessionRef.current !== sessionId || activeTurnRef.current !== turnId) {
          return;
        }
        const nextTurn = applyStreamEvent(activeTurnStateRef.current ?? createInitialTurnState(turnId), event);
        activeTurnStateRef.current = nextTurn;
        setActiveTurn(nextTurn);
        if (event.type === "turn.done") {
          finishActiveTurn(sessionId, turnId);
        }
      }, () => {
        if (activeSessionRef.current === sessionId && activeTurnRef.current === turnId) {
          setAppError("会话流连接已中断");
          setActiveTurn(null);
          activeTurnRef.current = "";
          activeTurnStateRef.current = null;
          activeSourceRef.current = null;
        }
      });
    } catch (error) {
      setAppError(readError(error));
      setActiveTurn(null);
    }
  }

  async function handleCancelTurn() {
    if (!activeSessionId) {
      return;
    }
    try {
      await cancelSession(activeSessionId);
      closeActiveSource(activeSourceRef.current);
      activeTurnRef.current = "";
      activeTurnStateRef.current = null;
      activeSourceRef.current = null;
      setActiveTurn(null);
      setAppError("");
      await loadActiveTranscript(activeSessionId);
    } catch (error) {
      setAppError(readError(error));
    }
  }

  async function loadActiveTranscript(sessionId: string) {
    const transcript = await listTranscript(sessionId);
    if (activeSessionRef.current !== sessionId) {
      return;
    }
    setMessages(transcript.messages);
    setTimeline(transcript.timeline);
    setArtifacts(transcript.artifacts);
    setIsLoadingMessages(false);
  }

  async function handleOpenBridgePath(kind: "config" | "root") {
    try {
      await openBridgePath({ path: kind === "config" ? getMykeyPyPath(bridgeStatus) : bridgeStatus?.gaRoot });
      setAppError("");
    } catch (error) {
      setAppError(readError(error));
    }
  }

  async function handleDeleteSessions(sessionIds: string[]) {
    if (sessionIds.length === 0) {
      return;
    }
    const activeWasDeleted = sessionIds.includes(activeSessionId);
    try {
      if (activeWasDeleted) {
        closeActiveSource(activeSourceRef.current);
        activeTurnRef.current = "";
        activeTurnStateRef.current = null;
        activeSourceRef.current = null;
      }
      const nextSessions = await deleteSessions(sessionIds);
      const nextActiveId = nextSessions.some((session) => session.id === activeSessionId)
        ? activeSessionId
        : (nextSessions[0]?.id ?? "");
      setSessions(nextSessions);
      setActiveSessionId(nextActiveId);
      setMessages(activeWasDeleted ? [] : messages);
      setTimeline(activeWasDeleted ? [] : timeline);
      setArtifacts(activeWasDeleted ? [] : artifacts);
      setActiveTurn((current) => (activeWasDeleted ? null : current));
      setIsLoadingMessages(activeWasDeleted && Boolean(nextActiveId));
      setAppError("");
    } catch (error) {
      setAppError(readError(error));
    }
  }

  const activeSession = sessions.find((session) => session.id === activeSessionId);
  const activeModelProfile = modelProfiles.find((profile) => profile.active);
  const activeModelName = formatModelName(activeModelProfile);
  const modelLabel = activeModelName !== "未检测到生效模型" ? activeModelName : modelProfiles.length > 0 ? `${modelProfiles.length} 个模型配置` : "本地模型";
  return (
    <main className={`chat-workbench-shell ${sidebarCollapsed ? "is-sidebar-collapsed" : ""}`}>
      <ConversationRail
        sessions={sessions}
        activeSessionId={activeSessionId}
        modelLabel={modelLabel}
        onCreateSession={handleCreateSession}
        onDeleteSessions={handleDeleteSessions}
        onSelectSession={handleSelectSession}
      />
      <section className="conversation-main" aria-label="GenericAgent 智能工作台">
        <header className="conversation-header">
          <Button
            aria-label={sidebarCollapsed ? "展开侧栏" : "折叠侧栏"}
            className="header-menu"
            isIconOnly
            onPress={() => setSidebarCollapsed((current) => !current)}
            variant="tertiary"
          >
            <Menu size={18} />
          </Button>
          <div className="conversation-title">
            <h1>{formatChineseTitle(activeSession?.title ?? "新会话")}</h1>
            <span>{activeTurn?.status === "streaming" ? "正在流式输出" : "已就绪"}</span>
          </div>
          <div className="header-actions">
            <div className="bridge-meta-strip" aria-label="GA Bridge 状态">
              <Chip color={bridgeStatus?.ready ? "success" : "warning"} size="sm" variant="soft">
                <Chip.Label>GA Bridge</Chip.Label>
              </Chip>
              <Chip color="accent" size="sm" variant="soft">
                <Chip.Label>持久化</Chip.Label>
              </Chip>
              <Chip size="sm" variant="secondary">
                <Chip.Label>{sessions.length} 会话</Chip.Label>
              </Chip>
            </div>
            <Button
              aria-label="Bridge 诊断"
              className="bridge-diagnostics-button"
              isIconOnly
              onPress={toggleBridgeDiagnostics}
              ref={bridgeDiagnosticsButtonRef}
              size="sm"
              variant="tertiary"
            >
              <Info size={16} />
            </Button>
            <Button size="sm" variant="tertiary">
              <Search size={16} />
              搜索
            </Button>
          </div>
          {showBridgeDiagnostics || isBridgeDiagnosticsClosing ? (
            <div
              className={`bridge-diagnostics-panel ${isBridgeDiagnosticsClosing ? "bridge-diagnostics-panel--closing" : ""}`}
              aria-label="Bridge 诊断面板"
              ref={bridgeDiagnosticsPanelRef}
            >
              <div className="bridge-diagnostics-summary">
                <span>GA 根目录</span>
                <code>{bridgeStatus?.gaRoot ?? "未连接"}</code>
              </div>
              <BridgeConfigDetails activeProfile={activeModelProfile} profiles={modelProfiles} status={bridgeStatus} />
              <div className="bridge-diagnostics-actions">
                <Button className="bridge-open-button" onPress={() => handleOpenBridgePath("root")} size="sm" variant="secondary">
                  <FolderOpen size={15} />
                  打开 GA 根目录
                </Button>
                <Button className="bridge-open-button" onPress={() => handleOpenBridgePath("config")} size="sm" variant="secondary">
                  <FileCode size={15} />
                  打开 mykey.py
                </Button>
              </div>
            </div>
          ) : null}
        </header>
        {appError ? <div className="app-error">{appError}</div> : null}
        <ChatSurface
          activeTurn={activeTurn}
          artifacts={activeTurn ? [] : artifacts}
          isLoadingMessages={isLoadingMessages}
          messages={messages}
          timeline={activeTurn ? [] : timeline}
        />
        <div className="composer-stack">
          <div className="model-hot-reload-bar" aria-label="热加载配置与生效模型">
            <div className="model-hot-reload-copy">
              <span>生效模型</span>
              <strong title={activeModelName}>{activeModelName}</strong>
            </div>
            <div className="model-hot-reload-actions">
              <ModelProfileSwitch
                disabled={activeTurn?.status === "streaming" || isSwitchingModelProfile}
                profiles={modelProfiles}
                selectedProfileId={selectedProfileId}
                onProfileSelect={handleSwitchModelProfile}
              />
              <span>{bridgeMetadataReloadedAt ? `已热加载 ${bridgeMetadataReloadedAt}` : "读取 GA mykey 配置"}</span>
              <Button
                className="model-hot-reload-button"
                isDisabled={isReloadingBridgeMetadata}
                onPress={handleReloadBridgeMetadata}
                size="sm"
                variant="secondary"
              >
                <RefreshCcw size={14} />
                {isReloadingBridgeMetadata ? "热加载中" : "热加载配置"}
              </Button>
            </div>
          </div>
          <Composer
            disabled={activeTurn?.status === "streaming"}
            onCancel={handleCancelTurn}
            onSubmit={handleSubmit}
          />
        </div>
      </section>
    </main>
  );

  function finishActiveTurn(sessionId: string, turnId: string) {
    if (activeSessionRef.current !== sessionId || activeTurnRef.current !== turnId) {
      return;
    }
    const completedTurn = activeTurnStateRef.current;
    if (completedTurn) {
      setActiveTurn(completedTurn);
    }
    closeActiveSource(activeSourceRef.current);
    activeTurnRef.current = "";
    activeSourceRef.current = null;

    void refreshSessions();
  }

  async function refreshSessions() {
    try {
      setSessions(await listSessions());
    } catch {
      // Message rendering should stay stable even if the sidebar refresh fails.
    }
  }

  async function createSessionForSubmit() {
    const session = await createSession("新会话");
    setSessions((current) => [session, ...current]);
    setActiveSessionId(session.id);
    activeSessionRef.current = session.id;
    setTimeline([]);
    setArtifacts([]);
    setIsLoadingMessages(false);
    return session;
  }
}

function ModelProfileSwitch({
  disabled,
  onProfileSelect,
  profiles,
  selectedProfileId,
}: {
  disabled: boolean;
  onProfileSelect: (profileId: string) => void;
  profiles: ModelProfile[];
  selectedProfileId: string;
}) {
  function handleChange(value: Key | Key[] | null) {
    const next = Array.isArray(value) ? value[0] : value;
    if (next !== null && next !== undefined) {
      onProfileSelect(String(next));
    }
  }

  return (
    <Select
      aria-label="切换生效模型"
      className="profile-switch"
      isDisabled={disabled || profiles.length === 0}
      onChange={handleChange}
      placeholder="选择模型"
      value={selectedProfileId || null}
      variant="secondary"
    >
      <Select.Trigger>
        <Select.Value />
        <Select.Indicator />
      </Select.Trigger>
      <Select.Popover>
        <ListBox>
          {profiles.map((profile) => (
            <ListBox.Item id={String(profile.id)} key={profile.id} textValue={formatProfileOption(profile)}>
              {formatProfileOption(profile)}
              <ListBox.ItemIndicator />
            </ListBox.Item>
          ))}
        </ListBox>
      </Select.Popover>
    </Select>
  );
}

function readError(error: unknown): string {
  return error instanceof Error ? error.message : "发生了未知错误";
}

function BridgeConfigDetails({
  activeProfile,
  profiles,
  status,
}: {
  activeProfile: ModelProfile | undefined;
  profiles: ModelProfile[];
  status: BridgeStatus | null;
}) {
  const rows = [
    { label: "生效模型", value: formatModelName(activeProfile), detail: formatProfileName(activeProfile) },
    { label: "配置来源", value: "mykey.py", detail: activeProfile ? `profile id: ${activeProfile.id}` : "请热加载配置后重试" },
    { label: "HTTP 接口", value: status?.transport?.http ? "已启用" : "未确认", detail: "/status, /sessions, /session/*" },
    { label: "事件通道", value: status?.transport?.wsEventsOnly ? "仅事件" : "未启用", detail: status?.transport?.wsEventsOnly ? "/ws" : "当前使用 HTTP 轮询聊天" },
    { label: "可用 Profile", value: `${profiles.length} 个`, detail: formatProfileList(profiles) },
  ];

  return (
    <section className="bridge-config-details" aria-label="配置项详情">
      <strong>Bridge 配置</strong>
      <div className="bridge-config-grid">
        {rows.map((row) => (
          <div className="bridge-config-item" key={row.label}>
            <span>{row.label}</span>
            <b>{row.value}</b>
            <code>{row.detail}</code>
          </div>
        ))}
      </div>
    </section>
  );
}

function closeActiveSource(source: EventSource | null) {
  source?.close();
}

function formatChineseTitle(title: string): string {
  if (/^(new|first) chat$/i.test(title)) {
    return "新会话";
  }
  return title;
}

function formatMetadataReloadTime(date: Date): string {
  return date.toLocaleTimeString("zh-CN", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatModelName(profile: ModelProfile | undefined): string {
  return profile?.model?.trim() || profile?.name?.trim() || "未检测到生效模型";
}

function formatProfileName(profile: ModelProfile | undefined): string {
  return profile?.name?.trim() || "未检测到 active profile";
}

function formatProfileList(profiles: ModelProfile[]): string {
  if (profiles.length === 0) {
    return "暂无 profile";
  }
  return profiles.map((profile) => `${profile.active ? "active: " : ""}${profile.name}`).join(" / ");
}

function formatProfileOption(profile: ModelProfile): string {
  return profile.model?.trim() ? `${profile.name} / ${profile.model}` : profile.name;
}

function getActiveProfileId(profiles: ModelProfile[]): string {
  return String(profiles.find((profile) => profile.active)?.id ?? "");
}

function getMykeyPyPath(status: BridgeStatus | null): string | undefined {
  const root = status?.gaRoot?.replace(/[\\/]+$/, "");
  return root ? `${root}\\mykey.py` : undefined;
}
