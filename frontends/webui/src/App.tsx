import { FormEvent, KeyboardEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { AnimatePresence, motion } from "framer-motion";
import {
  Check,
  Circle,
  ChevronDown,
  Folder,
  FolderPlus,
  Menu,
  MessageSquareText,
  MoreHorizontal,
  PanelRightClose,
  PanelRightOpen,
  PauseCircle,
  Pin,
  PinOff,
  PlayCircle,
  Plus,
  RefreshCcw,
  RotateCcw,
  Send,
  SlidersHorizontal,
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
  resetConversation,
  setAutonomous,
  startChat,
  streamTask,
  switchLlm,
} from "./api";
import type {
  ConversationDetail,
  ConversationMessage,
  ConversationSummary,
  ExecutionTurn,
  GroupSummary,
  RuntimeState,
  StreamEvent,
} from "./types";

const nowLabel = () => new Date().toLocaleString();
const id = () => Math.random().toString(36).slice(2);
const STREAM_STEP_INTERVAL_MS = 40;
const STREAM_DONE_CATCHUP_INTERVAL_MS = 8;

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
};

const FINAL_INFO_BLOCK_RE = /\n*`{3,}\s*\n?\[Info\]\s*Final response to user\.\s*\n?`{3,}\s*$/i;
const FINAL_INFO_TRAIL_RE = /\n*\[Info\]\s*Final response to user\.\s*(?:`{3,}\s*)*$/i;

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
  const step = done ? Math.min(24, remaining.length) : Math.min(3, remaining.length);
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
  cleaned = cleaned.replace(FINAL_INFO_BLOCK_RE, "");
  cleaned = cleaned.replace(FINAL_INFO_TRAIL_RE, "");
  return cleaned.trim();
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
    <span className={`inline-flex min-h-9 items-center gap-2 rounded-full px-3 text-sm font-medium ${statusTone(state)}`}>
      <Circle className="h-3 w-3 fill-current" aria-hidden="true" />
      {label}
    </span>
  );
}

function SurfaceHeader({
  eyebrow,
  title,
  icon,
  rightSlot,
}: {
  eyebrow: string;
  title: string;
  icon?: ReactNode;
  rightSlot?: ReactNode;
}) {
  return (
    <div className="flex min-h-[68px] items-center justify-between border-b border-app-line bg-white px-5">
      <div className="flex min-w-0 items-center gap-3">
        {icon ? (
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-app-primarySoft text-app-primary">
            {icon}
          </div>
        ) : null}
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-app-muted">{eyebrow}</p>
          <h2 className="mt-1 truncate text-lg font-semibold text-app-text">{title}</h2>
        </div>
      </div>
      {rightSlot ? <div className="flex items-center gap-2">{rightSlot}</div> : null}
    </div>
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

function ChatMessageView({
  message,
  streaming = false,
}: {
  message: UiMessage;
  streaming?: boolean;
}) {
  const isUser = message.role === "user";
  return (
    <article className={`flex ${isUser ? "justify-end" : "justify-start"} ${streaming ? "smooth-message" : ""}`}>
      <div
        className={`max-w-[86%] rounded-[24px] px-5 py-4 shadow-sm ${
          isUser
            ? "bg-app-userBubble text-white"
            : "border border-app-line bg-white text-app-text"
        }`}
      >
        <div className={`mb-2 text-xs ${isUser ? "text-white/70" : "text-app-muted"}`}>
          {isUser ? "你" : message.role === "system" ? "System" : "GA"} · {message.time}
        </div>
        {isUser ? (
          <div className="message-content text-sm leading-7">{message.content}</div>
        ) : (
          <MarkdownContent content={message.content} streaming={streaming} />
        )}
      </div>
    </article>
  );
}

function EmptyHome({
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
    <section className="flex min-h-0 flex-1 items-center justify-center px-6 pb-10 pt-8">
      <div className="w-full max-w-[980px]">
        <div className="mx-auto max-w-2xl text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-app-primarySoft text-app-primary shadow-soft">
            <Sparkles className="h-7 w-7" aria-hidden="true" />
          </div>
          <h2 className="mt-8 text-5xl font-semibold tracking-tight text-app-text">你好，我是 GenericAgent</h2>
          <p className="mt-4 text-base leading-8 text-app-muted">
            极简、自我进化、自主执行。你可以直接交代任务，GA 会用浏览器、终端、文件系统和工具链把事情推进下去。
          </p>
        </div>

        <form className="mx-auto mt-12 max-w-3xl" onSubmit={onSubmit}>
          <div className="rounded-[32px] border border-app-line bg-white px-6 pb-4 pt-5 shadow-panel">
            <textarea
              className="min-h-[96px] w-full resize-none border-0 bg-transparent text-base leading-8 text-app-text placeholder:text-app-muted focus:outline-none"
              placeholder={running ? "任务运行中..." : "向 GenericAgent 提问"}
              value={draft}
              disabled={running || !state?.configured}
              onChange={(event) => onDraftChange(event.target.value)}
              onKeyDown={onKeyDown}
              rows={3}
            />
            <div className="mt-3 flex items-center justify-between gap-4">
              <div className="text-sm text-app-muted">支持自然语言任务输入，右侧保留 GA 控制能力。</div>
              <button
                type="submit"
                className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-app-primary text-white disabled:cursor-not-allowed disabled:bg-app-line"
                disabled={!draft.trim() || running || !state?.configured}
                aria-label="发送"
              >
                <Send className="h-5 w-5" aria-hidden="true" />
              </button>
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
    <form className="shrink-0 border-t border-app-line bg-white px-6 pb-6 pt-4" onSubmit={onSubmit}>
      <div className="rounded-[28px] border border-app-line bg-app-composer px-5 pb-3 pt-4 shadow-soft">
        <textarea
          className="min-h-[68px] w-full resize-none border-0 bg-transparent text-[15px] leading-7 text-app-text placeholder:text-app-muted focus:outline-none"
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
            {running && (
              <button
                type="button"
                className="icon-button-subtle"
                onClick={onAbort}
                aria-label="停止任务"
                title="停止任务"
              >
                <Square className="h-4 w-4" />
              </button>
            )}
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

function ControlPanel({
  state,
  turns,
  onRefresh,
  onSwitchLlm,
  onAbort,
  onReinject,
  onNew,
  onAutonomous,
  onTogglePanel,
  executionCollapsed,
  onToggleExecution,
  compact = false,
}: {
  state: RuntimeState | null;
  turns: ExecutionTurn[];
  onRefresh: () => void;
  onSwitchLlm: (index: number) => void;
  onAbort: () => void;
  onReinject: () => void;
  onNew: () => void;
  onAutonomous: (enabled: boolean) => void;
  onTogglePanel: () => void;
  executionCollapsed: boolean;
  onToggleExecution: () => void;
  compact?: boolean;
}) {
  return (
    <aside className={`flex h-full min-h-0 flex-col bg-white ${compact ? "" : "border-l border-app-line"}`}>
      <SurfaceHeader
        eyebrow="GA Controls"
        title="运行控制"
        icon={<SlidersHorizontal className="h-5 w-5" />}
        rightSlot={
          compact ? null : (
            <button
              type="button"
              className="icon-button-subtle"
              aria-label="收起运行控制"
              onClick={onTogglePanel}
            >
              <PanelRightClose className="h-5 w-5" />
            </button>
          )
        }
      />

      <div className="operation-scroll flex-1 space-y-5 overflow-y-auto px-5 py-5">
        <section className="space-y-3">
          <StatusBadge state={state} />
          <div className="rounded-2xl border border-app-line bg-app-surface p-4">
            <label className="mb-2 block text-sm font-medium text-app-text" htmlFor="llm-select">
              当前模型
            </label>
            <select
              id="llm-select"
              className="min-h-11 w-full rounded-xl border border-app-line bg-white px-3 text-sm text-app-text"
              value={state?.current_llm?.index ?? 0}
              onChange={(event) => onSwitchLlm(Number(event.target.value))}
              disabled={!state?.configured || state?.running}
            >
              {(state?.llms ?? []).map((llm) => (
                <option key={llm.index} value={llm.index}>
                  {llm.index}: {llm.name}
                </option>
              ))}
            </select>
            <p className="mt-2 text-xs leading-6 text-app-muted">
              切模型会让后续会话同步重新建立，运行中禁用切换以避免状态错乱。
            </p>
          </div>
        </section>

        <section className="space-y-2">
          <button className="control-button" type="button" onClick={onNew} disabled={!state?.configured || state?.running}>
            <RotateCcw className="h-4 w-4" />
            新建空白会话
          </button>
          <button className="control-button" type="button" onClick={onAbort} disabled={!state?.running}>
            <Square className="h-4 w-4" />
            停止当前任务
          </button>
          <button className="control-button" type="button" onClick={onReinject} disabled={!state?.configured || state?.running}>
            <RefreshCcw className="h-4 w-4" />
            重新注入 System Prompt
          </button>
          <button
            className="control-button"
            type="button"
            onClick={() => onAutonomous(!state?.autonomous_enabled)}
            disabled={!state?.configured || state?.running}
          >
            {state?.autonomous_enabled ? <PauseCircle className="h-4 w-4" /> : <PlayCircle className="h-4 w-4" />}
            {state?.autonomous_enabled ? "关闭自主行动" : "开启自主行动"}
          </button>
          <button className="control-button" type="button" onClick={onRefresh}>
            <Check className="h-4 w-4" />
            刷新状态
          </button>
        </section>

        <section className="rounded-2xl border border-app-line bg-app-surface p-4">
          <button
            type="button"
            className="flex w-full items-center justify-between text-left"
            onClick={onToggleExecution}
          >
            <h4 className="text-sm font-semibold text-app-text">执行摘要</h4>
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-white px-2 py-1 text-xs text-app-muted">{turns.length}</span>
              <ChevronDown className={`h-4 w-4 text-app-muted transition ${executionCollapsed ? "" : "rotate-180"}`} />
            </div>
          </button>
          {!executionCollapsed && (
            <div className="mt-3 max-h-[42vh] space-y-2 overflow-y-auto pr-1">
              {turns.length === 0 ? (
                <p className="text-xs leading-6 text-app-muted">当前会话还没有执行摘要。</p>
              ) : (
                turns.map((turn, index) => (
                  <details
                    key={`${turn.turn}-${index}`}
                    open={index === turns.length - 1}
                    className="rounded-xl bg-white px-3 py-3 text-sm text-app-text"
                  >
                    <summary className="cursor-pointer list-none font-medium">
                      Turn {turn.turn}
                      <span className="ml-2 text-xs text-app-muted">{turn.title}</span>
                    </summary>
                    <div className="mt-3 border-t border-app-line pt-3 text-xs leading-6 text-app-muted">
                      {turn.content ? <MarkdownContent content={turn.content} /> : "此轮没有 summary。"}
                    </div>
                  </details>
                ))
              )}
            </div>
          )}
        </section>
      </div>
    </aside>
  );
}

function ControlPanelRail({
  state,
  onExpand,
}: {
  state: RuntimeState | null;
  onExpand: () => void;
}) {
  return (
    <aside className="hidden h-full border-l border-app-line bg-white xl:flex xl:w-[64px] xl:flex-col xl:items-center xl:gap-3 xl:py-4">
      <button
        type="button"
        className="icon-button-subtle"
        aria-label="展开运行控制"
        onClick={onExpand}
      >
        <PanelRightOpen className="h-5 w-5" />
      </button>
      <Circle
        className={`h-3 w-3 ${state?.running ? "fill-app-success text-app-success" : "fill-app-primary text-app-primary"}`}
        aria-hidden="true"
      />
      <span className="text-[11px] font-semibold uppercase tracking-[0.22em] text-app-muted [writing-mode:vertical-rl]">
        Controls
      </span>
    </aside>
  );
}

function RightControlShell({
  collapsed,
  state,
  turns,
  onExpand,
  onCollapse,
  onRefresh,
  onSwitchLlm,
  onAbort,
  onReinject,
  onNew,
  onAutonomous,
  onToggleExecution,
  executionCollapsed,
}: {
  collapsed: boolean;
  state: RuntimeState | null;
  turns: ExecutionTurn[];
  onExpand: () => void;
  onCollapse: () => void;
  onRefresh: () => void;
  onSwitchLlm: (index: number) => void;
  onAbort: () => void;
  onReinject: () => void;
  onNew: () => void;
  onAutonomous: (enabled: boolean) => void;
  onToggleExecution: () => void;
  executionCollapsed: boolean;
}) {
  return (
    <AnimatePresence initial={false} mode="wait">
      {collapsed ? (
        <motion.aside
          key="rail"
          initial={{ width: 64, opacity: 0.7 }}
          animate={{ width: 64, opacity: 1 }}
          exit={{ width: 0, opacity: 0 }}
          transition={{ type: "spring", stiffness: 420, damping: 38, mass: 0.8 }}
          className="hidden h-full overflow-hidden border-l border-app-line bg-white xl:flex xl:flex-col xl:items-center xl:gap-3 xl:py-4"
        >
          <button
            type="button"
            className="icon-button-subtle"
            aria-label="展开运行控制"
            onClick={onExpand}
          >
            <PanelRightOpen className="h-5 w-5" />
          </button>
          <Circle
            className={`h-3 w-3 ${state?.running ? "fill-app-success text-app-success" : "fill-app-primary text-app-primary"}`}
            aria-hidden="true"
          />
          <span className="text-[11px] font-semibold uppercase tracking-[0.22em] text-app-muted [writing-mode:vertical-rl]">
            Controls
          </span>
        </motion.aside>
      ) : (
        <motion.aside
          key="panel"
          initial={{ width: 360, opacity: 0.7, x: 8 }}
          animate={{ width: 360, opacity: 1, x: 0 }}
          exit={{ width: 0, opacity: 0, x: 8 }}
          transition={{ type: "spring", stiffness: 380, damping: 34, mass: 0.9 }}
          className="hidden h-full min-h-0 overflow-hidden border-l border-app-line bg-white xl:flex xl:flex-col"
        >
          <ControlPanel
            state={state}
            turns={turns}
            onRefresh={onRefresh}
            onSwitchLlm={onSwitchLlm}
            onAbort={onAbort}
            onReinject={onReinject}
            onNew={onNew}
            onAutonomous={onAutonomous}
            onTogglePanel={onCollapse}
            executionCollapsed={executionCollapsed}
            onToggleExecution={onToggleExecution}
          />
        </motion.aside>
      )}
    </AnimatePresence>
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
        <DropdownMenu.Content
          className="dropdown-panel"
          sideOffset={8}
          align="end"
        >
          <DropdownMenu.Item className="dropdown-item" onSelect={() => onRename(conversation)}>
            <MessageSquareText className="h-4 w-4" />
            重命名
          </DropdownMenu.Item>
          <DropdownMenu.Item
            className="dropdown-item"
            onSelect={() => onPin(conversation, !conversation.pinned)}
          >
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
  onCreateConversation,
  onSelectConversation,
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
  onCreateConversation: () => void;
  onSelectConversation: (conversationId: string) => void;
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

  return (
    <aside className="flex h-full min-h-0 flex-col border-r border-app-line bg-app-sidebar">
      <div className="px-6 pb-4 pt-6">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h1 className="text-[34px] font-semibold tracking-tight text-app-text">GenericAgent</h1>
            <p className="mt-2 text-sm leading-6 text-app-muted">极简、自我进化、自主执行的本地 Agent 框架。</p>
          </div>
        </div>

        <button
          type="button"
          className="mt-5 inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-2xl bg-white px-4 text-sm font-medium text-app-text shadow-soft ring-1 ring-app-line transition hover:bg-app-surface disabled:cursor-not-allowed disabled:opacity-50"
          onClick={onCreateConversation}
          disabled={!state?.configured || running}
        >
          <Plus className="h-4 w-4" />
          新建对话
        </button>
      </div>

      <div className="operation-scroll min-h-0 flex-1 overflow-y-auto px-4 pb-6">
        <div className="space-y-6">
          {pinned.length > 0 && (
            <section>
              <div className="mb-2 px-2 text-xs font-semibold uppercase tracking-[0.18em] text-app-muted">
                置顶对话
              </div>
              <div className="space-y-1.5">
                {pinned.map((conversation) => (
                  <button
                    key={conversation.id}
                    type="button"
                    className={`sidebar-item ${activeConversationId === conversation.id ? "active" : ""}`}
                    onClick={() => onSelectConversation(conversation.id)}
                    disabled={running && activeConversationId !== conversation.id}
                  >
                    <div className="flex min-w-0 flex-1 items-start gap-3">
                      <Pin className="mt-1 h-4 w-4 shrink-0 text-app-primary" />
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
          )}

          <section>
            <div className="mb-2 flex items-center justify-between px-2">
              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-app-muted">对话分组</div>
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
              <div key={group.id} className="mb-4">
                <div className="mb-1 flex items-center justify-between px-2">
                  <div className="flex items-center gap-2 text-sm font-medium text-app-text">
                    <Folder className="h-4 w-4 text-app-muted" />
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
                <div className="space-y-1.5">
                  {group.conversations.length === 0 ? (
                    <div className="rounded-2xl px-4 py-3 text-xs text-app-muted">分组里还没有会话</div>
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

            <div className="mb-2 px-2 text-xs font-semibold uppercase tracking-[0.18em] text-app-muted">最近对话</div>
            <div className="space-y-1.5">
              {ungrouped.map((conversation) => (
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
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/28 lg:hidden" />
        <Dialog.Content className="fixed inset-y-0 left-0 z-50 w-[min(92vw,360px)] border-r border-app-line bg-app-sidebar shadow-panel lg:hidden">
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function ControlDialog({
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
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 w-[min(92vw,360px)] bg-white shadow-panel xl:hidden">
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
  const [controlOpen, setControlOpen] = useState(false);
  const [controlsCollapsed, setControlsCollapsed] = useState(false);
  const [executionCollapsed, setExecutionCollapsed] = useState(false);
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
      }
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
    // 中文注释：如果流式目标被后端整体替换，直接用最新内容覆盖，避免动画状态错乱。
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
    if (done && content.startsWith(streamDisplayedRef.current)) {
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

  const syncConversationList = (nextState: RuntimeState | null) => {
    if (nextState?.conversations) {
      setConversations(nextState.conversations);
    }
    if (nextState?.groups) {
      setGroups(nextState.groups);
    }
  };

  const openConversation = async (conversationId: string) => {
    if (running && activeConversationId !== conversationId) {
      setError("当前任务仍在运行，请先停止任务后再切换会话。");
      return;
    }
    // 中文注释：切换会话时先切 UI 与中间层 active 会话，不在这里直接触发 GA 重放。
    setError("");
    const detail = await activateConversation(conversationId);
    setActiveConversation(detail);
    setMessages(toUiMessages(detail));
    setSidebarOpen(false);
    const nextState = await fetchState();
    setState(nextState);
    syncConversationList(nextState);
  };

  const handleCreateConversation = async () => {
    setError("");
    const conversation = await createConversation();
    const detail = await fetchConversation(conversation.id);
    setActiveConversation(detail);
    setMessages([]);
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
    } else {
      setActiveConversation(null);
      setMessages([]);
    }
  };

  const handlePinConversation = async (conversation: ConversationSummary, pinned: boolean) => {
    await pinConversation(conversation.id, pinned);
    const nextState = await fetchState();
    setState(nextState);
    syncConversationList(nextState);
  };

  const handleMoveConversation = async (conversation: ConversationSummary, groupId: string | null) => {
    await fetch("/api/conversations/" + conversation.id + "/move", {
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
    resetStreamingAssistant();

    let conversationId = activeConversationId;
    // 中文注释：空首页首发消息时，先由中间层创建真实会话，再进入线程态。
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
    };
    setMessages((items) => [...items, userMessage]);
    scrollChatToBottom("smooth");

    try {
      const { task_id } = await startChat(conversationId, prompt);
      const nextState = await fetchState();
      setState(nextState);
      syncConversationList(nextState);
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
            // 中文注释：执行摘要与聊天正文分流展示，避免把规划内容混入主消息流。
            setTurns(payload.execution_log);
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
            setMessages(toUiMessages(detail));
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

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSubmit();
    }
  };

  const desktopShellClass = useMemo(
    () => "grid h-screen h-dvh min-h-0 overflow-hidden bg-app-bg text-app-text xl:grid-cols-[320px_minmax(0,1fr)_auto]",
    [],
  );

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
    <div className={desktopShellClass}>
      <div className="hidden xl:block">
        <ConversationSidebar
          state={state}
          conversations={conversations}
          groups={groups}
          activeConversationId={activeConversationId}
          running={running}
          onCreateConversation={() => void handleCreateConversation()}
          onSelectConversation={(conversationId) => void openConversation(conversationId)}
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
        <SurfaceHeader
          eyebrow="Conversation"
          title={activeConversation?.summary.title || "新建对话"}
          icon={<MessageSquareText className="h-5 w-5" />}
          rightSlot={
            <>
              <button
                type="button"
                className="icon-button-subtle xl:hidden"
                aria-label="打开会话侧栏"
                onClick={() => setSidebarOpen(true)}
              >
                <Menu className="h-5 w-5" />
              </button>
              <button
                type="button"
                className="icon-button-subtle xl:hidden"
                aria-label="打开 GA 控制面板"
                onClick={() => setControlOpen(true)}
              >
                <PanelRightOpen className="h-5 w-5" />
              </button>
            </>
          }
        />

        {error && (
          <div className="shrink-0 border-b border-app-line bg-app-danger/10 px-6 py-3 text-sm text-app-danger">
            {error}
          </div>
        )}

        <section ref={chatScrollRef} className="operation-scroll min-h-0 flex-1 overflow-y-auto">
          {!hasThread ? (
            <EmptyHome
              state={state}
              draft={draft}
              running={running}
              onDraftChange={setDraft}
              onKeyDown={handleKeyDown}
              onSubmit={(event) => void handleSubmit(event)}
            />
          ) : (
            <div className="mx-auto flex min-h-full w-full max-w-4xl flex-col px-6 pb-8 pt-8">
              <div className="mb-6">
                <h2 className="text-[30px] font-semibold tracking-tight text-app-text">
                  {activeConversation?.summary.title || "当前会话"}
                </h2>
                <p className="mt-2 text-sm leading-7 text-app-muted">
                  当前会话基于 GA 的执行能力持续推进，可在右侧控制模型和运行状态。
                </p>
              </div>
              <div className="space-y-5">
                {messages.map((message) => (
                  <ChatMessageView
                    key={message.id}
                    message={message}
                    streaming={
                      streamAnimating && message.role === "assistant" && message === messages[messages.length - 1]
                    }
                  />
                ))}
              </div>
            </div>
          )}
        </section>

        {hasThread && (
          <Composer
            state={state}
            draft={draft}
            running={running}
            onDraftChange={setDraft}
            onKeyDown={handleKeyDown}
            onSubmit={(event) => void handleSubmit(event)}
            onAbort={() => void abortTask().then(refreshState)}
          />
        )}
      </main>

      <RightControlShell
        collapsed={controlsCollapsed}
        state={state}
        turns={turns}
        onExpand={() => setControlsCollapsed(false)}
        onCollapse={() => setControlsCollapsed(true)}
        onRefresh={() => void refreshState()}
        onSwitchLlm={(index) => void switchLlm(index).then((next) => { setState(next); syncConversationList(next); })}
        onAbort={() => void abortTask().then(refreshState)}
        onReinject={() => void reinject().then(refreshState)}
        onNew={() => void handleCreateConversation()}
        onAutonomous={(enabled) =>
          void setAutonomous(enabled).then((result) => {
            setState((prev) => (prev ? { ...prev, autonomous_enabled: result.autonomous_enabled } : prev));
          })
        }
        onToggleExecution={() => setExecutionCollapsed((value) => !value)}
        executionCollapsed={executionCollapsed}
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
              onCreateConversation={() => void handleCreateConversation()}
              onSelectConversation={(conversationId) => void openConversation(conversationId)}
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

      <ControlDialog open={controlOpen} onOpenChange={setControlOpen}>
        <div className="flex h-full min-h-0 flex-col">
          <div className="flex items-center justify-between border-b border-app-line px-5 py-4">
            <div className="text-base font-semibold text-app-text">GA 控制区</div>
            <button type="button" className="icon-button-subtle" onClick={() => setControlOpen(false)}>
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="min-h-0 flex-1">
            <ControlPanel
              state={state}
              turns={turns}
              compact
              onRefresh={() => void refreshState()}
              onSwitchLlm={(index) =>
                void switchLlm(index).then((next) => {
                  setState(next);
                  syncConversationList(next);
                })
              }
              onAbort={() => void abortTask().then(refreshState)}
              onReinject={() => void reinject().then(refreshState)}
              onNew={() => void handleCreateConversation()}
              onAutonomous={(enabled) =>
                void setAutonomous(enabled).then((result) => {
                  setState((prev) => (prev ? { ...prev, autonomous_enabled: result.autonomous_enabled } : prev));
                })
              }
              onTogglePanel={() => setControlOpen(false)}
              executionCollapsed={executionCollapsed}
              onToggleExecution={() => setExecutionCollapsed((value) => !value)}
            />
          </div>
        </div>
      </ControlDialog>

      <div id="last-reply-time" className="hidden">
        {lastReplyTime}
      </div>
    </div>
  );
}
