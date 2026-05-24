import type { MessageRecord, SessionRecord, SessionTranscript, StreamEvent } from "./types";

const API_BASE = normalizeBase(import.meta.env.VITE_GA_HEROUI_API_TARGET ?? "");

export type BridgeStatus = {
  ok?: boolean;
  ready?: boolean;
  running?: boolean;
  gaRoot?: string;
  mykeyPath?: string;
  sessionCount?: number;
  activeSessionId?: string;
  transport?: {
    http?: boolean;
    wsEventsOnly?: boolean;
  };
};

export type ModelProfile = {
  id: string;
  name: string;
  active: boolean;
};

type BridgeSession = {
  id: string;
  title: string;
  createdAt: number | string;
  updatedAt: number | string;
  lastError?: string;
};

type BridgeStatusResponse = BridgeStatus;

type BridgeProfilesResponse = {
  profiles?: ModelProfile[];
};

type BridgeMessage = {
  id: number;
  role: string;
  content: string;
  ts?: number | string;
  turn_id?: string;
  response_id?: string;
  responseId?: string;
  gaTurn?: number;
  outputs?: string[];
  source?: string;
};

type BridgeSessionDetail = {
  sessionId?: string;
  session?: BridgeSession;
  messages?: BridgeMessage[];
  partial?: { content?: string } | null;
  status?: string;
  lastError?: string;
};

type BridgeMessages = {
  sessionId?: string;
  status?: string;
  messages?: BridgeMessage[];
  partial?: { content?: string } | null;
  msgSeq?: number;
  updatedAt?: number | string;
  lastError?: string;
};

const TURN_POLL_INTERVAL_MS = 700;

export async function listSessions(): Promise<SessionRecord[]> {
  const response = await fetch(apiUrl("/sessions"));
  const payload = await readJson<{ sessions: BridgeSession[] }>(response);
  return payload.sessions.map(mapSessionRecord);
}

export async function getBridgeStatus(): Promise<BridgeStatus> {
  const response = await fetch(apiUrl("/status"));
  return readJson<BridgeStatusResponse>(response);
}

export async function listModelProfiles(): Promise<ModelProfile[]> {
  const response = await fetch(apiUrl("/model-profiles"));
  const payload = await readJson<BridgeProfilesResponse>(response);
  return payload.profiles ?? [];
}

export async function createSession(title = "新会话"): Promise<SessionRecord> {
  const response = await fetch(apiUrl("/session/new"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  const payload = await readJson<{ session: BridgeSession }>(response);
  return mapSessionRecord(payload.session);
}

export async function deleteSessions(sessionIds: string[]): Promise<SessionRecord[]> {
  if (sessionIds.length === 0) {
    return listSessions();
  }
  await Promise.all(
    sessionIds.map(async (sessionId) => {
      const response = await fetch(apiUrl(`/session/${encodeURIComponent(sessionId)}`), { method: "DELETE" });
      await readJson(response);
    }),
  );
  return listSessions();
}

export async function listMessages(sessionId: string): Promise<MessageRecord[]> {
  const response = await fetch(apiUrl(`/session/${encodeURIComponent(sessionId)}/messages`));
  const payload = await readJson<BridgeMessages>(response);
  return (payload.messages ?? []).map(mapMessageRecord);
}

export async function listTranscript(sessionId: string): Promise<SessionTranscript> {
  const response = await fetch(apiUrl(`/session/${encodeURIComponent(sessionId)}`));
  const payload = await readJson<BridgeSessionDetail>(response);
  return {
    messages: (payload.messages ?? []).map(mapMessageRecord),
    timeline: [],
    artifacts: [],
  };
}

export async function createTurn(sessionId: string, content: string): Promise<string> {
  const response = await fetch(apiUrl(`/session/${encodeURIComponent(sessionId)}/prompt`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt: content }),
  });
  const payload = await readJson<{ seq?: number; userMessageId?: number }>(response);
  const seq = typeof payload.seq === "number" ? payload.seq : typeof payload.userMessageId === "number" ? payload.userMessageId : 0;
  return `ga|${encodeURIComponent(sessionId)}|${seq}`;
}

export function subscribeTurn(
  turnId: string,
  onEvent: (event: StreamEvent) => void,
  onError?: (error: Event) => void,
): EventSource {
  const { sessionId, afterId } = parseTurnId(turnId);
  const state = {
    closed: false,
    lastMessageId: afterId,
    lastPartial: "",
    emittedFinal: false,
    sawRunning: false,
  };

  const poll = async () => {
    if (state.closed) {
      return;
    }
    try {
      const response = await fetch(apiUrl(`/session/${encodeURIComponent(sessionId)}/messages?after=${state.lastMessageId}&limit=200`));
      const payload = await readJson<BridgeMessages>(response);
      const partial = String(payload.partial?.content ?? "");
      if (partial && partial !== state.lastPartial) {
        const delta = partial.startsWith(state.lastPartial) ? partial.slice(state.lastPartial.length) : partial;
        state.lastPartial = partial;
        state.sawRunning = true;
        onEvent({
          type: "phase.update",
          turn_id: turnId,
          session_id: sessionId,
          data: { phase: "generating", label: "正在生成回答" },
        });
        if (delta) {
          onEvent({
            type: "answer.delta",
            turn_id: turnId,
            session_id: sessionId,
            data: { delta },
          });
        }
      }

      for (const message of payload.messages ?? []) {
        const messageId = Number(message.id) || 0;
        if (messageId <= state.lastMessageId) {
          continue;
        }
        state.lastMessageId = messageId;
        if (message.role !== "assistant") {
          continue;
        }
        state.emittedFinal = true;
        onEvent({
          type: "answer.final",
          turn_id: turnId,
          session_id: sessionId,
          data: {
            text: String(message.content ?? ""),
            response_id: message.responseId || message.response_id || `${turnId}:response:${messageId}`,
            created_at: toIsoTimestamp(message.ts),
          },
        });
      }

      const status = String(payload.status ?? "");
      if (status === "running") {
        state.sawRunning = true;
        if (!state.lastPartial) {
          onEvent({
            type: "phase.update",
            turn_id: turnId,
            session_id: sessionId,
            data: { phase: "understanding", label: "正在理解请求" },
          });
        }
      } else if (status === "error" || status === "cancelled") {
        onEvent({
          type: "turn.error",
          turn_id: turnId,
          session_id: sessionId,
          data: { message: payload.lastError || (status === "cancelled" ? "任务已取消" : "请求失败") },
        });
        onEvent({
          type: "turn.done",
          turn_id: turnId,
          session_id: sessionId,
          data: { ok: false },
        });
        close();
        return;
      } else if (status === "idle" && (state.emittedFinal || payload.messages?.length)) {
        onEvent({
          type: "turn.done",
          turn_id: turnId,
          session_id: sessionId,
          data: { ok: true },
        });
        close();
        return;
      }
    } catch (error) {
      if (!state.closed) {
        onError?.(toEvent(error));
        close();
      }
      return;
    }
    window.setTimeout(poll, TURN_POLL_INTERVAL_MS);
  };

  const close = () => {
    state.closed = true;
  };

  void poll();
  return { close } as EventSource;
}

function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

function normalizeBase(base: string): string {
  if (!base) {
    return "";
  }
  return base.endsWith("/") ? base.slice(0, -1) : base;
}

function parseTurnId(turnId: string): { sessionId: string; afterId: number } {
  const parts = turnId.split("|");
  if (parts.length < 3) {
    return { sessionId: "", afterId: 0 };
  }
  return {
    sessionId: decodeURIComponent(parts[1] || ""),
    afterId: Number(parts[2]) || 0,
  };
}

function mapSessionRecord(session: BridgeSession): SessionRecord {
  return {
    id: session.id,
    title: session.title,
    created_at: toIsoTimestamp(session.createdAt),
    updated_at: toIsoTimestamp(session.updatedAt),
  };
}

function mapMessageRecord(message: BridgeMessage): MessageRecord {
  return {
    role: message.role === "user" ? "user" : "assistant",
    content: String(message.content ?? ""),
    created_at: toIsoTimestamp(message.ts),
    turn_id: message.turn_id,
    response_id: message.responseId || message.response_id,
    ga_turn: message.gaTurn,
    outputs: message.outputs,
    source: message.source,
  };
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`请求失败：${response.status}`);
  }
  return (await response.json()) as T;
}

function toIsoTimestamp(value: number | string | undefined): string {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return new Date().toISOString();
  }
  const ms = value > 1e12 ? value : value * 1000;
  return new Date(ms).toISOString();
}

function toEvent(error: unknown): Event {
  return (error instanceof Event ? error : new Event("error")) as Event;
}
