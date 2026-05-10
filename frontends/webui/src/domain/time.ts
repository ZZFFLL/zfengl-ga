export const nowLabel = () => new Date().toLocaleString();

export function formatMessageTime(raw: string) {
  if (!raw) return nowLabel();
  return raw;
}
