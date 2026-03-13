/** Chat and agent-related types */

export type MessageRole = "user" | "assistant" | "system";

export interface Citation {
  document_id: string;
  document_name: string;
  chunk_text: string;
  page_number?: number;
  relevance_score: number;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  citations: Citation[];
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
