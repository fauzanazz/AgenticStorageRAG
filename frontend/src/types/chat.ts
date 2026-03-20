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
  type: "thinking" | "tool_call" | "narration";
  /** For thinking/narration steps — the text */
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

// ---------------------------------------------------------------------------
// Artifact types
// ---------------------------------------------------------------------------

export interface Artifact {
  id: string;
  conversation_id: string;
  message_id?: string;
  user_id: string;
  type: string;
  title: string;
  content: string;
  language?: string;
  created_at: string;
  updated_at: string;
}

export interface ArtifactStartPayload {
  artifact_id: string;
  title: string;
  type: string;
}

export interface ArtifactDeltaPayload {
  artifact_id: string;
  content: string;
}

export interface ArtifactEndPayload {
  artifact_id: string;
  title: string;
  type: string;
  content_length: number;
  error?: string;
}

// ---------------------------------------------------------------------------
// Chat Attachments
// ---------------------------------------------------------------------------

export type AttachmentStatus = "uploading" | "ready" | "error";

export interface ChatAttachment {
  id: string;
  filename: string;
  size: number;
  mime_type: string;
  status: AttachmentStatus;
  /** Only set when status is "error" */
  error?: string;
}

export interface DriveBrowseEntry {
  id: string;
  name: string;
  mime_type: string;
  size: number | null;
  is_folder: boolean;
  modified_time: string | null;
}
