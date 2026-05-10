import { Button, Dropdown } from "antd";
import { Folder, FolderPlus, MoreHorizontal, PanelLeft, Pin, Plus, Sparkles } from "lucide-react";
import type { ConversationSummary, GroupSummary, RuntimeState } from "../../types";
import { buildGroups } from "../../domain/conversation-groups";
import { previewText } from "../../domain/message-text";
import { buildBulkDeleteLabel } from "../../state/sidebar-selection";
import { ConversationActions } from "./ConversationActions";

export function ConversationSidebar({
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
    `ga-sidebar-row group flex min-h-[40px] w-full items-center gap-2 border px-2.5 py-2 text-left transition ${
      activeConversationId === conversationId
        ? "is-active border-app-line text-app-textStrong"
        : "border-transparent text-app-text"
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
        <div className="ga-sidebar-brand flex items-center gap-3">
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
                置顶对话 · {pinned.length}
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
                  <div className="flex min-w-0 items-center gap-2 text-[13px] font-medium text-app-text/90">
                    <Folder className="h-3.5 w-3.5 shrink-0 text-app-muted" />
                    <span className="truncate">{group.name}</span>
                    <span className="ga-sidebar-meta shrink-0">{group.conversations.length}</span>
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
              <div className="sidebar-section-title px-0">最近对话 · {ungrouped.length}</div>
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
