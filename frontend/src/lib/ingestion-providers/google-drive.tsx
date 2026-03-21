"use client";

import React, { useState, useRef } from "react";
import {
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Check,
  Folder,
  FolderOpen,
  Loader2,
} from "lucide-react";
import { useDriveFolders, useDefaultFolder } from "@/hooks/use-ingestion";
import type { DriveFolderEntry } from "@/types/ingestion";
import type { IngestionProvider, FolderChooserProps, ProviderState } from "./types";

// ── Folder tree node ──────────────────────────────────────────────────────

function FolderNode({
  folder,
  selectedId,
  onSelect,
  depth = 0,
}: {
  folder: DriveFolderEntry;
  selectedId: string | null;
  onSelect: (id: string, name: string) => void;
  depth?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  // For shortcuts, browse the target folder's children
  const browseId = folder.target_id ?? folder.file_id;
  const { data: children, isLoading } = useDriveFolders(browseId, expanded);
  const isSelected = selectedId === browseId;
  const subfolders = children?.filter((c) => c.is_folder) ?? [];

  return (
    <div>
      <div
        className="flex items-center gap-1 py-1.5 px-2 rounded-lg cursor-pointer transition-colors hover:bg-black/5 group"
        style={{
          paddingLeft: `${depth * 20 + 8}px`,
          background: isSelected ? "var(--accent)" : undefined,
        }}
      >
        <button
          onClick={(e) => {
            e.stopPropagation();
            setExpanded((v) => !v);
          }}
          className="w-5 h-5 flex items-center justify-center shrink-0 rounded transition-colors hover:bg-black/10"
        >
          {isLoading ? (
            <Loader2 className="size-3 animate-spin" style={{ color: "var(--muted-foreground)" }} />
          ) : expanded ? (
            <ChevronDown className="size-3.5" style={{ color: "var(--muted-foreground)" }} />
          ) : (
            <ChevronRight className="size-3.5" style={{ color: "var(--muted-foreground)" }} />
          )}
        </button>

        <div
          role="button"
          tabIndex={0}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(browseId, folder.name); } }}
          className="flex items-center gap-2 flex-1 min-w-0"
          onClick={() => onSelect(browseId, folder.name)}
        >
          {expanded ? (
            <FolderOpen className="size-4 shrink-0" style={{ color: isSelected ? "var(--primary)" : "var(--warning)" }} />
          ) : (
            <Folder className="size-4 shrink-0" style={{ color: isSelected ? "var(--primary)" : "var(--warning)" }} />
          )}
          <span
            className="text-sm truncate"
            style={{ fontWeight: isSelected ? 600 : 400, color: isSelected ? "var(--primary)" : undefined }}
          >
            {folder.name}
          </span>
        </div>

        {isSelected && (
          <Check className="size-4 shrink-0" style={{ color: "var(--primary)" }} />
        )}
      </div>

      {expanded && subfolders.length > 0 && (
        <div>
          {subfolders.map((child) => (
            <FolderNode
              key={child.file_id}
              folder={child}
              selectedId={selectedId}
              onSelect={onSelect}
              depth={depth + 1}
            />
          ))}
        </div>
      )}

      {expanded && !isLoading && subfolders.length === 0 && (
        <p
          className="text-xs py-1"
          style={{ paddingLeft: `${(depth + 1) * 20 + 8}px`, color: "var(--outline-variant)" }}
        >
          No subfolders
        </p>
      )}
    </div>
  );
}

// ── Folder picker ─────────────────────────────────────────────────────────

function DriveFolderPicker({
  selectedFolderId,
  selectedFolderName,
  onSelect,
}: FolderChooserProps) {
  const [open, setOpen] = useState(false);
  const { data: rootFolders, isLoading, error } = useDriveFolders("root", open);
  const folders = rootFolders?.filter((f) => f.is_folder) ?? [];

  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{ background: "var(--card)", border: "1px solid var(--border)" }}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full p-4 flex items-center justify-between gap-3 transition-colors hover:bg-black/[0.02]"
      >
        <div className="flex items-center gap-3 min-w-0">
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: "var(--accent)" }}
          >
            <FolderOpen className="size-4" style={{ color: "var(--primary)" }} />
          </div>
          <div className="text-left min-w-0">
            <p className="text-sm font-medium">Drive Folder</p>
            {selectedFolderName ? (
              <p className="text-xs truncate" style={{ color: "var(--primary)" }}>
                {selectedFolderName}
              </p>
            ) : (
              <p className="text-xs" style={{ color: "var(--outline)" }}>
                No folder selected — will scan entire Drive
              </p>
            )}
          </div>
        </div>
        {open ? (
          <ChevronUp className="size-4 shrink-0" style={{ color: "var(--muted-foreground)" }} />
        ) : (
          <ChevronDown className="size-4 shrink-0" style={{ color: "var(--muted-foreground)" }} />
        )}
      </button>

      {open && (
        <div
          className="px-2 pb-3 max-h-80 overflow-y-auto"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          {isLoading && (
            <div className="py-4 flex items-center justify-center gap-2">
              <Loader2 className="size-4 animate-spin" style={{ color: "var(--primary)" }} />
              <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>Loading folders...</span>
            </div>
          )}

          {error && (
            <p className="py-3 px-2 text-xs" style={{ color: "var(--destructive)" }}>
              Failed to load folders: {error.message}
            </p>
          )}

          {!isLoading && !error && folders.length === 0 && (
            <p className="py-3 px-2 text-xs" style={{ color: "var(--outline-variant)" }}>
              No folders found in Drive root
            </p>
          )}

          {folders.map((folder) => (
            <FolderNode
              key={folder.file_id}
              folder={folder}
              selectedId={selectedFolderId}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Provider hook ─────────────────────────────────────────────────────────

function useGoogleDriveState(): ProviderState {
  const { defaultFolder, saveDefaultFolder, isSaving } = useDefaultFolder();

  const syncedRef = useRef(false);
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null);
  const [selectedFolderName, setSelectedFolderName] = useState<string | null>(null);

  // Sync selection with saved default (once)
  if (defaultFolder && !syncedRef.current) {
    syncedRef.current = true;
    setSelectedFolderId(defaultFolder.folder_id);
    setSelectedFolderName(defaultFolder.folder_name);
  }

  const isDirty =
    selectedFolderId !== (defaultFolder?.folder_id ?? null) ||
    selectedFolderName !== (defaultFolder?.folder_name ?? null);

  return {
    folderId: selectedFolderId,
    folderName: selectedFolderName,
    setFolder: (id, name) => {
      setSelectedFolderId(id);
      setSelectedFolderName(name);
    },
    isDirty,
    saveDefault: async () => {
      if (selectedFolderId && selectedFolderName) {
        await saveDefaultFolder(selectedFolderId, selectedFolderName);
      }
    },
    isSaving,
  };
}

// ── Exported provider ─────────────────────────────────────────────────────

export const googleDriveProvider: IngestionProvider = {
  key: "google_drive",
  label: "Google Drive",
  icon: FolderOpen,
  hasFolderBrowser: true,
  FolderChooser: DriveFolderPicker,
  buildTriggerParams: ({ folderId, force }) => ({
    source: "google_drive",
    folder_id: folderId,
    force,
  }),
  useProviderState: useGoogleDriveState,
};
