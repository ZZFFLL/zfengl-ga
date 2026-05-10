import { CSSProperties, FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { App as AntApp, Button, ConfigProvider, Drawer, Dropdown, Input, Modal, Select, Tag, Tooltip } from "antd";
import type { MenuProps } from "antd";
import {
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
} from "lucide-react";
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
  buildBulkDeleteLabel,
  pruneSelectedConversations,
  toggleSelectedConversation,
} from "./state/sidebar-selection";
import { ChatHome } from "./components/chat/ChatHome";
import { ChatMessageView } from "./components/chat/ChatMessageView";
import { buildGroups } from "./domain/conversation-groups";
import { previewText, sanitizeDisplayText } from "./domain/message-text";
import { formatMessageTime, nowLabel } from "./domain/time";
import { nextSmoothContent, prefersReducedMotion, streamStepInterval } from "./domain/streaming-text";
import { gaTheme } from "./theme";

const id = () => Math.random().toString(36).slice(2);
const DEFAULT_CONTINUE_COMMAND = "/continue 1";

type ContinueCompatResult = {
  message: string;
  history: Array<{ role: "user" | "assistant"; content: string }>;
};

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
    <form className="shrink-0 border-t border-app-line bg-white/86 px-3 py-3 backdrop-blur md:px-4 md:py-4" onSubmit={onSubmit}>
      <div className="ga-composer-surface mx-auto max-w-[900px] rounded-xl px-4 py-3">
        <textarea
          id="chat-composer-draft"
          name="chat-composer-draft"
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
              <Button
                icon={<Square className="h-4 w-4" aria-hidden="true" />}
                onClick={onAbort}
              >
                停止
              </Button>
            ) : null}
            <Button
              type="primary"
              htmlType="submit"
              shape="circle"
              disabled={!draft.trim() || running || !state?.configured}
              aria-label="发送"
              icon={<Send className="h-4 w-4" aria-hidden="true" />}
            >
            </Button>
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
  const topMenuItems: MenuProps["items"] = [
    {
      key: "new",
      label: "新建空白会话",
      icon: <RotateCcw className="h-4 w-4" aria-hidden="true" />,
      disabled: !state?.configured || running,
      onClick: onCreateConversation,
    },
    {
      key: "refresh",
      label: "刷新状态",
      icon: <RefreshCcw className="h-4 w-4" aria-hidden="true" />,
      onClick: onRefresh,
    },
    {
      key: "reinject",
      label: "重新注入 System Prompt",
      icon: <RefreshCcw className="h-4 w-4" aria-hidden="true" />,
      disabled: !state?.configured || running,
      onClick: onReinject,
    },
    {
      key: "autonomous",
      label: state?.autonomous_enabled ? "关闭自主行动" : "开启自主行动",
      icon: state?.autonomous_enabled ? (
        <PauseCircle className="h-4 w-4" aria-hidden="true" />
      ) : (
        <PlayCircle className="h-4 w-4" aria-hidden="true" />
      ),
      disabled: !state?.configured || running,
      onClick: () => onAutonomous(!state?.autonomous_enabled),
    },
    { type: "divider" },
    {
      key: "continue",
      label: "恢复旧会话（兼容）",
      icon: <MessageSquareText className="h-4 w-4" aria-hidden="true" />,
      disabled: running,
      onClick: onOpenContinue,
    },
  ];

  return (
    <header className="ga-topbar shrink-0">
      <div className="flex min-h-[52px] items-center gap-2.5 px-3 py-2 md:px-5">
        <Tooltip title="打开会话侧栏">
          <Button
            type="text"
            className="xl:hidden"
            aria-label="打开会话侧栏"
            icon={<Menu className="h-5 w-5" aria-hidden="true" />}
            onClick={onOpenSidebar}
          />
        </Tooltip>

        <div className="min-w-0 flex items-center gap-3">
          <div className="min-w-0">
            <div className="truncate text-[15px] font-semibold text-app-textStrong">{conversationTitle}</div>
            <div className="mt-0.5 flex min-w-0 items-center gap-2 text-xs text-app-muted">
              <span className="truncate">{running ? "任务执行中" : state?.configured ? "准备就绪" : "未配置"}</span>
            </div>
          </div>
        </div>

        <div className="ml-auto flex min-w-0 items-center gap-2">
          <div className="hidden min-h-9 min-w-0 items-center gap-2 rounded-xl border border-app-line bg-white px-2 py-1 shadow-[0_1px_0_rgba(31,41,55,0.03)] sm:flex">
            <span className="shrink-0 text-[11px] font-semibold uppercase text-app-muted">
              Model
            </span>
            <Select
              aria-label="选择当前模型"
              className="ga-model-select min-w-[168px]"
              size="small"
              variant="borderless"
              value={state?.current_llm?.index ?? 0}
              disabled={!state?.configured || running}
              options={(state?.llms ?? []).map((llm) => ({
                value: llm.index,
                label: llm.current ? `${llm.name} · 当前` : llm.name,
              }))}
              onChange={(value) => onSwitchLlm(Number(value))}
            />
          </div>

          <StatusBadge state={state} />

          {running ? (
            <Button
              type="primary"
              icon={<Square className="h-4 w-4" aria-hidden="true" />}
              onClick={onAbort}
            >
              停止任务
            </Button>
          ) : null}

          <Dropdown
            menu={{ items: topMenuItems }}
            trigger={["click"]}
            placement="bottomRight"
            overlayClassName="ga-dropdown"
          >
            <Button
              type="text"
              aria-label="更多 GA 操作"
              icon={<MoreHorizontal className="h-5 w-5" aria-hidden="true" />}
            />
          </Dropdown>
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
    <Modal
      open={open}
      title="恢复旧会话（兼容入口）"
      width={720}
      centered
      destroyOnClose={false}
      onCancel={() => onOpenChange(false)}
      footer={null}
      className="ga-modal"
    >
      <p className="mt-1 text-sm leading-7 text-app-muted">
        这里保留 `/continue` 兼容能力，但不会把旧日志体系改成新会话真相源。
      </p>

      <form className="mt-6 space-y-4" onSubmit={onSubmit}>
        <div className="rounded-2xl border border-app-line bg-app-surface px-4 py-4">
          <label className="mb-2 block text-sm font-medium text-app-text" htmlFor="continue-command">
            兼容命令
          </label>
          <Input
            id="continue-command"
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
            <section className="rounded-2xl border border-app-line bg-app-surface px-4 py-4">
              <div className="text-sm font-semibold text-app-text">执行结果</div>
              <div className="mt-3 whitespace-pre-wrap text-sm leading-7 text-app-text">{result.message}</div>
            </section>

            <section className="rounded-2xl border border-app-line bg-app-surface px-4 py-4">
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm font-semibold text-app-text">兼容历史预览</div>
                <Tag bordered={false}>{result.history.length}</Tag>
              </div>
              <div className="mt-3 max-h-[280px] space-y-3 overflow-y-auto">
                {result.history.length === 0 ? (
                  <div className="text-sm text-app-muted">这次兼容恢复没有返回可展示的历史记录。</div>
                ) : (
                  result.history.map((message, index) => (
                    <div key={`${message.role}-${index}`} className="rounded-xl bg-white px-4 py-3 ring-1 ring-app-line/70">
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
          <Button onClick={() => onOpenChange(false)}>关闭</Button>
          <Button type="primary" htmlType="submit" loading={loading} disabled={!command.trim()}>
            执行兼容恢复
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function ConversationActions({
  conversation,
  groups,
  running,
  actionsAlwaysVisible = false,
  onRename,
  onDelete,
  onPin,
  onMove,
}: {
  conversation: ConversationSummary;
  groups: GroupSummary[];
  running: boolean;
  actionsAlwaysVisible?: boolean;
  onRename: (conversation: ConversationSummary) => void;
  onDelete: (conversation: ConversationSummary) => void;
  onPin: (conversation: ConversationSummary, pinned: boolean) => void;
  onMove: (conversation: ConversationSummary, groupId: string | null) => void;
}) {
  const handleMenuClick: MenuProps["onClick"] = ({ key }) => {
    const keyText = String(key);
    if (keyText === "rename") {
      onRename(conversation);
      return;
    }
    if (keyText === "pin") {
      onPin(conversation, !conversation.pinned);
      return;
    }
    if (keyText === "move-none") {
      onMove(conversation, null);
      return;
    }
    if (keyText.startsWith("move-")) {
      onMove(conversation, keyText.slice("move-".length));
      return;
    }
    if (keyText === "delete") {
      onDelete(conversation);
    }
  };

  const items: MenuProps["items"] = [
    {
      key: "rename",
      label: "重命名",
      icon: <MessageSquareText className="h-4 w-4" aria-hidden="true" />,
    },
    {
      key: "pin",
      label: conversation.pinned ? "取消置顶" : "置顶",
      icon: conversation.pinned ? (
        <PinOff className="h-4 w-4" aria-hidden="true" />
      ) : (
        <Pin className="h-4 w-4" aria-hidden="true" />
      ),
    },
    {
      key: "move",
      label: "移动到分组",
      icon: <Folder className="h-4 w-4" aria-hidden="true" />,
      children: [
        {
          key: "move-none",
          label: "未分组",
        },
        ...groups.map((group) => ({
          key: `move-${group.id}`,
          label: group.name,
        })),
      ],
    },
    { type: "divider" },
    {
      key: "delete",
      danger: true,
      label: "删除",
      icon: <Trash2 className="h-4 w-4" aria-hidden="true" />,
    },
  ];

  return (
    <Dropdown menu={{ items, onClick: handleMenuClick }} trigger={["click"]} placement="bottomRight" overlayClassName="ga-dropdown">
      <Button
        type="text"
        size="small"
        className={`shrink-0 text-app-muted transition ${
          actionsAlwaysVisible ? "opacity-100" : "opacity-0 group-hover:opacity-100 focus:opacity-100"
        }`}
        aria-label="会话更多操作"
        disabled={running}
        icon={<MoreHorizontal className="h-4 w-4" aria-hidden="true" />}
        onClick={(event) => event.stopPropagation()}
      />
    </Dropdown>
  );
}

function ConversationSidebar({
  state,
  conversations,
  groups,
  activeConversationId,
  running,
  actionsAlwaysVisible = false,
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
  actionsAlwaysVisible?: boolean;
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
  const conversationRowClass = (conversationId: string) =>
    `group flex min-h-[42px] w-full items-center gap-2 rounded-xl border px-2.5 py-2 text-left transition ${
      activeConversationId === conversationId
        ? "ga-sidebar-active border-app-line text-app-textStrong"
        : "border-transparent text-app-text hover:border-app-line hover:bg-white/64"
    }`;

  if (collapsed) {
    return (
      <aside className="ga-sidebar flex h-full min-h-0 flex-col items-center px-2 py-3">
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
    <aside className="ga-sidebar flex h-full min-h-0 flex-col">
      <div className="px-4 pb-3 pt-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white text-app-primary ring-1 ring-app-line">
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
                  <div
                    key={conversation.id}
                    className={conversationRowClass(conversation.id)}
                  >
                    <button
                      type="button"
                      className="flex min-w-0 flex-1 items-start gap-2.5 text-left disabled:cursor-not-allowed disabled:opacity-60"
                      onClick={() => onSelectConversation(conversation.id)}
                      disabled={running && activeConversationId !== conversation.id}
                    >
                      <Pin className="mt-0.5 h-4 w-4 shrink-0 text-app-primary" />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium">{conversation.title}</div>
                        <div className="mt-1 truncate text-xs text-app-muted">{previewText(conversation.preview)}</div>
                      </div>
                    </button>
                    <ConversationActions
                      conversation={conversation}
                      groups={groups}
                      running={running}
                      actionsAlwaysVisible={actionsAlwaysVisible}
                      onRename={onRenameConversation}
                      onDelete={onDeleteConversation}
                      onPin={onPinConversation}
                      onMove={onMoveConversation}
                    />
                  </div>
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
                  <Dropdown
                    menu={{
                      items: [
                        {
                          key: "rename",
                          label: "重命名分组",
                          onClick: () => onRenameGroup(group),
                        },
                        {
                          key: "delete",
                          danger: true,
                          label: "删除分组",
                          onClick: () => onDeleteGroup(group),
                        },
                      ],
                    }}
                    trigger={["click"]}
                    placement="bottomRight"
                    overlayClassName="ga-dropdown"
                  >
                    <Button
                      type="text"
                      size="small"
                      aria-label="分组更多操作"
                      disabled={running}
                      icon={<MoreHorizontal className="h-4 w-4" aria-hidden="true" />}
                      onClick={(event) => event.stopPropagation()}
                    />
                  </Dropdown>
                </div>
                <div className="sidebar-list">
                  {group.conversations.length === 0 ? (
                    <div className="rounded-xl px-3 py-2 text-xs text-app-muted">分组里还没有会话</div>
                  ) : (
                    group.conversations.map((conversation) => (
                      <div
                        key={conversation.id}
                        className={conversationRowClass(conversation.id)}
                      >
                        <button
                          type="button"
                          className="min-w-0 flex-1 text-left disabled:cursor-not-allowed disabled:opacity-60"
                          onClick={() => onSelectConversation(conversation.id)}
                          disabled={running && activeConversationId !== conversation.id}
                        >
                          <div className="truncate text-sm font-medium">{conversation.title}</div>
                          <div className="mt-1 truncate text-xs text-app-muted">{previewText(conversation.preview)}</div>
                        </button>
                        <ConversationActions
                          conversation={conversation}
                          groups={groups}
                          running={running}
                          actionsAlwaysVisible={actionsAlwaysVisible}
                          onRename={onRenameConversation}
                          onDelete={onDeleteConversation}
                          onPin={onPinConversation}
                          onMove={onMoveConversation}
                        />
                      </div>
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
                <div
                  key={conversation.id}
                  className={conversationRowClass(conversation.id)}
                >
                  <button
                    type="button"
                    className="flex min-w-0 flex-1 items-center gap-2.5 text-left disabled:cursor-not-allowed disabled:opacity-60"
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
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{conversation.title}</span>
                      <span className="mt-1 block truncate text-xs text-app-muted">{previewText(conversation.preview)}</span>
                    </span>
                  </button>
                  {selectingRecent ? null : (
                    <ConversationActions
                      conversation={conversation}
                      groups={groups}
                      running={running}
                      actionsAlwaysVisible={actionsAlwaysVisible}
                      onRename={onRenameConversation}
                      onDelete={onDeleteConversation}
                      onPin={onPinConversation}
                      onMove={onMoveConversation}
                    />
                  )}
                </div>
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
    <Drawer
      open={open}
      placement="left"
      width="min(92vw, 340px)"
      title="会话列表"
      aria-label="会话列表"
      className="ga-sidebar-drawer xl:hidden"
      styles={{
        body: { padding: 0 },
        header: { borderBottom: "1px solid #d8deeb" },
      }}
      onClose={() => onOpenChange(false)}
    >
      {children}
    </Drawer>
  );
}

function GenericAgentWebUI() {
  const { modal } = AntApp.useApp();
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
  const autoScrollPinnedRef = useRef(true);

  const running = Boolean(state?.running);
  const activeConversationId = activeConversation?.summary.id ?? state?.active_conversation_id ?? null;
  const lastReplyTime = state?.last_reply_time || 0;
  const hasThread = messages.length > 0;
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
    if (!autoScrollPinnedRef.current) return;
    scrollChatToBottom(streamAnimating ? "auto" : "smooth");
  }, [messages, streamAnimating]);

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
        width: 460,
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
    autoScrollPinnedRef.current = true;
    const detail = await activateConversation(conversationId);
    setActiveConversation(detail);
    setMessages(toUiMessages(detail));
    setTurns(detail.execution_log ?? []);
    setSidebarOpen(false);
    const nextState = await fetchState();
    setState(nextState);
    syncConversationList(nextState);
  };

  const handleCreateConversation = async (titleHint = "") => {
    setError("");
    autoScrollPinnedRef.current = true;
    const conversation = await createConversation(titleHint);
    const detail = await fetchConversation(conversation.id);
    setActiveConversation(detail);
    setMessages([]);
    setTurns([]);
    resetStreamingAssistant();
    const nextState = await fetchState();
    setState(nextState);
    syncConversationList(nextState);
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
    if (nextActiveId) {
      autoScrollPinnedRef.current = true;
      const detail = await fetchConversation(nextActiveId);
      setActiveConversation(detail);
      setMessages(toUiMessages(detail));
      setTurns(detail.execution_log ?? []);
    } else {
      setActiveConversation(null);
      setMessages([]);
      setTurns([]);
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
    if (nextActiveId) {
      autoScrollPinnedRef.current = true;
      const detail = await fetchConversation(nextActiveId);
      const nextMessages = toUiMessages(detail);
      setActiveConversation(detail);
      setMessages(nextMessages);
      setTurns(detail.execution_log ?? []);
    } else {
      setActiveConversation(null);
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
        } as CSSProperties
      }
      className="ga-shell grid h-screen h-dvh min-h-0 overflow-hidden bg-app-bg text-app-text xl:grid-cols-[var(--sidebar-width)_minmax(0,1fr)] xl:transition-[grid-template-columns] xl:duration-300 xl:ease-out"
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
    </div>
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
