"use client";

import { FileUpload } from "@/components/documents/file-upload";
import { DocumentList } from "@/components/documents/document-list";
import { DriveTree } from "@/components/documents/drive-tree";
import { useDocuments } from "@/hooks/use-documents";
import { useDriveTree } from "@/hooks/use-drive-tree";

export default function DocumentsPage() {
  const uploads = useDocuments(1, 20, "upload");
  const driveTree = useDriveTree();

  const totalFiles = driveTree.data?.total_files ?? 0;
  const processedFiles = uploads.total;

  return (
    <div className="flex-1 p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Documents</h1>
        <p className="mt-1 text-sm" style={{ color: "var(--muted-foreground)" }}>
          Manage your uploaded documents and ingested Drive files.
        </p>
      </div>

      {/* Error displays */}
      {uploads.error && (
        <div
          className="rounded-xl px-4 py-3 text-sm"
          style={{
            background: "var(--error-container)",
            border: "1px solid color-mix(in srgb, var(--destructive) 20%, transparent)",
            color: "var(--destructive)",
          }}
        >
          {uploads.error}
        </div>
      )}
      {driveTree.error && (
        <div
          className="rounded-xl px-4 py-3 text-sm"
          style={{
            background: "var(--error-container)",
            border: "1px solid color-mix(in srgb, var(--destructive) 20%, transparent)",
            color: "var(--destructive)",
          }}
        >
          {driveTree.error}
        </div>
      )}

      {/* Two-column grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column — uploads */}
        <div className="lg:col-span-2 space-y-6">
          <FileUpload onUpload={uploads.uploadDocument} isUploading={uploads.isUploading} />

          <div>
            <h2 className="text-lg font-semibold mb-3">
              Your Uploads
              {uploads.total > 0 && (
                <span className="ml-2 text-sm font-normal" style={{ color: "var(--muted-foreground)" }}>
                  ({uploads.total})
                </span>
              )}
            </h2>
            <DocumentList
              documents={uploads.items}
              isLoading={uploads.isLoading}
              onDelete={uploads.deleteDocument}
              showSource={false}
            />
          </div>
        </div>

        {/* Right column — sidebar */}
        <div className="lg:col-span-1 space-y-6">
          {/* Storage summary card */}
          <div
            className="rounded-2xl p-5 space-y-3"
            style={{
              background: "var(--card)",
              border: "1px solid var(--border)",
            }}
          >
            <h3 className="text-sm font-semibold" style={{ color: "var(--muted-foreground)" }}>
              Storage Summary
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-2xl font-bold">{processedFiles}</p>
                <p className="text-xs" style={{ color: "var(--muted-foreground)" }}>Uploaded</p>
              </div>
              <div>
                <p className="text-2xl font-bold">{totalFiles}</p>
                <p className="text-xs" style={{ color: "var(--muted-foreground)" }}>Drive Files</p>
              </div>
            </div>
          </div>

          {/* Google Drive */}
          <div
            className="rounded-2xl p-5"
            style={{
              background: "var(--card)",
              border: "1px solid var(--border)",
            }}
          >
            <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--muted-foreground)" }}>
              Google Drive
            </h3>
            <DriveTree data={driveTree.data} isLoading={driveTree.isLoading} />
          </div>
        </div>
      </div>
    </div>
  );
}
