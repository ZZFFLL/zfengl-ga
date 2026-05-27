import { Button, Chip } from "@heroui/react";
import { FileCode, FolderOpen, Info, Loader2, Menu, Search } from "lucide-react";
import { AnimatePresence, motion, useIsPresent } from "motion/react";
import { useEffect, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from "react";
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
  replayTurn,
  regenerateSessionTitle,
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
  findLatestHumanInteractionPrompt,
  mergeCompletedTurnIntoHistory,
  type HumanInteractionPrompt,
  type TurnState,
} from "./state";
import type { ArtifactRecord, ExecutionStep, ImageAttachment, MessageRecord, SessionRecord } from "./types";

const SIDEBAR_WIDTH_STORAGE_KEY = "genericagent.heroui.sidebarWidth";
const DEFAULT_SIDEBAR_WIDTH = 240;
const MIN_SIDEBAR_WIDTH = 220;
const MAX_SIDEBAR_WIDTH = 420;

function clampSidebarWidth(width: number) {
  return Math.max(MIN_SIDEBAR_WIDTH, Math.min(MAX_SIDEBAR_WIDTH, Math.round(width)));
}

function readStoredSidebarWidth() {
  if (typeof window === "undefined") {
    return DEFAULT_SIDEBAR_WIDTH;
  }
  try {
    const storedWidth = Number(window.localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY));
    return Number.isFinite(storedWidth) ? clampSidebarWidth(storedWidth) : DEFAULT_SIDEBAR_WIDTH;
  } catch {
    return DEFAULT_SIDEBAR_WIDTH;
  }
}

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
  const [sidebarWidth, setSidebarWidth] = useState(() => readStoredSidebarWidth());
  const [isSidebarResizing, setIsSidebarResizing] = useState(false);
  const [showBridgeDiagnostics, setShowBridgeDiagnostics] = useState(false);
  const [isSwitchingModelProfile, setIsSwitchingModelProfile] = useState(false);
  const [regeneratingTitleSessionId, setRegeneratingTitleSessionId] = useState("");
  const activeSourceRef = useRef<EventSource | null>(null);
  const activeSessionRef = useRef("");
  const activeTurnRef = useRef("");
  const activeTurnStateRef = useRef<TurnState | null>(null);
  // SSE 回调会持有创建时的闭包，完成归档时必须读取最新 transcript。
  const messagesRef = useRef<MessageRecord[]>([]);
  const timelineRef = useRef<ExecutionStep[]>([]);
  const artifactsRef = useRef<ArtifactRecord[]>([]);
  const isMountedRef = useRef(true);
  const shellRef = useRef<HTMLElement | null>(null);
  const sidebarResizeCleanupRef = useRef<(() => void) | null>(null);
  const bridgeDiagnosticsButtonRef = useRef<HTMLButtonElement | null>(null);
  const bridgeDiagnosticsPanelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    activeSessionRef.current = activeSessionId;
  }, [activeSessionId]);

  useEffect(() => {
    messagesRef.current = messages;
    timelineRef.current = timeline;
    artifactsRef.current = artifacts;
  }, [messages, timeline, artifacts]);

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
      sidebarResizeCleanupRef.current?.();
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    try {
      window.localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(sidebarWidth));
    } catch {
      // localStorage can be unavailable in restricted browser contexts.
    }
  }, [sidebarWidth]);

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
    if (!showBridgeDiagnostics) {
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
  }, [showBridgeDiagnostics]);

  useEffect(() => {
    return () => {
      sidebarResizeCleanupRef.current?.();
    };
  }, []);

  function openBridgeDiagnostics() {
    setShowBridgeDiagnostics(true);
  }

  function closeBridgeDiagnostics() {
    if (!showBridgeDiagnostics) {
      return;
    }
    setShowBridgeDiagnostics(false);
  }

  function toggleBridgeDiagnostics() {
    if (showBridgeDiagnostics) {
      closeBridgeDiagnostics();
      return;
    }
    openBridgeDiagnostics();
  }

  function handleSidebarResizePointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (sidebarCollapsed || event.button !== 0) {
      return;
    }
    const shell = shellRef.current;
    if (!shell) {
      return;
    }
    const shellRect = shell.getBoundingClientRect();
    event.preventDefault();
    sidebarResizeCleanupRef.current?.();
    setIsSidebarResizing(true);

    const handlePointerMove = (moveEvent: PointerEvent) => {
      setSidebarWidth(clampSidebarWidth(moveEvent.clientX - shellRect.left));
    };

    const cleanup = () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", cleanup);
      window.removeEventListener("pointercancel", cleanup);
      if (isMountedRef.current) {
        setIsSidebarResizing(false);
      }
      sidebarResizeCleanupRef.current = null;
    };

    sidebarResizeCleanupRef.current = cleanup;
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", cleanup);
    window.addEventListener("pointercancel", cleanup);
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
      if (!silent) {
        setAppError("");
      }
    } catch (error) {
      if (!silent) {
        throw error;
      }
    }
  }

  async function handleSwitchModelProfile(profileId: string) {
    if (!profileId || profileId === selectedProfileId || isSwitchingModelProfile) {
      return;
    }
    setIsSwitchingModelProfile(true);
    try {
      const profiles = await switchModelProfile(profileId, activeSessionId || undefined);
      // 切模型后以后端返回的最新 profile 列表为准，避免前端本地状态漂移。
      setModelProfiles(profiles);
      setSelectedProfileId(getActiveProfileId(profiles) || profileId);
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

  async function handleSubmit(content: string, images: ImageAttachment[] = [], displayContent?: string) {
    const sessionId = activeSessionId || (await createSessionForSubmit()).id;
    const startedAt = new Date().toISOString();
    const terminalTurn =
      activeTurnStateRef.current?.status === "done" || activeTurnStateRef.current?.status === "error"
        ? activeTurnStateRef.current
        : null;
    const history = terminalTurn
      ? mergeCompletedTurnIntoHistory(messages, timeline, artifacts, terminalTurn)
      : { messages, timeline, artifacts };
    const optimistic: MessageRecord = {
      role: "user",
      content: displayContent || content,
      created_at: new Date().toISOString(),
      agent_prompt: displayContent ? content : undefined,
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
      const turnId = await createTurn(sessionId, content, images, displayContent);
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
      activeTurnStateRef.current = createInitialTurnState(turnId, startedAt);
      setActiveTurn(activeTurnStateRef.current);
      activeSourceRef.current = subscribeTurn(turnId, (event) => {
        if (activeSessionRef.current !== sessionId || activeTurnRef.current !== turnId) {
          return;
        }
        const nextTurn = applyStreamEvent(activeTurnStateRef.current ?? createInitialTurnState(turnId, startedAt), event);
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
  const isRegeneratingActiveTitle = Boolean(
    activeSession && activeSessionId && regeneratingTitleSessionId === activeSessionId,
  );
  const activeModelProfile = modelProfiles.find((profile) => profile.active);
  const activeModelName = formatModelName(activeModelProfile);
  const modelLabel = activeModelName !== "未检测到生效模型" ? activeModelName : modelProfiles.length > 0 ? `${modelProfiles.length} 个模型配置` : "本地模型";
  const humanInteractionPrompt = findLatestHumanInteractionPrompt(messages, timeline, activeTurn);
  return (
    <main
      className={`chat-workbench-shell ${sidebarCollapsed ? "is-sidebar-collapsed" : ""} ${isSidebarResizing ? "is-sidebar-resizing" : ""}`}
      ref={shellRef}
      style={{ "--sidebar-width": `${sidebarWidth}px` } as CSSProperties}
    >
      <ConversationRail
        sessions={sessions}
        activeSessionId={activeSessionId}
        modelLabel={modelLabel}
        regeneratingSessionId={regeneratingTitleSessionId}
        onCreateSession={handleCreateSession}
        onDeleteSessions={handleDeleteSessions}
        onRegenerateSessionTitle={(sessionId) => void handleRegenerateSessionTitle(sessionId)}
        onSelectSession={handleSelectSession}
      />
      <div
        aria-label="调整会话列表宽度"
        aria-orientation="vertical"
        className="sidebar-resize-handle"
        onPointerDown={handleSidebarResizePointerDown}
        role="separator"
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
            {isRegeneratingActiveTitle ? (
              <span className="conversation-title-status">
                <Loader2 size={12} />
                正在生成标题…
              </span>
            ) : null}
          </div>
          <div className="header-actions">
            <div className="bridge-meta-strip" aria-label="HeroBridge 状态">
              <Chip color={bridgeStatus?.ready ? "success" : "warning"} size="sm" variant="soft">
                <Chip.Label title={bridgeStatus?.ready ? "已连接" : "连接中"}>HeroBridge</Chip.Label>
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
          <AnimatePresence initial={false}>
            {showBridgeDiagnostics ? (
              <motion.div
                animate={{ opacity: 1, scale: 1, y: 0 }}
                aria-label="Bridge 诊断面板"
                className="bridge-diagnostics-panel"
                exit={{ opacity: 0, scale: 0.96, y: -10 }}
                initial={{ opacity: 0, scale: 0.96, y: -12 }}
                ref={bridgeDiagnosticsPanelRef}
                transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
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
              </motion.div>
            ) : null}
          </AnimatePresence>
        </header>
        {appError ? <div className="app-error">{appError}</div> : null}
        <ChatSurface
          activeTurn={activeTurn}
          artifacts={artifacts}
          isLoadingMessages={isLoadingMessages}
          messages={messages}
          onReplayTurn={(message) => void handleReplayTurn(message)}
          sessionTitle={activeSession?.title ?? "新会话"}
          timeline={timeline}
        />
        <div className="composer-stack">
          <HumanInteractionPromptPanel humanInteractionPrompt={humanInteractionPrompt} onAskUserChoice={(choice) => void handleSubmit(choice)} />
          <Composer
            disabled={activeTurn?.status === "streaming"}
            modelProfiles={modelProfiles}
            onCancel={handleCancelTurn}
            onModelProfileSelect={handleSwitchModelProfile}
            onSubmit={handleSubmit}
            selectedProfileId={selectedProfileId}
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
      const history = mergeCompletedTurnIntoHistory(messagesRef.current, timelineRef.current, artifactsRef.current, completedTurn);
      messagesRef.current = history.messages;
      timelineRef.current = history.timeline;
      artifactsRef.current = history.artifacts;
      setMessages(history.messages);
      setTimeline(history.timeline);
      setArtifacts(history.artifacts);
      setActiveTurn(null);
      activeTurnStateRef.current = null;
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

  async function handleRegenerateSessionTitle(sessionId: string) {
    try {
      setRegeneratingTitleSessionId(sessionId);
      const updated = await regenerateSessionTitle(sessionId);
      setSessions((current) =>
        current.map((session) =>
          session.id === updated.id
            ? {
                ...session,
                title: updated.title,
                updated_at: updated.updated_at,
              }
            : session,
        ),
      );
      if (activeSessionId === updated.id) {
        setMessages((current) => [...current]);
      }
      setAppError("");
      void refreshSessions();
    } catch (error) {
      setAppError(readError(error));
    } finally {
      setRegeneratingTitleSessionId((current) => (current === sessionId ? "" : current));
    }
  }

  async function handleReplayTurn(message: MessageRecord) {
    if (activeTurn?.status === "streaming") {
      return;
    }
    if (!activeSessionId) {
      setAppError("当前没有可重答的会话");
      return;
    }
    const turnId = message.turn_id || "";
    if (!turnId) {
      setAppError("未找到可重新回答的本轮提问");
      return;
    }
    try {
      closeActiveSource(activeSourceRef.current);
      activeSourceRef.current = null;
      activeTurnRef.current = "";
      activeTurnStateRef.current = null;
      setAppError("");

      const replayedTurnId = await replayTurn(activeSessionId, turnId);
      const startedAt = new Date().toISOString();
      const trimmedTranscript = await listTranscript(activeSessionId);
      if (activeSessionRef.current !== activeSessionId) {
        return;
      }
      setMessages(trimmedTranscript.messages);
      setTimeline(trimmedTranscript.timeline);
      setArtifacts(trimmedTranscript.artifacts);
      activeTurnRef.current = replayedTurnId;
      activeTurnStateRef.current = createInitialTurnState(replayedTurnId, startedAt);
      setActiveTurn(activeTurnStateRef.current);
      activeSourceRef.current = subscribeTurn(replayedTurnId, (event) => {
        if (activeSessionRef.current !== activeSessionId || activeTurnRef.current !== replayedTurnId) {
          return;
        }
        const nextTurn = applyStreamEvent(activeTurnStateRef.current ?? createInitialTurnState(replayedTurnId, startedAt), event);
        activeTurnStateRef.current = nextTurn;
        setActiveTurn(nextTurn);
        if (event.type === "turn.done") {
          finishActiveTurn(activeSessionId, replayedTurnId);
        }
      }, () => {
        if (activeSessionRef.current === activeSessionId && activeTurnRef.current === replayedTurnId) {
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
}

function HumanInteractionPromptPanel({
  humanInteractionPrompt: prompt,
  onAskUserChoice,
}: {
  humanInteractionPrompt: HumanInteractionPrompt | null;
  onAskUserChoice: (choice: string) => void;
}) {
  const activePrompt = prompt && !prompt.disabled ? prompt : null;
  const candidates = activePrompt?.interaction.candidates.filter((candidate) => candidate.trim()) ?? [];

  return (
    // 交给 Motion 播放退出动画后再卸载，避免手写计时器和面板状态漂移。
    <AnimatePresence initial={false}>
      {activePrompt && candidates.length > 0 ? (
        <HumanInteractionPromptCard
          candidates={candidates}
          key={activePrompt.stepId}
          onAskUserChoice={onAskUserChoice}
          prompt={activePrompt}
        />
      ) : null}
    </AnimatePresence>
  );
}

function HumanInteractionPromptCard({
  candidates,
  onAskUserChoice,
  prompt,
}: {
  candidates: string[];
  onAskUserChoice: (choice: string) => void;
  prompt: HumanInteractionPrompt;
}) {
  const isPresent = useIsPresent();

  return (
    <motion.div
      animate={{ opacity: 1, y: 0 }}
      aria-hidden={isPresent ? undefined : true}
      aria-label="ask_user 待选回复"
      className="ask-user-panel composer-ask-user-panel"
      exit={{ opacity: 0, scale: 0.96, y: 14 }}
      initial={{ opacity: 0, scale: 0.96, y: 18 }}
      transition={{ damping: 22, mass: 0.8, stiffness: 260, type: "spring" }}
    >
      {prompt.interaction.question ? <div className="ask-user-question">{prompt.interaction.question}</div> : null}
      <div className="ask-user-choice-list" aria-label="可选回复">
        {candidates.map((candidate) => (
          <Button
            className="ask-user-choice"
            isDisabled={!isPresent}
            key={candidate}
            onPress={() => onAskUserChoice(candidate)}
            size="sm"
            variant="secondary"
          >
            {candidate}
          </Button>
        ))}
      </div>
    </motion.div>
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
