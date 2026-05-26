export type StreamEventType =
  | "answer.delta"
  | "answer.retract"
  | "answer.final"
  | "phase.update"
  | "timeline.step"
  | "tool.start"
  | "tool.end"
  | "artifact.created"
  | "suggestion.created"
  | "turn.error"
  | "turn.done";

export type StreamEvent = {
  type: StreamEventType;
  turn_id: string;
  session_id: string;
  data: Record<string, unknown>;
};

export type SessionRecord = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type MessageRecord = {
  role: "user" | "assistant";
  content: string;
  created_at: string;
  turn_id?: string;
  response_id?: string;
  ga_turn?: number;
  outputs?: string[];
  source?: string;
  elapsed_ms?: number;
};

export type ImageAttachment = {
  id: string;
  name: string;
  dataUrl: string;
};

export type ExecutionStep = {
  id: string;
  turn_id?: string;
  response_id?: string;
  kind:
    | "thought"
    | "search"
    | "read"
    | "file"
    | "command"
    | "skill"
    | "tape"
    | "agent"
    | "help"
    | "control"
    | "tool"
    | "phase"
    | "complete";
  title: string;
  status: "running" | "done" | "failed";
  summary: string;
  detail: string;
  input?: string;
  output?: string;
  error?: string;
  elapsed_ms?: number;
  tool_name?: string;
  tool_label?: string;
  created_at?: string;
  default_open?: boolean;
  interaction?: HumanInteraction;
};

export type HumanInteraction = {
  status: string;
  intent: "HUMAN_INTERVENTION" | string;
  question: string;
  candidates: string[];
};

export type ArtifactRecord = {
  id: string;
  turn_id?: string;
  response_id?: string;
  name: string;
  kind: "file" | "link" | "text";
  path?: string;
  url?: string;
  created_at?: string;
};

export type FollowupSuggestion = {
  id: string;
  text: string;
};

export type SessionTranscript = {
  messages: MessageRecord[];
  timeline: ExecutionStep[];
  artifacts: ArtifactRecord[];
};

export type TurnPhase = {
  phase: string;
  label: string;
};

export type TurnResponse = {
  id: string;
  content: string;
  created_at?: string;
  elapsed_ms?: number;
};

export type ToolCard = {
  id: string;
  name: string;
  status: "running" | "done" | "failed";
  summary?: string;
  elapsedMs?: number;
};
