"use client";

import { useState, useRef, useEffect } from "react";
import { Paperclip, Upload, HardDrive } from "lucide-react";

interface AttachmentButtonProps {
  onUploadFiles: (files: FileList) => void;
  onBrowseDrive: () => void;
  disabled?: boolean;
  attachmentCount?: number;
}

export function AttachmentButton({
  onUploadFiles,
  onBrowseDrive,
  disabled = false,
  attachmentCount = 0,
}: AttachmentButtonProps) {
  const [open, setOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      onUploadFiles(e.target.files);
      setOpen(false);
      // Reset so the same file can be selected again
      e.target.value = "";
    }
  };

  const ACCEPTED_TYPES = ".png,.jpg,.jpeg,.gif,.webp,.txt,.pdf,.docx,.doc";

  return (
    <div className="relative" ref={popoverRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={disabled}
        className="flex items-center justify-center w-9 h-9 rounded-lg transition-colors hover:bg-black/[0.05] disabled:opacity-30"
        style={{ color: "var(--on-surface-variant)" }}
        title="Attach files"
      >
        <Paperclip className="size-[18px]" />
        {attachmentCount > 0 && (
          <span
            className="absolute -top-1 -right-1 flex items-center justify-center w-4 h-4 rounded-full text-[10px] font-bold text-white"
            style={{ background: "var(--primary)" }}
          >
            {attachmentCount}
          </span>
        )}
      </button>

      {open && (
        <div
          className="absolute bottom-full left-0 z-50 mb-2 min-w-[200px] rounded-xl py-1 shadow-xl"
          style={{
            background: "var(--card)",
            border: "1px solid var(--outline-variant)",
          }}
        >
          <button
            onClick={() => {
              fileInputRef.current?.click();
            }}
            className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm transition-colors hover:bg-black/[0.05]"
            style={{ color: "var(--on-surface-variant)" }}
          >
            <Upload className="size-4" />
            Upload files
          </button>
          <button
            onClick={() => {
              onBrowseDrive();
              setOpen(false);
            }}
            className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm transition-colors hover:bg-black/[0.05]"
            style={{ color: "var(--on-surface-variant)" }}
          >
            <HardDrive className="size-4" />
            Browse Drive
          </button>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={ACCEPTED_TYPES}
        onChange={handleFileChange}
        className="hidden"
      />
    </div>
  );
}
