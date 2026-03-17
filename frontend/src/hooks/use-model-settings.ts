"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type {
  ModelCatalog,
  ModelSettings,
  UpdateModelSettingsRequest,
} from "@/types/settings";

const SETTINGS_KEY = ["settings", "models"] as const;
const CATALOG_KEY = ["settings", "models", "catalog"] as const;

export function useModelSettings() {
  const queryClient = useQueryClient();

  const settingsQuery = useQuery<ModelSettings>({
    queryKey: SETTINGS_KEY,
    queryFn: () => apiClient.get<ModelSettings>("/settings/models"),
  });

  const catalogQuery = useQuery<ModelCatalog>({
    queryKey: CATALOG_KEY,
    queryFn: () => apiClient.get<ModelCatalog>("/settings/models/catalog"),
    staleTime: Infinity, // catalog never changes at runtime
  });

  const updateMutation = useMutation({
    mutationFn: (data: UpdateModelSettingsRequest) =>
      apiClient.put<ModelSettings>("/settings/models", data),
    onSuccess: (updated) => {
      queryClient.setQueryData(SETTINGS_KEY, updated);
    },
  });

  return {
    settings: settingsQuery.data ?? null,
    catalog: catalogQuery.data ?? null,
    isLoading: settingsQuery.isLoading,
    isSaving: updateMutation.isPending,
    error:
      (settingsQuery.error as Error)?.message ??
      (updateMutation.error as Error)?.message ??
      null,
    isSuccess: updateMutation.isSuccess,
    updateSettings: (data: UpdateModelSettingsRequest) =>
      updateMutation.mutateAsync(data),
  };
}
