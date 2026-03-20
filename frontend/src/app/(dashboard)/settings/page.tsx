"use client";

import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiClient } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type { LLMCostSummary } from "@/types/ingestion";
import { ProfileCard } from "@/components/settings/profile-card";
import { ModelConfigCard } from "@/components/settings/model-config-card";
import { CostSummaryCard } from "@/components/settings/cost-summary-card";
import { PreferencesCard } from "@/components/settings/preferences-card";
import { DangerZoneCard } from "@/components/settings/danger-zone-card";

export default function SettingsPage() {
  const { user, logout } = useAuth();

  const costQuery = useQuery<LLMCostSummary>({
    queryKey: queryKeys.ingestion.cost(),
    queryFn: () => apiClient.get<LLMCostSummary>("/admin/ingestion/cost"),
    enabled: !!user?.is_admin,
  });
  const costSummary = costQuery.data ?? null;
  const costError = costQuery.error ? (costQuery.error as Error).message : null;

  return (
    <div className="flex-1 p-6 lg:p-8 space-y-8 max-w-2xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm" style={{ color: "var(--muted-foreground)" }}>
          Manage your account preferences
        </p>
      </div>

      <ProfileCard user={user} />
      <ModelConfigCard />

      {/* LLM API Cost (admin only) */}
      {user?.is_admin && (costSummary ? (
        <CostSummaryCard cost={costSummary} />
      ) : costError ? (
        <div
          className="rounded-2xl p-4 text-sm"
          style={{ background: "var(--error-container)", border: "1px solid color-mix(in srgb, var(--destructive) 15%, transparent)", color: "var(--destructive)" }}
        >
          Cost data error: {costError}
        </div>
      ) : null)}

      <PreferencesCard />
      <DangerZoneCard onLogout={logout} />
    </div>
  );
}
