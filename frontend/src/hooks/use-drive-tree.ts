"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type { DriveTreeResponse } from "@/types/documents";

function fetchDriveTree(): Promise<DriveTreeResponse> {
  return apiClient.get<DriveTreeResponse>("/documents/drive-tree");
}

export function useDriveTree() {
  const query = useQuery({
    queryKey: queryKeys.documents.driveTree(),
    queryFn: fetchDriveTree,
  });

  return {
    data: query.data ?? null,
    isLoading: query.isLoading,
    error: query.error ? "Failed to load Drive tree" : null,
    refresh: query.refetch,
  };
}
