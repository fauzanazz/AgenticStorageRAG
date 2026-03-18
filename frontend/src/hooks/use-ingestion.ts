"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type {
  IngestionJob,
  IngestionJobList,
  IngestionStatsResponse,
  LLMCostSummary,
  TriggerIngestionRequest,
} from "@/types/ingestion";

// ── Query / mutation functions ─────────────────────────────────────────────

function fetchJobs(page: number): Promise<IngestionJobList> {
  return apiClient.get<IngestionJobList>(`/admin/ingestion/jobs?page=${page}`);
}

function fetchStats(): Promise<IngestionStatsResponse> {
  return apiClient.get<IngestionStatsResponse>("/admin/ingestion/stats");
}

function fetchCost(): Promise<LLMCostSummary> {
  return apiClient.get<LLMCostSummary>("/admin/ingestion/cost");
}

function triggerIngestionRequest(
  req: TriggerIngestionRequest
): Promise<IngestionJob> {
  return apiClient.post<IngestionJob>("/admin/ingestion/trigger", req);
}

function cancelJobRequest(jobId: string): Promise<IngestionJob> {
  return apiClient.post<IngestionJob>(
    `/admin/ingestion/jobs/${jobId}/cancel`
  );
}

// ── Active-job detector (drives polling interval) ─────────────────────────

function hasActiveJobs(jobs: IngestionJob[]): boolean {
  return jobs.some((j) =>
    (["pending", "scanning", "processing"] as IngestionJob["status"][]).includes(
      j.status
    )
  );
}

// ── Hook ───────────────────────────────────────────────────────────────────

export function useIngestion(page = 1) {
  const queryClient = useQueryClient();

  // ── Jobs query (with auto-polling while active) ──────────────────────────
  const jobsQuery = useQuery({
    queryKey: queryKeys.ingestion.jobs(page),
    queryFn: () => fetchJobs(page),
    // Poll every 4 s only when there are active jobs; computed from last data.
    refetchInterval: (query) => {
      const jobs: IngestionJob[] = query.state.data?.items ?? [];
      return hasActiveJobs(jobs) ? 4_000 : false;
    },
  });

  // ── Stats query ──────────────────────────────────────────────────────────
  const statsQuery = useQuery({
    queryKey: queryKeys.ingestion.stats(),
    queryFn: fetchStats,
    // Also poll stats while jobs are active so the stats panel stays live.
    refetchInterval: (query) => {
      const jobs: IngestionJob[] = jobsQuery.data?.items ?? [];
      return hasActiveJobs(jobs) ? 4_000 : false;
    },
  });

  // ── Cost query ───────────────────────────────────────────────────────────
  const costQuery = useQuery({
    queryKey: queryKeys.ingestion.cost(),
    queryFn: fetchCost,
  });

  // ── Trigger mutation ─────────────────────────────────────────────────────
  const triggerMutation = useMutation({
    mutationFn: (req: TriggerIngestionRequest = {}) =>
      triggerIngestionRequest(req),
    onSuccess: () => {
      // Invalidate jobs + stats so the new job shows up immediately.
      queryClient.invalidateQueries({ queryKey: queryKeys.ingestion.all });
    },
  });

  // ── Cancel mutation ──────────────────────────────────────────────────────
  const cancelMutation = useMutation({
    mutationFn: (jobId: string) => cancelJobRequest(jobId),
    onSuccess: (updatedJob) => {
      // Optimistically update the cached job list before re-fetch.
      queryClient.setQueryData<IngestionJobList>(
        queryKeys.ingestion.jobs(page),
        (prev) =>
          prev
            ? {
                ...prev,
                items: prev.items.map((j) =>
                  j.id === updatedJob.id ? updatedJob : j
                ),
              }
            : prev
      );
      // Invalidate stats because cancellation changes counts.
      queryClient.invalidateQueries({ queryKey: queryKeys.ingestion.stats() });
    },
  });

  return {
    // data
    jobs: jobsQuery.data?.items ?? [],
    totalJobs: jobsQuery.data?.total ?? 0,
    stats: statsQuery.data ?? null,
    costSummary: costQuery.data ?? null,

    // loading / error states
    isLoading: jobsQuery.isLoading,
    isTriggering: triggerMutation.isPending,
    error:
      jobsQuery.error?.message ??
      triggerMutation.error?.message ??
      cancelMutation.error?.message ??
      null,

    // mutations
    triggerIngestion: (req: TriggerIngestionRequest = {}) =>
      triggerMutation.mutateAsync(req),
    cancelJob: (jobId: string) => cancelMutation.mutateAsync(jobId),

    // manual refresh — invalidates the whole ingestion namespace
    refresh: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.ingestion.all }),

    // legacy individual fetchers (kept for backward-compat)
    fetchJobs: (p = 1) =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.ingestion.jobs(p),
      }),
    fetchStats: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.ingestion.stats() }),
    fetchCostSummary: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.ingestion.cost() }),

    setError: (_: string | null) => {
      // Kept for backward-compat; errors are now managed by TanStack Query.
    },
  };
}
