"use client";

import { useState, useCallback } from "react";
import { apiClient } from "@/lib/api-client";
import type {
  IngestionJob,
  IngestionJobList,
  IngestionStatsResponse,
  LLMCostSummary,
  TriggerIngestionRequest,
} from "@/types/ingestion";

export function useIngestion() {
  const [jobs, setJobs] = useState<IngestionJob[]>([]);
  const [totalJobs, setTotalJobs] = useState(0);
  const [stats, setStats] = useState<IngestionStatsResponse | null>(null);
  const [costSummary, setCostSummary] = useState<LLMCostSummary | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isTriggering, setIsTriggering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchJobs = useCallback(async (page = 1) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.get<IngestionJobList>(
        `/admin/ingestion/jobs?page=${page}`
      );
      setJobs(data.items);
      setTotalJobs(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load jobs");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const data = await apiClient.get<IngestionStatsResponse>(
        "/admin/ingestion/stats"
      );
      setStats(data);
    } catch {
      // stats are non-fatal
    }
  }, []);

  const fetchCostSummary = useCallback(async () => {
    try {
      const data = await apiClient.get<LLMCostSummary>("/admin/ingestion/cost");
      setCostSummary(data);
    } catch {
      // non-fatal
    }
  }, []);

  const refresh = useCallback(async (page = 1) => {
    await Promise.all([fetchJobs(page), fetchStats(), fetchCostSummary()]);
  }, [fetchJobs, fetchStats, fetchCostSummary]);

  const triggerIngestion = useCallback(
    async (request: TriggerIngestionRequest = {}) => {
      setIsTriggering(true);
      setError(null);
      try {
        const job = await apiClient.post<IngestionJob>(
          "/admin/ingestion/trigger",
          request
        );
        setJobs((prev) => [job, ...prev]);
        fetchStats();
        return job;
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to trigger ingestion"
        );
        return null;
      } finally {
        setIsTriggering(false);
      }
    },
    [fetchStats]
  );

  const cancelJob = useCallback(async (jobId: string) => {
    try {
      const updated = await apiClient.post<IngestionJob>(
        `/admin/ingestion/jobs/${jobId}/cancel`
      );
      setJobs((prev) =>
        prev.map((j) => (j.id === jobId ? updated : j))
      );
      fetchStats();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel job");
    }
  }, [fetchStats]);

  return {
    jobs,
    totalJobs,
    stats,
    costSummary,
    isLoading,
    isTriggering,
    error,
    fetchJobs,
    fetchStats,
    fetchCostSummary,
    refresh,
    triggerIngestion,
    cancelJob,
    setError,
  };
}
