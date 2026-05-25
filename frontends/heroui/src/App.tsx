import { Button, Chip } from "@heroui/react";
import { FileCode, FolderOpen, Info, Menu, Search } from "lucide-react";
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
  findLatestHumanInteractionPrompt,
  mergeCompletedTurnIntoHistory,
  type HumanInteractionPrompt,
  type TurnState,
} from "./state";
import type { ArtifactRecord, ExecutionStep, ImageAttachment, MessageRecord, SessionRecord } from "./types";

const PROMPT_PANEL_ANIMATION_MS = 180;

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
  const [isSwitchingModelProfile, setIsSwitchingModelProfile] = useState(false);
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
  const humanInteractionPrompt = findLatestHumanInteractionPrompt(messages, timeline, activeTurn);
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
          artifacts={artifacts}
          isLoadingMessages={isLoadingMessages}
          messages={messages}
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

function HumanInteractionPromptPanel({
  humanInteractionPrompt: prompt,
  onAskUserChoice,
}: {
  humanInteractionPrompt: HumanInteractionPrompt | null;
  onAskUserChoice: (choice: string) => void;
}) {
  const [promptState, setPromptState] = useState<{
    prompt: HumanInteractionPrompt;
    stage: "entering" | "visible" | "exiting";
  } | null>(null);
  const animationTimerRef = useRef<number | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const activePrompt = prompt && !prompt.disabled ? prompt : null;

  useEffect(() => {
    if (animationTimerRef.current !== null) {
      window.clearTimeout(animationTimerRef.current);
      animationTimerRef.current = null;
    }
    if (animationFrameRef.current !== null) {
      window.cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }

    if (activePrompt) {
      setPromptState({ prompt: activePrompt, stage: "entering" });
      animationFrameRef.current = window.requestAnimationFrame(() => {
        setPromptState((current) =>
          current?.prompt.stepId === activePrompt.stepId ? { ...current, stage: "visible" } : current,
        );
        animationFrameRef.current = null;
      });
      return;
    }

    setPromptState((current) => (current ? { ...current, stage: "exiting" } : null));
    animationTimerRef.current = window.setTimeout(() => {
      setPromptState(null);
      animationTimerRef.current = null;
    }, PROMPT_PANEL_ANIMATION_MS);
  }, [activePrompt?.stepId, activePrompt?.interaction.question, activePrompt?.interaction.candidates.join("\u0000")]);

  useEffect(
    () => () => {
      if (animationTimerRef.current !== null) {
        window.clearTimeout(animationTimerRef.current);
      }
      if (animationFrameRef.current !== null) {
        window.cancelAnimationFrame(animationFrameRef.current);
      }
    },
    [],
  );

  if (!promptState) {
    return null;
  }
  const candidates = promptState.prompt.interaction.candidates.filter((candidate) => candidate.trim());
  if (candidates.length === 0) {
    return null;
  }
  const panelClassName = [
    "ask-user-panel",
    "composer-ask-user-panel",
    promptState.stage === "entering" ? "ask-user-panel--enter" : "",
    promptState.stage === "exiting" ? "ask-user-panel--exit" : "",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div
      aria-hidden={promptState.stage === "exiting" ? true : undefined}
      aria-label="ask_user 待选回复"
      className={panelClassName}
    >
      {promptState.prompt.interaction.question ? <div className="ask-user-question">{promptState.prompt.interaction.question}</div> : null}
      <div className="ask-user-choice-list" aria-label="可选回复">
        {candidates.map((candidate) => (
          <Button
            className="ask-user-choice"
            isDisabled={promptState.stage === "exiting"}
            key={candidate}
            onPress={() => onAskUserChoice(candidate)}
            size="sm"
            variant="secondary"
          >
            {candidate}
          </Button>
        ))}
      </div>
    </div>
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
