"use client";

import { useEffect } from "react";
import { MobileHeader } from "@/components/layout/mobile-header";
import { Button } from "@/components/ui/button";
import { useIngestion } from "@/hooks/use-ingestion";
import { cn } from "@/lib/utils";
import type { IngestionJob, IngestionStatus } from "@/types/ingestion";

const STATUS_STYLES: Record<IngestionStatus, { bg: string; text: string; label: string }> = {
  pending: { bg: "bg-yellow-100 dark:bg-yellow-900/30", text: "text-yellow-700 dark:text-yellow-400", label: "Pending" },
  scanning: { bg: "bg-blue-100 dark:bg-blue-900/30", text: "text-blue-700 dark:text-blue-400", label: "Scanning" },
  processing: { bg: "bg-blue-100 dark:bg-blue-900/30", text: "text-blue-700 dark:text-blue-400", label: "Processing" },
  completed: { bg: "bg-green-100 dark:bg-green-900/30", text: "text-green-700 dark:text-green-400", label: "Completed" },
  failed: { bg: "bg-red-100 dark:bg-red-900/30", text: "text-red-700 dark:text-red-400", label: "Failed" },
  cancelled: { bg: "bg-gray-100 dark:bg-gray-900/30", text: "text-gray-700 dark:text-gray-400", label: "Cancelled" },
};

function StatusBadge({ status }: { status: IngestionStatus }) {
  const style = STATUS_STYLES[status] || STATUS_STYLES.pending;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        style.bg,
        style.text
      )}
    >
      {(status === "scanning" || status === "processing") && (
        <span className="mr-1.5 inline-block h-2 w-2 animate-pulse rounded-full bg-current" />
      )}
      {style.label}
    </span>
  );
}

function ProgressBar({ job }: { job: IngestionJob }) {
  if (job.total_files === 0) return null;
  const progress = ((job.processed_files + job.failed_files + job.skipped_files) / job.total_files) * 100;

  return (
    <div className="mt-2">
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>
          {job.processed_files} processed, {job.failed_files} failed, {job.skipped_files} skipped
        </span>
        <span>{job.total_files} total</span>
      </div>
      <div className="bg-secondary mt-1 h-2 overflow-hidden rounded-full">
        <div
          className="bg-primary h-full rounded-full transition-all duration-300"
          style={{ width: `${Math.min(progress, 100)}%` }}
        />
      </div>
    </div>
  );
}

function JobCard({
  job,
  onCancel,
}: {
  job: IngestionJob;
  onCancel: (id: string) => void;
}) {
  const isActive = ["pending", "scanning", "processing"].includes(job.status);

  return (
    <div className="rounded-xl border p-4">
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <StatusBadge status={job.status} />
            <span className="text-muted-foreground text-xs">
              {new Date(job.started_at).toLocaleString()}
            </span>
          </div>
          <p className="mt-1 text-sm font-medium">
            {job.source === "google_drive" ? "Google Drive" : job.source}
            {job.folder_id ? ` (folder: ${job.folder_id})` : " (all files)"}
          </p>
        </div>

        {isActive && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => onCancel(job.id)}
            className="shrink-0"
          >
            Cancel
          </Button>
        )}
      </div>

      <ProgressBar job={job} />

      {job.error_message && (
        <p className="text-destructive mt-2 text-xs">
          {job.error_message}
        </p>
      )}

      {job.completed_at && (
        <p className="text-muted-foreground mt-2 text-xs">
          Completed: {new Date(job.completed_at).toLocaleString()}
          {" -- "}
          Duration:{" "}
          {Math.round(
            (new Date(job.completed_at).getTime() -
              new Date(job.started_at).getTime()) /
              1000
          )}s
        </p>
      )}
    </div>
  );
}

export default function IngestionPage() {
  const {
    jobs,
    isLoading,
    isTriggering,
    error,
    fetchJobs,
    triggerIngestion,
    cancelJob,
    setError,
  } = useIngestion();

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  // Auto-refresh when jobs are active
  useEffect(() => {
    const hasActive = jobs.some((j) =>
      ["pending", "scanning", "processing"].includes(j.status)
    );
    if (!hasActive) return;

    const interval = setInterval(() => fetchJobs(), 5000);
    return () => clearInterval(interval);
  }, [jobs, fetchJobs]);

  return (
    <>
      <MobileHeader title="Admin: Ingestion" />

      <div className="flex-1 overflow-y-auto p-4 md:p-6">
        <div className="mx-auto max-w-3xl space-y-6">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-bold">Base Knowledge Ingestion</h1>
              <p className="text-muted-foreground mt-1 text-sm">
                Ingest files from Google Drive into the base Knowledge Graph.
              </p>
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-3">
            <Button
              onClick={() => triggerIngestion()}
              disabled={isTriggering}
            >
              {isTriggering ? "Starting..." : "Ingest from Drive"}
            </Button>
            <Button
              variant="outline"
              onClick={() => triggerIngestion({ force: true })}
              disabled={isTriggering}
            >
              Force Re-ingest All
            </Button>
            <Button variant="ghost" onClick={() => fetchJobs()}>
              Refresh
            </Button>
          </div>

          {/* Error */}
          {error && (
            <div className="bg-destructive/10 text-destructive border-destructive/20 flex items-center justify-between rounded-lg border px-3 py-2 text-sm">
              <span>{error}</span>
              <button onClick={() => setError(null)} className="ml-2">
                Dismiss
              </button>
            </div>
          )}

          {/* Job list */}
          <div className="space-y-3">
            <h2 className="text-sm font-medium">
              Ingestion Jobs ({jobs.length})
            </h2>

            {isLoading && jobs.length === 0 ? (
              <div className="text-muted-foreground py-8 text-center text-sm">
                Loading...
              </div>
            ) : jobs.length === 0 ? (
              <div className="text-muted-foreground py-8 text-center text-sm">
                No ingestion jobs yet. Click &ldquo;Ingest from Drive&rdquo; to start.
              </div>
            ) : (
              jobs.map((job) => (
                <JobCard key={job.id} job={job} onCancel={cancelJob} />
              ))
            )}
          </div>
        </div>
      </div>
    </>
  );
}
