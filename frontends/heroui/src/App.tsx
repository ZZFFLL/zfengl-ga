import { Button, Chip } from "@heroui/react";
import { Menu, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
  createSession,
  createTurn,
  deleteSessions,
  getBridgeStatus,
  listModelProfiles,
  listSessions,
  listTranscript,
  subscribeTurn,
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
import type { ArtifactRecord, ExecutionStep, MessageRecord, SessionRecord } from "./types";

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
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const activeSourceRef = useRef<EventSource | null>(null);
  const activeSessionRef = useRef("");
  const activeTurnRef = useRef("");
  const activeTurnStateRef = useRef<TurnState | null>(null);

  useEffect(() => {
    activeSessionRef.current = activeSessionId;
  }, [activeSessionId]);

  useEffect(() => {
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
        void refreshBridgeMetadata();
      } catch (error) {
        if (!cancelled) {
          setAppError(readError(error));
        }
      }
    }

    async function refreshBridgeMetadata() {
      try {
        const [status, profiles] = await Promise.all([getBridgeStatus(), listModelProfiles()]);
        if (cancelled) {
          return;
        }
        setBridgeStatus(status);
        setModelProfiles(profiles);
      } catch {
        // Optional GA metadata should not block session restoration.
      }
    }

    void boot();
    return () => {
      cancelled = true;
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

  async function handleSubmit(content: string) {
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
      const turnId = await createTurn(sessionId, content);
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
  const modelLabel = activeModelProfile?.name ?? (modelProfiles.length > 0 ? `${modelProfiles.length} 个模型配置` : "本地模型");
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
            <Button size="sm" variant="tertiary">
              <Search size={16} />
              搜索
            </Button>
          </div>
        </header>
        {appError ? <div className="app-error">{appError}</div> : null}
        <ChatSurface
          activeTurn={activeTurn}
          artifacts={activeTurn ? [] : artifacts}
          isLoadingMessages={isLoadingMessages}
          messages={messages}
          timeline={activeTurn ? [] : timeline}
        />
        <Composer
          disabled={activeTurn?.status === "streaming"}
          onSubmit={handleSubmit}
        />
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

function readError(error: unknown): string {
  return error instanceof Error ? error.message : "发生了未知错误";
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
