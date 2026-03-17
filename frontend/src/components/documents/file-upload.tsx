"use client";

import { useCallback, useRef, useState } from "react";
import { Upload, X } from "lucide-react";

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
    if (file.size > 50 * 1024 * 1024) {
      setError("File must be under 50 MB");
      return;
    }
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
        onClick={() => inputRef.current?.click()}
        className="flex cursor-pointer flex-col items-center justify-center rounded-2xl p-8 transition-all"
        style={{
          border: isDragOver
            ? "2px dashed #6366F1"
            : "2px dashed rgba(255,255,255,0.1)",
          background: isDragOver
            ? "rgba(99,102,241,0.05)"
            : "rgba(255,255,255,0.02)",
          opacity: isUploading ? 0.5 : 1,
          pointerEvents: isUploading ? "none" : "auto",
        }}
      >
        <div
          className="w-12 h-12 rounded-xl flex items-center justify-center mb-3"
          style={{ background: "rgba(99,102,241,0.12)" }}
        >
          <Upload className="size-6" style={{ color: "#818CF8" }} />
        </div>
        <p className="text-sm font-medium text-white">
          {isDragOver ? "Drop file here" : "Click or drag file to upload"}
        </p>
        <p className="mt-1 text-xs" style={{ color: "rgba(255,255,255,0.4)" }}>
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
            background: "rgba(239,68,68,0.1)",
            border: "1px solid rgba(239,68,68,0.2)",
            color: "#FCA5A5",
          }}
        >
          {error}
        </div>
      )}

      {selectedFile && (
        <div
          className="flex items-center justify-between rounded-xl px-4 py-3"
          style={{
            background: "rgba(255,255,255,0.04)",
            border: "1px solid rgba(255,255,255,0.06)",
          }}
        >
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-white">
              {selectedFile.name}
            </p>
            <p className="text-xs" style={{ color: "rgba(255,255,255,0.4)" }}>
              {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleUpload}
              disabled={isUploading}
              className="h-9 px-4 rounded-xl text-sm font-semibold text-white transition-all hover:opacity-90 disabled:opacity-50"
              style={{ background: "linear-gradient(135deg, #6366F1, #A855F7)" }}
            >
              {isUploading ? "Uploading..." : "Upload"}
            </button>
            <button
              onClick={clearFile}
              className="rounded-lg p-1.5 transition-colors hover:bg-white/5"
              style={{ color: "rgba(255,255,255,0.4)" }}
            >
              <X className="size-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
