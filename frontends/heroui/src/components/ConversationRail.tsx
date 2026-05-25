import { Avatar, Button } from "@heroui/react";
import { CheckSquare, MessageCircle, MessageSquarePlus, Square, Trash2, X } from "lucide-react";
import { useState } from "react";
import type { SessionRecord } from "../types";

type ConversationRailProps = {
  sessions: SessionRecord[];
  activeSessionId: string;
  modelLabel: string;
  onCreateSession: () => void;
  onDeleteSessions: (sessionIds: string[]) => void;
  onSelectSession: (sessionId: string) => void;
};

export function ConversationRail({
  sessions,
  activeSessionId,
  modelLabel,
  onCreateSession,
  onDeleteSessions,
  onSelectSession,
}: ConversationRailProps) {
  const [isDeleting, setIsDeleting] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const allSelected = sessions.length > 0 && selectedIds.length === sessions.length;

  function toggleDeleting() {
    setIsDeleting((current) => !current);
    setSelectedIds([]);
  }

  function toggleSession(sessionId: string) {
    setSelectedIds((current) =>
      current.includes(sessionId) ? current.filter((id) => id !== sessionId) : [...current, sessionId],
    );
  }

  function toggleSelectAll() {
    setSelectedIds(allSelected ? [] : sessions.map((session) => session.id));
  }

  function deleteSelected() {
    onDeleteSessions(selectedIds);
    setIsDeleting(false);
    setSelectedIds([]);
  }

  return (
    <aside className="workspace-sidebar" aria-label="工作区导航">
      <div className="sidebar-profile">
        <Avatar className="profile-avatar" size="md">
          <Avatar.Fallback>B</Avatar.Fallback>
        </Avatar>
        <div className="profile-copy">
          <strong>GenericAgent 工作台</strong>
          <span>{modelLabel}</span>
          <div className="session-count-badge" aria-label="会话数">
            {sessions.length} 会话
          </div>
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="主要操作">
        <Button className="sidebar-nav-item" fullWidth onPress={onCreateSession} variant="tertiary">
          <MessageSquarePlus size={18} />
          <span>新建聊天</span>
        </Button>
      </nav>

      <div className="sidebar-divider" />
      <div className="recent-heading-row">
        <div className="recent-label">最近</div>
        <Button
          aria-label={isDeleting ? "取消批量删除" : "批量删除会话"}
          className="batch-delete-toggle"
          isDisabled={sessions.length === 0}
          isIconOnly
          onPress={toggleDeleting}
          size="sm"
          variant="ghost"
        >
          {isDeleting ? <X size={15} /> : <Trash2 size={15} />}
        </Button>
      </div>

      <nav className="recent-list" aria-label="最近会话">
        {sessions.map((session, index) => (
          <Button
            className={`recent-item ${session.id === activeSessionId ? "is-active" : ""}`}
            fullWidth
            key={session.id}
            onPress={() => (isDeleting ? toggleSession(session.id) : onSelectSession(session.id))}
            variant="tertiary"
          >
            {isDeleting ? (
              selectedIds.includes(session.id) ? (
                <CheckSquare size={18} />
              ) : (
                <Square size={18} />
              )
            ) : (
              <MessageCircle size={18} />
            )}
            <span>{formatChineseTitle(session.title, sessions, index)}</span>
          </Button>
        ))}
        {sessions.length === 0 ? <div className="recent-empty">暂无会话</div> : null}
      </nav>

      {isDeleting ? (
        <div className="batch-delete-bar">
          <Button
            className="batch-select-all-button"
            isDisabled={sessions.length === 0}
            onPress={toggleSelectAll}
            size="sm"
            variant="tertiary"
          >
            {allSelected ? "取消全选会话" : "全选所有会话"}
          </Button>
          <Button className="batch-delete-button" isDisabled={selectedIds.length === 0} onPress={deleteSelected} size="sm">
            删除 {selectedIds.length} 个
          </Button>
        </div>
      ) : null}
    </aside>
  );
}

function formatChineseTitle(title: string, sessions: SessionRecord[], index: number): string {
  if (/^(new|first) chat$/i.test(title)) {
    const defaultTitleCount = sessions.filter((session) => /^(new|first) chat$/i.test(session.title)).length;
    return defaultTitleCount > 1 ? `新会话 ${index + 1}` : "新会话";
  }
  return title;
}
