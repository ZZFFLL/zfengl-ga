import { Button, Dropdown } from "antd";
import type { MenuProps } from "antd";
import { Folder, MessageSquareText, MoreHorizontal, Pin, PinOff, Trash2 } from "lucide-react";
import type { ConversationSummary, GroupSummary } from "../../types";

export function ConversationActions({
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
