"use client";

import { FileText, Image as ImageIcon, X, Loader2 } from "lucide-react";
import type { ChatAttachment } from "@/types/chat";

interface AttachmentChipProps {
  attachment: ChatAttachment;
  onRemove: (id: string) => void;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function isImage(mime: string): boolean {
  return mime.startsWith("image/");
}

export function AttachmentChip({ attachment, onRemove }: AttachmentChipProps) {
  const uploading = attachment.status === "uploading";
  const error = attachment.status === "error";

  return (
    <div
      className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs max-w-[200px]"
      style={{
        background: error
          ? "color-mix(in srgb, var(--destructive) 10%, transparent)"
          : "var(--muted)",
        border: `1px solid ${error ? "color-mix(in srgb, var(--destructive) 30%, transparent)" : "var(--outline-variant)"}`,
        color: error ? "var(--destructive)" : "var(--on-surface-variant)",
      }}
      title={attachment.error || attachment.filename}
    >
      {uploading ? (
        <Loader2 className="size-3 animate-spin shrink-0" />
      ) : isImage(attachment.mime_type) ? (
        <ImageIcon className="size-3 shrink-0" />
      ) : (
        <FileText className="size-3 shrink-0" />
      )}
      <span className="truncate">{attachment.filename}</span>
      {attachment.size > 0 && !uploading && (
        <span className="shrink-0 opacity-60">{formatSize(attachment.size)}</span>
      )}
      <button
        type="button"
        onClick={() => onRemove(attachment.id)}
        className="shrink-0 rounded p-0.5 transition-colors hover:bg-black/10"
      >
        <X className="size-3" />
      </button>
    </div>
  );
}
