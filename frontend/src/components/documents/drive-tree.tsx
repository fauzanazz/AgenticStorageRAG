"use client";

import { useState, useMemo, useEffect } from "react";
import {
  ChevronRight,
  ChevronDown,
  Folder,
  FolderOpen,
  FileText,
} from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  DriveTreeResponse,
  DriveFolderNode,
  DriveFileNode,
  IndexedFileStatus,
} from "@/types/documents";

// ── Status badge ─────────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<
  IndexedFileStatus,
  { label: string; bg: string; color: string }
> = {
  pending: { label: "Scanned", bg: "#e3f2fd", color: "#1565c0" },
  processing: { label: "Processing", bg: "#fff3e0", color: "#e65100" },
  completed: { label: "Processed", bg: "#e8f5e9", color: "#2e7d32" },
  failed: { label: "Failed", bg: "#fce4ec", color: "#9e3f4e" },
  skipped: { label: "Skipped", bg: "#f0edef", color: "#7b7a7d" },
};

function StatusBadge({ status }: { status: IndexedFileStatus }) {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.pending;
  return (
    <span
      className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap"
      style={{ background: config.bg, color: config.color }}
    >
      {config.label}
    </span>
  );
}

function formatFileSize(bytes: number | null): string {
  if (bytes == null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

// ── FileNode ─────────────────────────────────────────────────────────────────

function FileNode({ file, depth }: { file: DriveFileNode; depth: number }) {
  return (
    <div
      className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm transition-colors hover:bg-black/[0.03]"
      style={{ paddingLeft: `${depth * 20 + 12}px` }}
    >
      <FileText className="size-4 shrink-0" style={{ color: "var(--primary)" }} />
      <span className="truncate" style={{ color: "color-mix(in srgb, var(--foreground) 80%, transparent)" }}>{file.file_name}</span>
      {file.size_bytes != null && (
        <span className="shrink-0 text-xs" style={{ color: "var(--outline)" }}>
          {formatFileSize(file.size_bytes)}
        </span>
      )}
      <span className="ml-auto shrink-0">
        <StatusBadge status={file.status} />
      </span>
    </div>
  );
}

// ── FolderNode ───────────────────────────────────────────────────────────────

function FolderNodeRow({
  folder,
  depth,
  expanded,
  onToggle,
}: {
  folder: DriveFolderNode;
  depth: number;
  expanded: Set<string>;
  onToggle: (path: string) => void;
}) {
  const isOpen = expanded.has(folder.path);

  return (
    <div>
      <button
        onClick={() => onToggle(folder.path)}
        className="flex w-full items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors hover:bg-black/[0.03]"
        style={{ paddingLeft: `${depth * 20 + 12}px` }}
      >
        {isOpen ? (
          <ChevronDown className="size-4 shrink-0" style={{ color: "var(--muted-foreground)" }} />
        ) : (
          <ChevronRight className="size-4 shrink-0" style={{ color: "var(--muted-foreground)" }} />
        )}
        {isOpen ? (
          <FolderOpen className="size-4 shrink-0" style={{ color: "#b8860b" }} />
        ) : (
          <Folder className="size-4 shrink-0" style={{ color: "#b8860b" }} />
        )}
        <span className="truncate">{folder.name}</span>
        <span
          className="ml-1 shrink-0 rounded-full px-1.5 py-0.5 text-[10px]"
          style={{ background: "var(--surface-container-high)", color: "var(--muted-foreground)" }}
        >
          {folder.processed_files}/{folder.total_files}
        </span>
      </button>

      {isOpen && (
        <>
          {folder.folders.map((child) => (
            <FolderNodeRow
              key={child.path}
              folder={child}
              depth={depth + 1}
              expanded={expanded}
              onToggle={onToggle}
            />
          ))}
          {folder.files.map((file) => (
            <FileNode key={file.id} file={file} depth={depth + 1} />
          ))}
        </>
      )}
    </div>
  );
}

// ── DriveTree (root) ─────────────────────────────────────────────────────────

interface DriveTreeProps {
  data: DriveTreeResponse | null;
  isLoading: boolean;
}

export function DriveTree({ data, isLoading }: DriveTreeProps) {
  // Initialize expanded set with first-level folder paths
  const initialExpanded = useMemo(() => {
    if (!data) return new Set<string>();
    return new Set(data.root.folders.map((f) => f.path));
  }, [data]);

  const [expanded, setExpanded] = useState<Set<string>>(initialExpanded);

  // Re-sync when data loads for the first time
  useEffect(() => {
    if (initialExpanded.size > 0) {
      setExpanded(initialExpanded);
    }
  }, [initialExpanded]);

  const toggle = (path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-8 rounded-lg" />
        ))}
      </div>
    );
  }

  if (!data || data.total_files === 0) {
    return (
      <div
        className="flex flex-col items-center justify-center rounded-2xl py-12 text-center"
        style={{ border: "2px dashed var(--outline-variant)" }}
      >
        <Folder className="mb-3 size-10" style={{ color: "var(--outline-variant)" }} />
        <p className="text-sm font-medium" style={{ color: "var(--muted-foreground)" }}>
          No Drive files indexed
        </p>
        <p className="mt-1 text-xs" style={{ color: "var(--outline)" }}>
          Run an ingestion job to scan Google Drive files
        </p>
      </div>
    );
  }

  return (
    <div>
      {/* Summary bar */}
      <div
        className="mb-3 flex items-center gap-4 rounded-xl px-4 py-2.5 text-xs"
        style={{
          background: "var(--card)",
          border: "1px solid var(--border)",
          color: "var(--muted-foreground)",
        }}
      >
        <span>{data.scanned_files} files scanned</span>
        <span style={{ color: "var(--border)" }}>|</span>
        <span style={{ color: "var(--success)" }}>{data.processed_files} processed</span>
        {data.total_files - data.processed_files > 0 && (
          <>
            <span style={{ color: "var(--border)" }}>|</span>
            <span>{data.total_files - data.processed_files} remaining</span>
          </>
        )}
      </div>

      {/* Tree */}
      <div
        className="rounded-2xl py-1"
        style={{
          background: "var(--card)",
          border: "1px solid var(--border)",
        }}
      >
        {data.root.folders.map((folder) => (
          <FolderNodeRow
            key={folder.path}
            folder={folder}
            depth={0}
            expanded={expanded}
            onToggle={toggle}
          />
        ))}
        {data.root.files.map((file) => (
          <FileNode key={file.id} file={file} depth={0} />
        ))}
      </div>
    </div>
  );
}
