"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { FileText, Folder, Image, X } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import type { DriveBrowseEntry } from "@/types/chat";

interface DriveFileBrowserProps {
  open: boolean;
  onClose: () => void;
  onAttach: (fileIds: string[]) => void;
}

interface Breadcrumb {
  id: string | null;
  name: string;
}

function formatFileSize(bytes: number | null): string {
  if (bytes === null || bytes === undefined) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileIcon(entry: DriveBrowseEntry) {
  if (entry.is_folder) return <Folder size={18} />;
  if (entry.mime_type.startsWith("image/")) return <Image size={18} />;
  return <FileText size={18} />;
}

function sortEntries(entries: DriveBrowseEntry[]): DriveBrowseEntry[] {
  return [...entries].sort((a, b) => {
    if (a.is_folder && !b.is_folder) return -1;
    if (!a.is_folder && b.is_folder) return 1;
    return a.name.localeCompare(b.name);
  });
}

export function DriveFileBrowser({ open, onClose, onAttach }: DriveFileBrowserProps) {
  const [currentFolderId, setCurrentFolderId] = useState<string | null>(null);
  const [breadcrumbs, setBreadcrumbs] = useState<Breadcrumb[]>([
    { id: null, name: "My Drive" },
  ]);
  const [entries, setEntries] = useState<DriveBrowseEntry[]>([]);
  const [selectedFileIds, setSelectedFileIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const backdropRef = useRef<HTMLDivElement>(null);

  const resetState = useCallback(() => {
    setCurrentFolderId(null);
    setBreadcrumbs([{ id: null, name: "My Drive" }]);
    setEntries([]);
    setSelectedFileIds(new Set());
    setError(null);
  }, []);

  // Fetch entries when folder changes or modal opens
  useEffect(() => {
    if (!open) return;

    let cancelled = false;
    setLoading(true);
    setError(null);

    const params = currentFolderId ? `?folder_id=${encodeURIComponent(currentFolderId)}` : "";
    apiClient
      .get<DriveBrowseEntry[]>(`/admin/ingestion/drive/browse-files${params}`)
      .then((data) => {
        if (!cancelled) setEntries(sortEntries(data));
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || "Failed to load files");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, currentFolderId]);

  // Reset when modal closes
  useEffect(() => {
    if (!open) resetState();
  }, [open, resetState]);

  const handleFolderClick = (folder: DriveBrowseEntry) => {
    setBreadcrumbs((prev) => [...prev, { id: folder.id, name: folder.name }]);
    setCurrentFolderId(folder.id);
    setSelectedFileIds(new Set());
  };

  const handleBreadcrumbClick = (index: number) => {
    const target = breadcrumbs[index];
    setBreadcrumbs((prev) => prev.slice(0, index + 1));
    setCurrentFolderId(target.id);
    setSelectedFileIds(new Set());
  };

  const toggleFileSelection = (fileId: string) => {
    setSelectedFileIds((prev) => {
      const next = new Set(prev);
      if (next.has(fileId)) next.delete(fileId);
      else next.add(fileId);
      return next;
    });
  };

  const handleAttach = () => {
    onAttach(Array.from(selectedFileIds));
    onClose();
  };

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === backdropRef.current) onClose();
  };

  if (!open) return null;

  const selectedCount = selectedFileIds.size;

  return (
    <div
      ref={backdropRef}
      onClick={handleBackdropClick}
      className="fixed inset-0 z-50 flex items-start justify-center"
      style={{ background: "rgba(0,0,0,0.5)" }}
    >
      <div
        className="flex flex-col w-full h-full sm:h-auto sm:max-w-lg sm:mt-20 sm:rounded-xl overflow-hidden shadow-xl"
        style={{
          background: "var(--card)",
          border: "1px solid var(--outline-variant)",
          maxHeight: "calc(100vh - 5rem)",
        }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-4 py-3 shrink-0"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <h2 className="text-base font-semibold">Browse Google Drive</h2>
          <button
            onClick={onClose}
            className="p-1 rounded-md transition-colors hover:bg-black/[0.06]"
            style={{ color: "var(--muted-foreground)" }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Breadcrumbs */}
        <div
          className="flex items-center gap-1 px-4 py-2 text-sm overflow-x-auto shrink-0"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          {breadcrumbs.map((crumb, i) => (
            <span key={i} className="flex items-center gap-1 whitespace-nowrap">
              {i > 0 && (
                <span style={{ color: "var(--muted-foreground)" }}>/</span>
              )}
              <button
                onClick={() => handleBreadcrumbClick(i)}
                className="hover:underline transition-colors"
                style={{
                  color:
                    i === breadcrumbs.length - 1
                      ? "var(--on-surface)"
                      : "var(--primary)",
                  fontWeight: i === breadcrumbs.length - 1 ? 600 : 400,
                }}
              >
                {crumb.name}
              </button>
            </span>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto min-h-0">
          {loading && (
            <div className="p-4 space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="flex items-center gap-3">
                  <div
                    className="h-5 w-5 rounded animate-pulse"
                    style={{ background: "var(--muted)" }}
                  />
                  <div
                    className="h-4 rounded animate-pulse flex-1"
                    style={{
                      background: "var(--muted)",
                      maxWidth: `${60 + (i % 3) * 15}%`,
                    }}
                  />
                </div>
              ))}
            </div>
          )}

          {!loading && error && (
            <div
              className="p-4 text-sm text-center"
              style={{ color: "var(--on-surface-variant)" }}
            >
              {error}
            </div>
          )}

          {!loading && !error && entries.length === 0 && (
            <div
              className="p-8 text-sm text-center"
              style={{ color: "var(--on-surface-variant)" }}
            >
              No files found in this folder
            </div>
          )}

          {!loading && !error && entries.length > 0 && (
            <ul className="py-1">
              {entries.map((entry) => {
                const isSelected = selectedFileIds.has(entry.id);

                if (entry.is_folder) {
                  return (
                    <li key={entry.id}>
                      <button
                        onClick={() => handleFolderClick(entry)}
                        className="flex items-center gap-3 w-full px-4 py-2.5 text-left text-sm transition-colors hover:bg-black/[0.04]"
                      >
                        <span style={{ color: "var(--primary)" }}>
                          {getFileIcon(entry)}
                        </span>
                        <span className="truncate flex-1 font-medium">
                          {entry.name}
                        </span>
                      </button>
                    </li>
                  );
                }

                return (
                  <li key={entry.id}>
                    <button
                      onClick={() => toggleFileSelection(entry.id)}
                      className="flex items-center gap-3 w-full px-4 py-2.5 text-left text-sm transition-colors hover:bg-black/[0.04]"
                      style={{
                        background: isSelected
                          ? "var(--primary-dim)"
                          : undefined,
                      }}
                    >
                      {/* Checkbox */}
                      <span
                        className="flex items-center justify-center h-4 w-4 rounded border shrink-0"
                        style={{
                          borderColor: isSelected
                            ? "var(--primary)"
                            : "var(--outline-variant)",
                          background: isSelected
                            ? "var(--primary)"
                            : "transparent",
                          color: "white",
                        }}
                      >
                        {isSelected && (
                          <svg
                            width="10"
                            height="10"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="3"
                          >
                            <polyline points="20 6 9 17 4 12" />
                          </svg>
                        )}
                      </span>
                      <span style={{ color: "var(--on-surface-variant)" }}>
                        {getFileIcon(entry)}
                      </span>
                      <span className="truncate flex-1">{entry.name}</span>
                      {entry.size !== null && (
                        <span
                          className="text-xs shrink-0"
                          style={{ color: "var(--muted-foreground)" }}
                        >
                          {formatFileSize(entry.size)}
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Footer */}
        <div
          className="flex items-center justify-end gap-2 px-4 py-3 shrink-0"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-lg transition-colors hover:bg-black/[0.06]"
            style={{ color: "var(--on-surface-variant)" }}
          >
            Cancel
          </button>
          <button
            onClick={handleAttach}
            disabled={selectedCount === 0}
            className="px-4 py-2 text-sm font-medium rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            style={{
              background:
                selectedCount > 0 ? "var(--primary)" : "var(--muted)",
              color: selectedCount > 0 ? "white" : "var(--muted-foreground)",
            }}
          >
            {selectedCount === 0
              ? "Attach files"
              : `Attach ${selectedCount} file${selectedCount > 1 ? "s" : ""}`}
          </button>
        </div>
      </div>
    </div>
  );
}
