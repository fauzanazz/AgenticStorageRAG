/** Document-related types */

export type DocumentStatus =
  | "uploading"
  | "processing"
  | "ready"
  | "failed"
  | "expired";

export interface Document {
  id: string;
  filename: string;
  file_type: string;
  file_size: number;
  status: DocumentStatus;
  uploaded_at: string;
  expires_at: string;
  chunk_count: number;
  metadata: Record<string, unknown>;
}
