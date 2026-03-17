"use client";

import { FileUpload } from "@/components/documents/file-upload";
import { DocumentList } from "@/components/documents/document-list";
import { useDocuments } from "@/hooks/use-documents";

export default function DocumentsPage() {
  const { items, total, isLoading, error, isUploading, uploadDocument, deleteDocument } =
    useDocuments();

  return (
    <div className="flex-1 p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white tracking-tight">Documents</h1>
        <p className="mt-1 text-sm" style={{ color: "rgba(255,255,255,0.4)" }}>
          Upload PDF or DOCX files to build your knowledge base. Files expire after 7 days.
        </p>
      </div>

      {/* Upload area */}
      <FileUpload onUpload={uploadDocument} isUploading={isUploading} />

      {/* Error display */}
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

      {/* Document list */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">
            Your Documents
            {total > 0 && (
              <span className="ml-2 text-sm font-normal" style={{ color: "rgba(255,255,255,0.4)" }}>
                ({total})
              </span>
            )}
          </h2>
        </div>
        <DocumentList
          documents={items}
          isLoading={isLoading}
          onDelete={deleteDocument}
        />
      </div>
    </div>
  );
}
