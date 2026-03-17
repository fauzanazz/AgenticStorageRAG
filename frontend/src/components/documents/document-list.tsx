"use client";

import { FileText, Trash2 } from "lucide-react";
import type { Document, DocumentStatus } from "@/types/documents";
import { Skeleton } from "@/components/ui/skeleton";

interface DocumentListProps {
  documents: Document[];
  isLoading: boolean;
  onDelete: (id: string) => void;
}

const STATUS_CONFIG: Record<
  DocumentStatus,
  { label: string; bg: string; color: string }
> = {
  uploading: { label: "Uploading", bg: "rgba(59,130,246,0.15)", color: "#60A5FA" },
  processing: { label: "Processing", bg: "rgba(245,158,11,0.15)", color: "#FBBF24" },
  ready: { label: "Ready", bg: "rgba(34,197,94,0.15)", color: "#4ADE80" },
  failed: { label: "Failed", bg: "rgba(239,68,68,0.15)", color: "#FCA5A5" },
  expired: { label: "Expired", bg: "rgba(255,255,255,0.06)", color: "rgba(255,255,255,0.4)" },
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
}: DocumentListProps) {
  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-20 rounded-2xl" />
        ))}
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div
        className="flex flex-col items-center justify-center rounded-2xl py-12 text-center"
        style={{ border: "2px dashed rgba(255,255,255,0.08)" }}
      >
        <FileText className="mb-3 size-10" style={{ color: "rgba(255,255,255,0.2)" }} />
        <p className="text-sm font-medium" style={{ color: "rgba(255,255,255,0.4)" }}>
          No documents yet
        </p>
        <p className="mt-1 text-xs" style={{ color: "rgba(255,255,255,0.3)" }}>
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
          className="flex items-center justify-between rounded-2xl px-4 py-3 transition-all hover:bg-white/[0.02]"
          style={{
            background: "rgba(255,255,255,0.03)",
            border: "1px solid rgba(255,255,255,0.06)",
          }}
        >
          <div className="flex items-center gap-3 min-w-0">
            <div
              className="flex size-10 shrink-0 items-center justify-center rounded-xl"
              style={{ background: "rgba(99,102,241,0.12)" }}
            >
              <FileText className="size-5" style={{ color: "#818CF8" }} />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-white">
                {doc.filename}
              </p>
              <p className="flex items-center gap-2 text-xs" style={{ color: "rgba(255,255,255,0.4)" }}>
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
              className="rounded-lg p-1.5 transition-colors hover:bg-white/5"
              style={{ color: "rgba(255,255,255,0.3)" }}
            >
              <Trash2 className="size-4" />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
