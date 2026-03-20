/** Chat and agent-related types */

export type MessageRole = "user" | "assistant" | "system";

export interface Citation {
  document_id: string;
  document_name: string;
  chunk_text: string;
  page_number?: number;
  relevance_score: number;
  source_url: string | null;
}

export interface ToolResultItem {
  content?: string;
  entity_name?: string;
  entity_type?: string;
  description?: string;
  source?: string;
  score?: number;
  similarity?: number;
  relevance?: number;
  document_id?: string;
  relationships?: { type: string; target: string }[];
}

export interface NarrativeStep {
  type: "thinking" | "tool_call";
  /** For thinking steps — the reasoning text */
  content?: string;
  /** For tool_call steps */
  tool_name?: string;
  tool_label?: string;
  tool_args?: Record<string, unknown>;
  tool_status?: "running" | "done" | "error";
  tool_summary?: string;
  tool_count?: number;
  tool_duration_ms?: number;
  tool_results?: ToolResultItem[];
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  citations: Citation[];
  steps: NarrativeStep[];
  timestamp: string;
  is_clarifying_question?: boolean;
}

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

// ---------------------------------------------------------------------------
// SSE event payloads (match backend schemas)
// ---------------------------------------------------------------------------

export interface ToolStartPayload {
  tool_name: string;
  tool_label: string;
  arguments: Record<string, unknown>;
}

export interface ToolResultPayload {
  tool_name: string;
  tool_label: string;
  summary: string;
  count: number;
  duration_ms: number;
  error: string | null;
  results?: ToolResultItem[];
}

export interface ConversationCreatedPayload {
  conversation_id: string;
}

export interface MessageCreatedPayload {
  message_id: string;
  role: "user" | "assistant";
}

export interface DonePayload {
  conversation_id: string;
  citations_count: number;
  tools_used: string[];
}

export interface CitationPayload {
  document_id?: string;
  document_name?: string;
  entity_name?: string;
  content_snippet?: string;
  page_number?: number;
  relevance_score?: number;
  source_url?: string | null;
}

export interface ErrorPayload {
  error: string;
}
