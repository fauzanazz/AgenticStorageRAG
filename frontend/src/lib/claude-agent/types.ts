export interface ToolCallRecord {
  tool_name: string;
  arguments: Record<string, unknown>;
  result_summary: string;
  duration_ms: number;
  results: Record<string, unknown>[];
}

export interface CitationData {
  document_id?: string;
  document_name?: string;
  chunk_id?: string;
  entity_id?: string;
  entity_name?: string;
  content_snippet: string;
  page_number?: number;
  source_type: string;
  relevance_score: number;
  source_url?: string | null;
}

export interface StreamRequest {
  message: string;
  conversation_id?: string;
  model?: string;
  enable_thinking?: boolean;
  attachment_ids?: string[];
}
