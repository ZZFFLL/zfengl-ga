// 中文注释：侧栏批量选择只服务“最近对话”，保持选择逻辑独立于 JSX。
export function toggleSelectedConversation(selectedIds: string[], conversationId: string) {
  if (selectedIds.includes(conversationId)) {
    return selectedIds.filter((id) => id !== conversationId);
  }
  return [...selectedIds, conversationId];
}

export function pruneSelectedConversations(selectedIds: string[], availableIds: string[]) {
  const available = new Set(availableIds);
  return selectedIds.filter((id) => available.has(id));
}

export function buildBulkDeleteLabel(selectedCount: number) {
  return selectedCount > 0 ? `删除 ${selectedCount}` : "删除";
}
