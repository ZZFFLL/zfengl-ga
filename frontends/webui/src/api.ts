import type { RuntimeState, StreamEvent } from "./types";

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

export async function startChat(prompt: string): Promise<{ task_id: string }> {
  return readJson<{ task_id: string }>(
    await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
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
    if (payload.event === "done" || payload.event === "app_error") {
      source.close();
      handlers.onClose();
    }
  };
  source.addEventListener("next", handle);
  source.addEventListener("done", handle);
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

export async function resetConversation(): Promise<{ message: string }> {
  return readJson<{ message: string }>(await fetch("/api/new", { method: "POST" }));
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

export async function startPet(): Promise<{ ok: boolean; started: boolean }> {
  return readJson(await fetch("/api/pet", { method: "POST" }));
}
