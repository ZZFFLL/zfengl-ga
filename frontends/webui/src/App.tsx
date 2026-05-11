import { CSSProperties, FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { App as AntApp, ConfigProvider, Drawer, Input, Layout, Splitter } from "antd";
import {
  abortTask,
  activateConversation,
  continueConversation,
  createConversation,
  createGroup,
  deleteConversation,
  deleteGroup,
  fetchConversation,
  fetchState,
  pinConversation,
  reinject,
  renameConversation,
  renameGroup,
  setAutonomous,
  startChat,
  streamTask,
  switchLlm,
} from "./api";
import type {
  ConversationDetail,
  ConversationSummary,
  ExecutionTurn,
  GroupSummary,
  RuntimeState,
  StreamEvent,
  UiMessage,
} from "./types";
import { isNearScrollBottom } from "./state/chat-scroll-state";
import {
  pruneSelectedConversations,
  toggleSelectedConversation,
} from "./state/sidebar-selection";
import { ChatHome } from "./components/chat/ChatHome";
import { TaskStream } from "./components/chat/TaskStream";
import { StatusBadge } from "./components/app/StatusBadge";
import { Composer } from "./components/composer/Composer";
import { RunInspector } from "./components/context/RunInspector";
import { RunInspectorToggle } from "./components/context/RunInspectorToggle";
import { ConversationSidebar } from "./components/sidebar/ConversationSidebar";
import { ContinueCompatDialog } from "./components/dialogs/ContinueCompatDialog";
import type { ContinueCompatResult } from "./components/dialogs/ContinueCompatDialog";
import { SidebarDialog } from "./components/dialogs/SidebarDialog";
import { TopBar } from "./components/shell/TopBar";
import { sanitizeDisplayText } from "./domain/message-text";
import { formatMessageTime, nowLabel } from "./domain/time";
import { nextSmoothContent, prefersReducedMotion, streamStepInterval } from "./domain/streaming-text";
import type { InspectorTarget } from "./state/task-stream-state";
import { buildTaskStreamItems, chooseActiveInspectorTarget } from "./state/task-stream-state";
import {
  nextWorkbenchLayoutFromInspectorResize,
  nextWorkbenchLayoutFromSidebarResize,
  readWorkbenchLayoutPreference,
  writeWorkbenchLayoutPreference,
} from "./state/workbench-layout-state";
import { gaTheme } from "./theme";

const id = () => Math.random().toString(36).slice(2);
const DEFAULT_CONTINUE_COMMAND = "/continue 1";
const INSPECTOR_DRAWER_DESKTOP_QUERY = "(min-width: 80rem)";
const SIDEBAR_COLLAPSED_WIDTH = "4.75rem";

function toUiMessages(detail: ConversationDetail | null) {
  if (!detail) return [];
  return detail.messages.map((message) => ({
    id: message.id,
    role: message.role,
    content: sanitizeDisplayText(message.content),
    time: formatMessageTime(message.created_at),
    executionLog: message.execution_log ?? [],
  }));
}

function GenericAgentWebUI() {
  const { modal } = AntApp.useApp();
  const [state, setState] = useState<RuntimeState | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [activeConversation, setActiveConversation] = useState<ConversationDetail | null>(null);
  const [draftConversationActive, setDraftConversationActive] = useState(false);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [turns, setTurns] = useState<ExecutionTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [inspectorDrawerDesktop, setInspectorDrawerDesktop] = useState(false);
  const [inspectorVisible, setInspectorVisible] = useState(false);
  const [selectedInspectorTaskId, setSelectedInspectorTaskId] = useState<string | null>(null);
  const [selectedInspectorTarget, setSelectedInspectorTarget] = useState<InspectorTarget | null>(null);
  const [continueDialogOpen, setContinueDialogOpen] = useState(false);
  const [continueCommand, setContinueCommand] = useState(DEFAULT_CONTINUE_COMMAND);
  const [continueLoading, setContinueLoading] = useState(false);
  const [continueError, setContinueError] = useState("");
  const [continueResult, setContinueResult] = useState<ContinueCompatResult | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [selectingRecent, setSelectingRecent] = useState(false);
  const [selectedRecentIds, setSelectedRecentIds] = useState<string[]>([]);
  const [streamAnimating, setStreamAnimating] = useState(false);
  const [workbenchLayout, setWorkbenchLayout] = useState(() =>
    readWorkbenchLayoutPreference(typeof window === "undefined" ? undefined : window.localStorage),
  );
  const chatScrollRef = useRef<HTMLElement | null>(null);
  const streamRef = useRef<EventSource | null>(null);
  const streamTargetRef = useRef("");
  const streamDisplayedRef = useRef("");
  const streamDoneRef = useRef(false);
  const streamAnimationFrameRef = useRef<number | null>(null);
  const streamLastStepAtRef = useRef(0);
  const autoScrollPinnedRef = useRef(true);
  const wasRunningRef = useRef(false);

  const running = Boolean(state?.running);
  const activeConversationId = draftConversationActive
    ? null
    : activeConversation?.summary.id ?? state?.active_conversation_id ?? null;
  const lastReplyTime = state?.last_reply_time || 0;
  const hasThread = messages.length > 0;
  const contextTurns = turns.length > 0 ? turns : running ? [] : activeConversation?.execution_log ?? [];
  const taskItems = buildTaskStreamItems(messages, turns, streamAnimating);
  const latestInspectableItem =
    [...taskItems].reverse().find((item) => item.executionLog.length > 0 || item.pending) ?? null;
  const selectedInspectorItem = selectedInspectorTaskId
    ? taskItems.find((item) => item.id === selectedInspectorTaskId) ?? null
    : null;
  const inspectorTurns = selectedInspectorItem ? selectedInspectorItem.executionLog : contextTurns;
  const effectiveInspectorTarget = selectedInspectorItem ? selectedInspectorTarget : null;
  const activeInspectorTarget = chooseActiveInspectorTarget(
    inspectorTurns,
    inspectorVisible && running && !effectiveInspectorTarget,
    effectiveInspectorTarget,
  );
  const inspectorOpen = inspectorVisible && (running || Boolean(activeInspectorTarget));
  const inspectorToggleVisible =
    hasThread &&
    !inspectorOpen &&
    (running || contextTurns.length > 0 || taskItems.some((item) => item.executionLog.length > 0));
  const inspectorToggleTurnCount =
    latestInspectableItem?.executionLog.length || inspectorTurns.length || contextTurns.length;
  const sidebarPanelSize = sidebarCollapsed ? SIDEBAR_COLLAPSED_WIDTH : `${workbenchLayout.sidebar}%`;
  const sidebarPanelResizable = !sidebarCollapsed;
  const mainPanelSize = inspectorOpen && inspectorDrawerDesktop ? `${workbenchLayout.main}%` : "100%";
  const inspectorPanelSize = `${workbenchLayout.inspector}%`;
  const recentConversationIds = conversations
    .filter((conversation) => !conversation.group_id && !conversation.pinned)
    .map((conversation) => conversation.id);

  const syncConversationList = (nextState: RuntimeState | null) => {
    if (nextState?.conversations) {
      setConversations(nextState.conversations);
    }
    if (nextState?.groups) {
      setGroups(nextState.groups);
    }
  };

  useEffect(() => {
    setSelectedRecentIds((current) => pruneSelectedConversations(current, recentConversationIds));
  }, [conversations]);

  const refreshState = async () => {
    try {
      const next = await fetchState();
      setState(next);
      setConversations(next.conversations ?? []);
      setGroups(next.groups ?? []);
      setTurns(next.execution_log ?? []);

      const candidateId = activeConversationId ?? next.active_conversation_id;
      if (candidateId) {
        const detail = await fetchConversation(candidateId);
        setActiveConversation(detail);
        setMessages(toUiMessages(detail));
        setDraftConversationActive(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  useEffect(() => {
    void refreshState();
    return () => {
      streamRef.current?.close();
      cancelStreamingFrame();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const media = window.matchMedia(INSPECTOR_DRAWER_DESKTOP_QUERY);
    const syncInspectorDrawerViewport = () => {
      setInspectorDrawerDesktop(media.matches);
    };

    syncInspectorDrawerViewport();
    media.addEventListener("change", syncInspectorDrawerViewport);
    return () => media.removeEventListener("change", syncInspectorDrawerViewport);
  }, []);

  useEffect(() => {
    if (!autoScrollPinnedRef.current) return;
    scrollChatToBottom("auto");
  }, [messages, streamAnimating, turns]);

  useEffect(() => {
    const target = chatScrollRef.current;
    if (!target) return;

    const updateAutoScrollPinned = () => {
      autoScrollPinnedRef.current = isNearScrollBottom(
        target.scrollTop,
        target.clientHeight,
        target.scrollHeight,
      );
    };

    updateAutoScrollPinned();
    target.addEventListener("scroll", updateAutoScrollPinned, { passive: true });
    return () => {
      target.removeEventListener("scroll", updateAutoScrollPinned);
    };
  }, [activeConversationId, hasThread]);

  function scrollChatToBottom(behavior: ScrollBehavior = "auto") {
    const target = chatScrollRef.current;
    if (!target) return;
    autoScrollPinnedRef.current = true;
    window.requestAnimationFrame(() => {
      target.scrollTo({ top: target.scrollHeight, behavior });
    });
  }

  function cancelStreamingFrame() {
    if (streamAnimationFrameRef.current !== null) {
      window.cancelAnimationFrame(streamAnimationFrameRef.current);
      streamAnimationFrameRef.current = null;
    }
  }

  function updateStreamingAssistant(content: string) {
    if (!content.trim()) {
      return;
    }
    streamDisplayedRef.current = content;
    setMessages((items) => {
      const copy = [...items];
      const last = copy[copy.length - 1];
      if (last?.role === "assistant") {
        copy[copy.length - 1] = { ...last, content, pending: false };
      } else {
        copy.push({ id: id(), role: "assistant", content, time: nowLabel(), executionLog: [], pending: false });
      }
      return copy;
    });
  }

  function stepStreamingAssistant(timestamp: number) {
    streamAnimationFrameRef.current = null;
    const target = streamTargetRef.current;
    const displayed = streamDisplayedRef.current;
    if (displayed === target) {
      setStreamAnimating(!streamDoneRef.current);
      return;
    }
    // 中文注释：如果后端流式内容发生整体替换，直接覆盖，避免逐字动画和真实输出脱节。
    if (!target.startsWith(displayed)) {
      updateStreamingAssistant(target);
      setStreamAnimating(false);
      return;
    }
    const interval = streamStepInterval(target.length - displayed.length, streamDoneRef.current);
    if (streamLastStepAtRef.current === 0) streamLastStepAtRef.current = timestamp - interval;
    if (timestamp - streamLastStepAtRef.current < interval) {
      streamAnimationFrameRef.current = window.requestAnimationFrame(stepStreamingAssistant);
      return;
    }
    streamLastStepAtRef.current = timestamp;
    const nextContent = nextSmoothContent(displayed, target, streamDoneRef.current);
    updateStreamingAssistant(nextContent);
    if (autoScrollPinnedRef.current) {
      scrollChatToBottom("auto");
    }
    if (nextContent.length < target.length) {
      streamAnimationFrameRef.current = window.requestAnimationFrame(stepStreamingAssistant);
    } else {
      setStreamAnimating(!streamDoneRef.current);
    }
  }

  function queueStreamingAssistant(content: string, done = false) {
    const cleanedContent = sanitizeDisplayText(content);
    streamTargetRef.current = cleanedContent;
    streamDoneRef.current = streamDoneRef.current || done;
    if (prefersReducedMotion()) {
      cancelStreamingFrame();
      updateStreamingAssistant(cleanedContent);
      setStreamAnimating(false);
      return;
    }
    if (streamDisplayedRef.current === cleanedContent) {
      setStreamAnimating(!streamDoneRef.current);
      return;
    }
    if (done && cleanedContent.startsWith(streamDisplayedRef.current)) {
      streamLastStepAtRef.current = 0;
    }
    setStreamAnimating(true);
    if (streamAnimationFrameRef.current === null) {
      streamAnimationFrameRef.current = window.requestAnimationFrame(stepStreamingAssistant);
    }
  }

  function resetStreamingAssistant() {
    cancelStreamingFrame();
    streamTargetRef.current = "";
    streamDisplayedRef.current = "";
    streamDoneRef.current = false;
    streamLastStepAtRef.current = 0;
    setStreamAnimating(false);
  }

  function askText(title: string, defaultValue = "") {
    return new Promise<string | null>((resolve) => {
      let nextValue = defaultValue;
      let settled = false;
      let destroy: (() => void) | undefined;
      const resolveOnce = (value: string | null) => {
        if (settled) return;
        settled = true;
        resolve(value);
      };
      const confirmRef = modal.confirm({
        title,
        icon: null,
        width: "min(92vw, 28.75rem)",
        zIndex: 1500,
        okText: "确认",
        cancelText: "取消",
        autoFocusButton: "ok",
        content: (
          <Input
            id="ga-modal-text-input"
            name="ga-modal-text-input"
            defaultValue={defaultValue}
            autoFocus
            onChange={(event) => {
              nextValue = event.target.value;
            }}
            onPressEnter={() => {
              resolveOnce(nextValue.trim() || null);
              destroy?.();
            }}
          />
        ),
        onOk: () => {
          resolveOnce(nextValue.trim() || null);
        },
        onCancel: () => {
          resolveOnce(null);
        },
      });
      destroy = confirmRef.destroy;
    });
  }

  function confirmAction(options: { title: string; content?: string; danger?: boolean }) {
    return new Promise<boolean>((resolve) => {
      let settled = false;
      const resolveOnce = (value: boolean) => {
        if (settled) return;
        settled = true;
        resolve(value);
      };
      modal.confirm({
        title: options.title,
        content: options.content,
        zIndex: 1500,
        okText: "确认",
        cancelText: "取消",
        okButtonProps: options.danger ? { danger: true } : undefined,
        onOk: () => resolveOnce(true),
        onCancel: () => resolveOnce(false),
      });
    });
  }

  const openConversation = async (conversationId: string) => {
    if (running && activeConversationId !== conversationId) {
      setError("当前任务仍在运行，请先停止任务后再切换会话。");
      return;
    }
    // 中文注释：这里先切 UI 与中间层 active 会话，不在切换动作里主动触发 GA 重放。
    setError("");
    closeInspector();
    autoScrollPinnedRef.current = true;
    const detail = await activateConversation(conversationId);
    setActiveConversation(detail);
    setDraftConversationActive(false);
    setMessages(toUiMessages(detail));
    setTurns(detail.execution_log ?? []);
    setSidebarOpen(false);
    const nextState = await fetchState();
    setState(nextState);
    syncConversationList(nextState);
  };

  const handleCreateConversation = async () => {
    setError("");
    autoScrollPinnedRef.current = true;
    setDraftConversationActive(true);
    setActiveConversation(null);
    setMessages([]);
    setTurns([]);
    setDraft("");
    closeInspector();
    resetStreamingAssistant();
    setSidebarOpen(false);
  };

  const handleRenameConversation = async (conversation: ConversationSummary) => {
    const title = await askText("请输入新的会话标题", conversation.title);
    if (!title) return;
    await renameConversation(conversation.id, title);
    const nextState = await fetchState();
    setState(nextState);
    syncConversationList(nextState);
    if (activeConversationId === conversation.id) {
      const detail = await fetchConversation(conversation.id);
      setActiveConversation(detail);
    }
  };

  const handleDeleteConversation = async (conversation: ConversationSummary) => {
    const confirmed = await confirmAction({
      title: `确认删除会话“${conversation.title}”吗？`,
      danger: true,
    });
    if (!confirmed) return;
    await deleteConversation(conversation.id);
    const nextState = await fetchState();
    setState(nextState);
    syncConversationList(nextState);
    const nextActiveId = nextState.active_conversation_id;
    if (conversation.id === activeConversationId || nextActiveId !== activeConversationId) {
      closeInspector();
    }
    if (nextActiveId) {
      autoScrollPinnedRef.current = true;
      const detail = await fetchConversation(nextActiveId);
      setDraftConversationActive(false);
      setActiveConversation(detail);
      setMessages(toUiMessages(detail));
      setTurns(detail.execution_log ?? []);
    } else {
      setActiveConversation(null);
      setDraftConversationActive(false);
      setMessages([]);
      setTurns([]);
      closeInspector();
    }
  };

  const handleBulkDeleteRecent = async () => {
    if (selectedRecentIds.length === 0) return;
    const confirmed = await confirmAction({
      title: `确认删除选中的 ${selectedRecentIds.length} 个最近对话吗？`,
      danger: true,
    });
    if (!confirmed) return;
    // 中文注释：复用现有软删除接口逐个删除，避免为首版批量操作扩后端协议。
    for (const conversationId of selectedRecentIds) {
      await deleteConversation(conversationId);
    }
    setSelectingRecent(false);
    setSelectedRecentIds([]);
    const nextState = await fetchState();
    setState(nextState);
    syncConversationList(nextState);
    const nextActiveId = nextState.active_conversation_id;
    if (selectedRecentIds.includes(activeConversationId ?? "") || nextActiveId !== activeConversationId) {
      closeInspector();
    }
    if (nextActiveId) {
      autoScrollPinnedRef.current = true;
      const detail = await fetchConversation(nextActiveId);
      const nextMessages = toUiMessages(detail);
      setDraftConversationActive(false);
      setActiveConversation(detail);
      setMessages(nextMessages);
      setTurns(detail.execution_log ?? []);
    } else {
      setActiveConversation(null);
      setDraftConversationActive(false);
      setMessages([]);
      setTurns([]);
    }
  };

  const handlePinConversation = async (conversation: ConversationSummary, pinned: boolean) => {
    await pinConversation(conversation.id, pinned);
    const nextState = await fetchState();
    setState(nextState);
    syncConversationList(nextState);
  };

  const handleMoveConversation = async (conversation: ConversationSummary, groupId: string | null) => {
    await fetch(`/api/conversations/${conversation.id}/move`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ group_id: groupId }),
    });
    const nextState = await fetchState();
    setState(nextState);
    syncConversationList(nextState);
  };

  const handleCreateGroup = async () => {
    const name = await askText("请输入分组名称", "新分组");
    if (!name) return;
    await createGroup(name);
    const nextState = await fetchState();
    setState(nextState);
    syncConversationList(nextState);
  };

  const handleRenameGroup = async (group: GroupSummary) => {
    const name = await askText("请输入新的分组名称", group.name);
    if (!name) return;
    await renameGroup(group.id, name);
    const nextState = await fetchState();
    setState(nextState);
    syncConversationList(nextState);
  };

  const handleDeleteGroup = async (group: GroupSummary) => {
    const confirmed = await confirmAction({
      title: `确认删除分组“${group.name}”吗？`,
      content: "分组内会话会回到未分组。",
      danger: true,
    });
    if (!confirmed) return;
    await deleteGroup(group.id);
    const nextState = await fetchState();
    setState(nextState);
    syncConversationList(nextState);
  };

  const handleSubmit = async (event?: FormEvent) => {
    event?.preventDefault();
    const prompt = draft.trim();
    if (!prompt || running || !state?.configured) return;

    setDraft("");
    setError("");
    setTurns([]);
    closeInspector();
    resetStreamingAssistant();

    let conversationId = activeConversationId;
    // 中文注释：空首页首次发送时，先创建真实会话，再切入线程态。
    if (!conversationId) {
      setDraftConversationActive(false);
      const created = await createConversation(prompt);
      conversationId = created.id;
      const detail = await fetchConversation(conversationId);
      setActiveConversation(detail);
      setMessages([]);
    }

    const userMessage: UiMessage = {
      id: id(),
      role: "user",
      content: prompt,
      time: nowLabel(),
      executionLog: [],
    };
    const pendingAssistantMessage: UiMessage = {
      id: id(),
      role: "assistant",
      content: "",
      time: nowLabel(),
      executionLog: [],
      pending: true,
    };
    setMessages((items) => [...items, userMessage, pendingAssistantMessage]);
    scrollChatToBottom("auto");

    try {
      const { task_id } = await startChat(conversationId, prompt);
      const nextState = await fetchState();
      setState(nextState);
      syncConversationList(nextState);
      const renamedDetail = await fetchConversation(conversationId);
      setActiveConversation(renamedDetail);
      streamRef.current = streamTask(task_id, {
        onEvent: (payload: StreamEvent) => {
          if (payload.event === "message_delta") {
            queueStreamingAssistant(payload.content);
            return;
          }
          if (payload.event === "message_done") {
            queueStreamingAssistant(payload.content, true);
            return;
          }
          if (payload.event === "execution_update") {
            // 中文注释：当前运行态摘要进入消息级执行过程，不再塞进聊天正文。
            setTurns(payload.execution_log);
            setMessages((items) => {
              const copy = [...items];
              const last = copy[copy.length - 1];
              if (last?.role === "assistant") {
                copy[copy.length - 1] = { ...last, executionLog: payload.execution_log, pending: true };
              }
              return copy;
            });
          }
        },
        onError: async (err) => {
          resetStreamingAssistant();
          setError(err.message);
          const latest = await fetchState();
          setState(latest);
          syncConversationList(latest);
        },
        onClose: async () => {
          const latest = await fetchState();
          setState(latest);
          syncConversationList(latest);
          if (conversationId) {
            const detail = await fetchConversation(conversationId);
            setActiveConversation(detail);
            const nextMessages = toUiMessages(detail);
            setMessages(nextMessages);
            setTurns(detail.execution_log ?? []);
          }
        },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      const latest = await fetchState();
      setState(latest);
      syncConversationList(latest);
    }
  };

  const handleContinueCompat = async (event?: FormEvent) => {
    event?.preventDefault();
    const command = continueCommand.trim();
    if (!command || continueLoading) return;

    setContinueLoading(true);
    setContinueError("");
    try {
      // 中文注释：兼容恢复只展示返回结果，不把旧体系历史强行写入新会话列表。
      const result = await continueConversation(command);
      setContinueResult(result);
      const nextState = await fetchState();
      setState(nextState);
      syncConversationList(nextState);
    } catch (err) {
      setContinueError(err instanceof Error ? err.message : String(err));
    } finally {
      setContinueLoading(false);
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSubmit();
    }
  };

  const selectInspectorTarget = (taskId: string, target: InspectorTarget) => {
    setSelectedInspectorTaskId(taskId);
    setSelectedInspectorTarget(target);
    setInspectorVisible(true);
  };

  const openLatestInspector = () => {
    if (latestInspectableItem) {
      setSelectedInspectorTaskId(latestInspectableItem.id);
      setSelectedInspectorTarget(
        running || latestInspectableItem.executionLog.length === 0
          ? null
          : { turnIndex: latestInspectableItem.executionLog.length - 1, toolIndex: null },
      );
    } else {
      setSelectedInspectorTaskId(null);
      setSelectedInspectorTarget(null);
    }
    setInspectorVisible(true);
  };

  const closeInspector = () => {
    setInspectorVisible(false);
    setSelectedInspectorTaskId(null);
    setSelectedInspectorTarget(null);
  };

  const handleSidebarResizeEnd = (sizes: number[]) => {
    if (sidebarCollapsed) return;
    const nextLayout = nextWorkbenchLayoutFromSidebarResize(workbenchLayout, sizes);
    setWorkbenchLayout(nextLayout);
    writeWorkbenchLayoutPreference(window.localStorage, nextLayout);
  };

  const handleInspectorResizeEnd = (sizes: number[]) => {
    if (!inspectorOpen || !inspectorDrawerDesktop) return;
    const nextLayout = nextWorkbenchLayoutFromInspectorResize(workbenchLayout, sizes);
    setWorkbenchLayout(nextLayout);
    writeWorkbenchLayoutPreference(window.localStorage, nextLayout);
  };

  const renderTopBar = () => (
    <TopBar
      state={state}
      running={running}
      conversationTitle={activeConversation?.summary.title || "新对话"}
      onOpenSidebar={() => setSidebarOpen(true)}
      onCreateConversation={() => void handleCreateConversation()}
      onSwitchLlm={(index) =>
        void switchLlm(index).then((next) => {
          setState(next);
          syncConversationList(next);
        })
      }
      onAbort={() => void abortTask().then(refreshState)}
      onRefresh={() => void refreshState()}
      onReinject={() => void reinject().then(refreshState)}
      onAutonomous={(enabled) =>
        void setAutonomous(enabled).then((result) => {
          setState((prev) => (prev ? { ...prev, autonomous_enabled: result.autonomous_enabled } : prev));
        })
      }
      onOpenContinue={() => {
        setContinueResult(null);
        setContinueError("");
        setContinueCommand(DEFAULT_CONTINUE_COMMAND);
        setContinueDialogOpen(true);
      }}
    />
  );

  const renderMainPanel = () => (
    <div className="ga-workbench-main-panel">
      <main className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden">
        {error ? (
          <div className="shrink-0 border-b border-app-line bg-app-danger/10 px-6 py-3 text-sm text-app-danger">
            {error}
          </div>
        ) : null}

        <section ref={chatScrollRef} className="operation-scroll min-h-0 flex-1 overflow-y-auto">
          {!hasThread ? (
            <ChatHome
              state={state}
              draft={draft}
              running={running}
              onDraftChange={setDraft}
              onKeyDown={handleKeyDown}
              onSubmit={(event) => void handleSubmit(event)}
            />
          ) : (
            <div className="ga-chat-stream-frame mx-auto flex min-h-full w-full flex-col">
              <TaskStream
                items={taskItems}
                streaming={streamAnimating}
                onSelectInspectorTarget={selectInspectorTarget}
              />
            </div>
          )}
        </section>

        {hasThread ? (
          <Composer
            state={state}
            draft={draft}
            running={running}
            onDraftChange={setDraft}
            onKeyDown={handleKeyDown}
            onSubmit={(event) => void handleSubmit(event)}
            onAbort={() => void abortTask().then(refreshState)}
          />
        ) : null}
      </main>
    </div>
  );

  useEffect(() => {
    if (wasRunningRef.current && !running) {
      closeInspector();
    }
    wasRunningRef.current = running;
  }, [running]);

  if (state && !state.configured) {
    return (
      <main className="flex h-screen h-dvh items-center justify-center overflow-hidden bg-app-bg p-6">
        <section className="max-w-2xl rounded-[1.75rem] border border-app-line bg-white p-8 shadow-panel">
          <StatusBadge state={state} />
          <h1 className="mt-5 text-3xl font-semibold text-app-text">LLM 尚未配置</h1>
          <p className="mt-4 text-sm leading-8 text-app-muted">
            请先在 `mykey.py` 中配置可用模型后重启 WebUI。当前错误：
            {state.error || "没有检测到可用的 LLM backend。"}
          </p>
        </section>
      </main>
    );
  }

  return (
    <Layout
      style={
        {
          "--sidebar-width": sidebarPanelSize,
        } as CSSProperties
      }
      className="ga-shell ga-workbench-shell h-screen h-dvh min-h-0 overflow-hidden bg-app-bg text-app-text"
    >
      <Splitter
        className="ga-workbench-desktop-splitter hidden xl:flex"
        layout="horizontal"
        onResizeEnd={handleSidebarResizeEnd}
      >
        <Splitter.Panel
          size={sidebarPanelSize}
          min={sidebarCollapsed ? SIDEBAR_COLLAPSED_WIDTH : "12%"}
          max={sidebarCollapsed ? SIDEBAR_COLLAPSED_WIDTH : "28%"}
          resizable={sidebarPanelResizable}
        >
          <ConversationSidebar
            state={state}
            conversations={conversations}
            groups={groups}
            activeConversationId={activeConversationId}
            running={running}
            collapsed={sidebarCollapsed}
            selectingRecent={selectingRecent}
            selectedRecentIds={selectedRecentIds}
            onToggleCollapsed={() => setSidebarCollapsed((current) => !current)}
            onCreateConversation={() => void handleCreateConversation()}
            onSelectConversation={(conversationId) => void openConversation(conversationId)}
            onToggleRecentSelection={() => {
              setSelectingRecent((current) => !current);
              setSelectedRecentIds([]);
            }}
            onToggleRecentConversation={(conversationId) =>
              setSelectedRecentIds((current) => toggleSelectedConversation(current, conversationId))
            }
            onBulkDeleteRecent={() => void handleBulkDeleteRecent()}
            onRenameConversation={(conversation) => void handleRenameConversation(conversation)}
            onDeleteConversation={(conversation) => void handleDeleteConversation(conversation)}
            onPinConversation={(conversation, pinned) => void handlePinConversation(conversation, pinned)}
            onMoveConversation={(conversation, groupId) => void handleMoveConversation(conversation, groupId)}
            onCreateGroup={() => void handleCreateGroup()}
            onRenameGroup={(group) => void handleRenameGroup(group)}
            onDeleteGroup={(group) => void handleDeleteGroup(group)}
          />
        </Splitter.Panel>
        <Splitter.Panel>
          <Layout className="min-h-0 min-w-0 overflow-hidden bg-transparent">
            {renderTopBar()}

            <Layout.Content className="min-h-0 min-w-0 overflow-hidden">
              <div className="ga-workbench-content-frame">
                <Splitter
                  className="ga-workbench-main-splitter"
                  layout="horizontal"
                  onResizeEnd={handleInspectorResizeEnd}
                >
                  <Splitter.Panel size={mainPanelSize} min="50%" resizable={inspectorOpen && inspectorDrawerDesktop}>
                    {renderMainPanel()}
                  </Splitter.Panel>
                  {inspectorOpen && inspectorDrawerDesktop ? (
                    <Splitter.Panel size={inspectorPanelSize} min="20%" max="36%">
                      <div className="ga-workbench-inspector-panel is-open" aria-hidden={false}>
                        <RunInspector
                          turns={inspectorTurns}
                          target={activeInspectorTarget}
                          running={running}
                          onClose={closeInspector}
                          onAbort={() => void abortTask().then(refreshState)}
                        />
                      </div>
                    </Splitter.Panel>
                  ) : null}
                </Splitter>

                {inspectorToggleVisible ? (
                  <RunInspectorToggle
                    running={running}
                    turnCount={inspectorToggleTurnCount}
                    onClick={openLatestInspector}
                  />
                ) : null}
              </div>
            </Layout.Content>
          </Layout>
        </Splitter.Panel>
      </Splitter>

      <Layout className="ga-workbench-mobile-layout min-h-0 min-w-0 overflow-hidden bg-transparent xl:hidden">
        {renderTopBar()}

        <Layout.Content className="min-h-0 min-w-0 overflow-hidden">
          <div className="ga-workbench-content-frame">
            {renderMainPanel()}

            {inspectorToggleVisible ? (
              <RunInspectorToggle
                running={running}
                turnCount={inspectorToggleTurnCount}
                onClick={openLatestInspector}
              />
            ) : null}
          </div>
        </Layout.Content>
      </Layout>

      <SidebarDialog open={sidebarOpen} onOpenChange={setSidebarOpen}>
        <ConversationSidebar
          state={state}
          conversations={conversations}
          groups={groups}
          activeConversationId={activeConversationId}
          running={running}
          actionsAlwaysVisible
          selectingRecent={selectingRecent}
          selectedRecentIds={selectedRecentIds}
          onCreateConversation={() => void handleCreateConversation()}
          onSelectConversation={(conversationId) => void openConversation(conversationId)}
          onToggleRecentSelection={() => {
            setSelectingRecent((current) => !current);
            setSelectedRecentIds([]);
          }}
          onToggleRecentConversation={(conversationId) =>
            setSelectedRecentIds((current) => toggleSelectedConversation(current, conversationId))
          }
          onBulkDeleteRecent={() => void handleBulkDeleteRecent()}
          onRenameConversation={(conversation) => void handleRenameConversation(conversation)}
          onDeleteConversation={(conversation) => void handleDeleteConversation(conversation)}
          onPinConversation={(conversation, pinned) => void handlePinConversation(conversation, pinned)}
          onMoveConversation={(conversation, groupId) => void handleMoveConversation(conversation, groupId)}
          onCreateGroup={() => void handleCreateGroup()}
          onRenameGroup={(group) => void handleRenameGroup(group)}
          onDeleteGroup={(group) => void handleDeleteGroup(group)}
        />
      </SidebarDialog>

      <Drawer
        open={inspectorOpen && !inspectorDrawerDesktop}
        placement="right"
        width="min(92vw, 22.5rem)"
        title={null}
        closable={false}
        aria-label="运行详情"
        rootClassName="ga-run-inspector-drawer-root xl:hidden"
        className="ga-run-inspector-drawer"
        onClose={closeInspector}
      >
        <RunInspector
          turns={inspectorTurns}
          target={activeInspectorTarget}
          running={running}
          onClose={closeInspector}
          onAbort={() => void abortTask().then(refreshState)}
        />
      </Drawer>

      <ContinueCompatDialog
        open={continueDialogOpen}
        command={continueCommand}
        loading={continueLoading}
        error={continueError}
        result={continueResult}
        onOpenChange={setContinueDialogOpen}
        onCommandChange={setContinueCommand}
        onSubmit={(event) => void handleContinueCompat(event)}
      />

      <div id="last-reply-time" className="hidden">
        {lastReplyTime}
      </div>
    </Layout>
  );
}

export default function App() {
  return (
    <ConfigProvider theme={gaTheme} componentSize="middle">
      <AntApp className="h-full">
        <GenericAgentWebUI />
      </AntApp>
    </ConfigProvider>
  );
}
