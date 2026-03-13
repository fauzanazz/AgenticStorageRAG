"use client";

import { useCallback, useEffect, useState } from "react";
import { apiClient, ApiError } from "@/lib/api-client";
import type { Document } from "@/types/documents";

interface DocumentListState {
  items: Document[];
  total: number;
  page: number;
  pageSize: number;
  isLoading: boolean;
  error: string | null;
}

interface UseDocumentsReturn extends DocumentListState {
  refresh: () => Promise<void>;
  uploadDocument: (file: File) => Promise<Document>;
  deleteDocument: (id: string) => Promise<void>;
  isUploading: boolean;
}

interface DocumentListApiResponse {
  items: Document[];
  total: number;
  page: number;
  page_size: number;
}

export function useDocuments(): UseDocumentsReturn {
  const [state, setState] = useState<DocumentListState>({
    items: [],
    total: 0,
    page: 1,
    pageSize: 20,
    isLoading: true,
    error: null,
  });
  const [isUploading, setIsUploading] = useState(false);

  const refresh = useCallback(async () => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    try {
      const data = await apiClient.get<DocumentListApiResponse>(
        `/documents?page=${state.page}&page_size=${state.pageSize}`
      );
      setState((prev) => ({
        ...prev,
        items: data.items,
        total: data.total,
        isLoading: false,
      }));
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Failed to load documents";
      setState((prev) => ({ ...prev, isLoading: false, error: message }));
    }
  }, [state.page, state.pageSize]);

  const uploadDocument = useCallback(
    async (file: File): Promise<Document> => {
      setIsUploading(true);
      try {
        const formData = new FormData();
        formData.append("file", file);
        const doc = await apiClient.upload<Document>("/documents", formData);
        // Refresh the list after upload
        await refresh();
        return doc;
      } finally {
        setIsUploading(false);
      }
    },
    [refresh]
  );

  const deleteDocument = useCallback(
    async (id: string) => {
      await apiClient.delete(`/documents/${id}`);
      await refresh();
    },
    [refresh]
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  return {
    ...state,
    refresh,
    uploadDocument,
    deleteDocument,
    isUploading,
  };
}
