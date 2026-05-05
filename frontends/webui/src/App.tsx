import { CSSProperties, FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import {
  ArrowRight,
  ChevronDown,
  Circle,
  Folder,
  FolderPlus,
  Menu,
  MessageSquareText,
  MoreHorizontal,
  PanelLeft,
  PauseCircle,
  Pin,
  PinOff,
  PlayCircle,
  Plus,
  RefreshCcw,
  RotateCcw,
  Send,
  Sparkles,
  Square,
  Trash2,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
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
} from "./types";
import {
  buildExecutionChipLabel,
  buildExecutionPanelStateClassName,
  findLatestExecutionMessageId,
  resolveExecutionChipRunning,
  resolveExecutionPanelToggle,
  resolveExecutionTurns,
  shouldShowPendingAssistant,
} from "./execution-panel-state";
import {
  buildBulkDeleteLabel,
  pruneSelectedConversations,
  toggleSelectedConversation,
} from "./sidebar-selection";

const nowLabel = () => new Date().toLocaleString();
const id = () => Math.random().toString(36).slice(2);
const STREAM_STEP_INTERVAL_MS = 40;
const STREAM_DONE_CATCHUP_INTERVAL_MS = 8;
const DEFAULT_CONTINUE_COMMAND = "/continue 1";

type GraphemeSegment = { segment: string };
type GraphemeSegmenter = { segment(input: string): Iterable<GraphemeSegment> };
type GraphemeSegmenterConstructor = new (
  locales?: string | string[],
  options?: { granularity: "grapheme" },
) => GraphemeSegmenter;

type UiMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  time: string;
  executionLog: ExecutionTurn[];
  pending?: boolean;
};

type ContinueCompatResult = {
  message: string;
  history: Array<{ role: "user" | "assistant"; content: string }>;
};

const FINAL_INFO_BLOCK_RE = /\n*`{3,}\s*\n?\[Info\]\s*Final response to user\.\s*\n?`{3,}\s*$/i;
const FINAL_INFO_TRAIL_RE = /\n*\[Info\]\s*Final response to user\.\s*(?:`{3,}\s*)*$/i;
const TOOL_START_RE = /🛠️ Tool:\s*`([^`]+)`\s*📥 args:\s*/g;

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
  if (!done) return STREAM_STEP_INTERVAL_MS;
  if (remainingChars > 480) return 0;
  if (remainingChars > 160) return 2;
  return STREAM_DONE_CATCHUP_INTERVAL_MS;
}

function nextSmoothContent(displayed: string, target: string, done = false) {
  const remaining = splitGraphemes(target.slice(displayed.length));
  if (remaining.length === 0) return target;
  const step = done ? Math.min(28, remaining.length) : Math.min(3, remaining.length);
  return displayed + remaining.slice(0, step).join("");
}

function prefersReducedMotion() {
  return Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
}

function formatMessageTime(raw: string) {
  if (!raw) return nowLabel();
  return raw;
}

function sanitizeDisplayText(text: string) {
  let cleaned = text || "";
  cleaned = stripToolTraceBlocks(cleaned);
  cleaned = cleaned.replace(FINAL_INFO_BLOCK_RE, "");
  cleaned = cleaned.replace(FINAL_INFO_TRAIL_RE, "");
  cleaned = cleaned.replace(/\n{3,}/g, "\n\n");
  return cleaned.trim();
}

function consumeFencedBlock(text: string) {
  const match = /^\s*(`{3,})([^\n]*)\n/.exec(text);
  if (!match) return { body: "", remainder: text };
  const fence = match[1];
  const start = match[0].length;
  const endMarker = `\n${fence}`;
  const end = text.indexOf(endMarker, start);
  if (end < 0) return { body: "", remainder: text };
  return {
    body: text.slice(start, end).trim(),
    remainder: text.slice(end + endMarker.length),
  };
}

function stripToolTraceBlocks(text: string) {
  const source = text || "";
  const parts: string[] = [];
  let cursor = 0;

  while (cursor < source.length) {
    TOOL_START_RE.lastIndex = cursor;
    const match = TOOL_START_RE.exec(source);
    if (!match) {
      parts.push(source.slice(cursor));
      break;
    }
    parts.push(source.slice(cursor, match.index));
    cursor = TOOL_START_RE.lastIndex;

    const argsBlock = consumeFencedBlock(source.slice(cursor));
    if (argsBlock.remainder !== source.slice(cursor)) {
      cursor = source.length - argsBlock.remainder.length;
    }

    while (cursor < source.length) {
      const leading = source.slice(cursor);
      const trimmed = leading.replace(/^\s+/, "");
      const consumedWs = leading.length - trimmed.length;
      cursor += consumedWs;
      const block = consumeFencedBlock(source.slice(cursor));
      if (block.remainder === source.slice(cursor)) {
        break;
      }
      cursor = source.length - block.remainder.length;
    }

    while (cursor < source.length && /[\r\n]/.test(source[cursor])) {
      cursor += 1;
    }
  }

  return parts.join("");
}

function previewText(text: string) {
  const cleaned = sanitizeDisplayText(text || "");
  return cleaned.replace(/\s+/g, " ").trim() || "暂无消息";
}

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

function buildGroups(groups: GroupSummary[], conversations: ConversationSummary[]) {
  const groupMap = new Map<string, ConversationSummary[]>();
  for (const conversation of conversations) {
    if (!conversation.group_id) continue;
    if (!groupMap.has(conversation.group_id)) {
      groupMap.set(conversation.group_id, []);
    }
    groupMap.get(conversation.group_id)?.push(conversation);
  }
  return groups.map((group) => ({
    ...group,
    conversations: groupMap.get(group.id) ?? [],
  }));
}

function statusTone(state: RuntimeState | null) {
  if (!state?.configured) return "bg-app-warning/10 text-app-warning";
  if (state.running) return "bg-app-success/10 text-app-success";
  return "bg-app-primarySoft text-app-primary";
}

function StatusBadge({ state }: { state: RuntimeState | null }) {
  const label = !state?.configured ? "未配置" : state.running ? "运行中" : "空闲";
  return (
    <span
      className={`inline-flex min-h-9 items-center gap-2 rounded-full px-3 text-sm font-medium ${statusTone(state)}`}
    >
      <Circle className="h-3 w-3 fill-current" aria-hidden="true" />
      {label}
    </span>
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
    <div className="markdown-content text-sm leading-7">
      <div>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>
      {streaming && <span className="streaming-cursor" aria-hidden="true" />}
    </div>
  );
}

function ExecutionToolCallCard({
  toolCall,
}: {
  toolCall: ExecutionTurn["tool_calls"][number];
}) {
  const [open, setOpen] = useState(false);

  return (
    <section className="rounded-[18px] border border-app-line/70 bg-white">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
        onClick={() => setOpen((value) => !value)}
      >
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-app-text">🛠️ {toolCall.tool}</div>
          <div className="mt-1 truncate text-xs text-app-muted">
            {toolCall.status || toolCall.action || "查看工具调用详情"}
          </div>
        </div>
        <ChevronDown className={`h-4 w-4 shrink-0 text-app-muted transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open ? (
        <div className="space-y-3 border-t border-app-line/70 px-4 py-4">
          {toolCall.args ? (
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-app-muted">Args</div>
              <pre className="mt-2 overflow-x-auto rounded-2xl bg-slate-900 px-4 py-3 text-xs leading-6 text-slate-100">
                <code>{toolCall.args}</code>
              </pre>
            </div>
          ) : null}
          {toolCall.result ? (
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-app-muted">Result</div>
              <pre className="mt-2 overflow-x-auto rounded-2xl bg-slate-900 px-4 py-3 text-xs leading-6 text-slate-100">
                <code>{toolCall.result}</code>
              </pre>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function ExecutionSummaryContent({
  turns,
}: {
  turns: ExecutionTurn[];
}) {
  if (turns.length === 0) return null;

  return (
    <div className="space-y-3">
      {turns.map((turn, index) => (
        <section key={`${turn.turn}-${index}`} className="rounded-[22px] border border-app-line bg-app-surface px-4 py-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-sm font-semibold text-app-text">Turn {turn.turn}</div>
              <div className="mt-1 text-xs text-app-muted">{turn.title}</div>
            </div>
          </div>
          <div className="mt-4 border-t border-app-line/70 pt-4 text-sm leading-7 text-app-muted">
            {turn.content ? <MarkdownContent content={turn.content} /> : "此轮没有 summary。"}
          </div>
          {turn.tool_calls.length > 0 ? (
            <div className="mt-4 space-y-3 border-t border-app-line/70 pt-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-app-muted">
                工具调用
              </div>
              {turn.tool_calls.map((toolCall, toolIndex) => (
                <ExecutionToolCallCard
                  key={`${turn.turn}-${toolCall.tool}-${toolIndex}`}
                  toolCall={toolCall}
                />
              ))}
            </div>
          ) : null}
        </section>
      ))}
    </div>
  );
}

function ExecutionChip({
  turns,
  streaming,
  onClick,
}: {
  turns: ExecutionTurn[];
  streaming: boolean;
  onClick: () => void;
}) {
  const label = buildExecutionChipLabel(turns, streaming);
  if (!label) return null;

  return (
    <button
      type="button"
      className={`thought-chip mb-3 inline-flex items-center gap-2 rounded-full border border-app-line bg-app-surface px-3 py-2 text-sm text-app-muted transition hover:border-app-primary/30 hover:bg-white hover:text-app-text ${
        streaming ? "is-thinking" : ""
      }`}
      onClick={onClick}
    >
      <Sparkles className="h-4 w-4 text-app-primary" />
      <span className="font-medium">{label}</span>
      <span className="rounded-full bg-white px-2 py-0.5 text-[11px] text-app-muted">{turns.length}</span>
      <ArrowRight className="h-4 w-4" />
    </button>
  );
}

function ChatMessageView({
  message,
  streaming = false,
  liveExecutionLog = [],
  onOpenExecution,
}: {
  message: UiMessage;
  streaming?: boolean;
  liveExecutionLog?: ExecutionTurn[];
  onOpenExecution: (messageId: string) => void;
}) {
  const isUser = message.role === "user";
  const effectiveExecutionLog = resolveExecutionTurns(message, liveExecutionLog, streaming);
  const executionChipRunning = resolveExecutionChipRunning(Boolean(message.pending), streaming);
  const isPendingAssistant =
    message.role === "assistant" &&
    shouldShowPendingAssistant(Boolean(message.pending), message.content, effectiveExecutionLog);

  return (
    <article className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className="max-w-[88%]">
        {!isUser ? (
          <ExecutionChip
            turns={effectiveExecutionLog}
            streaming={executionChipRunning}
            onClick={() => onOpenExecution(message.id)}
          />
        ) : null}
        <div
          className={`rounded-[24px] px-5 py-4 shadow-sm ${
            isUser
              ? "bg-app-userBubble text-white"
              : "border border-app-line bg-white text-app-text"
          }`}
        >
          <div className={`mb-2 text-xs ${isUser ? "text-white/70" : "text-app-muted"}`}>
            {isUser ? "你" : message.role === "system" ? "System" : "GA"} · {message.time}
          </div>
          {isPendingAssistant ? (
            <div className="flex items-center gap-3 text-sm text-app-muted">
              <span className="inline-flex h-2.5 w-2.5 rounded-full bg-app-primary animate-pulse" />
              <span>任务执行中...</span>
            </div>
          ) : isUser ? (
            <div className="message-content text-sm leading-7">{message.content}</div>
          ) : (
            <MarkdownContent content={message.content} streaming={streaming} />
          )}
        </div>
      </div>
    </article>
  );
}

function ExecutionPanel({
  message,
  turns,
  open,
  onClose,
}: {
  message: UiMessage | null;
  turns: ExecutionTurn[];
  open: boolean;
  onClose: () => void;
}) {
  return (
    <aside className={buildExecutionPanelStateClassName(open)}>
      {message ? (
        <>
          <button
            type="button"
            className={`absolute right-5 top-5 z-10 flex h-12 w-12 items-center justify-center rounded-full border border-app-line bg-white text-app-text shadow-panel transition-[opacity,transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-soft ${
              open ? "opacity-100 translate-y-0" : "pointer-events-none opacity-0 -translate-y-1"
            }`}
            onClick={onClose}
            aria-label="关闭执行过程"
          >
            <X className="h-5 w-5" />
          </button>
          <div
            className={`operation-scroll min-h-0 flex-1 overflow-y-auto px-5 pb-5 pt-24 transition-[opacity,transform] duration-200 ${
              open ? "opacity-100 translate-x-0" : "pointer-events-none opacity-0 translate-x-2"
            }`}
          >
            <ExecutionSummaryContent turns={turns} />
          </div>
        </>
      ) : null}
    </aside>
  );
}

function ExecutionPanelDialog({
  open,
  message,
  turns,
  onOpenChange,
}: {
  open: boolean;
  message: UiMessage | null;
  turns: ExecutionTurn[];
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/28 backdrop-blur-[1px] xl:hidden" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 w-[min(92vw,420px)] bg-white shadow-panel transition-[transform,opacity] duration-300 ease-out xl:hidden data-[state=open]:translate-x-0 data-[state=open]:opacity-100 data-[state=closed]:translate-x-full data-[state=closed]:opacity-0">
          {open && message ? (
            <div className="relative flex h-full min-h-0 flex-col">
              <button
                type="button"
                className="absolute right-5 top-5 z-10 flex h-12 w-12 items-center justify-center rounded-full border border-app-line bg-white text-app-text shadow-panel transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-soft"
                onClick={() => onOpenChange(false)}
                aria-label="关闭执行过程"
              >
                <X className="h-5 w-5" />
              </button>
              <div className="operation-scroll min-h-0 flex-1 overflow-y-auto px-5 pb-5 pt-24">
                <ExecutionSummaryContent turns={turns} />
              </div>
            </div>
          ) : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function ChatHome({
  state,
  draft,
  running,
  onDraftChange,
  onKeyDown,
  onSubmit,
}: {
  state: RuntimeState | null;
  draft: string;
  running: boolean;
  onDraftChange: (value: string) => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onSubmit: (event?: FormEvent) => void;
}) {
  return (
    <section className="flex min-h-full flex-col justify-center px-6 pb-16 pt-8">
      <div className="mx-auto w-full max-w-[860px]">
        <div className="text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-app-primarySoft text-app-primary">
            <Sparkles className="h-6 w-6" aria-hidden="true" />
          </div>
          <h2 className="mt-8 text-5xl font-semibold tracking-tight text-app-text">你想让 GenericAgent 做什么？</h2>
          <p className="mx-auto mt-4 max-w-2xl text-base leading-8 text-app-muted">
            保留 GA 的模型切换、停止任务、重注入和自主行动能力，但把主视觉让给聊天本身。
          </p>
        </div>

        <form className="mx-auto mt-16 max-w-[820px]" onSubmit={onSubmit}>
          <div className="rounded-[28px] border border-app-line bg-white/95 px-5 py-4 shadow-soft backdrop-blur">
            <div className="flex items-start gap-4">
              <div className="mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-app-primarySoft text-app-primary">
                <MessageSquareText className="h-5 w-5" aria-hidden="true" />
              </div>
              <textarea
                className="min-h-[44px] flex-1 resize-none border-0 bg-transparent pt-2 text-base leading-8 text-app-text placeholder:text-app-muted focus:outline-none"
                placeholder={running ? "任务运行中..." : "有什么我能帮您的吗？"}
                value={draft}
                disabled={running || !state?.configured}
                onChange={(event) => onDraftChange(event.target.value)}
                onKeyDown={onKeyDown}
                rows={2}
              />
              <button
                type="submit"
                className="mt-1 inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-app-primary text-white disabled:cursor-not-allowed disabled:bg-app-line"
                disabled={!draft.trim() || running || !state?.configured}
                aria-label="发送"
              >
                <Send className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <div className="mt-3 flex items-center justify-between gap-3 text-xs text-app-muted">
              <span>GA 原有控制能力保留在顶部和更多菜单。</span>
              <span>Shift+Enter 换行，Enter 发送</span>
            </div>
          </div>
        </form>
      </div>
    </section>
  );
}

function Composer({
  state,
  draft,
  running,
  onDraftChange,
  onKeyDown,
  onSubmit,
  onAbort,
}: {
  state: RuntimeState | null;
  draft: string;
  running: boolean;
  onDraftChange: (value: string) => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onSubmit: (event?: FormEvent) => void;
  onAbort: () => void;
}) {
  return (
    <form className="shrink-0 border-t border-app-line/70 bg-white/75 px-4 py-4 backdrop-blur" onSubmit={onSubmit}>
      <div className="mx-auto max-w-[860px] rounded-[24px] border border-app-line bg-white px-5 py-4 shadow-soft">
        <textarea
          className="min-h-[64px] w-full resize-none border-0 bg-transparent text-[15px] leading-7 text-app-text placeholder:text-app-muted focus:outline-none"
          placeholder={running ? "任务运行中..." : "继续补充问题，Shift+Enter 换行"}
          value={draft}
          disabled={running || !state?.configured}
          onChange={(event) => onDraftChange(event.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
        />
        <div className="mt-3 flex items-center justify-between gap-3">
          <div className="text-xs text-app-muted">Shift+Enter 换行，Enter 发送。</div>
          <div className="flex items-center gap-2">
            {running ? (
              <button
                type="button"
                className="inline-flex min-h-10 items-center gap-2 rounded-full border border-app-line bg-white px-4 text-sm font-medium text-app-text"
                onClick={onAbort}
              >
                <Square className="h-4 w-4" />
                停止
              </button>
            ) : null}
            <button
              type="submit"
              className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-app-primary text-white disabled:cursor-not-allowed disabled:bg-app-line"
              disabled={!draft.trim() || running || !state?.configured}
              aria-label="发送"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </form>
  );
}

function TopBar({
  state,
  running,
  conversationTitle,
  onOpenSidebar,
  onCreateConversation,
  onSwitchLlm,
  onAbort,
  onRefresh,
  onReinject,
  onAutonomous,
  onOpenContinue,
}: {
  state: RuntimeState | null;
  running: boolean;
  conversationTitle: string;
  onOpenSidebar: () => void;
  onCreateConversation: () => void;
  onSwitchLlm: (index: number) => void;
  onAbort: () => void;
  onRefresh: () => void;
  onReinject: () => void;
  onAutonomous: (enabled: boolean) => void;
  onOpenContinue: () => void;
}) {
  return (
    <header className="shrink-0 border-b border-app-line/80 bg-white/90 backdrop-blur">
      <div className="flex min-h-[54px] items-center gap-3 px-4 py-2 md:px-6">
        <button
          type="button"
          className="icon-button-subtle h-9 w-9 xl:hidden"
          aria-label="打开会话侧栏"
          onClick={onOpenSidebar}
        >
          <Menu className="h-5 w-5" />
        </button>

        <div className="min-w-0 flex items-center gap-3">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-app-text">{conversationTitle}</div>
          </div>
        </div>

        <div className="ml-auto flex min-w-0 items-center gap-2">
          <div className="hidden min-h-9 min-w-0 items-center gap-2 rounded-full border border-app-line bg-app-surface px-3 py-1 sm:flex">
            <span className="shrink-0 text-[11px] font-semibold uppercase tracking-[0.18em] text-app-muted">
              Model
            </span>
            <select
              className="min-w-0 border-0 bg-transparent pr-2 text-sm text-app-text focus:outline-none"
              value={state?.current_llm?.index ?? 0}
              onChange={(event) => onSwitchLlm(Number(event.target.value))}
              disabled={!state?.configured || running}
            >
              {(state?.llms ?? []).map((llm) => (
                <option key={llm.index} value={llm.index}>
                  {llm.name}
                </option>
              ))}
            </select>
          </div>

          <StatusBadge state={state} />

          {running ? (
            <button
              type="button"
              className="inline-flex min-h-9 items-center gap-2 rounded-full bg-app-primary px-4 text-sm font-medium text-white"
              onClick={onAbort}
            >
              <Square className="h-4 w-4" />
              停止任务
            </button>
          ) : null}

          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <button type="button" className="icon-button-subtle h-9 w-9" aria-label="更多 GA 操作">
                <MoreHorizontal className="h-5 w-5" />
              </button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content className="dropdown-panel" sideOffset={10} align="end">
                <DropdownMenu.Item
                  className="dropdown-item"
                  disabled={!state?.configured || running}
                  onSelect={() => onCreateConversation()}
                >
                  <RotateCcw className="h-4 w-4" />
                  新建空白会话
                </DropdownMenu.Item>
                <DropdownMenu.Item className="dropdown-item" onSelect={() => onRefresh()}>
                  <RefreshCcw className="h-4 w-4" />
                  刷新状态
                </DropdownMenu.Item>
                <DropdownMenu.Item
                  className="dropdown-item"
                  disabled={!state?.configured || running}
                  onSelect={() => onReinject()}
                >
                  <RefreshCcw className="h-4 w-4" />
                  重新注入 System Prompt
                </DropdownMenu.Item>
                <DropdownMenu.Item
                  className="dropdown-item"
                  disabled={!state?.configured || running}
                  onSelect={() => onAutonomous(!state?.autonomous_enabled)}
                >
                  {state?.autonomous_enabled ? <PauseCircle className="h-4 w-4" /> : <PlayCircle className="h-4 w-4" />}
                  {state?.autonomous_enabled ? "关闭自主行动" : "开启自主行动"}
                </DropdownMenu.Item>
                <DropdownMenu.Separator className="my-1 h-px bg-app-line" />
                <DropdownMenu.Item
                  className="dropdown-item"
                  disabled={running}
                  onSelect={() => onOpenContinue()}
                >
                  <MessageSquareText className="h-4 w-4" />
                  恢复旧会话（兼容）
                </DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        </div>
      </div>
    </header>
  );
}

function ContinueCompatDialog({
  open,
  command,
  loading,
  error,
  result,
  onOpenChange,
  onCommandChange,
  onSubmit,
}: {
  open: boolean;
  command: string;
  loading: boolean;
  error: string;
  result: ContinueCompatResult | null;
  onOpenChange: (open: boolean) => void;
  onCommandChange: (value: string) => void;
  onSubmit: (event?: FormEvent) => void;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/24 backdrop-blur-[2px]" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(92vw,720px)] -translate-x-1/2 -translate-y-1/2 rounded-[28px] border border-app-line bg-white p-6 shadow-panel">
          <div className="flex items-start justify-between gap-4">
            <div>
              <Dialog.Title className="text-xl font-semibold text-app-text">恢复旧会话（兼容入口）</Dialog.Title>
              <Dialog.Description className="mt-2 text-sm leading-7 text-app-muted">
                这里保留 `/continue` 兼容能力，但不会把旧日志体系改成新会话真相源。
              </Dialog.Description>
            </div>
            <button type="button" className="icon-button-subtle" onClick={() => onOpenChange(false)} aria-label="关闭">
              <X className="h-4 w-4" />
            </button>
          </div>

          <form className="mt-6 space-y-4" onSubmit={onSubmit}>
            <div className="rounded-[22px] border border-app-line bg-app-surface px-4 py-4">
              <label className="mb-2 block text-sm font-medium text-app-text" htmlFor="continue-command">
                兼容命令
              </label>
              <input
                id="continue-command"
                className="w-full rounded-2xl border border-app-line bg-white px-4 py-3 text-sm text-app-text outline-none"
                value={command}
                onChange={(event) => onCommandChange(event.target.value)}
                placeholder={DEFAULT_CONTINUE_COMMAND}
              />
              <p className="mt-2 text-xs leading-6 text-app-muted">示例：`/continue 1`。接口仍走现有后端兼容逻辑。</p>
            </div>

            {error ? (
              <div className="rounded-2xl border border-app-danger/20 bg-app-danger/10 px-4 py-3 text-sm text-app-danger">
                {error}
              </div>
            ) : null}

            {result ? (
              <div className="space-y-4">
                <section className="rounded-[22px] border border-app-line bg-app-surface px-4 py-4">
                  <div className="text-sm font-semibold text-app-text">执行结果</div>
                  <div className="mt-3 whitespace-pre-wrap text-sm leading-7 text-app-text">{result.message}</div>
                </section>

                <section className="rounded-[22px] border border-app-line bg-app-surface px-4 py-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-semibold text-app-text">兼容历史预览</div>
                    <span className="rounded-full bg-white px-2 py-1 text-xs text-app-muted">{result.history.length}</span>
                  </div>
                  <div className="mt-3 max-h-[280px] space-y-3 overflow-y-auto">
                    {result.history.length === 0 ? (
                      <div className="text-sm text-app-muted">这次兼容恢复没有返回可展示的历史记录。</div>
                    ) : (
                      result.history.map((message, index) => (
                        <div key={`${message.role}-${index}`} className="rounded-2xl bg-white px-4 py-3">
                          <div className="text-xs font-medium text-app-muted">
                            {message.role === "user" ? "用户" : "GA"}
                          </div>
                          <div className="mt-2 whitespace-pre-wrap text-sm leading-7 text-app-text">
                            {message.content}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </section>
              </div>
            ) : null}

            <div className="flex items-center justify-end gap-3">
              <button
                type="button"
                className="inline-flex min-h-11 items-center rounded-full border border-app-line bg-white px-4 text-sm font-medium text-app-text"
                onClick={() => onOpenChange(false)}
              >
                关闭
              </button>
              <button
                type="submit"
                className="inline-flex min-h-11 items-center rounded-full bg-app-primary px-4 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-app-line"
                disabled={loading || !command.trim()}
              >
                {loading ? "处理中..." : "执行兼容恢复"}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function ConversationActions({
  conversation,
  groups,
  running,
  onRename,
  onDelete,
  onPin,
  onMove,
}: {
  conversation: ConversationSummary;
  groups: GroupSummary[];
  running: boolean;
  onRename: (conversation: ConversationSummary) => void;
  onDelete: (conversation: ConversationSummary) => void;
  onPin: (conversation: ConversationSummary, pinned: boolean) => void;
  onMove: (conversation: ConversationSummary, groupId: string | null) => void;
}) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          className="icon-button-ghost"
          aria-label="会话更多操作"
          disabled={running}
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content className="dropdown-panel" sideOffset={8} align="end">
          <DropdownMenu.Item className="dropdown-item" onSelect={() => onRename(conversation)}>
            <MessageSquareText className="h-4 w-4" />
            重命名
          </DropdownMenu.Item>
          <DropdownMenu.Item className="dropdown-item" onSelect={() => onPin(conversation, !conversation.pinned)}>
            {conversation.pinned ? <PinOff className="h-4 w-4" /> : <Pin className="h-4 w-4" />}
            {conversation.pinned ? "取消置顶" : "置顶"}
          </DropdownMenu.Item>
          <DropdownMenu.Sub>
            <DropdownMenu.SubTrigger className="dropdown-item">
              <Folder className="h-4 w-4" />
              移动到分组
            </DropdownMenu.SubTrigger>
            <DropdownMenu.Portal>
              <DropdownMenu.SubContent className="dropdown-panel" sideOffset={6}>
                <DropdownMenu.Item className="dropdown-item" onSelect={() => onMove(conversation, null)}>
                  未分组
                </DropdownMenu.Item>
                {groups.map((group) => (
                  <DropdownMenu.Item
                    key={group.id}
                    className="dropdown-item"
                    onSelect={() => onMove(conversation, group.id)}
                  >
                    {group.name}
                  </DropdownMenu.Item>
                ))}
              </DropdownMenu.SubContent>
            </DropdownMenu.Portal>
          </DropdownMenu.Sub>
          <DropdownMenu.Separator className="my-1 h-px bg-app-line" />
          <DropdownMenu.Item className="dropdown-item danger" onSelect={() => onDelete(conversation)}>
            <Trash2 className="h-4 w-4" />
            删除
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function ConversationSidebar({
  state,
  conversations,
  groups,
  activeConversationId,
  running,
  collapsed = false,
  selectingRecent = false,
  selectedRecentIds = [],
  onToggleCollapsed,
  onCreateConversation,
  onSelectConversation,
  onToggleRecentSelection,
  onToggleRecentConversation,
  onBulkDeleteRecent,
  onRenameConversation,
  onDeleteConversation,
  onPinConversation,
  onMoveConversation,
  onCreateGroup,
  onRenameGroup,
  onDeleteGroup,
}: {
  state: RuntimeState | null;
  conversations: ConversationSummary[];
  groups: GroupSummary[];
  activeConversationId: string | null;
  running: boolean;
  collapsed?: boolean;
  selectingRecent?: boolean;
  selectedRecentIds?: string[];
  onToggleCollapsed?: () => void;
  onCreateConversation: () => void;
  onSelectConversation: (conversationId: string) => void;
  onToggleRecentSelection?: () => void;
  onToggleRecentConversation?: (conversationId: string) => void;
  onBulkDeleteRecent?: () => void;
  onRenameConversation: (conversation: ConversationSummary) => void;
  onDeleteConversation: (conversation: ConversationSummary) => void;
  onPinConversation: (conversation: ConversationSummary, pinned: boolean) => void;
  onMoveConversation: (conversation: ConversationSummary, groupId: string | null) => void;
  onCreateGroup: () => void;
  onRenameGroup: (group: GroupSummary) => void;
  onDeleteGroup: (group: GroupSummary) => void;
}) {
  const pinned = conversations.filter((conversation) => conversation.pinned);
  const ungrouped = conversations.filter((conversation) => !conversation.group_id && !conversation.pinned);
  const grouped = buildGroups(
    groups,
    conversations.filter((conversation) => !conversation.pinned),
  );
  const selectedRecentSet = new Set(selectedRecentIds);

  if (collapsed) {
    return (
      <aside className="flex h-full min-h-0 flex-col items-center border-r border-app-line/80 bg-app-sidebar px-2 py-3">
        <button
          type="button"
          className="flex h-10 w-10 items-center justify-center rounded-[15px] text-app-text transition hover:bg-[#e8ecf3]"
          aria-label="展开会话侧栏"
          onClick={onToggleCollapsed}
        >
          <PanelLeft className="h-5 w-5" />
        </button>
        <button
          type="button"
          className="mt-2 flex h-10 w-10 items-center justify-center rounded-[15px] text-app-text transition hover:bg-[#e8ecf3] disabled:cursor-not-allowed disabled:opacity-50"
          aria-label="新建对话"
          onClick={onCreateConversation}
          disabled={!state?.configured || running}
        >
          <Plus className="h-5 w-5" />
        </button>
      </aside>
    );
  }

  return (
    <aside className="flex h-full min-h-0 flex-col border-r border-app-line/80 bg-app-sidebar">
      <div className="px-4 pb-3 pt-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[15px] bg-white/75 text-app-primary ring-1 ring-app-line/70">
            <Sparkles className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-lg font-semibold tracking-tight text-app-text">GenericAgent</h1>
          </div>
          {onToggleCollapsed ? (
            <button
              type="button"
              className="icon-button-ghost"
              aria-label="收起会话侧栏"
              onClick={onToggleCollapsed}
            >
              <PanelLeft className="h-4 w-4" />
            </button>
          ) : null}
        </div>

        <button
          type="button"
          className="mt-4 inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-full bg-white/75 px-4 text-sm font-medium text-app-text ring-1 ring-app-line/80 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
          onClick={onCreateConversation}
          disabled={!state?.configured || running}
        >
          <Plus className="h-4 w-4" />
          新建对话
        </button>
      </div>

      <div className="operation-scroll min-h-0 flex-1 overflow-y-auto px-2 pb-4">
        <div className="space-y-4">
          {pinned.length > 0 ? (
            <section>
              <div className="sidebar-section-title mb-1.5">
                置顶对话
              </div>
              <div className="sidebar-list">
                {pinned.map((conversation) => (
                  <button
                    key={conversation.id}
                    type="button"
                    className={`sidebar-item ${activeConversationId === conversation.id ? "active" : ""}`}
                    onClick={() => onSelectConversation(conversation.id)}
                    disabled={running && activeConversationId !== conversation.id}
                  >
                    <div className="flex min-w-0 flex-1 items-start gap-2.5">
                      <Pin className="mt-0.5 h-4 w-4 shrink-0 text-app-primary" />
                      <div className="min-w-0 flex-1 text-left">
                        <div className="truncate text-sm font-medium">{conversation.title}</div>
                        <div className="mt-1 truncate text-xs text-app-muted">{previewText(conversation.preview)}</div>
                      </div>
                    </div>
                    <ConversationActions
                      conversation={conversation}
                      groups={groups}
                      running={running}
                      onRename={onRenameConversation}
                      onDelete={onDeleteConversation}
                      onPin={onPinConversation}
                      onMove={onMoveConversation}
                    />
                  </button>
                ))}
              </div>
            </section>
          ) : null}

          <section>
            <div className="mb-1.5 flex items-center justify-between px-2">
              <div className="sidebar-section-title px-0">对话分组</div>
              <button
                type="button"
                className="icon-button-ghost"
                aria-label="新建分组"
                onClick={onCreateGroup}
                disabled={running}
              >
                <FolderPlus className="h-4 w-4" />
              </button>
            </div>

            {grouped.map((group) => (
              <div key={group.id} className="mb-3">
                <div className="mb-1 flex items-center justify-between px-2">
                  <div className="flex items-center gap-2 text-[13px] font-medium text-app-text/90">
                    <Folder className="h-3.5 w-3.5 text-app-muted" />
                    {group.name}
                  </div>
                  <DropdownMenu.Root>
                    <DropdownMenu.Trigger asChild>
                      <button type="button" className="icon-button-ghost" disabled={running}>
                        <MoreHorizontal className="h-4 w-4" />
                      </button>
                    </DropdownMenu.Trigger>
                    <DropdownMenu.Portal>
                      <DropdownMenu.Content className="dropdown-panel" sideOffset={8} align="end">
                        <DropdownMenu.Item className="dropdown-item" onSelect={() => onRenameGroup(group)}>
                          重命名分组
                        </DropdownMenu.Item>
                        <DropdownMenu.Item className="dropdown-item danger" onSelect={() => onDeleteGroup(group)}>
                          删除分组
                        </DropdownMenu.Item>
                      </DropdownMenu.Content>
                    </DropdownMenu.Portal>
                  </DropdownMenu.Root>
                </div>
                <div className="sidebar-list">
                  {group.conversations.length === 0 ? (
                    <div className="rounded-xl px-3 py-2 text-xs text-app-muted">分组里还没有会话</div>
                  ) : (
                    group.conversations.map((conversation) => (
                      <button
                        key={conversation.id}
                        type="button"
                        className={`sidebar-item ${activeConversationId === conversation.id ? "active" : ""}`}
                        onClick={() => onSelectConversation(conversation.id)}
                        disabled={running && activeConversationId !== conversation.id}
                      >
                        <div className="min-w-0 flex-1 text-left">
                          <div className="truncate text-sm font-medium">{conversation.title}</div>
                          <div className="mt-1 truncate text-xs text-app-muted">{previewText(conversation.preview)}</div>
                        </div>
                        <ConversationActions
                          conversation={conversation}
                          groups={groups}
                          running={running}
                          onRename={onRenameConversation}
                          onDelete={onDeleteConversation}
                          onPin={onPinConversation}
                          onMove={onMoveConversation}
                        />
                      </button>
                    ))
                  )}
                </div>
              </div>
            ))}

            <div className="mb-1.5 flex items-center justify-between gap-2 px-2">
              <div className="sidebar-section-title px-0">最近对话</div>
              {ungrouped.length > 0 ? (
                <div className="flex items-center gap-1">
                  {selectingRecent ? (
                    <button
                      type="button"
                      className="rounded-full px-2 py-1 text-[11px] font-medium text-app-danger transition hover:bg-[#e8ecf3] disabled:cursor-not-allowed disabled:opacity-40"
                      disabled={selectedRecentIds.length === 0 || running}
                      onClick={onBulkDeleteRecent}
                    >
                      {buildBulkDeleteLabel(selectedRecentIds.length)}
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="rounded-full px-2 py-1 text-[11px] font-medium text-app-muted transition hover:bg-[#e8ecf3] hover:text-app-text disabled:cursor-not-allowed disabled:opacity-40"
                    disabled={running}
                    onClick={onToggleRecentSelection}
                  >
                    {selectingRecent ? "取消" : "选择"}
                  </button>
                </div>
              ) : null}
            </div>
            <div className="sidebar-list">
              {ungrouped.map((conversation) => (
                <button
                  key={conversation.id}
                  type="button"
                  className={`sidebar-item ${activeConversationId === conversation.id ? "active" : ""}`}
                  onClick={() =>
                    selectingRecent
                      ? onToggleRecentConversation?.(conversation.id)
                      : onSelectConversation(conversation.id)
                  }
                  disabled={running && activeConversationId !== conversation.id}
                >
                  {selectingRecent ? (
                    <span
                      className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
                        selectedRecentSet.has(conversation.id)
                          ? "border-app-primary bg-app-primary text-white"
                          : "border-app-line bg-white"
                      }`}
                      aria-hidden="true"
                    >
                      {selectedRecentSet.has(conversation.id) ? <span className="h-1.5 w-1.5 rounded-full bg-white" /> : null}
                    </span>
                  ) : null}
                  <div className="min-w-0 flex-1 text-left">
                    <div className="truncate text-sm font-medium">{conversation.title}</div>
                    <div className="mt-1 truncate text-xs text-app-muted">{previewText(conversation.preview)}</div>
                  </div>
                  {selectingRecent ? null : (
                    <ConversationActions
                      conversation={conversation}
                      groups={groups}
                      running={running}
                      onRename={onRenameConversation}
                      onDelete={onDeleteConversation}
                      onPin={onPinConversation}
                      onMove={onMoveConversation}
                    />
                  )}
                </button>
              ))}
            </div>
          </section>
        </div>
      </div>
    </aside>
  );
}

function SidebarDialog({
  open,
  onOpenChange,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: React.ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/28 xl:hidden" />
        <Dialog.Content className="fixed inset-y-0 left-0 z-50 w-[min(92vw,340px)] border-r border-app-line bg-app-sidebar shadow-panel xl:hidden">
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export default function App() {
  const [state, setState] = useState<RuntimeState | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [activeConversation, setActiveConversation] = useState<ConversationDetail | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [turns, setTurns] = useState<ExecutionTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [continueDialogOpen, setContinueDialogOpen] = useState(false);
  const [continueCommand, setContinueCommand] = useState(DEFAULT_CONTINUE_COMMAND);
  const [continueLoading, setContinueLoading] = useState(false);
  const [continueError, setContinueError] = useState("");
  const [continueResult, setContinueResult] = useState<ContinueCompatResult | null>(null);
  const [executionPanelOpen, setExecutionPanelOpen] = useState(false);
  const [selectedExecutionMessageId, setSelectedExecutionMessageId] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [selectingRecent, setSelectingRecent] = useState(false);
  const [selectedRecentIds, setSelectedRecentIds] = useState<string[]>([]);
  const [streamAnimating, setStreamAnimating] = useState(false);
  const chatScrollRef = useRef<HTMLElement | null>(null);
  const streamRef = useRef<EventSource | null>(null);
  const streamTargetRef = useRef("");
  const streamDisplayedRef = useRef("");
  const streamDoneRef = useRef(false);
  const streamAnimationFrameRef = useRef<number | null>(null);
  const streamLastStepAtRef = useRef(0);

  const running = Boolean(state?.running);
  const activeConversationId = activeConversation?.summary.id ?? state?.active_conversation_id ?? null;
  const lastReplyTime = state?.last_reply_time || 0;
  const hasThread = messages.length > 0;
  const selectedExecutionMessage = messages.find((message) => message.id === selectedExecutionMessageId) ?? null;
  const latestExecutionMessageId = findLatestExecutionMessageId(messages);
  const selectedExecutionTurns = selectedExecutionMessage
    ? resolveExecutionTurns(
        selectedExecutionMessage,
        streamAnimating && selectedExecutionMessageId === messages[messages.length - 1]?.id ? turns : [],
        Boolean(streamAnimating && selectedExecutionMessageId === messages[messages.length - 1]?.id),
      )
    : [];
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
        setSelectedExecutionMessageId(findLatestExecutionMessageId(toUiMessages(detail)));
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
    scrollChatToBottom(streamAnimating ? "auto" : "smooth");
  }, [messages, streamAnimating]);

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
    scrollChatToBottom("auto");
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

  const openConversation = async (conversationId: string) => {
    if (running && activeConversationId !== conversationId) {
      setError("当前任务仍在运行，请先停止任务后再切换会话。");
      return;
    }
    // 中文注释：这里先切 UI 与中间层 active 会话，不在切换动作里主动触发 GA 重放。
    setError("");
    const detail = await activateConversation(conversationId);
    setActiveConversation(detail);
    setMessages(toUiMessages(detail));
    setTurns(detail.execution_log ?? []);
    setExecutionPanelOpen(false);
    setSelectedExecutionMessageId(findLatestExecutionMessageId(toUiMessages(detail)));
    setSidebarOpen(false);
    const nextState = await fetchState();
    setState(nextState);
    syncConversationList(nextState);
  };

  const handleCreateConversation = async (titleHint = "") => {
    setError("");
    const conversation = await createConversation(titleHint);
    const detail = await fetchConversation(conversation.id);
    setActiveConversation(detail);
    setMessages([]);
    setTurns([]);
    setExecutionPanelOpen(false);
    setSelectedExecutionMessageId(null);
    resetStreamingAssistant();
    const nextState = await fetchState();
    setState(nextState);
    syncConversationList(nextState);
    setSidebarOpen(false);
  };

  const handleRenameConversation = async (conversation: ConversationSummary) => {
    const title = window.prompt("请输入新的会话标题", conversation.title);
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
    if (!window.confirm(`确认删除会话“${conversation.title}”吗？`)) return;
    await deleteConversation(conversation.id);
    const nextState = await fetchState();
    setState(nextState);
    syncConversationList(nextState);
    const nextActiveId = nextState.active_conversation_id;
    if (nextActiveId) {
      const detail = await fetchConversation(nextActiveId);
      setActiveConversation(detail);
      setMessages(toUiMessages(detail));
      setTurns(detail.execution_log ?? []);
      setSelectedExecutionMessageId(findLatestExecutionMessageId(toUiMessages(detail)));
    } else {
      setActiveConversation(null);
      setMessages([]);
      setTurns([]);
      setExecutionPanelOpen(false);
      setSelectedExecutionMessageId(null);
    }
  };

  const handleBulkDeleteRecent = async () => {
    if (selectedRecentIds.length === 0) return;
    if (!window.confirm(`确认删除选中的 ${selectedRecentIds.length} 个最近对话吗？`)) return;
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
    if (nextActiveId) {
      const detail = await fetchConversation(nextActiveId);
      const nextMessages = toUiMessages(detail);
      setActiveConversation(detail);
      setMessages(nextMessages);
      setTurns(detail.execution_log ?? []);
      setSelectedExecutionMessageId(findLatestExecutionMessageId(nextMessages));
    } else {
      setActiveConversation(null);
      setMessages([]);
      setTurns([]);
      setExecutionPanelOpen(false);
      setSelectedExecutionMessageId(null);
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
    const name = window.prompt("请输入分组名称", "新分组");
    if (!name) return;
    await createGroup(name);
    const nextState = await fetchState();
    setState(nextState);
    syncConversationList(nextState);
  };

  const handleRenameGroup = async (group: GroupSummary) => {
    const name = window.prompt("请输入新的分组名称", group.name);
    if (!name) return;
    await renameGroup(group.id, name);
    const nextState = await fetchState();
    setState(nextState);
    syncConversationList(nextState);
  };

  const handleDeleteGroup = async (group: GroupSummary) => {
    if (!window.confirm(`确认删除分组“${group.name}”吗？分组内会话会回到未分组。`)) return;
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
    resetStreamingAssistant();

    let conversationId = activeConversationId;
    // 中文注释：空首页首次发送时，先创建真实会话，再切入线程态。
    if (!conversationId) {
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
    scrollChatToBottom("smooth");

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
            // 中文注释：当前运行态摘要进入消息级思考胶囊和右侧执行过程面板，不再塞进聊天正文。
            setTurns(payload.execution_log);
            setMessages((items) => {
              const copy = [...items];
              const last = copy[copy.length - 1];
              if (last?.role === "assistant") {
                copy[copy.length - 1] = { ...last, executionLog: payload.execution_log, pending: true };
              }
              return copy;
            });
            setSelectedExecutionMessageId((current) => current ?? messages[messages.length - 1]?.id ?? null);
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
            setSelectedExecutionMessageId((current) => current ?? findLatestExecutionMessageId(nextMessages));
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

  const handleOpenExecutionPanel = (messageId: string) => {
    const next = resolveExecutionPanelToggle(selectedExecutionMessageId, executionPanelOpen, messageId);
    setSelectedExecutionMessageId(next.messageId);
    setExecutionPanelOpen(next.open);
  };

  useEffect(() => {
    if (!selectedExecutionMessageId) return;
    const exists = messages.some((message) => message.id === selectedExecutionMessageId);
    if (!exists) {
      setExecutionPanelOpen(false);
      setSelectedExecutionMessageId(null);
    }
  }, [messages, selectedExecutionMessageId]);

  if (state && !state.configured) {
    return (
      <main className="flex h-screen h-dvh items-center justify-center overflow-hidden bg-app-bg p-6">
        <section className="max-w-2xl rounded-[28px] border border-app-line bg-white p-8 shadow-panel">
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
    <div
      style={
        {
          "--sidebar-width": sidebarCollapsed ? "76px" : "280px",
          "--execution-width": executionPanelOpen ? "380px" : "0px",
        } as CSSProperties
      }
      className="grid h-screen h-dvh min-h-0 overflow-hidden bg-app-bg text-app-text xl:grid-cols-[var(--sidebar-width)_minmax(0,1fr)_var(--execution-width)] xl:transition-[grid-template-columns] xl:duration-300 xl:ease-out"
    >
      <div className="hidden xl:block">
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
      </div>

      <main className="flex min-h-0 min-w-0 flex-col overflow-hidden">
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
            <div className="mx-auto flex min-h-full w-full max-w-[920px] flex-col px-6 pb-10 pt-8">
              <div className="space-y-5">
                {messages.map((message, index) => {
                  const isStreamingAssistant =
                    streamAnimating && message.role === "assistant" && index === messages.length - 1;
                  return (
                    <ChatMessageView
                      key={message.id}
                      message={message}
                      streaming={isStreamingAssistant}
                      liveExecutionLog={isStreamingAssistant ? turns : []}
                      onOpenExecution={handleOpenExecutionPanel}
                    />
                  );
                })}
              </div>
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

      <ExecutionPanel
        message={selectedExecutionMessage}
        turns={selectedExecutionTurns}
        open={executionPanelOpen}
        onClose={() => setExecutionPanelOpen(false)}
      />

      <SidebarDialog open={sidebarOpen} onOpenChange={setSidebarOpen}>
        <div className="flex h-full min-h-0 flex-col">
          <div className="flex items-center justify-between border-b border-app-line px-5 py-4">
            <div className="text-base font-semibold text-app-text">会话列表</div>
            <button type="button" className="icon-button-subtle" onClick={() => setSidebarOpen(false)}>
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="min-h-0 flex-1">
            <ConversationSidebar
              state={state}
              conversations={conversations}
              groups={groups}
              activeConversationId={activeConversationId}
              running={running}
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
          </div>
        </div>
      </SidebarDialog>

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

      <ExecutionPanelDialog
        open={executionPanelOpen && !window.matchMedia("(min-width: 1280px)").matches}
        message={selectedExecutionMessage}
        turns={selectedExecutionTurns}
        onOpenChange={setExecutionPanelOpen}
      />

      <div id="last-reply-time" className="hidden">
        {lastReplyTime}
      </div>
    </div>
  );
}
