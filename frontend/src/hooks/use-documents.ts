"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient, ApiError } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type { Document } from "@/types/documents";

interface DocumentListApiResponse {
  items: Document[];
  total: number;
  page: number;
  page_size: number;
}

// ── Query functions ────────────────────────────────────────────────────────

function fetchDocuments(
  page: number,
  pageSize: number
): Promise<DocumentListApiResponse> {
  return apiClient.get<DocumentListApiResponse>(
    `/documents?page=${page}&page_size=${pageSize}`
  );
}

// ── Hook ──────────────────────────────────────────────────────────────────

export function useDocuments(page = 1, pageSize = 20) {
  const queryClient = useQueryClient();

  // ── List query ──────────────────────────────────────────────────────────
  const query = useQuery({
    queryKey: queryKeys.documents.list(page, pageSize),
    queryFn: () => fetchDocuments(page, pageSize),
  });

  // ── Upload mutation ──────────────────────────────────────────────────────
  const uploadMutation = useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      return apiClient.upload<Document>("/documents", formData);
    },
    onSuccess: () => {
      // Invalidate all document lists so any page reflects the new upload.
      queryClient.invalidateQueries({ queryKey: queryKeys.documents.lists() });
      // Also invalidate the dashboard stats which count documents.
      queryClient.invalidateQueries({ queryKey: queryKeys.documents.stats() });
    },
  });

  // ── Delete mutation ──────────────────────────────────────────────────────
  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiClient.delete(`/documents/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.documents.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.documents.stats() });
    },
  });

  return {
    // data
    items: query.data?.items ?? [],
    total: query.data?.total ?? 0,
    page: query.data?.page ?? page,
    pageSize: query.data?.page_size ?? pageSize,

    // loading / error states
    isLoading: query.isLoading,
    error: query.error
      ? query.error instanceof ApiError
        ? query.error.message
        : "Failed to load documents"
      : null,

    // mutations
    uploadDocument: uploadMutation.mutateAsync,
    isUploading: uploadMutation.isPending,
    uploadError: uploadMutation.error?.message ?? null,

    deleteDocument: (id: string) => deleteMutation.mutateAsync(id),
    isDeleting: deleteMutation.isPending,

    // manual refresh (maps to refetch for backward-compat)
    refresh: query.refetch,
  };
}
