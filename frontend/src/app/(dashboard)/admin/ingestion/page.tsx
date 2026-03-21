"use client";

import React, { useState } from "react";
import { redirect } from "next/navigation";
import { RefreshCw, ChevronDown, ChevronUp, ChevronRight, DollarSign, FileText, CheckCircle2, Clock, XCircle, SkipForward, Save, Loader2 } from "lucide-react";
import { useAuth } from "@/hooks/use-auth";
import { useIngestion, useProviders } from "@/hooks/use-ingestion";
import { getProvider, getAllProviders } from "@/lib/ingestion-providers";
import type { IngestionProvider, ProviderState } from "@/lib/ingestion-providers";
import type { DriveFolderEntry, FileEvent, FileEvents, IngestionJob, IngestionStatus, LLMCostSummary, ProviderInfo } from "@/types/ingestion";
import { Skeleton } from "@/components/ui/skeleton";

// ── Status config ────────────────────────────────────────────────────────────

const STATUS_STYLES: Record<IngestionStatus, { bg: string; color: string; label: string }> = {
  pending:    { bg: "#fff3e0", color: "#e65100", label: "Queued" },
  scanning:   { bg: "#e3f2fd", color: "#1565c0", label: "Scanning" },
  processing: { bg: "#dce1ff", color: "#3557bc", label: "Processing" },
  completed:  { bg: "#e8f5e9", color: "#2e7d32", label: "Completed" },
  failed:     { bg: "#fce4ec", color: "#9e3f4e", label: "Failed" },
  cancelled:  { bg: "#f0edef", color: "#7b7a7d", label: "Cancelled" },
};

function StatusBadge({ status }: { status: IngestionStatus }) {
  const s = STATUS_STYLES[status] ?? STATUS_STYLES.pending;
  const isActive = status === "scanning" || status === "processing";
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium"
      style={{ background: s.bg, color: s.color }}
    >
      {isActive && (
        <span
          className="inline-block h-1.5 w-1.5 animate-pulse rounded-full"
          style={{ background: "currentColor" }}
        />
      )}
      {s.label}
    </span>
  );
}

// ── Progress bar ─────────────────────────────────────────────────────────────

function ProgressBar({ job }: { job: IngestionJob }) {
  if (job.total_files === 0) return null;
  const done = job.processed_files + job.failed_files + job.skipped_files;
  const pct = Math.min((done / job.total_files) * 100, 100);

  return (
    <div className="mt-3 space-y-1">
      <div className="flex justify-between text-xs" style={{ color: "var(--muted-foreground)" }}>
        <span>
          <span style={{ color: "var(--success)" }}>{job.processed_files}</span> processed
          {job.failed_files > 0 && (
            <> · <span style={{ color: "var(--destructive)" }}>{job.failed_files}</span> failed</>
          )}
          {job.skipped_files > 0 && (
            <> · <span style={{ color: "var(--warning)" }}>{job.skipped_files}</span> skipped</>
          )}
        </span>
        <span>{job.total_files} total</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full" style={{ background: "var(--surface-container-high)" }}>
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: "linear-gradient(90deg, var(--primary), var(--chart-3))" }}
        />
      </div>
    </div>
  );
}

// ── File list ─────────────────────────────────────────────────────────────────

const FILE_STATE_STYLES: Record<FileEvent["state"], { icon: React.JSX.Element; color: string; label: string }> = {
  started:   { icon: <Clock className="size-3" />,         color: "#3557bc", label: "Ingesting" },
  completed: { icon: <CheckCircle2 className="size-3" />,  color: "#2e7d32", label: "Done" },
  skipped:   { icon: <SkipForward className="size-3" />,   color: "#e65100", label: "Skipped" },
  failed:    { icon: <XCircle className="size-3" />,       color: "#9e3f4e", label: "Failed" },
};

function FileList({ fileEvents }: { fileEvents: FileEvents }) {
  const entries = Object.entries(fileEvents);
  if (entries.length === 0) return null;

  const sorted = entries.sort(([, a], [, b]) => {
    if (a.state === "started" && b.state !== "started") return -1;
    if (b.state === "started" && a.state !== "started") return 1;
    return new Date(b.ts).getTime() - new Date(a.ts).getTime();
  });

  return (
    <div
      className="mt-3 rounded-xl overflow-hidden"
      style={{ background: "rgba(0,0,0,0.08)", border: "1px solid var(--border)" }}
    >
      <div
        className="px-3 py-2 text-xs font-medium flex items-center gap-1.5"
        style={{ color: "var(--muted-foreground)", borderBottom: "1px solid var(--border)" }}
      >
        <FileText className="size-3" />
        Files
        <span className="ml-auto" style={{ color: "var(--outline)" }}>
          {entries.filter(([, e]) => e.state === "completed").length}/{entries.length}
        </span>
      </div>
      <div className="max-h-52 overflow-y-auto divide-y" style={{ borderColor: "var(--border)" }}>
        {sorted.map(([fileId, ev]) => {
          const style = FILE_STATE_STYLES[ev.state];
          const shortFolder = ev.folder?.split("/").slice(-2).join(" > ") ?? "";
          return (
            <div key={fileId} className="flex items-center gap-2 px-3 py-2">
              <span style={{ color: style.color }} className="shrink-0">{style.icon}</span>
              <div className="flex-1 min-w-0">
                <p
                  className="text-xs font-medium truncate"
                  style={{ color: ev.state === "started" ? "#1a1a1a" : "var(--on-surface-variant)" }}
                >
                  {ev.name}
                </p>
                {shortFolder && (
                  <p className="text-[10px] truncate" style={{ color: "var(--outline-variant)" }}>
                    {shortFolder}
                  </p>
                )}
              </div>
              <div className="shrink-0 text-right">
                <span className="text-[10px] font-medium" style={{ color: style.color }}>{style.label}</span>
                {ev.state === "completed" && ev.chunks != null && (
                  <p className="text-[10px]" style={{ color: "var(--outline-variant)" }}>
                    {ev.chunks} chunks
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Job card ─────────────────────────────────────────────────────────────────

function JobCard({ job, onCancel, onRetry, isRetrying }: { job: IngestionJob; onCancel: (id: string) => void; onRetry: (id: string) => void; isRetrying: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const isActive = ["pending", "scanning", "processing"].includes(job.status);
  const meta = job.metadata;
  const fileEvents = meta.file_events ?? {};
  const fileCount = Object.keys(fileEvents).length;
  const hasSummary = !!meta.orchestrator_summary;
  const hasExpandable = fileCount > 0 || hasSummary;

  const activeFile = Object.values(fileEvents).find((e) => e.state === "started");

  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{ background: "var(--card)", border: "1px solid var(--border)" }}
    >
      <div className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1 space-y-1.5">
            <div className="flex items-center gap-2 flex-wrap">
              <StatusBadge status={job.status} />
              <span className="text-xs" style={{ color: "var(--outline)" }}>
                {new Date(job.started_at).toLocaleString()}
              </span>
              {job.completed_at && (
                <span className="text-xs" style={{ color: "var(--outline)" }}>
                  · {Math.round((new Date(job.completed_at).getTime() - new Date(job.started_at).getTime()) / 1000)}s
                </span>
              )}
            </div>

            <p className="text-sm font-medium">
              {job.source === "google_drive" ? "Google Drive" : job.source}
              {job.folder_id && (
                <span className="ml-1 font-mono text-xs" style={{ color: "var(--outline)" }}>
                  ({job.folder_id.slice(0, 16)}...)
                </span>
              )}
            </p>

            {isActive && activeFile && (
              <p className="text-xs flex items-center gap-1.5" style={{ color: "var(--primary)" }}>
                <Clock className="size-3 shrink-0" />
                <span className="truncate">{activeFile.name}</span>
              </p>
            )}
            {job.status === "pending" && (
              <p className="text-xs flex items-center gap-1.5" style={{ color: "var(--warning)" }}>
                <Clock className="size-3 shrink-0" />
                Waiting for worker to become available...
              </p>
            )}
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {isActive && (
              <button
                onClick={() => onCancel(job.id)}
                className="h-8 px-3 rounded-xl text-xs font-medium transition-all hover:opacity-80"
                style={{ border: "1px solid var(--outline-variant)", color: "var(--muted-foreground)" }}
              >
                Cancel
              </button>
            )}
            {(job.status === "failed" || job.status === "cancelled") && (
              <button
                onClick={() => onRetry(job.id)}
                disabled={isRetrying}
                className="h-8 px-3 rounded-xl text-xs font-medium transition-all hover:opacity-80 disabled:opacity-50"
                style={{ border: "1px solid var(--primary)", color: "var(--primary)" }}
              >
                {isRetrying ? "Retrying..." : "Retry"}
              </button>
            )}
            {hasExpandable && (
              <button
                onClick={() => setExpanded((v) => !v)}
                className="h-8 w-8 rounded-xl flex items-center justify-center transition-all hover:bg-black/5"
                style={{ color: "var(--muted-foreground)" }}
              >
                {expanded ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
              </button>
            )}
          </div>
        </div>

        <ProgressBar job={job} />

        {job.error_message && (
          <p className="mt-2 text-xs" style={{ color: "var(--destructive)" }}>
            {job.error_message}
          </p>
        )}
      </div>

      {expanded && (
        <div
          className="px-5 pb-5 space-y-3"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          {fileCount > 0 && <FileList fileEvents={fileEvents} />}

          {hasSummary && (
            <div
              className="rounded-xl p-3 text-xs"
              style={{ background: "color-mix(in srgb, var(--accent) 50%, transparent)", color: "var(--on-surface-variant)" }}
            >
              <p className="font-medium mb-1" style={{ color: "var(--primary)" }}>Orchestrator Summary</p>
              <p className="whitespace-pre-wrap">{meta.orchestrator_summary}</p>
            </div>
          )}

          {meta.orchestrator_warning && (
            <div
              className="rounded-xl p-3 text-xs"
              style={{ background: "color-mix(in srgb, var(--warning-container) 50%, transparent)", color: "var(--warning)" }}
            >
              <p className="font-medium">Warning</p>
              <p>{meta.orchestrator_warning}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Cost summary card ─────────────────────────────────────────────────────────

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function CostSummaryCard({ cost }: { cost: LLMCostSummary }) {
  const [expanded, setExpanded] = useState(false);
  const hasModels = Object.keys(cost.by_model).length > 0;

  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{ background: "var(--card)", border: "1px solid var(--border)" }}
    >
      <div className="p-4 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: "var(--accent)" }}
          >
            <DollarSign className="size-4" style={{ color: "var(--primary)" }} />
          </div>
          <div>
            <p className="text-xs font-medium" style={{ color: "var(--muted-foreground)" }}>
              LLM Cost (session)
            </p>
            <p className="text-xl font-bold">
              ${cost.total_cost_usd < 0.0001 && cost.total_cost_usd > 0
                ? "<$0.0001"
                : `$${cost.total_cost_usd.toFixed(4)}`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-6">
          <div className="text-right hidden sm:block">
            <p className="text-xs" style={{ color: "var(--outline)" }}>Tokens in</p>
            <p className="text-sm font-semibold">{formatTokens(cost.total_input_tokens)}</p>
          </div>
          <div className="text-right hidden sm:block">
            <p className="text-xs" style={{ color: "var(--outline)" }}>Tokens out</p>
            <p className="text-sm font-semibold">{formatTokens(cost.total_output_tokens)}</p>
          </div>
          <div className="text-right hidden sm:block">
            <p className="text-xs" style={{ color: "var(--outline)" }}>Calls</p>
            <p className="text-sm font-semibold">{cost.total_calls.toLocaleString()}</p>
          </div>

          {hasModels && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="h-8 w-8 rounded-xl flex items-center justify-center transition-all hover:bg-black/5"
              style={{ color: "var(--muted-foreground)" }}
            >
              {expanded ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
            </button>
          )}
        </div>
      </div>

      {expanded && hasModels && (
        <div
          className="px-4 pb-4 space-y-2"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          <p className="pt-3 text-xs font-medium" style={{ color: "var(--muted-foreground)" }}>By model</p>
          {Object.entries(cost.by_model).map(([model, s]) => (
            <div
              key={model}
              className="flex items-center justify-between rounded-xl px-3 py-2 text-xs"
              style={{ background: "var(--card)" }}
            >
              <span className="font-mono truncate max-w-[180px]" style={{ color: "var(--primary)" }}>{model}</span>
              <div className="flex gap-4 shrink-0">
                <span style={{ color: "var(--muted-foreground)" }}>
                  {s.calls} call{s.calls !== 1 ? "s" : ""}
                </span>
                <span style={{ color: "var(--muted-foreground)" }}>
                  {formatTokens(s.input_tokens + s.output_tokens)} tok
                </span>
                <span className="font-semibold">${s.cost_usd.toFixed(4)}</span>
              </div>
            </div>
          ))}
          <p className="text-xs pt-1" style={{ color: "var(--outline-variant)" }}>
            {cost.source === "redis" ? "Aggregated across all workers" : cost.note || ""}
          </p>
        </div>
      )}
    </div>
  );
}

// ── Stats bar ─────────────────────────────────────────────────────────────────

function StatsBar({ stats }: { stats: NonNullable<ReturnType<typeof useIngestion>["stats"]> }) {
  const items = [
    { label: "Total Jobs",     value: stats.total_jobs },
    { label: "Files Processed", value: stats.total_files_processed, color: "var(--success)" },
    { label: "Files Failed",   value: stats.total_files_failed, color: stats.total_files_failed > 0 ? "var(--destructive)" : undefined },
    { label: "Files Skipped",  value: stats.total_files_skipped, color: stats.total_files_skipped > 0 ? "var(--warning)" : undefined },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {items.map((item) => (
        <div
          key={item.label}
          className="rounded-2xl p-4"
          style={{ background: "var(--card)", border: "1px solid var(--border)" }}
        >
          <p className="text-2xl font-bold" style={item.color ? { color: item.color } : undefined}>
            {item.value.toLocaleString()}
          </p>
          <p className="text-xs mt-0.5" style={{ color: "var(--muted-foreground)" }}>{item.label}</p>
        </div>
      ))}
    </div>
  );
}

// ── Worker state ──────────────────────────────────────────────────────────────

function WorkerState({ stats }: { stats: NonNullable<ReturnType<typeof useIngestion>["stats"]> }) {
  const statusOrder: IngestionStatus[] = ["processing", "scanning", "pending", "completed", "failed", "cancelled"];

  return (
    <div
      className="rounded-2xl p-5"
      style={{ background: "var(--card)", border: "1px solid var(--border)" }}
    >
      <p className="text-sm font-semibold mb-3">Job Distribution</p>
      <div className="flex flex-wrap gap-2">
        {statusOrder.map((s) => {
          const count = stats.jobs_by_status[s] ?? 0;
          if (count === 0) return null;
          const style = STATUS_STYLES[s];
          return (
            <span
              key={s}
              className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium"
              style={{ background: style.bg, color: style.color }}
            >
              {style.label}
              <span
                className="rounded-full px-1.5 py-px text-[10px] font-bold"
                style={{ background: "rgba(0,0,0,0.08)" }}
              >
                {count}
              </span>
            </span>
          );
        })}
      </div>

      {stats.active_job && (
        <div className="mt-4 pt-4" style={{ borderTop: "1px solid var(--border)" }}>
          <p className="text-xs font-medium mb-2" style={{ color: "var(--muted-foreground)" }}>Active Job</p>
          <div className="flex items-center justify-between gap-2">
            <StatusBadge status={stats.active_job.status} />
            <span className="text-xs truncate flex-1 text-right">
              {stats.active_job.processed_files}/{stats.active_job.total_files} files
            </span>
          </div>
          {stats.active_job.metadata?.current_action && (
            <p className="mt-1.5 text-xs" style={{ color: "var(--primary)" }}>
              {stats.active_job.metadata.current_action}
            </p>
          )}
          {stats.active_job.total_files > 0 && <ProgressBar job={stats.active_job} />}
        </div>
      )}
    </div>
  );
}

// ── Provider section (wrapper to safely call provider hooks) ──────────────────

function ProviderSection({
  provider,
  isTriggering,
  onTrigger,
}: {
  provider: IngestionProvider;
  isTriggering: boolean;
  onTrigger: (params: ReturnType<IngestionProvider["buildTriggerParams"]>) => void;
}) {
  const state = provider.useProviderState();
  const FolderChooser = provider.FolderChooser;

  return (
    <>
      {/* Folder chooser (if provider supports it) */}
      {provider.hasFolderBrowser && FolderChooser && (
        <FolderChooser
          selectedFolderId={state.folderId}
          selectedFolderName={state.folderName}
          onSelect={state.setFolder}
        />
      )}

      {/* Actions */}
      <div className="flex gap-3 flex-wrap items-center">
        <button
          onClick={() => onTrigger(provider.buildTriggerParams({ folderId: state.folderId, force: false }))}
          disabled={isTriggering}
          className="h-10 px-5 rounded-xl text-sm font-semibold text-white transition-all hover:opacity-90 disabled:opacity-50"
          style={{ background: "var(--primary)" }}
        >
          {isTriggering ? "Starting..." : `Ingest from ${provider.label}`}
        </button>
        <button
          onClick={() => onTrigger(provider.buildTriggerParams({ folderId: state.folderId, force: true }))}
          disabled={isTriggering}
          className="h-10 px-5 rounded-xl text-sm font-medium transition-all hover:opacity-80"
          style={{ border: "1px solid var(--outline-variant)", color: "var(--on-surface-variant)" }}
        >
          Force Re-ingest All
        </button>
        {state.isDirty && state.folderId && (
          <button
            onClick={state.saveDefault}
            disabled={state.isSaving}
            className="h-10 px-4 rounded-xl flex items-center gap-2 text-sm font-medium transition-all hover:opacity-80"
            style={{ border: "1px solid var(--primary)", color: "var(--primary)" }}
          >
            {state.isSaving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
            Save as Default
          </button>
        )}
      </div>
    </>
  );
}

// ── Provider dropdown ─────────────────────────────────────────────────────────

function ProviderDropdown({
  providers,
  selectedKey,
  onSelect,
}: {
  providers: ProviderInfo[];
  selectedKey: string;
  onSelect: (key: string) => void;
}) {
  if (providers.length <= 1) return null;

  return (
    <div className="flex items-center gap-3">
      <label htmlFor="ingestion-source-select" className="text-sm font-medium" style={{ color: "var(--muted-foreground)" }}>
        Source
      </label>
      <select
        id="ingestion-source-select"
        value={selectedKey}
        onChange={(e) => onSelect(e.target.value)}
        className="h-10 px-3 rounded-xl text-sm font-medium appearance-none cursor-pointer"
        style={{
          background: "var(--card)",
          border: "1px solid var(--border)",
          color: "var(--foreground)",
        }}
      >
        {providers.map((p) => {
          const localProvider = getProvider(p.key);
          return (
            <option key={p.key} value={p.key} disabled={!p.configured || !localProvider}>
              {p.label}{!p.configured ? " (not configured)" : ""}
            </option>
          );
        })}
      </select>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function IngestionPage() {
  const { user } = useAuth();
  const {
    jobs,
    stats,
    costSummary,
    costError,
    isLoading,
    isTriggering,
    error,
    refresh,
    triggerIngestion,
    cancelJob,
    retryJob,
    isRetrying,
    setError,
  } = useIngestion();

  const { data: backendProviders } = useProviders();
  const [selectedProviderKey, setSelectedProviderKey] = useState("google_drive");

  const activeProvider = getProvider(selectedProviderKey);
  const providerList = backendProviders ?? [{ key: "google_drive", label: "Google Drive", configured: true }];

  // Admin guard
  if (user && !user.is_admin) {
    redirect("/");
  }

  return (
    <div className="flex-1 p-6 lg:p-8 space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Base Knowledge Ingestion</h1>
          <p className="mt-1 text-sm" style={{ color: "var(--muted-foreground)" }}>
            Agent orchestrator that recursively explores sources, classifies documents, and builds the Knowledge Graph.
          </p>
        </div>
        <button
          onClick={() => refresh()}
          className="h-10 px-4 rounded-xl flex items-center gap-2 text-sm font-medium transition-all hover:bg-black/5 shrink-0"
          style={{ color: "var(--muted-foreground)" }}
        >
          <RefreshCw className="size-4" />
          Refresh
        </button>
      </div>

      {/* Provider selector */}
      <ProviderDropdown
        providers={providerList}
        selectedKey={selectedProviderKey}
        onSelect={setSelectedProviderKey}
      />

      {/* Provider-specific section (keyed to force remount on switch) */}
      {activeProvider && (
        <ProviderSection
          key={selectedProviderKey}
          provider={activeProvider}
          isTriggering={isTriggering}
          onTrigger={(params) => triggerIngestion(params)}
        />
      )}

      {/* Error */}
      {error && (
        <div
          className="flex items-center justify-between rounded-xl px-4 py-3 text-sm"
          style={{ background: "var(--error-container)", border: "1px solid color-mix(in srgb, var(--destructive) 20%, transparent)", color: "var(--destructive)" }}
        >
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-2 hover:opacity-70">Dismiss</button>
        </div>
      )}

      {/* Stats bar */}
      {stats && <StatsBar stats={stats} />}

      {/* Cost summary */}
      {costSummary ? (
        <CostSummaryCard cost={costSummary} />
      ) : costError ? (
        <div
          className="rounded-2xl p-4 text-sm"
          style={{ background: "color-mix(in srgb, var(--error-container) 50%, transparent)", border: "1px solid color-mix(in srgb, var(--destructive) 15%, transparent)", color: "var(--destructive)" }}
        >
          Cost data error: {costError}
        </div>
      ) : null}

      {/* Two-column: job list + worker state */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-3">
          <h2 className="text-sm font-medium">
            Ingestion Jobs
            <span className="ml-2 text-xs" style={{ color: "var(--outline)" }}>({jobs.length})</span>
          </h2>

          {isLoading && jobs.length === 0 ? (
            <div className="space-y-3">
              {[1, 2, 3].map((n) => (
                <Skeleton key={n} className="h-24 rounded-2xl" />
              ))}
            </div>
          ) : jobs.length === 0 ? (
            <div
              className="rounded-2xl py-12 text-center"
              style={{ background: "var(--card)", border: "1px solid var(--border)" }}
            >
              <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
                No ingestion jobs yet. Select a source and click &ldquo;Ingest&rdquo; to start.
              </p>
            </div>
          ) : (
            jobs.map((job) => (
              <JobCard key={job.id} job={job} onCancel={cancelJob} onRetry={retryJob} isRetrying={isRetrying} />
            ))
          )}
        </div>

        <div className="space-y-3">
          <h2 className="text-sm font-medium">Worker Summary</h2>
          {stats ? (
            <WorkerState stats={stats} />
          ) : (
            <Skeleton className="h-32 rounded-2xl" />
          )}
        </div>
      </div>
    </div>
  );
}
