"use client";

import { FileText, MoreVertical, Trash2 } from "lucide-react";
import type { Document, DocumentStatus } from "@/types/documents";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface DocumentListProps {
  documents: Document[];
  isLoading: boolean;
  onDelete: (id: string) => void;
}

const STATUS_CONFIG: Record<
  DocumentStatus,
  { label: string; className: string }
> = {
  uploading: {
    label: "Uploading",
    className: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  },
  processing: {
    label: "Processing",
    className: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  },
  ready: {
    label: "Ready",
    className: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  },
  failed: {
    label: "Failed",
    className: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  },
  expired: {
    label: "Expired",
    className: "bg-gray-100 text-gray-700 dark:bg-gray-900/30 dark:text-gray-400",
  },
};

function StatusBadge({ status }: { status: DocumentStatus }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.processing;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        config.className
      )}
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
          <div
            key={i}
            className="h-20 animate-pulse rounded-lg bg-muted"
          />
        ))}
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-12 text-center">
        <FileText className="mb-3 size-10 text-muted-foreground" />
        <p className="text-sm font-medium text-muted-foreground">
          No documents yet
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Upload a PDF or DOCX to get started
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {documents.map((doc) => (
        <Card key={doc.id} className="transition-colors hover:bg-muted/30">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 py-3">
            <div className="flex items-center gap-3 min-w-0">
              <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                <FileText className="size-5 text-primary" />
              </div>
              <div className="min-w-0">
                <CardTitle className="truncate text-sm">
                  {doc.filename}
                </CardTitle>
                <CardDescription className="flex items-center gap-2 text-xs">
                  <span>{formatFileSize(doc.file_size)}</span>
                  <span>-</span>
                  <span>{formatDate(doc.uploaded_at)}</span>
                  {doc.chunk_count > 0 && (
                    <>
                      <span>-</span>
                      <span>{doc.chunk_count} chunks</span>
                    </>
                  )}
                </CardDescription>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <StatusBadge status={doc.status} />
              <Button
                variant="ghost"
                size="icon-xs"
                onClick={() => onDelete(doc.id)}
                title="Delete document"
              >
                <Trash2 className="size-3.5 text-muted-foreground" />
              </Button>
            </div>
          </CardHeader>
        </Card>
      ))}
    </div>
  );
}
