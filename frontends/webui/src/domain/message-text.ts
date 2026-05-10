export const FINAL_INFO_BLOCK_RE = /\n*`{3,}\s*\n?\[Info\]\s*Final response to user\.\s*\n?`{3,}\s*$/i;
export const FINAL_INFO_TRAIL_RE = /\n*\[Info\]\s*Final response to user\.\s*(?:`{3,}\s*)*$/i;
export const TOOL_START_RE = /🛠️ Tool:\s*`([^`]+)`\s*📥 args:\s*/g;

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

export function stripToolTraceBlocks(text: string) {
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

export function sanitizeDisplayText(text: string) {
  let cleaned = text || "";
  cleaned = stripToolTraceBlocks(cleaned);
  cleaned = cleaned.replace(FINAL_INFO_BLOCK_RE, "");
  cleaned = cleaned.replace(FINAL_INFO_TRAIL_RE, "");
  cleaned = cleaned.replace(/\n{3,}/g, "\n\n");
  return cleaned.trim();
}

export function previewText(text: string) {
  const cleaned = sanitizeDisplayText(text || "");
  return cleaned.replace(/\s+/g, " ").trim() || "暂无消息";
}
