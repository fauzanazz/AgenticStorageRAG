/** Ingestion domain types */

export type IngestionStatus =
  | "pending"
  | "scanning"
  | "processing"
  | "completed"
  | "failed"
  | "cancelled";

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
  metadata: Record<string, unknown>;
  started_at: string;
  completed_at: string | null;
}

export interface IngestionJobList {
  items: IngestionJob[];
  total: number;
}

export interface TriggerIngestionRequest {
  folder_id?: string | null;
  force?: boolean;
}
