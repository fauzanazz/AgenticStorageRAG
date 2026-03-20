"use client";

import { useCallback, useRef, useState } from "react";
import { Upload, X } from "lucide-react";

const ALLOWED_MIME_TYPES = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);

interface FileUploadProps {
  onUpload: (file: File) => Promise<unknown>;
  isUploading: boolean;
  accept?: string;
}

export function FileUpload({
  onUpload,
  isUploading,
  accept = ".pdf,.docx",
}: FileUploadProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const validateAndSetFile = useCallback((file: File) => {
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!ext || !["pdf", "docx"].includes(ext)) {
      setError("Only PDF and DOCX files are supported");
      return;
    }
    if (file.type && !ALLOWED_MIME_TYPES.has(file.type)) {
      setError(
        "File type does not match extension. Please upload a valid PDF or DOCX."
      );
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      setError("File must be under 50 MB");
      return;
    }
    setError(null);
    setSelectedFile(file);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    setError(null);

    const file = e.dataTransfer.files[0];
    if (file) {
      validateAndSetFile(file);
    }
  }, [validateAndSetFile]);

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setError(null);
      const file = e.target.files?.[0];
      if (file) {
        validateAndSetFile(file);
      }
    },
    [validateAndSetFile]
  );

  const handleUpload = useCallback(async () => {
    if (!selectedFile) return;
    setError(null);
    try {
      await onUpload(selectedFile);
      setSelectedFile(null);
      if (inputRef.current) {
        inputRef.current.value = "";
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Upload failed"
      );
    }
  }, [selectedFile, onUpload]);

  const clearFile = useCallback(() => {
    setSelectedFile(null);
    setError(null);
    if (inputRef.current) {
      inputRef.current.value = "";
    }
  }, []);

  return (
    <div className="space-y-3">
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); inputRef.current?.click(); } }}
        onClick={() => inputRef.current?.click()}
        className="flex cursor-pointer flex-col items-center justify-center rounded-2xl p-8 transition-all"
        style={{
          border: isDragOver
            ? "2px dashed var(--primary)"
            : "2px dashed var(--outline-variant)",
          background: isDragOver
            ? "color-mix(in srgb, var(--accent) 25%, transparent)"
            : "var(--surface-container-low)",
          opacity: isUploading ? 0.5 : 1,
          pointerEvents: isUploading ? "none" : "auto",
        }}
      >
        <div
          className="w-12 h-12 rounded-xl flex items-center justify-center mb-3"
          style={{ background: "var(--accent)" }}
        >
          <Upload className="size-6" style={{ color: "var(--primary)" }} />
        </div>
        <p className="text-sm font-medium">
          {isDragOver ? "Drop file here" : "Click or drag file to upload"}
        </p>
        <p className="mt-1 text-xs" style={{ color: "var(--muted-foreground)" }}>
          PDF or DOCX, up to 50 MB
        </p>
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          onChange={handleFileSelect}
          className="hidden"
        />
      </div>

      {error && (
        <div
          className="rounded-xl px-4 py-3 text-sm"
          style={{
            background: "var(--error-container)",
            border: "1px solid color-mix(in srgb, var(--destructive) 20%, transparent)",
            color: "var(--destructive)",
          }}
        >
          {error}
        </div>
      )}

      {selectedFile && (
        <div
          className="flex items-center justify-between rounded-xl px-4 py-3"
          style={{
            background: "var(--muted)",
            border: "1px solid var(--border)",
          }}
        >
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">
              {selectedFile.name}
            </p>
            <p className="text-xs" style={{ color: "var(--muted-foreground)" }}>
              {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleUpload}
              disabled={isUploading}
              className="h-9 px-4 rounded-xl text-sm font-semibold text-white transition-all hover:opacity-90 disabled:opacity-50"
              style={{ background: "var(--primary)" }}
            >
              {isUploading ? "Uploading..." : "Upload"}
            </button>
            <button
              onClick={clearFile}
              className="rounded-lg p-1.5 transition-colors hover:bg-black/5"
              style={{ color: "var(--muted-foreground)" }}
            >
              <X className="size-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
