export type LlmInfo = {
  index: number;
  name: string;
  current: boolean;
};

export type ExecutionTurn = {
  turn: number;
  title: string;
  content: string;
};

export type RuntimeState = {
  configured: boolean;
  current_llm: LlmInfo | null;
  llms: LlmInfo[];
  running: boolean;
  autonomous_enabled: boolean;
  last_reply_time: number;
  error?: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  time: string;
};

export type StreamEvent = {
  event: "next" | "done" | "heartbeat" | "app_error";
  content?: string;
  execution_log?: ExecutionTurn[];
  error?: string;
};
