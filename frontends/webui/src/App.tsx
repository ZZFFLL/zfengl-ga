import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  Circle,
  MessageSquareText,
  PanelLeft,
  PanelRight,
  PauseCircle,
  PlayCircle,
  RefreshCcw,
  RotateCcw,
  Send,
  Settings2,
  Square,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  abortTask,
  continueConversation,
  fetchState,
  reinject,
  resetConversation,
  setAutonomous,
  startChat,
  streamTask,
  switchLlm,
} from "./api";
import type { ChatMessage, ExecutionTurn, RuntimeState } from "./types";

const nowLabel = () => new Date().toLocaleString();
const id = () => Math.random().toString(36).slice(2);
const STREAM_STEP_INTERVAL_MS = 55;
const STREAM_DONE_CATCHUP_INTERVAL_MS = 36;

type GraphemeSegment = { segment: string };
type GraphemeSegmenter = { segment(input: string): Iterable<GraphemeSegment> };
type GraphemeSegmenterConstructor = new (
  locales?: string | string[],
  options?: { granularity: "grapheme" },
) => GraphemeSegmenter;

const graphemeSegmenter = (() => {
  const Segmenter = (Intl as typeof Intl & { Segmenter?: GraphemeSegmenterConstructor }).Segmenter;
  return Segmenter ? new Segmenter(undefined, { granularity: "grapheme" }) : null;
})();

function splitGraphemes(text: string) {
  if (!text) return [];
  if (graphemeSegmenter) {
    return Array.from(graphemeSegmenter.segment(text), (item) => item.segment);
  }
  return Array.from(text);
}

function streamStepInterval(remainingChars: number, done: boolean) {
  return done && remainingChars > 900 ? STREAM_DONE_CATCHUP_INTERVAL_MS : STREAM_STEP_INTERVAL_MS;
}

function nextSmoothContent(displayed: string, target: string) {
  const remaining = splitGraphemes(target.slice(displayed.length));
  if (remaining.length === 0) return target;
  const step = 1;
  return displayed + remaining.slice(0, step).join("");
}

function prefersReducedMotion() {
  return Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
}

function statusTone(state: RuntimeState | null) {
  if (!state?.configured) return "bg-app-warning/10 text-app-warning";
  if (state.running) return "bg-app-success/10 text-app-success";
  return "bg-app-primarySoft text-app-primary";
}

function StatusBadge({ state }: { state: RuntimeState | null }) {
  const label = !state?.configured ? "未配置" : state.running ? "运行中" : "空闲";
  return (
    <span className={`inline-flex min-h-9 items-center gap-2 rounded-md px-3 text-sm font-medium ${statusTone(state)}`}>
      <Circle className="h-3 w-3 fill-current" aria-hidden="true" />
      {label}
    </span>
  );
}

function ControlPanel({
  state,
  onRefresh,
  onSwitchLlm,
  onAbort,
  onReinject,
  onNew,
  onAutonomous,
}: {
  state: RuntimeState | null;
  onRefresh: () => void;
  onSwitchLlm: (index: number) => void;
  onAbort: () => void;
  onReinject: () => void;
  onNew: () => void;
  onAutonomous: (enabled: boolean) => void;
}) {
  return (
    <aside className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto border-r border-app-line bg-app-panel p-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-app-muted">Agent</p>
        <h1 className="mt-1 text-xl font-semibold text-app-text">GenericAgent</h1>
      </div>

      <StatusBadge state={state} />

      <section className="space-y-2">
        <label className="text-sm font-medium text-app-text" htmlFor="llm-select">
          LLM Core
        </label>
        <select
          id="llm-select"
          className="min-h-11 w-full rounded-md border border-app-line bg-white px-3 text-sm text-app-text"
          value={state?.current_llm?.index ?? 0}
          onChange={(event) => onSwitchLlm(Number(event.target.value))}
          disabled={!state?.configured}
        >
          {(state?.llms ?? []).map((llm) => (
            <option key={llm.index} value={llm.index}>
              {llm.index}: {llm.name}
            </option>
          ))}
        </select>
        <p className="text-xs leading-5 text-app-muted">
          当前：{state?.current_llm?.name ?? "未检测到可用模型"}
        </p>
      </section>

      <section className="grid gap-2">
        <button className="control-button" type="button" onClick={onAbort} disabled={!state?.running}>
          <Square className="h-4 w-4" aria-hidden="true" />
          停止任务
        </button>
        <button className="control-button" type="button" onClick={onReinject} disabled={!state?.configured}>
          <RefreshCcw className="h-4 w-4" aria-hidden="true" />
          重新注入 System Prompt
        </button>
        <button className="control-button" type="button" onClick={onNew} disabled={!state?.configured}>
          <RotateCcw className="h-4 w-4" aria-hidden="true" />
          新对话
        </button>
      </section>

      <section className="grid gap-2 border-t border-app-line pt-4">
        <button
          className="control-button"
          type="button"
          onClick={() => onAutonomous(!state?.autonomous_enabled)}
          disabled={!state?.configured}
        >
          {state?.autonomous_enabled ? (
            <PauseCircle className="h-4 w-4" aria-hidden="true" />
          ) : (
            <PlayCircle className="h-4 w-4" aria-hidden="true" />
          )}
          {state?.autonomous_enabled ? "禁止自主行动" : "允许自主行动"}
        </button>
      </section>

      <button className="control-button mt-auto" type="button" onClick={onRefresh}>
        <Settings2 className="h-4 w-4" aria-hidden="true" />
        刷新状态
      </button>
    </aside>
  );
}

function MarkdownContent({
  content,
  streaming = false,
}: {
  content: string;
  streaming?: boolean;
}) {
  return (
    <div className="markdown-content text-sm leading-6">
      <div>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>
      {streaming && <span className="streaming-cursor" aria-hidden="true" />}
    </div>
  );
}

function ExecutionLog({
  turns,
  collapsed = false,
  onToggle,
}: {
  turns: ExecutionTurn[];
  collapsed?: boolean;
  onToggle?: () => void;
}) {
  if (collapsed) {
    return (
      <aside className="flex h-full min-h-0 flex-col items-center gap-3 border-l border-app-line bg-app-panel p-2">
        <button
          type="button"
          className="icon-button"
          aria-label="展开当前执行摘要"
          title="展开当前执行摘要"
          onClick={onToggle}
        >
          <PanelRight className="h-5 w-5" aria-hidden="true" />
        </button>
        <span className="rounded-md bg-app-primarySoft px-2 py-1 text-xs font-medium text-app-primary">
          {turns.length}
        </span>
        <span className="side-label text-xs font-semibold text-app-muted">当前执行摘要</span>
      </aside>
    );
  }

  return (
    <aside className="flex h-full min-h-0 flex-col border-l border-app-line bg-app-panel">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-app-line p-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-app-muted">Execution</p>
          <h2 className="mt-1 text-lg font-semibold text-app-text">当前执行摘要</h2>
        </div>
        {onToggle && (
          <button
            type="button"
            className="icon-button"
            aria-label="收起当前执行摘要"
            title="收起当前执行摘要"
            onClick={onToggle}
          >
            <PanelRight className="h-5 w-5" aria-hidden="true" />
          </button>
        )}
      </div>
      <div className="operation-scroll min-h-0 flex-1 overflow-auto p-3">
        {turns.length === 0 ? (
          <div className="rounded-md border border-dashed border-app-line p-4 text-sm leading-6 text-app-muted">
            当前还没有可展示的执行摘要。最新任务出现 summary 后会显示在这里。
          </div>
        ) : (
          <div className="space-y-2">
            {turns.map((turn, index) => (
              <details
                key={`${turn.turn}-${index}`}
                open={index === turns.length - 1}
                className="rounded-md border border-app-line bg-white"
              >
                <summary className="flex min-h-11 cursor-pointer items-center gap-2 px-3 text-sm font-medium text-app-text">
                  <ChevronDown className="h-4 w-4" aria-hidden="true" />
                  Turn {turn.turn}: {turn.title}
                </summary>
                <div className="border-t border-app-line p-3 text-app-muted">
                  {turn.content ? (
                    <MarkdownContent content={turn.content} />
                  ) : (
                    <p className="text-sm leading-6 text-app-muted">此轮没有 summary。</p>
                  )}
                </div>
              </details>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}

function ChatMessageView({
  message,
  streaming = false,
}: {
  message: ChatMessage;
  streaming?: boolean;
}) {
  const isUser = message.role === "user";
  return (
    <article className={`flex ${isUser ? "justify-end" : "justify-start"} ${streaming ? "smooth-message" : ""}`}>
      <div
        className={`max-w-[86%] rounded-lg border px-4 py-3 shadow-sm ${
          isUser
            ? "border-app-primary/20 bg-app-primary text-white"
            : "border-app-line bg-white text-app-text"
        }`}
      >
        <div className={`mb-2 text-xs ${isUser ? "text-white/75" : "text-app-muted"}`}>
          {isUser ? "User" : message.role === "system" ? "System" : "Agent"} · {message.time}
        </div>
        {isUser ? (
          <div className="message-content text-sm leading-6">{message.content}</div>
        ) : (
          <MarkdownContent content={message.content} streaming={streaming} />
        )}
      </div>
    </article>
  );
}

export default function App() {
  const [state, setState] = useState<RuntimeState | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [turns, setTurns] = useState<ExecutionTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [controlsOpen, setControlsOpen] = useState(false);
  const [logsOpen, setLogsOpen] = useState(false);
  const [logsCollapsed, setLogsCollapsed] = useState(false);
  const [streamAnimating, setStreamAnimating] = useState(false);
  const chatScrollRef = useRef<HTMLElement | null>(null);
  const streamRef = useRef<EventSource | null>(null);
  const streamTargetRef = useRef("");
  const streamDisplayedRef = useRef("");
  const streamDoneRef = useRef(false);
  const streamAnimationFrameRef = useRef<number | null>(null);
  const streamLastStepAtRef = useRef(0);

  const running = Boolean(state?.running);
  const lastReplyTime = state?.last_reply_time || 0;

  const refreshState = async () => {
    try {
      setState(await fetchState());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  useEffect(() => {
    refreshState();
    return () => {
      streamRef.current?.close();
      cancelStreamingFrame();
    };
  }, []);

  useEffect(() => {
    scrollChatToBottom(streamAnimating ? "auto" : "smooth");
  }, [messages, streamAnimating]);

  const pushSystem = (content: string) => {
    setMessages((items) => [...items, { id: id(), role: "system", content, time: nowLabel() }]);
  };

  const appendAssistant = (content: string) => {
    setMessages((items) => [...items, { id: id(), role: "assistant", content, time: nowLabel() }]);
  };

  function scrollChatToBottom(behavior: ScrollBehavior = "auto") {
    const target = chatScrollRef.current;
    if (!target) return;
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
    streamDisplayedRef.current = content;
    setMessages((items) => {
      const copy = [...items];
      const last = copy[copy.length - 1];
      if (last?.role === "assistant") {
        copy[copy.length - 1] = { ...last, content };
      } else {
        copy.push({ id: id(), role: "assistant", content, time: nowLabel() });
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
    const nextContent = nextSmoothContent(displayed, target);
    updateStreamingAssistant(nextContent);
    scrollChatToBottom("auto");
    if (nextContent.length < target.length) {
      streamAnimationFrameRef.current = window.requestAnimationFrame(stepStreamingAssistant);
    } else {
      setStreamAnimating(!streamDoneRef.current);
    }
  }

  function queueStreamingAssistant(content: string, done = false) {
    streamTargetRef.current = content;
    streamDoneRef.current = streamDoneRef.current || done;
    if (prefersReducedMotion()) {
      cancelStreamingFrame();
      updateStreamingAssistant(content);
      setStreamAnimating(false);
      return;
    }
    if (streamDisplayedRef.current === content) {
      setStreamAnimating(!streamDoneRef.current);
      return;
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

  const handleSubmit = async (event?: FormEvent) => {
    event?.preventDefault();
    const prompt = draft.trim();
    if (!prompt || running) return;
    setDraft("");
    setError("");
    resetStreamingAssistant();
    setMessages((items) => [...items, { id: id(), role: "user", content: prompt, time: nowLabel() }]);
    scrollChatToBottom("smooth");

    try {
      if (prompt === "/new") {
        const result = await resetConversation();
        resetStreamingAssistant();
        setMessages([{ id: id(), role: "system", content: result.message, time: nowLabel() }]);
        setTurns([]);
        await refreshState();
        return;
      }
      if (prompt.startsWith("/continue")) {
        const result = await continueConversation(prompt);
        resetStreamingAssistant();
        if (result.history.length) {
          setMessages(
            result.history.map((msg) => ({
              id: id(),
              role: msg.role,
              content: msg.content,
              time: nowLabel(),
            })),
          );
        }
        appendAssistant(result.message);
        await refreshState();
        return;
      }

      updateStreamingAssistant("");
      const { task_id } = await startChat(prompt);
      await refreshState();
      streamRef.current = streamTask(task_id, {
        onEvent: (payload) => {
          if (payload.content !== undefined) queueStreamingAssistant(payload.content, payload.event === "done");
          if (payload.execution_log) setTurns(payload.execution_log);
        },
        onError: (err) => {
          resetStreamingAssistant();
          setError(err.message);
          refreshState();
        },
        onClose: () => refreshState(),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      await refreshState();
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  };

  const shellClass = useMemo(
    () =>
      `grid h-screen h-dvh min-h-0 overflow-hidden bg-app-bg text-app-text md:grid-cols-[240px_minmax(0,1fr)] ${
        logsCollapsed
          ? "lg:grid-cols-[260px_minmax(0,1fr)_56px]"
          : "lg:grid-cols-[260px_minmax(0,1fr)_360px]"
      }`,
    [logsCollapsed],
  );

  if (state && !state.configured) {
    return (
      <main className="flex h-screen h-dvh items-center justify-center overflow-hidden bg-app-bg p-6">
        <section className="max-w-xl rounded-lg border border-app-line bg-white p-6 shadow-panel">
          <StatusBadge state={state} />
          <h1 className="mt-4 text-2xl font-semibold text-app-text">LLM 尚未配置</h1>
          <p className="mt-3 text-sm leading-6 text-app-muted">
            请在 mykey.py 中配置可用模型后重启 WebUI。当前错误：
            {state.error || "没有检测到可用的 LLM backend。"}
          </p>
        </section>
      </main>
    );
  }

  return (
    <div className={shellClass}>
      <div className="hidden min-h-0 md:block">
        <ControlPanel
          state={state}
          onRefresh={refreshState}
          onSwitchLlm={async (index) => setState(await switchLlm(index))}
          onAbort={async () => {
            await abortTask();
            await refreshState();
          }}
          onReinject={async () => {
            await reinject();
            pushSystem("System Prompt will be reinjected on next task.");
          }}
          onNew={async () => {
            const result = await resetConversation();
            setMessages([{ id: id(), role: "system", content: result.message, time: nowLabel() }]);
            setTurns([]);
            await refreshState();
          }}
          onAutonomous={async (enabled) => {
            const result = await setAutonomous(enabled);
            setState((prev) => (prev ? { ...prev, autonomous_enabled: result.autonomous_enabled } : prev));
          }}
        />
      </div>

      <main className="flex min-h-0 min-w-0 flex-col overflow-hidden">
        <header className="flex min-h-16 shrink-0 items-center justify-between border-b border-app-line bg-white px-4">
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="icon-button md:hidden"
              aria-label="打开控制面板"
              onClick={() => setControlsOpen(true)}
            >
              <PanelLeft className="h-5 w-5" />
            </button>
            <MessageSquareText className="h-5 w-5 text-app-primary" aria-hidden="true" />
            <div>
              <h1 className="text-base font-semibold">GenericAgent</h1>
              <p className="text-xs text-app-muted">Agent operations console</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge state={state} />
            <button
              type="button"
              className="icon-button lg:hidden"
              aria-label="打开当前执行摘要"
              onClick={() => setLogsOpen(true)}
            >
              <PanelRight className="h-5 w-5" />
            </button>
          </div>
        </header>

        {error && (
          <div className="shrink-0 border-b border-app-line bg-app-danger/10 px-4 py-2 text-sm text-app-danger">
            {error}
          </div>
        )}

        <section ref={chatScrollRef} className="operation-scroll min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
          {messages.length === 0 ? (
            <div className="mx-auto mt-12 max-w-2xl rounded-lg border border-dashed border-app-line bg-white p-6 text-center text-app-muted">
              <h2 className="text-lg font-semibold text-app-text">开始一个任务</h2>
              <p className="mt-2 text-sm leading-6">
                输入自然语言任务，或使用 /new、/continue、/continue N 管理当前上下文。
              </p>
            </div>
          ) : (
            messages.map((message) => (
              <ChatMessageView
                key={message.id}
                message={message}
                streaming={
                  streamAnimating && message.role === "assistant" && message === messages[messages.length - 1]
                }
              />
            ))
          )}
        </section>

        <form className="shrink-0 border-t border-app-line bg-white p-4" onSubmit={handleSubmit}>
          <div className="flex items-end gap-3 rounded-lg border border-app-line bg-app-bg p-2">
            <textarea
              className="min-h-12 flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-6 text-app-text placeholder:text-app-muted"
              placeholder={running ? "任务运行中..." : "输入指令，Shift+Enter 换行"}
              value={draft}
              disabled={running}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
            />
            <button
              type="submit"
              className="inline-flex min-h-11 items-center gap-2 rounded-md bg-app-primary px-4 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!draft.trim() || running}
            >
              <Send className="h-4 w-4" aria-hidden="true" />
              发送
            </button>
          </div>
        </form>
      </main>

      <div className="hidden min-h-0 lg:block">
        <ExecutionLog
          turns={turns}
          collapsed={logsCollapsed}
          onToggle={() => setLogsCollapsed((value) => !value)}
        />
      </div>

      {controlsOpen && (
        <div className="fixed inset-0 z-40 bg-black/20 md:hidden" onClick={() => setControlsOpen(false)}>
          <div className="h-full w-[280px]" onClick={(event) => event.stopPropagation()}>
            <ControlPanel
              state={state}
              onRefresh={refreshState}
              onSwitchLlm={async (index) => setState(await switchLlm(index))}
              onAbort={async () => {
                await abortTask();
                await refreshState();
              }}
              onReinject={async () => {
                await reinject();
                pushSystem("System Prompt will be reinjected on next task.");
              }}
              onNew={async () => {
                const result = await resetConversation();
                setMessages([{ id: id(), role: "system", content: result.message, time: nowLabel() }]);
                setTurns([]);
                await refreshState();
              }}
              onAutonomous={async (enabled) => {
                const result = await setAutonomous(enabled);
                setState((prev) => (prev ? { ...prev, autonomous_enabled: result.autonomous_enabled } : prev));
              }}
            />
          </div>
        </div>
      )}

      {logsOpen && (
        <div className="fixed inset-0 z-40 bg-black/20 lg:hidden" onClick={() => setLogsOpen(false)}>
          <div className="ml-auto h-full w-[min(390px,92vw)]" onClick={(event) => event.stopPropagation()}>
            <ExecutionLog turns={turns} />
          </div>
        </div>
      )}

      <div id="last-reply-time" className="hidden">
        {lastReplyTime}
      </div>
    </div>
  );
}
