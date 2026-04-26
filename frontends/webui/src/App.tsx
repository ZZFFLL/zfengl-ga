import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
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
import {
  abortTask,
  continueConversation,
  fetchState,
  reinject,
  resetConversation,
  setAutonomous,
  startChat,
  startPet,
  streamTask,
  switchLlm,
} from "./api";
import type { ChatMessage, ExecutionTurn, RuntimeState } from "./types";

const nowLabel = () => new Date().toLocaleString();
const id = () => Math.random().toString(36).slice(2);

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
  onPet,
}: {
  state: RuntimeState | null;
  onRefresh: () => void;
  onSwitchLlm: (index: number) => void;
  onAbort: () => void;
  onReinject: () => void;
  onNew: () => void;
  onAutonomous: (enabled: boolean) => void;
  onPet: () => void;
}) {
  return (
    <aside className="flex h-full flex-col gap-4 border-r border-app-line bg-app-panel p-4">
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
        <button className="control-button" type="button" onClick={onPet} disabled={!state?.configured}>
          <Bot className="h-4 w-4" aria-hidden="true" />
          启动桌面宠物
        </button>
      </section>

      <button className="control-button mt-auto" type="button" onClick={onRefresh}>
        <Settings2 className="h-4 w-4" aria-hidden="true" />
        刷新状态
      </button>
    </aside>
  );
}

function ExecutionLog({ turns }: { turns: ExecutionTurn[] }) {
  return (
    <aside className="flex h-full flex-col border-l border-app-line bg-app-panel">
      <div className="border-b border-app-line p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-app-muted">Execution</p>
        <h2 className="mt-1 text-lg font-semibold text-app-text">运行日志</h2>
      </div>
      <div className="operation-scroll flex-1 overflow-auto p-3">
        {turns.length === 0 ? (
          <div className="rounded-md border border-dashed border-app-line p-4 text-sm leading-6 text-app-muted">
            当前还没有可折叠的运行过程。出现 LLM Running 标记后会自动归档到这里。
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
                <pre className="message-content border-t border-app-line p-3 text-xs leading-5 text-app-muted">
                  {turn.content}
                </pre>
              </details>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}

function ChatMessageView({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <article className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
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
        <div className="message-content text-sm leading-6">{message.content}</div>
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
  const streamRef = useRef<EventSource | null>(null);

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
    return () => streamRef.current?.close();
  }, []);

  const pushSystem = (content: string) => {
    setMessages((items) => [...items, { id: id(), role: "system", content, time: nowLabel() }]);
  };

  const appendAssistant = (content: string) => {
    setMessages((items) => [...items, { id: id(), role: "assistant", content, time: nowLabel() }]);
  };

  const updateStreamingAssistant = (content: string) => {
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
  };

  const handleSubmit = async (event?: FormEvent) => {
    event?.preventDefault();
    const prompt = draft.trim();
    if (!prompt || running) return;
    setDraft("");
    setError("");
    setMessages((items) => [...items, { id: id(), role: "user", content: prompt, time: nowLabel() }]);

    try {
      if (prompt === "/new") {
        const result = await resetConversation();
        setMessages([{ id: id(), role: "system", content: result.message, time: nowLabel() }]);
        setTurns([]);
        await refreshState();
        return;
      }
      if (prompt.startsWith("/continue")) {
        const result = await continueConversation(prompt);
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
          if (payload.content !== undefined) updateStreamingAssistant(payload.content);
          if (payload.execution_log) setTurns(payload.execution_log);
        },
        onError: (err) => {
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
      "grid h-screen min-h-screen bg-app-bg text-app-text lg:grid-cols-[260px_minmax(0,1fr)_360px] md:grid-cols-[240px_minmax(0,1fr)]",
    [],
  );

  if (state && !state.configured) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-app-bg p-6">
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
      <div className="hidden md:block">
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
          onPet={async () => {
            const result = await startPet();
            pushSystem(result.started ? "Desktop pet started." : "Desktop pet request sent.");
          }}
        />
      </div>

      <main className="flex min-w-0 flex-col">
        <header className="flex min-h-16 items-center justify-between border-b border-app-line bg-white px-4">
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
              aria-label="打开运行日志"
              onClick={() => setLogsOpen(true)}
            >
              <PanelRight className="h-5 w-5" />
            </button>
          </div>
        </header>

        {error && (
          <div className="border-b border-app-line bg-app-danger/10 px-4 py-2 text-sm text-app-danger">
            {error}
          </div>
        )}

        <section className="operation-scroll flex-1 space-y-4 overflow-auto p-4">
          {messages.length === 0 ? (
            <div className="mx-auto mt-12 max-w-2xl rounded-lg border border-dashed border-app-line bg-white p-6 text-center text-app-muted">
              <h2 className="text-lg font-semibold text-app-text">开始一个任务</h2>
              <p className="mt-2 text-sm leading-6">
                输入自然语言任务，或使用 /new、/continue、/continue N 管理当前上下文。
              </p>
            </div>
          ) : (
            messages.map((message) => <ChatMessageView key={message.id} message={message} />)
          )}
        </section>

        <form className="border-t border-app-line bg-white p-4" onSubmit={handleSubmit}>
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

      <div className="hidden lg:block">
        <ExecutionLog turns={turns} />
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
              onPet={async () => {
                const result = await startPet();
                pushSystem(result.started ? "Desktop pet started." : "Desktop pet request sent.");
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
