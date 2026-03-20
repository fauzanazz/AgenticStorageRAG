"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient, ApiError } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type { Document, DocumentSource } from "@/types/documents";

interface DocumentListApiResponse {
  items: Document[];
  total: number;
  page: number;
  page_size: number;
}

// ── Query functions ────────────────────────────────────────────────────────

function fetchDocuments(
  page: number,
  pageSize: number,
  source?: DocumentSource
): Promise<DocumentListApiResponse> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (source) params.set("source", source);
  return apiClient.get<DocumentListApiResponse>(
    `/documents?${params.toString()}`
  );
}

// ── Hook ──────────────────────────────────────────────────────────────────

export function useDocuments(
  page = 1,
  pageSize = 20,
  source?: DocumentSource
) {
  const queryClient = useQueryClient();

  // ── List query ──────────────────────────────────────────────────────────
  const query = useQuery({
    queryKey: queryKeys.documents.list(page, pageSize, source),
    queryFn: () => fetchDocuments(page, pageSize, source),
  });

  // ── Upload mutation ──────────────────────────────────────────────────────
  const uploadMutation = useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      return apiClient.upload<Document>("/documents", formData);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.documents.lists() });
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

    // manual refresh
    refresh: query.refetch,
  };
}
