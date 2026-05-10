import type { ConversationSummary, GroupSummary } from "../types";

export function buildGroups(groups: GroupSummary[], conversations: ConversationSummary[]) {
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
