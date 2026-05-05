export type ExecutionToolCall = {
  tool: string;
  args: string;
  result: string;
  action: string;
  status: string;
};

export type LlmInfo = {
  index: number;
  name: string;
  current: boolean;
};

export type ExecutionTurn = {
  turn: number;
  title: string;
  content: string;
  tool_calls: ExecutionToolCall[];
};

export type GroupSummary = {
  id: string;
  name: string;
  sort_order: number;
  created_at: string;
  updated_at: string;
};

export type ConversationSummary = {
  id: string;
  title: string;
  group_id: string | null;
  pinned: boolean;
  archived: boolean;
  preview: string;
  last_message_at: string;
  created_at: string;
  updated_at: string;
};

export type ConversationMessage = {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  source: string;
  execution_log: ExecutionTurn[];
  created_at: string;
};

export type ConversationDetail = {
  summary: ConversationSummary;
  messages: ConversationMessage[];
  execution_log: ExecutionTurn[];
};

export type RuntimeState = {
  configured: boolean;
  current_llm: LlmInfo | null;
  llms: LlmInfo[];
  running: boolean;
  autonomous_enabled: boolean;
  last_reply_time: number;
  active_conversation_id: string | null;
  execution_log: ExecutionTurn[];
  conversations?: ConversationSummary[];
  groups?: GroupSummary[];
  error?: string;
};

export type StreamEvent =
  | {
      event: "message_delta" | "message_done";
      content: string;
      conversation_id: string;
    }
  | {
      event: "execution_update";
      execution_log: ExecutionTurn[];
      conversation_id: string;
    }
  | {
      event: "heartbeat";
      status: string;
    }
  | {
      event: "app_error";
      error: string;
    };
