import type {
  ArtifactRecord,
  ExecutionStep,
  FollowupSuggestion,
  HumanInteraction,
  MessageRecord,
  StreamEvent,
  ToolCard,
  TurnPhase,
  TurnResponse,
} from "./types";

export type TurnState = {
  turnId: string;
  startedAt: string;
  currentResponseId: string;
  answer: string;
  finalAnswer: string;
  responses: TurnResponse[];
  steps: ExecutionStep[];
  artifacts: ArtifactRecord[];
  suggestions: FollowupSuggestion[];
  phase: TurnPhase | null;
  tools: ToolCard[];
  status: "idle" | "streaming" | "done" | "error";
  error: string;
};

export type HumanInteractionPrompt = {
  stepId: string;
  turnId: string;
  interaction: HumanInteraction;
  disabled: boolean;
};

export type ThreadItem =
  | { type: "message"; id: string; message: MessageRecord }
  | {
      type: "turn";
      id: string;
      turnId: string;
      messages: MessageRecord[];
      steps: ExecutionStep[];
      artifacts: ArtifactRecord[];
      rounds: TurnRound[];
    };

export type TurnRound = {
  id: string;
  responseId: string;
  message?: MessageRecord;
  steps: ExecutionStep[];
  artifacts: ArtifactRecord[];
  items: TurnRoundItem[];
};

export type TurnRoundItem =
  | { type: "message"; id: string; message: MessageRecord; created_at?: string }
  | { type: "step"; id: string; step: ExecutionStep; created_at?: string }
  | { type: "artifact"; id: string; artifact: ArtifactRecord; created_at?: string };

export function createInitialTurnState(turnId: string, startedAt = new Date().toISOString()): TurnState {
  return {
    turnId,
    startedAt,
    currentResponseId: "",
    answer: "",
    finalAnswer: "",
    responses: [],
    steps: [],
    artifacts: [],
    suggestions: [],
    phase: null,
    tools: [],
    status: "streaming",
    error: "",
  };
}

export function applyStreamEvent(state: TurnState, event: StreamEvent): TurnState {
  switch (event.type) {
    case "answer.delta": {
      const responseId = readResponseId(event.data.response_id) || state.currentResponseId || nextResponseId(state);
      return {
        ...state,
        currentResponseId: responseId,
        answer: state.answer + String(event.data.delta ?? ""),
        status: "streaming",
      };
    }
    case "answer.retract": {
      const responseId = readResponseId(event.data.response_id);
      if (!responseId || responseId !== state.currentResponseId) {
        return state;
      }
      return {
        ...state,
        currentResponseId: "",
        answer: "",
      };
    }
    case "answer.final": {
      const finalAnswer = String(event.data.text ?? state.answer);
      if (!finalAnswer.trim()) {
        return { ...state, currentResponseId: "", answer: "", finalAnswer };
      }
      const responseId = readResponseId(event.data.response_id) || state.currentResponseId || nextResponseId(state);
      const response: TurnResponse = {
        id: responseId,
        content: finalAnswer,
      };
      if (typeof event.data.created_at === "string") {
        response.created_at = event.data.created_at;
      }
      if (typeof event.data.elapsed_ms === "number") {
        response.elapsed_ms = event.data.elapsed_ms;
      }
      return {
        ...state,
        currentResponseId: "",
        answer: "",
        finalAnswer,
        responses: [...state.responses, response],
      };
    }
    case "phase.update":
      return {
        ...state,
        phase: {
          phase: String(event.data.phase ?? "working"),
          label: localizePhaseLabel(event.data.label, event.data.phase),
        },
      };
    case "timeline.step":
      return reduceTimelineStep(state, event);
    case "artifact.created":
      return reduceArtifactEvent(state, event);
    case "suggestion.created":
      return reduceSuggestionEvent(state, event);
    case "tool.start":
    case "tool.end":
      return reduceToolEvent(state, event);
    case "turn.error":
      return {
        ...state,
        status: "error",
        error: String(event.data.message ?? "未知错误"),
        steps: upsertStep(closeRunningSteps(state.steps, "failed"), {
          id: `${state.turnId}:complete`,
          turn_id: state.turnId,
          response_id: "",
          kind: "complete",
          title: "任务失败",
          status: "failed",
          summary: "本轮执行失败",
          detail: "",
        }),
      };
    case "turn.done":
      if (state.status === "error") {
        return state;
      }
      const turnElapsedMs = typeof event.data.elapsed_ms === "number" ? event.data.elapsed_ms : undefined;
      return {
        ...state,
        status: "done",
        phase: { phase: "done", label: "本轮执行完成" },
        steps: closeRunningSteps(state.steps, "done"),
        responses:
          typeof turnElapsedMs === "number" && state.responses.length > 0
            ? state.responses.map((response, index) =>
                index === state.responses.length - 1 ? { ...response, elapsed_ms: turnElapsedMs } : response,
              )
            : state.responses,
      };
  }
}

export function appendFinalAssistantMessage(
  messages: MessageRecord[],
  turn: TurnState,
  createdAt = new Date().toISOString(),
): MessageRecord[] {
  if (turn.status === "error") {
    return messages;
  }
  const responses = turn.responses.length > 0 ? turn.responses : [{ id: `${turn.turnId}:response`, content: turn.answer }];
  const nextMessages = responses
    .map((response) => {
      const message = {
        role: "assistant" as const,
        content: response.content.trim(),
        turn_id: turn.turnId,
        response_id: response.id,
        created_at: response.created_at ?? createdAt,
      };
      if (typeof response.elapsed_ms === "number") {
        return { ...message, elapsed_ms: response.elapsed_ms };
      }
      return message;
    })
    .filter((message) => message.content);
  if (nextMessages.length === 0) {
    return messages;
  }
  return [...messages, ...nextMessages];
}

export function mergeCompletedTurnIntoHistory(
  messages: MessageRecord[],
  timeline: ExecutionStep[],
  artifacts: ArtifactRecord[],
  turn: TurnState,
): {
  messages: MessageRecord[];
  timeline: ExecutionStep[];
  artifacts: ArtifactRecord[];
} {
  return {
    messages: appendFinalAssistantMessage(messages, turn),
    timeline: mergeRecordsById(timeline, turn.steps),
    artifacts: mergeRecordsById(artifacts, turn.artifacts),
  };
}

export function findLatestHumanInteractionPrompt(
  messages: MessageRecord[],
  timeline: ExecutionStep[],
  activeTurn: TurnState | null,
): HumanInteractionPrompt | null {
  const steps = [...timeline, ...(activeTurn?.steps ?? [])].filter(isHumanInteractionStep);
  const latest = steps[steps.length - 1];
  if (!latest || !latest.interaction) {
    return null;
  }
  return {
    stepId: latest.id,
    turnId: latest.turn_id || "",
    interaction: latest.interaction,
    disabled: hasLaterUserReply(messages, latest),
  };
}

export function buildThreadItems(
  messages: MessageRecord[],
  timeline: ExecutionStep[],
  artifacts: ArtifactRecord[],
): ThreadItem[] {
  const items: ThreadItem[] = [];
  const turnItems = new Map<string, Extract<ThreadItem, { type: "turn" }>>();

  for (const message of messages) {
    const turnId = message.turn_id || "";
    if (!turnId) {
      items.push({ type: "message", id: `message:${message.created_at}:${items.length}`, message });
      continue;
    }
    let item = turnItems.get(turnId);
    if (!item) {
      item = { type: "turn", id: `turn:${turnId}`, turnId, messages: [], steps: [], artifacts: [], rounds: [] };
      turnItems.set(turnId, item);
      items.push(item);
    }
    item.messages.push(message);
  }

  for (const step of timeline) {
    const turnId = step.turn_id || "";
    if (!turnId) {
      continue;
    }
    const item = turnItems.get(turnId);
    if (item) {
      item.steps.push(step);
    }
  }

  for (const artifact of artifacts) {
    const turnId = artifact.turn_id || "";
    if (!turnId) {
      continue;
    }
    const item = turnItems.get(turnId);
    if (item) {
      item.artifacts.push(artifact);
    }
  }

  const orphanTurnIds = new Set([
    ...timeline.map((step) => step.turn_id || "").filter(Boolean),
    ...artifacts.map((artifact) => artifact.turn_id || "").filter(Boolean),
  ]);
  for (const turnId of orphanTurnIds) {
    if (turnItems.has(turnId)) {
      continue;
    }
    const steps = timeline.filter((step) => step.turn_id === turnId);
    const turnArtifacts = artifacts.filter((artifact) => artifact.turn_id === turnId);
    const item: ThreadItem = {
      type: "turn",
      id: `turn:${turnId}`,
      turnId,
      messages: [],
      steps,
      artifacts: turnArtifacts,
      rounds: [],
    };
    const insertionIndex = findTimelineInsertionIndex(items, steps);
    items.splice(insertionIndex, 0, item);
  }

  for (const item of turnItems.values()) {
    item.rounds = buildTurnRounds(item.messages, item.steps, item.artifacts);
  }
  for (const item of items) {
    if (item.type === "turn" && item.rounds.length === 0) {
      item.rounds = buildTurnRounds(item.messages, item.steps, item.artifacts);
    }
  }

  return items;
}

export function buildTurnRounds(
  messages: MessageRecord[],
  steps: ExecutionStep[],
  artifacts: ArtifactRecord[],
): TurnRound[] {
  const rounds: TurnRound[] = [];
  const roundById = new Map<string, TurnRound>();

  // 去重：确保每个 step.id 和 artifact.id 只出现一次
  const uniqueSteps = deduplicateSteps(steps);
  const uniqueArtifacts = deduplicateArtifacts(artifacts);

  function ensureRound(responseId: string): TurnRound {
    const id = responseId || `round:${rounds.length + 1}`;
    const existing = roundById.get(id);
    if (existing) {
      return existing;
    }
    const round: TurnRound = { id, responseId, steps: [], artifacts: [], items: [] };
    roundById.set(id, round);
    rounds.push(round);
    return round;
  }

  const assistantMessages = messages.filter((message) => message.role === "assistant");
  assistantMessages.forEach((message, index) => {
    const responseId = message.response_id || `message:${message.created_at}:${index}`;
    ensureRound(responseId).message = message;
  });

  for (const step of uniqueSteps) {
    const responseId = step.response_id || "";
    if (responseId) {
      ensureRound(responseId).steps.push(step);
    }
  }
  for (const artifact of uniqueArtifacts) {
    const responseId = artifact.response_id || "";
    if (responseId) {
      ensureRound(responseId).artifacts.push(artifact);
    }
  }

  const unownedSteps = uniqueSteps.filter((step) => !step.response_id);
  const unownedArtifacts = uniqueArtifacts.filter((artifact) => !artifact.response_id);
  if (unownedSteps.length > 0 || unownedArtifacts.length > 0) {
    rounds.push({
      id: `turn-unowned:${rounds.length + 1}`,
      responseId: "",
      steps: unownedSteps,
      artifacts: unownedArtifacts,
      items: buildRoundItems([], unownedSteps, unownedArtifacts),
    });
  }

  for (const round of rounds) {
    round.items = buildRoundItems(round.message ? [round.message] : [], round.steps, round.artifacts);
  }

  return rounds;
}

function isHumanInteractionStep(step: ExecutionStep): boolean {
  return (
    step.tool_name === "ask_user" &&
    Boolean(step.interaction) &&
    Boolean(step.interaction?.candidates.some((candidate) => candidate.trim()))
  );
}

function hasLaterUserReply(messages: MessageRecord[], step: ExecutionStep): boolean {
  const stepTurnId = step.turn_id || "";
  const stepTime = readTimestamp(step.created_at);
  const hasTimestampMatch =
    stepTime !== null &&
    messages.some((message) => {
      if (message.role !== "user" || (stepTurnId && message.turn_id === stepTurnId)) {
        return false;
      }
      const messageTime = readTimestamp(message.created_at);
      return messageTime !== null && messageTime > stepTime;
    });
  if (hasTimestampMatch) {
    return true;
  }

  if (!stepTurnId) {
    return false;
  }
  const sameTurnUserIndex = findLastIndex(messages, (message) => message.role === "user" && message.turn_id === stepTurnId);
  if (sameTurnUserIndex < 0) {
    return false;
  }
  return messages.slice(sameTurnUserIndex + 1).some((message) => message.role === "user");
}

function findLastIndex<T>(items: T[], predicate: (item: T) => boolean): number {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    if (predicate(items[index])) {
      return index;
    }
  }
  return -1;
}

function readTimestamp(value?: string): number | null {
  if (!value) {
    return null;
  }
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp) ? null : timestamp;
}

function buildRoundItems(
  messages: MessageRecord[],
  steps: ExecutionStep[],
  artifacts: ArtifactRecord[],
): TurnRoundItem[] {
  const items: TurnRoundItem[] = [
    ...steps.map((step, index) => ({
      type: "step" as const,
      id: `step:${step.id}:${index}`,
      step,
      created_at: step.created_at,
    })),
    ...artifacts.map((artifact, index) => ({
      type: "artifact" as const,
      id: `artifact:${artifact.id}:${index}`,
      artifact,
      created_at: artifact.created_at,
    })),
    ...messages.map((message, index) => ({
      type: "message" as const,
      id: `message:${message.created_at || index}:${index}`,
      message,
      created_at: message.created_at,
    })),
  ];

  return items.sort((a, b) => {
    if (a.type === "message" && b.type !== "message") return 1;
    if (a.type !== "message" && b.type === "message") return -1;
    const timeA = a.created_at || "";
    const timeB = b.created_at || "";
    if (!timeA && !timeB) return 0;
    if (!timeA) return 1;
    if (!timeB) return -1;
    return timeA.localeCompare(timeB);
  });
}

function localizePhaseLabel(label: unknown, phase: unknown): string {
  const rawLabel = typeof label === "string" ? label : "";
  const normalizedLabel = rawLabel.trim().toLowerCase();
  const normalizedPhase = typeof phase === "string" ? phase.trim().toLowerCase() : "";
  const mapped =
    PHASE_LABELS[normalizedLabel] ??
    PHASE_LABELS[normalizedPhase] ??
    (rawLabel && /[^\x00-\x7F]/.test(rawLabel) ? rawLabel : "");
  return mapped || "正在处理";
}

const PHASE_LABELS: Record<string, string> = {
  "understanding request": "正在思考",
  understanding: "正在思考",
  working: "正在处理",
  "calling tool": "正在调用工具",
  calling_tool: "正在调用工具",
  "generating answer": "正在生成回答",
  generating: "正在生成回答",
};

function reduceToolEvent(state: TurnState, event: StreamEvent): TurnState {
  const id = String(event.data.id ?? event.data.name ?? "tool");
  const current = state.tools.find((tool) => tool.id === id);
  const next: ToolCard = {
    id,
    name: String(event.data.name ?? current?.name ?? id),
    status: event.type === "tool.start" ? "running" : readToolStatus(event.data.status),
    summary: typeof event.data.summary === "string" ? event.data.summary : current?.summary,
    elapsedMs: typeof event.data.elapsed_ms === "number" ? event.data.elapsed_ms : current?.elapsedMs,
  };

  return {
    ...state,
    tools: current ? state.tools.map((tool) => (tool.id === id ? next : tool)) : [...state.tools, next],
  };
}

function reduceTimelineStep(state: TurnState, event: StreamEvent): TurnState {
  const stepId = String(event.data.id ?? `${state.turnId}:step:${state.steps.length + 1}`);
  const current = state.steps.find((item) => item.id === stepId);
  const outputDelta = typeof event.data.output_delta === "string" ? event.data.output_delta : "";
  const detailDelta = typeof event.data.detail_delta === "string" ? event.data.detail_delta : "";
  const step: ExecutionStep = {
    id: stepId,
    turn_id: typeof event.data.turn_id === "string" ? event.data.turn_id : state.turnId,
    kind: readStepKind(event.data.kind),
    title: String(event.data.title ?? "执行步骤"),
    status: readStepStatus(event.data.status),
    summary: String(event.data.summary ?? current?.summary ?? ""),
    detail:
      detailDelta
        ? `${current?.detail ?? ""}${detailDelta}`
        : typeof event.data.detail === "string"
          ? event.data.detail
          : current?.detail ?? "",
    input: typeof event.data.input === "string" ? event.data.input : current?.input,
    output:
      typeof event.data.output === "string"
        ? event.data.output
        : outputDelta
          ? `${current?.output ?? ""}${outputDelta}`
          : current?.output,
    error: typeof event.data.error === "string" ? event.data.error : current?.error,
    elapsed_ms: typeof event.data.elapsed_ms === "number" ? event.data.elapsed_ms : current?.elapsed_ms,
    tool_name: typeof event.data.tool_name === "string" ? event.data.tool_name : current?.tool_name,
    tool_label: typeof event.data.tool_label === "string" ? event.data.tool_label : current?.tool_label,
    created_at: typeof event.data.created_at === "string" ? event.data.created_at : current?.created_at,
    default_open: typeof event.data.default_open === "boolean" ? event.data.default_open : current?.default_open,
    interaction: readInteraction(event.data.interaction) ?? current?.interaction,
  };
  if (isHiddenPhaseStep(step)) {
    return {
      ...state,
      steps: state.steps.filter((item) => item.id !== step.id),
    };
  }
  const responseId = readResponseId(event.data.response_id) || state.currentResponseId;
  if (responseId) {
    step.response_id = responseId;
  }
  return {
    ...state,
    steps: upsertStep(state.steps, step),
  };
}

function reduceArtifactEvent(state: TurnState, event: StreamEvent): TurnState {
  const artifact: ArtifactRecord = {
    id: String(event.data.id ?? `${state.turnId}:artifact:${state.artifacts.length + 1}`),
    turn_id: typeof event.data.turn_id === "string" ? event.data.turn_id : state.turnId,
    name: String(event.data.name ?? "附件"),
    kind: readArtifactKind(event.data.kind),
  };
  const responseId = readResponseId(event.data.response_id) || state.currentResponseId;
  if (responseId) {
    artifact.response_id = responseId;
  }
  if (typeof event.data.path === "string") {
    artifact.path = event.data.path;
  }
  if (typeof event.data.url === "string") {
    artifact.url = event.data.url;
  }
  if (typeof event.data.created_at === "string") {
    artifact.created_at = event.data.created_at;
  }
  return {
    ...state,
    artifacts: state.artifacts.some((current) => current.id === artifact.id)
      ? state.artifacts.map((current) => (current.id === artifact.id ? artifact : current))
      : [...state.artifacts, artifact],
  };
}

function reduceSuggestionEvent(state: TurnState, event: StreamEvent): TurnState {
  const suggestion: FollowupSuggestion = {
    id: String(event.data.id ?? `${state.turnId}:suggestion:${state.suggestions.length + 1}`),
    text: String(event.data.text ?? ""),
  };
  if (!suggestion.text.trim()) {
    return state;
  }
  return {
    ...state,
    suggestions: state.suggestions.some((current) => current.id === suggestion.id)
      ? state.suggestions.map((current) => (current.id === suggestion.id ? suggestion : current))
      : [...state.suggestions, suggestion],
  };
}

function upsertStep(steps: ExecutionStep[], step: ExecutionStep): ExecutionStep[] {
  return steps.some((current) => current.id === step.id)
    ? steps.map((current) => (current.id === step.id ? step : current))
    : [...steps, step];
}

function isHiddenPhaseStep(step: ExecutionStep): boolean {
  if (step.kind !== "phase") {
    return false;
  }
  return /:phase:\d+:(start|end)$/.test(step.id) || /^第 \d+ 轮(开始|结束)$/.test(step.title);
}

function closeRunningSteps(steps: ExecutionStep[], status: "done" | "failed"): ExecutionStep[] {
  return steps.map((step) => (step.status === "running" ? { ...step, status } : step));
}

function mergeRecordsById<T extends { id: string }>(current: T[], next: T[]): T[] {
  const merged = [...current];
  for (const item of next) {
    const index = merged.findIndex((currentItem) => currentItem.id === item.id);
    if (index >= 0) {
      merged[index] = item;
    } else {
      merged.push(item);
    }
  }
  return merged;
}

function nextResponseId(state: TurnState): string {
  return `${state.turnId}:response:${state.responses.length + 1}`;
}

function readResponseId(value: unknown): string {
  return typeof value === "string" && value ? value : "";
}

function findTimelineInsertionIndex(items: ThreadItem[], steps: ExecutionStep[]): number {
  const firstStepTime = steps.map((step) => step.created_at || "").filter(Boolean).sort()[0] || "";
  if (!firstStepTime) {
    return items.length;
  }
  const index = items.findIndex(
    (item) => item.type === "message" && item.message.role === "assistant" && item.message.created_at >= firstStepTime,
  );
  return index >= 0 ? index : items.length;
}

function readToolStatus(value: unknown): ToolCard["status"] {
  return value === "failed" ? "failed" : "done";
}

function readStepStatus(value: unknown): ExecutionStep["status"] {
  if (value === "running" || value === "failed") {
    return value;
  }
  return "done";
}

function readStepKind(value: unknown): ExecutionStep["kind"] {
  if (
    value === "thought" ||
    value === "search" ||
    value === "read" ||
    value === "file" ||
    value === "command" ||
    value === "skill" ||
    value === "tape" ||
    value === "agent" ||
    value === "help" ||
    value === "control" ||
    value === "tool" ||
    value === "phase" ||
    value === "complete"
  ) {
    return value;
  }
  return "tool";
}

function readInteraction(value: unknown): ExecutionStep["interaction"] {
  if (!value || typeof value !== "object") {
    return undefined;
  }
  const interaction = value as Record<string, unknown>;
  const question = typeof interaction.question === "string" ? interaction.question : "";
  const candidates = Array.isArray(interaction.candidates)
    ? interaction.candidates.filter((candidate): candidate is string => typeof candidate === "string")
    : [];
  const status = typeof interaction.status === "string" ? interaction.status : "";
  const intent = typeof interaction.intent === "string" ? interaction.intent : "";
  if (!question && candidates.length === 0 && !status && !intent) {
    return undefined;
  }
  return { question, candidates, status, intent };
}

function readArtifactKind(value: unknown): ArtifactRecord["kind"] {
  if (value === "link" || value === "text") {
    return value;
  }
  return "file";
}

// 去重函数：确保每个 step/artifact 只出现一次
function deduplicateSteps(steps: ExecutionStep[]): ExecutionStep[] {
  // 简化：基于 step.id 去重，保留第一个
  const seen = new Map<string, ExecutionStep>();
  for (const step of steps) {
    if (!seen.has(step.id)) {
      seen.set(step.id, step);
    }
  }
  return Array.from(seen.values());
}

function deduplicateArtifacts(artifacts: ArtifactRecord[]): ArtifactRecord[] {
  // 简化：基于 artifact.id 去重，保留第一个
  const seen = new Map<string, ArtifactRecord>();
  for (const artifact of artifacts) {
    if (!seen.has(artifact.id)) {
      seen.set(artifact.id, artifact);
    }
  }
  return Array.from(seen.values());
}
