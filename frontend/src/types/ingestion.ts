/** Ingestion domain types */

export type IngestionStatus =
  | "pending"
  | "scanning"
  | "processing"
  | "completed"
  | "failed"
  | "cancelled";

export interface AgentLogEntry {
  ts: string;
  msg: string;
  processed: number;
  failed: number;
  skipped: number;
  total: number;
  folder?: string;
}

export type FileEventState = "started" | "completed" | "skipped" | "failed";

export interface FileEvent {
  name: string;
  state: FileEventState;
  ts: string;
  folder?: string;
  chunks?: number;
  embeddings?: number;
}

/** file_events is keyed by Drive file_id */
export type FileEvents = Record<string, FileEvent>;

export interface IngestionJobMetadata {
  current_action?: string;
  current_folder?: string;
  agent_log?: AgentLogEntry[];
  file_events?: FileEvents;
  orchestrator_summary?: string;
  orchestrator_warning?: string;
  [key: string]: unknown;
}

export interface IngestionJob {
  id: string;
  source: string;
  status: IngestionStatus;
  folder_id: string | null;
  total_files: number;
  processed_files: number;
  failed_files: number;
  skipped_files: number;
  error_message: string | null;
  metadata: IngestionJobMetadata;
  started_at: string;
  completed_at: string | null;
}

export interface IngestionJobList {
  items: IngestionJob[];
  total: number;
}

export interface IngestionStatsResponse {
  total_jobs: number;
  jobs_by_status: Record<string, number>;
  total_files_processed: number;
  total_files_failed: number;
  total_files_skipped: number;
  active_job: IngestionJob | null;
}

export interface TriggerIngestionRequest {
  folder_id?: string | null;
  force?: boolean;
}

export interface DriveFolderEntry {
  file_id: string;
  name: string;
  mime_type: string;
  size: number | null;
  modified_time: string | null;
  is_folder: boolean;
}

export interface DefaultFolder {
  folder_id: string | null;
  folder_name: string | null;
}

export interface LLMModelCostStats {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export interface LLMCostSummary {
  total_calls: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
  by_model: Record<string, LLMModelCostStats>;
  note?: string;
  source?: string;
}
