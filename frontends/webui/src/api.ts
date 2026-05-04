import type {
  ConversationDetail,
  ConversationSummary,
  GroupSummary,
  RuntimeState,
  StreamEvent,
} from "./types";

async function readJson<T>(response: Response): Promise<T> {
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.message || payload.error || response.statusText);
  }
  return payload as T;
}

export async function fetchState(): Promise<RuntimeState> {
  return readJson<RuntimeState>(await fetch("/api/state"));
}

export async function createConversation(
  titleHint = "",
  groupId: string | null = null,
): Promise<ConversationSummary> {
  return readJson<ConversationSummary>(
    await fetch("/api/conversations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title_hint: titleHint, group_id: groupId }),
    }),
  );
}

export async function fetchConversation(conversationId: string): Promise<ConversationDetail> {
  return readJson<ConversationDetail>(await fetch(`/api/conversations/${conversationId}`));
}

export async function renameConversation(
  conversationId: string,
  title: string,
): Promise<ConversationSummary> {
  return readJson<ConversationSummary>(
    await fetch(`/api/conversations/${conversationId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }),
  );
}

export async function deleteConversation(conversationId: string): Promise<{ ok: boolean }> {
  return readJson<{ ok: boolean }>(
    await fetch(`/api/conversations/${conversationId}`, {
      method: "DELETE",
    }),
  );
}

export async function activateConversation(conversationId: string): Promise<ConversationDetail> {
  return readJson<ConversationDetail>(
    await fetch(`/api/conversations/${conversationId}/activate`, {
      method: "POST",
    }),
  );
}

export async function pinConversation(
  conversationId: string,
  pinned: boolean,
): Promise<ConversationSummary> {
  return readJson<ConversationSummary>(
    await fetch(`/api/conversations/${conversationId}/pin`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pinned }),
    }),
  );
}

export async function moveConversation(
  conversationId: string,
  groupId: string | null,
): Promise<ConversationSummary> {
  return readJson<ConversationSummary>(
    await fetch(`/api/conversations/${conversationId}/move`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ group_id: groupId }),
    }),
  );
}

export async function createGroup(name: string): Promise<GroupSummary> {
  return readJson<GroupSummary>(
    await fetch("/api/groups", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
  );
}

export async function renameGroup(groupId: string, name: string): Promise<GroupSummary> {
  return readJson<GroupSummary>(
    await fetch(`/api/groups/${groupId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
  );
}

export async function deleteGroup(groupId: string): Promise<{ ok: boolean }> {
  return readJson<{ ok: boolean }>(
    await fetch(`/api/groups/${groupId}`, {
      method: "DELETE",
    }),
  );
}

export async function startChat(
  conversationId: string,
  prompt: string,
): Promise<{ task_id: string }> {
  return readJson<{ task_id: string }>(
    await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: conversationId, prompt }),
    }),
  );
}

export function streamTask(
  taskId: string,
  handlers: {
    onEvent: (event: StreamEvent) => void;
    onError: (error: Error) => void;
    onClose: () => void;
  },
): EventSource {
  const source = new EventSource(`/api/chat/${taskId}/stream`);
  const handle = (event: MessageEvent) => {
    const payload = JSON.parse(event.data) as StreamEvent;
    handlers.onEvent(payload);
    if (payload.event === "message_done" || payload.event === "app_error") {
      source.close();
      handlers.onClose();
    }
  };
  source.addEventListener("message_delta", handle);
  source.addEventListener("message_done", handle);
  source.addEventListener("execution_update", handle);
  source.addEventListener("heartbeat", handle);
  source.addEventListener("app_error", handle);
  source.onerror = () => {
    source.close();
    handlers.onError(new Error("stream connection failed"));
  };
  return source;
}

export async function abortTask(): Promise<{ ok: boolean }> {
  return readJson<{ ok: boolean }>(await fetch("/api/abort", { method: "POST" }));
}

export async function switchLlm(index: number): Promise<RuntimeState> {
  return readJson<RuntimeState>(
    await fetch("/api/llm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ index }),
    }),
  );
}

export async function reinject(): Promise<{ ok: boolean }> {
  return readJson<{ ok: boolean }>(await fetch("/api/reinject", { method: "POST" }));
}

export async function resetConversation(): Promise<{
  message: string;
  conversation: ConversationSummary;
}> {
  return readJson(await fetch("/api/new", { method: "POST" }));
}

export async function continueConversation(command: string): Promise<{
  message: string;
  history: Array<{ role: "user" | "assistant"; content: string }>;
}> {
  return readJson(
    await fetch("/api/continue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command }),
    }),
  );
}

export async function setAutonomous(enabled: boolean): Promise<{ autonomous_enabled: boolean }> {
  return readJson(
    await fetch("/api/autonomous", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }),
  );
}
