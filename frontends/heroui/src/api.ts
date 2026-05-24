import type { ExecutionStep, ImageAttachment, MessageRecord, SessionRecord, SessionTranscript, StreamEvent } from "./types";
import { parseGenericAgentOutputSteps } from "./ga_output_parser";

const API_BASE = normalizeBase(
  ((import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env?.VITE_GA_HEROUI_API_TARGET) ?? "",
);

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

export type BridgeConfig = {
  gaRoot?: string;
  mykeyPath?: string;
  config?: Record<string, unknown>;
};

export type ModelProfile = {
  id: string;
  name: string;
  model?: string;
  active: boolean;
};

export type PathOpenRequest = {
  kind?: "mykey";
  path?: string;
  target?: string;
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
  activeProfileId?: string;
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

type BridgeTimelineEvent = StreamEvent & {
  seq?: number;
  ts?: number;
};

type BridgeSessionDetail = {
  sessionId?: string;
  session?: BridgeSession;
  messages?: BridgeMessage[];
  events?: BridgeTimelineEvent[];
  eventSeq?: number;
  partial?: { content?: string } | null;
  status?: string;
  lastError?: string;
};

type BridgeMessages = {
  sessionId?: string;
  status?: string;
  messages?: BridgeMessage[];
  events?: BridgeTimelineEvent[];
  eventSeq?: number;
  partial?: { content?: string } | null;
  msgSeq?: number;
  updatedAt?: number | string;
  lastError?: string;
};

const TURN_POLL_INTERVAL_MS = 700;
const TURN_EVENT_CURSORS = new Map<string, number>();

export async function listSessions(): Promise<SessionRecord[]> {
  const response = await fetch(apiUrl("/sessions"));
  const payload = await readJson<{ sessions: BridgeSession[] }>(response);
  return payload.sessions.map(mapSessionRecord);
}

export async function getBridgeStatus(): Promise<BridgeStatus> {
  const response = await fetch(apiUrl("/status"));
  return readJson<BridgeStatusResponse>(response);
}

export async function getBridgeConfig(): Promise<BridgeConfig> {
  const response = await fetch(apiUrl("/config"));
  return readJson<BridgeConfig>(response);
}

export async function listModelProfiles(): Promise<ModelProfile[]> {
  const response = await fetch(apiUrl("/model-profiles"));
  const payload = await readJson<BridgeProfilesResponse>(response);
  return payload.profiles ?? [];
}

export async function switchModelProfile(profileId: string, sessionId?: string): Promise<ModelProfile[]> {
  const response = await fetch(apiUrl("/model-profile"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profileId, sessionId }),
  });
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
  const messages = (payload.messages ?? []).map(mapMessageRecord);
  return {
    messages,
    timeline: mapEventsToTimeline(payload.events ?? [], messages),
    artifacts: [],
  };
}

export async function createTurn(sessionId: string, content: string, images: ImageAttachment[] = []): Promise<string> {
  const response = await fetch(apiUrl(`/session/${encodeURIComponent(sessionId)}/prompt`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt: content, images }),
  });
  const payload = await readJson<{ seq?: number; userMessageId?: number; eventSeq?: number }>(response);
  const seq = typeof payload.seq === "number" ? payload.seq : typeof payload.userMessageId === "number" ? payload.userMessageId : 0;
  const turnId = `ga|${encodeURIComponent(sessionId)}|${seq}`;
  if (typeof payload.eventSeq === "number") {
    TURN_EVENT_CURSORS.set(turnId, payload.eventSeq);
  }
  return turnId;
}

export async function cancelSession(sessionId: string): Promise<void> {
  const response = await fetch(apiUrl(`/session/${encodeURIComponent(sessionId)}/cancel`), { method: "POST" });
  await readJson(response);
}

export async function openBridgePath(request: PathOpenRequest): Promise<void> {
  const response = await fetch(apiUrl("/path/open"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  await readJson(response);
}

export function subscribeTurn(
  turnId: string,
  onEvent: (event: StreamEvent) => void,
  onError?: (error: Event) => void,
): EventSource {
  if (typeof EventSource === "undefined") {
    return subscribeTurnPolling(turnId, onEvent, onError);
  }

  const { sessionId } = parseTurnId(turnId);
  const afterEvent = TURN_EVENT_CURSORS.get(turnId) ?? 0;
  const params = new URLSearchParams({
    after_event: String(afterEvent),
    turn_id: turnId,
  });
  const source = new EventSource(apiUrl(`/session/${encodeURIComponent(sessionId)}/events?${params.toString()}`));
  let closed = false;
  let sawEvent = false;
  let fallback: EventSource | null = null;

  const close = () => {
    closed = true;
    TURN_EVENT_CURSORS.delete(turnId);
    if (fallback) {
      fallback.close();
      return;
    }
    source.close();
  };

  source.onmessage = (message) => {
    if (closed) {
      return;
    }
    try {
      const event = JSON.parse(message.data) as StreamEvent & { seq?: number };
      sawEvent = true;
      if (typeof event.seq === "number") {
        TURN_EVENT_CURSORS.set(turnId, Math.max(TURN_EVENT_CURSORS.get(turnId) ?? 0, event.seq));
      }
      if (event.turn_id !== turnId) {
        return;
      }
      onEvent(event);
      if (event.type === "turn.done" || event.type === "turn.error") {
        close();
      }
    } catch (error) {
      onError?.(toEvent(error));
      close();
    }
  };

  source.onerror = (error) => {
    if (closed) {
      return;
    }
    if (!sawEvent) {
      source.close();
      fallback = subscribeTurnPolling(turnId, onEvent, onError);
      return;
    }
  };

  return { close } as EventSource;
}

function subscribeTurnPolling(
  turnId: string,
  onEvent: (event: StreamEvent) => void,
  onError?: (error: Event) => void,
): EventSource {
  const { sessionId, afterId } = parseTurnId(turnId);
  const state = {
    closed: false,
    lastMessageId: afterId,
    lastEventSeq: TURN_EVENT_CURSORS.get(turnId) ?? 0,
    lastPartial: "",
    emittedFinal: false,
    sawStructuredEvents: false,
    sawStructuredTimeline: false,
    sawRunning: false,
  };

  const poll = async () => {
    if (state.closed) {
      return;
    }
    try {
      const response = await fetch(
        apiUrl(`/session/${encodeURIComponent(sessionId)}/messages?after=${state.lastMessageId}&after_event=${state.lastEventSeq}&limit=200`),
      );
      const payload = await readJson<BridgeMessages>(response);
      const payloadEvents = payload.events ?? [];
      for (const event of payloadEvents) {
        if (typeof event.seq === "number") {
          state.lastEventSeq = Math.max(state.lastEventSeq, event.seq);
        }
      }
      const relevantEvents = payloadEvents.filter((event) => event.turn_id === turnId);
      const hasStructuredEvents = relevantEvents.length > 0;
      state.sawStructuredEvents = state.sawStructuredEvents || hasStructuredEvents;
      state.sawStructuredTimeline = state.sawStructuredTimeline || relevantEvents.some((event) => event.type === "timeline.step");
      const hasStructuredFinal = relevantEvents.some((event) => event.type === "answer.final");
      const partial = String(payload.partial?.content ?? "");
      if (!state.sawStructuredEvents && partial && partial !== state.lastPartial) {
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

      for (const event of relevantEvents) {
        if (event.type === "answer.final") {
          state.emittedFinal = true;
        }
        onEvent(event);
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
        const responseId = message.responseId || message.response_id || `${turnId}:response:${messageId}`;
        const createdAt = toIsoTimestamp(message.ts);
        const shouldEmitMessageFinal = !hasStructuredFinal && !state.emittedFinal;
        state.emittedFinal = true;
        if (shouldEmitMessageFinal) {
          onEvent({
            type: "answer.final",
            turn_id: turnId,
            session_id: sessionId,
            data: {
              text: String(message.content ?? ""),
              response_id: responseId,
              created_at: createdAt,
            },
          });
        }
        if (!state.sawStructuredTimeline) {
          emitBridgeOutputs(message, turnId, sessionId, responseId, createdAt, onEvent);
        }
      }

      const status = String(payload.status ?? "");
      if (status === "running") {
        state.sawRunning = true;
        if (!state.lastPartial && !state.sawStructuredEvents) {
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
    TURN_EVENT_CURSORS.delete(turnId);
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

function mapEventsToTimeline(events: BridgeTimelineEvent[], messages: MessageRecord[]): ExecutionStep[] {
  const steps: ExecutionStep[] = [];
  for (const event of events) {
    if (event.type !== "timeline.step") {
      continue;
    }
    const data = event.data;
    const id = String(data.id ?? "");
    if (!id) {
      continue;
    }
    const current = steps.find((step) => step.id === id);
    const outputDelta = typeof data.output_delta === "string" ? data.output_delta : "";
    const step: ExecutionStep = {
      id,
      turn_id: typeof data.turn_id === "string" ? data.turn_id : undefined,
      response_id: typeof data.response_id === "string" ? data.response_id : undefined,
      kind: readStepKindFromData(data.kind),
      title: String(data.title ?? "执行步骤"),
      status: data.status === "failed" ? "failed" : data.status === "running" ? "running" : "done",
      summary: String(data.summary ?? current?.summary ?? ""),
      detail: String(data.detail ?? current?.detail ?? ""),
      input: typeof data.input === "string" ? data.input : current?.input,
      output: typeof data.output === "string" ? data.output : outputDelta ? `${current?.output ?? ""}${outputDelta}` : current?.output,
      error: typeof data.error === "string" ? data.error : current?.error,
      elapsed_ms: typeof data.elapsed_ms === "number" ? data.elapsed_ms : current?.elapsed_ms,
      tool_name: typeof data.tool_name === "string" ? data.tool_name : current?.tool_name,
      tool_label: typeof data.tool_label === "string" ? data.tool_label : current?.tool_label,
      created_at: typeof data.created_at === "string" ? data.created_at : current?.created_at,
      default_open: typeof data.default_open === "boolean" ? data.default_open : current?.default_open,
    };
    if (isHiddenPhaseStep(step)) {
      continue;
    }
    const index = steps.findIndex((currentStep) => currentStep.id === id);
    if (index >= 0) {
      steps[index] = step;
    } else {
      steps.push(step);
    }
  }
  return steps.length > 0 ? steps : mapOutputsToTimeline(messages);
}

function isHiddenPhaseStep(step: ExecutionStep): boolean {
  if (step.kind !== "phase") {
    return false;
  }
  return /:phase:\d+:(start|end)$/.test(step.id) || /^第 \d+ 轮(开始|结束)$/.test(step.title);
}

function readStepKindFromData(kind: unknown): ExecutionStep["kind"] {
  const value = String(kind ?? "tool");
  const allowed: ExecutionStep["kind"][] = [
    "thought",
    "search",
    "read",
    "file",
    "command",
    "skill",
    "tape",
    "agent",
    "help",
    "control",
    "tool",
    "phase",
    "complete",
  ];
  return allowed.includes(value as ExecutionStep["kind"]) ? (value as ExecutionStep["kind"]) : "tool";
}

function mapOutputsToTimeline(messages: MessageRecord[]): ExecutionStep[] {
  return messages.flatMap((message) => {
    const responseId = message.response_id || `${message.turn_id || message.created_at}:response`;
    return (message.outputs ?? []).flatMap((output, index) =>
      parseGenericAgentOutputSteps(output, {
        idPrefix: `${responseId}:output:${index + 1}`,
        turnId: message.turn_id,
        responseId: message.response_id,
        createdAt: message.created_at,
        gaTurn: message.ga_turn,
      }),
    );
  });
}

function emitBridgeOutputs(
  message: BridgeMessage,
  turnId: string,
  sessionId: string,
  responseId: string,
  createdAt: string,
  onEvent: (event: StreamEvent) => void,
) {
  (message.outputs ?? []).forEach((output, index) => {
    const steps = parseGenericAgentOutputSteps(output, {
      idPrefix: `${responseId}:output:${index + 1}`,
      turnId,
      responseId,
      createdAt,
      gaTurn: message.gaTurn,
    });
    steps.forEach((step) => {
      onEvent({
        type: "timeline.step",
        turn_id: turnId,
        session_id: sessionId,
        data: step,
      });
    });
  });
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
