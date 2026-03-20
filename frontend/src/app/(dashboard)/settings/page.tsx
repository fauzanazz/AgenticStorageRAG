"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth, type User } from "@/hooks/use-auth";
import { useModelSettings } from "@/hooks/use-model-settings";
import { apiClient } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type { LLMCostSummary } from "@/types/ingestion";
import { User as UserIcon, Bell, Shield, Check, Loader2, Cpu, Eye, EyeOff, AlertTriangle, DollarSign, ChevronDown, ChevronUp } from "lucide-react";

// ---------------------------------------------------------------------------
// Helper: format token counts
// ---------------------------------------------------------------------------

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

// ---------------------------------------------------------------------------
// Cost summary card (admin only)
// ---------------------------------------------------------------------------

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
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: "var(--accent)" }}
          >
            <DollarSign className="size-4" style={{ color: "var(--primary)" }} />
          </div>
          <div>
            <h2 className="text-base font-semibold">LLM API Cost</h2>
            <p className="text-xs mt-0.5" style={{ color: "var(--outline)" }}>
              Total cost:&nbsp;
              <span className="font-semibold">
                {cost.total_cost_usd < 0.0001 && cost.total_cost_usd > 0
                  ? "<$0.0001"
                  : `$${cost.total_cost_usd.toFixed(4)}`}
              </span>
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

// ---------------------------------------------------------------------------
// Helper: group catalog models by provider for <optgroup> rendering
// ---------------------------------------------------------------------------

function groupByProvider<T extends { provider: string }>(items: T[]): { provider: string; items: T[] }[] {
  const map = new Map<string, T[]>();
  for (const item of items) {
    if (!map.has(item.provider)) map.set(item.provider, []);
    map.get(item.provider)!.push(item);
  }
  return Array.from(map.entries()).map(([provider, items]) => ({ provider, items }));
}

// ---------------------------------------------------------------------------
// Provider → key field mapping
// ---------------------------------------------------------------------------

const PROVIDER_KEY_FIELD: Record<string, "anthropic" | "openai" | "dashscope" | "openrouter"> = {
  Anthropic: "anthropic",
  OpenAI: "openai",
  DashScope: "dashscope",
  OpenRouter: "openrouter",
};

// ---------------------------------------------------------------------------
// Settings page
// ---------------------------------------------------------------------------

export default function SettingsPage() {
  const { user, logout } = useAuth();
  const queryClient = useQueryClient();
  const { settings, catalog, isSaving, isSuccess: modelSaveSuccess, error: modelError, updateSettings } = useModelSettings();

  const [fullName, setFullName] = useState(user?.full_name || "");

  // Model selection state (controlled; initialized from settings once loaded)
  const [chatModel, setChatModel] = useState<string>("");
  const [ingestionModel, setIngestionModel] = useState<string>("");
  const [embeddingModel, setEmbeddingModel] = useState<string>("");

  // API key state — tracked per provider
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({
    anthropic: "",
    openai: "",
    dashscope: "",
    openrouter: "",
  });
  const [showKey, setShowKey] = useState<Record<string, boolean>>({
    anthropic: false,
    openai: false,
    dashscope: false,
    openrouter: false,
  });

  // Initialize model fields from server once loaded
  const [modelsInitialized, setModelsInitialized] = useState(false);
  if (settings && !modelsInitialized) {
    setChatModel(settings.chat_model);
    setIngestionModel(settings.ingestion_model);
    setEmbeddingModel(settings.embedding_model);
    setModelsInitialized(true);
  }

  const updateProfileMutation = useMutation({
    mutationFn: (name: string) =>
      apiClient.patch<User>("/auth/me", { full_name: name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.auth.me() });
      setTimeout(() => updateProfileMutation.reset(), 3_000);
    },
  });

  const handleSaveProfile = () => {
    if (!fullName.trim()) return;
    updateProfileMutation.mutate(fullName.trim());
  };

  const handleSaveModels = async () => {
    await updateSettings({
      chat_model: chatModel || undefined,
      ingestion_model: ingestionModel || undefined,
      embedding_model: embeddingModel || undefined,
      // Send "" to leave existing key unchanged, send actual value to update, send null to clear
      anthropic_api_key: apiKeys.anthropic,
      openai_api_key: apiKeys.openai,
      dashscope_api_key: apiKeys.dashscope,
      openrouter_api_key: apiKeys.openrouter,
    });
    // Clear plaintext keys from local state after save
    setApiKeys({ anthropic: "", openai: "", dashscope: "", openrouter: "" });
  };

  // Determine which provider is required for a selected model
  const getProviderForModel = (modelId: string): string => {
    if (modelId.startsWith("anthropic/")) return "Anthropic";
    if (modelId.startsWith("openai/")) return "OpenAI";
    if (modelId.startsWith("dashscope/")) return "DashScope";
    if (modelId.startsWith("openrouter/")) return "OpenRouter";
    return "";
  };

  const hasKeyForModel = (modelId: string): boolean => {
    if (!settings) return true; // optimistic while loading
    const provider = getProviderForModel(modelId);
    const keyField = PROVIDER_KEY_FIELD[provider];
    if (!keyField) return true;
    // Also consider a key just typed in this session
    if (apiKeys[keyField]) return true;
    const keyStatus = settings[`${keyField}_api_key` as "anthropic_api_key" | "openai_api_key" | "dashscope_api_key" | "openrouter_api_key"];
    return typeof keyStatus === "object" && keyStatus.has_key === true;
  };

  // ── LLM cost (admin only) ──
  const costQuery = useQuery<LLMCostSummary>({
    queryKey: queryKeys.ingestion.cost(),
    queryFn: () => apiClient.get<LLMCostSummary>("/admin/ingestion/cost"),
    enabled: !!user?.is_admin,
  });
  const costSummary = costQuery.data ?? null;
  const costError = costQuery.error ? (costQuery.error as Error).message : null;

  const hasChanges = fullName.trim() !== (user?.full_name || "");
  const isSavingProfile = updateProfileMutation.isPending;
  const profileSaveSuccess = updateProfileMutation.isSuccess;
  const profileSaveError = updateProfileMutation.error?.message ?? null;

  const inputClassName =
    "w-full h-12 rounded-xl px-4 text-sm text-foreground placeholder:text-outline-variant outline-none focus:ring-2 focus:ring-primary/50 transition-all";
  const inputStyle = {
    background: "var(--surface-container-high)",
    border: "1px solid var(--outline-variant)",
  };

  const selectClassName =
    "w-full h-12 rounded-xl px-4 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/50 transition-all appearance-none cursor-pointer";
  const selectStyle = {
    background: "var(--surface-container-high)",
    border: "1px solid var(--outline-variant)",
  };

  const chatGroups = catalog ? groupByProvider(catalog.chat_models) : [];
  const embeddingGroups = catalog ? groupByProvider(catalog.embedding_models) : [];

  const providers = [
    { id: "anthropic", label: "Anthropic", placeholder: "sk-ant-..." },
    { id: "openai", label: "OpenAI", placeholder: "sk-..." },
    { id: "dashscope", label: "DashScope", placeholder: "sk-..." },
    { id: "openrouter", label: "OpenRouter", placeholder: "sk-or-v1-..." },
  ] as const;

  return (
    <div className="flex-1 p-6 lg:p-8 space-y-8 max-w-2xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm" style={{ color: "var(--muted-foreground)" }}>
          Manage your account preferences
        </p>
      </div>

      {/* Profile Section */}
      <div
        className="rounded-2xl p-6"
        style={{
          background: "var(--card)",
          border: "1px solid var(--border)",
        }}
      >
        <div className="flex items-center gap-3 mb-6">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: "var(--accent)" }}
          >
            <UserIcon className="size-4" style={{ color: "var(--primary)" }} />
          </div>
          <h2 className="text-base font-semibold">Profile</h2>
        </div>

        <div className="space-y-4">
          <div className="space-y-2">
            <label htmlFor="settings-fullname" className="block text-sm font-medium" style={{ color: "var(--on-surface-variant)" }}>
              Full Name
            </label>
            <input
              id="settings-fullname"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Your name"
              className={inputClassName}
              style={inputStyle}
            />
          </div>
          <div className="space-y-2">
            <label htmlFor="settings-email" className="block text-sm font-medium" style={{ color: "var(--on-surface-variant)" }}>
              Email Address
            </label>
            <input
              id="settings-email"
              type="email"
              defaultValue={user?.email || ""}
              placeholder="you@example.com"
              disabled
              className={`${inputClassName} opacity-50 cursor-not-allowed`}
              style={inputStyle}
            />
            <p className="text-xs" style={{ color: "var(--outline)" }}>
              Email cannot be changed.
            </p>
          </div>
        </div>

        {/* Save button + feedback */}
        <div className="mt-6 flex items-center gap-3">
          <button
            onClick={handleSaveProfile}
            disabled={!hasChanges || isSavingProfile}
            className="h-10 px-5 rounded-xl text-sm font-semibold text-white transition-all hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
            style={{ background: "var(--primary)" }}
          >
            {isSavingProfile ? (
              <Loader2 className="size-4 animate-spin" />
            ) : profileSaveSuccess ? (
              <Check className="size-4" />
            ) : null}
            {isSavingProfile ? "Saving..." : profileSaveSuccess ? "Saved" : "Save Changes"}
          </button>

          {profileSaveError && (
            <span className="text-xs" style={{ color: "var(--destructive)" }}>
              {profileSaveError}
            </span>
          )}
        </div>
      </div>

      {/* ── Model Configuration Section ─────────────────────────────── */}
      <div
        className="rounded-2xl p-6"
        style={{
          background: "var(--card)",
          border: "1px solid var(--border)",
        }}
      >
        <div className="flex items-center gap-3 mb-6">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: "var(--success-container)" }}
          >
            <Cpu className="size-4" style={{ color: "var(--success)" }} />
          </div>
          <div>
            <h2 className="text-base font-semibold">Model Configuration</h2>
            <p className="text-xs mt-0.5" style={{ color: "var(--outline)" }}>
              Your API keys are encrypted at rest and never shared.
            </p>
          </div>
        </div>

        {/* ── API Keys ── */}
        <div className="space-y-4 mb-8">
          <h3 className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--outline)" }}>
            API Keys
          </h3>
          {providers.map(({ id, label, placeholder }) => {
            const keyStatus = settings?.[`${id}_api_key` as "anthropic_api_key" | "openai_api_key" | "dashscope_api_key" | "openrouter_api_key"];
            const hasKey = typeof keyStatus === "object" && keyStatus.has_key === true;
            return (
              <div key={id} className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium" style={{ color: "var(--on-surface-variant)" }}>
                    {label}
                  </label>
                  {hasKey ? (
                    <span
                      className="text-xs px-2 py-0.5 rounded-full font-medium"
                      style={{ background: "var(--success-container)", color: "var(--success)" }}
                    >
                      Configured
                    </span>
                  ) : (
                    <span
                      className="text-xs px-2 py-0.5 rounded-full font-medium"
                      style={{ background: "var(--surface-container-high)", color: "var(--outline)" }}
                    >
                      Not configured
                    </span>
                  )}
                </div>
                <div className="relative">
                  <input
                    type={showKey[id] ? "text" : "password"}
                    value={apiKeys[id]}
                    onChange={(e) => setApiKeys((prev) => ({ ...prev, [id]: e.target.value }))}
                    placeholder={hasKey ? "Enter new key to replace..." : placeholder}
                    className={`${inputClassName} pr-12`}
                    style={inputStyle}
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey((prev) => ({ ...prev, [id]: !prev[id] }))}
                    className="absolute right-3 top-1/2 -translate-y-1/2 p-1 rounded-lg transition-opacity hover:opacity-70"
                    style={{ color: "var(--outline)" }}
                  >
                    {showKey[id] ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </button>
                </div>
                {hasKey && !apiKeys[id] && (
                  <p className="text-xs" style={{ color: "var(--outline-variant)" }}>
                    Leave empty to keep your existing key.
                  </p>
                )}
              </div>
            );
          })}
        </div>

        {/* ── Model Selection ── */}
        <div className="space-y-4 mb-8">
          <h3 className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--outline)" }}>
            Model Selection
          </h3>

          {/* Chat Model */}
          <div className="space-y-1.5">
            <label htmlFor="settings-chat-model" className="block text-sm font-medium" style={{ color: "var(--on-surface-variant)" }}>
              Chat model
            </label>
            <select
              id="settings-chat-model"
              value={chatModel}
              onChange={(e) => setChatModel(e.target.value)}
              className={selectClassName}
              style={selectStyle}
              disabled={!catalog}
            >
              {chatGroups.map(({ provider, items }) => (
                <optgroup key={provider} label={provider}>
                  {items.map((m) => (
                    <option key={m.model_id} value={m.model_id}>
                      {m.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            {chatModel && !hasKeyForModel(chatModel) && (
              <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--warning)" }}>
                <AlertTriangle className="size-3.5" />
                Requires a {getProviderForModel(chatModel)} API key.
              </div>
            )}
          </div>

          {/* Ingestion Model */}
          <div className="space-y-1.5">
            <label htmlFor="settings-ingestion-model" className="block text-sm font-medium" style={{ color: "var(--on-surface-variant)" }}>
              Ingestion model
            </label>
            <select
              id="settings-ingestion-model"
              value={ingestionModel}
              onChange={(e) => setIngestionModel(e.target.value)}
              className={selectClassName}
              style={selectStyle}
              disabled={!catalog}
            >
              {chatGroups.map(({ provider, items }) => (
                <optgroup key={provider} label={provider}>
                  {items.map((m) => (
                    <option key={m.model_id} value={m.model_id}>
                      {m.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            {ingestionModel && !hasKeyForModel(ingestionModel) && (
              <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--warning)" }}>
                <AlertTriangle className="size-3.5" />
                Requires a {getProviderForModel(ingestionModel)} API key.
              </div>
            )}
          </div>

          {/* Embedding Model */}
          <div className="space-y-1.5">
            <label htmlFor="settings-embedding-model" className="block text-sm font-medium" style={{ color: "var(--on-surface-variant)" }}>
              Embedding model
            </label>
            <select
              id="settings-embedding-model"
              value={embeddingModel}
              onChange={(e) => setEmbeddingModel(e.target.value)}
              className={selectClassName}
              style={selectStyle}
              disabled={!catalog}
            >
              {embeddingGroups.map(({ provider, items }) => (
                <optgroup key={provider} label={provider}>
                  {items.map((m) => (
                    <option key={m.model_id} value={m.model_id}>
                      {m.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            {embeddingModel && !hasKeyForModel(embeddingModel) && (
              <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--warning)" }}>
                <AlertTriangle className="size-3.5" />
                Requires a {getProviderForModel(embeddingModel)} API key.
              </div>
            )}
          </div>
        </div>

        {/* Save button */}
        <div className="flex items-center gap-3">
          <button
            onClick={handleSaveModels}
            disabled={isSaving}
            className="h-10 px-5 rounded-xl text-sm font-semibold text-white transition-all hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
            style={{ background: "var(--success)" }}
          >
            {isSaving ? (
              <Loader2 className="size-4 animate-spin" />
            ) : modelSaveSuccess ? (
              <Check className="size-4" />
            ) : null}
            {isSaving ? "Saving..." : modelSaveSuccess ? "Saved" : "Save Model Settings"}
          </button>

          {modelError && (
            <span className="text-xs" style={{ color: "var(--destructive)" }}>
              {modelError}
            </span>
          )}
        </div>
      </div>

      {/* ── LLM API Cost (admin only) ──────────────────────────── */}
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

      {/* Preferences Section */}
      <div
        className="rounded-2xl p-6"
        style={{
          background: "var(--card)",
          border: "1px solid var(--border)",
        }}
      >
        <div className="flex items-center gap-3 mb-6">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: "#f3e5f5" }}
          >
            <Bell className="size-4" style={{ color: "var(--tertiary)" }} />
          </div>
          <h2 className="text-base font-semibold">Preferences</h2>
        </div>

        <div className="space-y-4">
          {["Email Notifications", "Auto-process Documents", "Show Citations in Chat"].map(
            (pref) => (
              <div key={pref} className="flex items-center justify-between">
                <span className="text-sm" style={{ color: "var(--on-surface-variant)" }}>
                  {pref}
                </span>
                <div
                  className="w-11 h-6 rounded-full relative cursor-pointer"
                  style={{ background: "color-mix(in srgb, var(--primary) 30%, transparent)" }}
                >
                  <div
                    className="w-5 h-5 rounded-full absolute top-0.5 right-0.5"
                    style={{ background: "var(--primary)" }}
                  />
                </div>
              </div>
            )
          )}
        </div>
        <p className="mt-4 text-xs" style={{ color: "var(--outline-variant)" }}>
          Preference toggles are coming soon.
        </p>
      </div>

      {/* Danger Zone */}
      <div
        className="rounded-2xl p-6"
        style={{
          background: "var(--error-container)",
          border: "1px solid color-mix(in srgb, var(--destructive) 15%, transparent)",
        }}
      >
        <div className="flex items-center gap-3 mb-4">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: "var(--error-container)" }}
          >
            <Shield className="size-4" style={{ color: "var(--destructive)" }} />
          </div>
          <h2 className="text-base font-semibold" style={{ color: "var(--destructive)" }}>
            Danger Zone
          </h2>
        </div>
        <p className="text-sm mb-4" style={{ color: "var(--muted-foreground)" }}>
          Sign out of your account on this device.
        </p>
        <button
          onClick={logout}
          className="h-10 px-4 rounded-xl text-sm font-semibold transition-all hover:opacity-80"
          style={{
            background: "var(--error-container)",
            color: "var(--destructive)",
            border: "1px solid color-mix(in srgb, var(--destructive) 20%, transparent)",
          }}
        >
          Sign Out
        </button>
      </div>
    </div>
  );
}
