"use client";

import { MobileHeader } from "@/components/layout/mobile-header";
import { FileUpload } from "@/components/documents/file-upload";
import { DocumentList } from "@/components/documents/document-list";
import { useDocuments } from "@/hooks/use-documents";

export default function DocumentsPage() {
  const { items, total, isLoading, error, isUploading, uploadDocument, deleteDocument, refresh } =
    useDocuments();

  return (
    <>
      <MobileHeader title="Documents" />
      <div className="flex-1 space-y-6 p-4 lg:p-8">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Documents</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Upload PDF or DOCX files to build your knowledge base.
            Files expire after 7 days.
          </p>
        </div>

        {/* Upload area */}
        <FileUpload onUpload={uploadDocument} isUploading={isUploading} />

        {/* Error display */}
        {error && (
          <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        )}

        {/* Document list */}
        <div>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-semibold">
              Your Documents
              {total > 0 && (
                <span className="ml-2 text-sm font-normal text-muted-foreground">
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
    </>
  );
}
