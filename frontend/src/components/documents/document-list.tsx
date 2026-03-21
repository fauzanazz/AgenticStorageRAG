"use client";

import { FileText, Trash2 } from "lucide-react";
import type { Document, DocumentStatus } from "@/types/documents";
import { Skeleton } from "@/components/ui/skeleton";

interface DocumentListProps {
  documents: Document[];
  isLoading: boolean;
  onDelete: (id: string) => void;
  showSource?: boolean;
}

const STATUS_CONFIG: Record<
  DocumentStatus,
  { label: string; bg: string; color: string }
> = {
  uploading: { label: "Uploading", bg: "#e3f2fd", color: "#1565c0" },
  processing: { label: "Processing", bg: "#fff3e0", color: "#e65100" },
  ready: { label: "Ready", bg: "#e8f5e9", color: "#2e7d32" },
  failed: { label: "Failed", bg: "#fce4ec", color: "#9e3f4e" },
  expired: { label: "Expired", bg: "#f0edef", color: "#7b7a7d" },
};

function StatusBadge({ status }: { status: DocumentStatus }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.processing;
  return (
    <span
      className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium"
      style={{ background: config.bg, color: config.color }}
    >
      {config.label}
    </span>
  );
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function DocumentList({
  documents,
  isLoading,
  onDelete,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  showSource = false,
}: DocumentListProps) {
  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((n) => (
          <Skeleton key={n} className="h-20 rounded-2xl" />
        ))}
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div
        className="flex flex-col items-center justify-center rounded-2xl py-12 text-center"
        style={{ border: "2px dashed var(--outline-variant)" }}
      >
        <FileText className="mb-3 size-10" style={{ color: "var(--outline-variant)" }} />
        <p className="text-sm font-medium" style={{ color: "var(--muted-foreground)" }}>
          No documents yet
        </p>
        <p className="mt-1 text-xs" style={{ color: "var(--outline)" }}>
          Upload a PDF or DOCX to get started
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {documents.map((doc) => (
        <div
          key={doc.id}
          className="flex items-center justify-between rounded-2xl px-4 py-3 transition-all hover:bg-black/[0.03]"
          style={{
            background: "var(--card)",
            border: "1px solid var(--border)",
          }}
        >
          <div className="flex items-center gap-3 min-w-0">
            <div
              className="flex size-10 shrink-0 items-center justify-center rounded-xl"
              style={{ background: "var(--accent)" }}
            >
              <FileText className="size-5" style={{ color: "var(--primary)" }} />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">
                {doc.filename}
              </p>
              <p className="flex items-center gap-2 text-xs" style={{ color: "var(--muted-foreground)" }}>
                <span>{formatFileSize(doc.file_size)}</span>
                <span>-</span>
                <span>{formatDate(doc.uploaded_at)}</span>
                {doc.chunk_count > 0 && (
                  <>
                    <span>-</span>
                    <span>{doc.chunk_count} chunks</span>
                  </>
                )}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <StatusBadge status={doc.status} />
            <button
              onClick={() => onDelete(doc.id)}
              title="Delete document"
              className="rounded-lg p-1.5 transition-colors hover:bg-black/5"
              style={{ color: "var(--outline)" }}
            >
              <Trash2 className="size-4" />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
