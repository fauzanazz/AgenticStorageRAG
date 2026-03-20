/** Document-related types */

export type DocumentStatus =
  | "uploading"
  | "processing"
  | "ready"
  | "failed"
  | "expired";

export type DocumentSource = "upload" | "google_drive";

export interface Document {
  id: string;
  filename: string;
  file_type: string;
  file_size: number;
  status: DocumentStatus;
  source: DocumentSource;
  uploaded_at: string;
  expires_at: string;
  chunk_count: number;
  is_base_knowledge: boolean;
  metadata: Record<string, unknown>;
}

/** Indexed file status from the ingestion pipeline */
export type IndexedFileStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed"
  | "skipped";

export interface DriveFileNode {
  id: string;
  drive_file_id: string;
  file_name: string;
  mime_type: string;
  size_bytes: number | null;
  folder_path: string;
  status: IndexedFileStatus;
  document_id: string | null;
  created_at: string;
  processed_at: string | null;
}

export interface DriveFolderNode {
  name: string;
  path: string;
  folders: DriveFolderNode[];
  files: DriveFileNode[];
  total_files: number;
  processed_files: number;
}

export interface DriveTreeResponse {
  root: DriveFolderNode;
  total_files: number;
  processed_files: number;
  scanned_files: number;
}
