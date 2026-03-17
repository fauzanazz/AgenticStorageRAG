"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth, type User } from "@/hooks/use-auth";
import { useModelSettings } from "@/hooks/use-model-settings";
import { apiClient } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import { User as UserIcon, Bell, Shield, Check, Loader2, Cpu, Eye, EyeOff, AlertTriangle } from "lucide-react";

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

const PROVIDER_KEY_FIELD: Record<string, "anthropic" | "openai" | "dashscope"> = {
  Anthropic: "anthropic",
  OpenAI: "openai",
  DashScope: "dashscope",
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
  });
  const [showKey, setShowKey] = useState<Record<string, boolean>>({
    anthropic: false,
    openai: false,
    dashscope: false,
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
    });
    // Clear plaintext keys from local state after save
    setApiKeys({ anthropic: "", openai: "", dashscope: "" });
  };

  // Determine which provider is required for a selected model
  const getProviderForModel = (modelId: string): string => {
    if (modelId.startsWith("anthropic/")) return "Anthropic";
    if (modelId.startsWith("openai/")) return "OpenAI";
    if (modelId.startsWith("dashscope/")) return "DashScope";
    return "";
  };

  const hasKeyForModel = (modelId: string): boolean => {
    if (!settings) return true; // optimistic while loading
    const provider = getProviderForModel(modelId);
    const keyField = PROVIDER_KEY_FIELD[provider];
    if (!keyField) return true;
    // Also consider a key just typed in this session
    if (apiKeys[keyField]) return true;
    const keyStatus = settings[`${keyField}_api_key` as "anthropic_api_key" | "openai_api_key" | "dashscope_api_key"];
    return typeof keyStatus === "object" && keyStatus.has_key === true;
  };

  const hasChanges = fullName.trim() !== (user?.full_name || "");
  const isSavingProfile = updateProfileMutation.isPending;
  const profileSaveSuccess = updateProfileMutation.isSuccess;
  const profileSaveError = updateProfileMutation.error?.message ?? null;

  const inputClassName =
    "w-full h-12 rounded-xl px-4 text-sm text-white placeholder:text-white/30 outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all";
  const inputStyle = {
    background: "rgba(255,255,255,0.06)",
    border: "1px solid rgba(255,255,255,0.08)",
  };

  const selectClassName =
    "w-full h-12 rounded-xl px-4 text-sm text-white outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all appearance-none cursor-pointer";
  const selectStyle = {
    background: "rgba(255,255,255,0.06)",
    border: "1px solid rgba(255,255,255,0.08)",
  };

  const chatGroups = catalog ? groupByProvider(catalog.chat_models) : [];
  const embeddingGroups = catalog ? groupByProvider(catalog.embedding_models) : [];

  const providers = [
    { id: "anthropic", label: "Anthropic", placeholder: "sk-ant-..." },
    { id: "openai", label: "OpenAI", placeholder: "sk-..." },
    { id: "dashscope", label: "DashScope", placeholder: "sk-..." },
  ] as const;

  return (
    <div className="flex-1 p-6 lg:p-8 space-y-8 max-w-2xl">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white tracking-tight">Settings</h1>
        <p className="mt-1 text-sm" style={{ color: "rgba(255,255,255,0.4)" }}>
          Manage your account preferences
        </p>
      </div>

      {/* Profile Section */}
      <div
        className="rounded-2xl p-6"
        style={{
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(255,255,255,0.06)",
        }}
      >
        <div className="flex items-center gap-3 mb-6">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: "rgba(99,102,241,0.12)" }}
          >
            <UserIcon className="size-4" style={{ color: "#818CF8" }} />
          </div>
          <h2 className="text-base font-semibold text-white">Profile</h2>
        </div>

        <div className="space-y-4">
          <div className="space-y-2">
            <label className="block text-sm font-medium" style={{ color: "rgba(255,255,255,0.6)" }}>
              Full Name
            </label>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Your name"
              className={inputClassName}
              style={inputStyle}
            />
          </div>
          <div className="space-y-2">
            <label className="block text-sm font-medium" style={{ color: "rgba(255,255,255,0.6)" }}>
              Email Address
            </label>
            <input
              type="email"
              defaultValue={user?.email || ""}
              placeholder="you@example.com"
              disabled
              className={`${inputClassName} opacity-50 cursor-not-allowed`}
              style={inputStyle}
            />
            <p className="text-xs" style={{ color: "rgba(255,255,255,0.3)" }}>
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
            style={{ background: "linear-gradient(135deg, #6366F1, #A855F7)" }}
          >
            {isSavingProfile ? (
              <Loader2 className="size-4 animate-spin" />
            ) : profileSaveSuccess ? (
              <Check className="size-4" />
            ) : null}
            {isSavingProfile ? "Saving..." : profileSaveSuccess ? "Saved" : "Save Changes"}
          </button>

          {profileSaveError && (
            <span className="text-xs" style={{ color: "#FCA5A5" }}>
              {profileSaveError}
            </span>
          )}
        </div>
      </div>

      {/* ── Model Configuration Section ─────────────────────────────── */}
      <div
        className="rounded-2xl p-6"
        style={{
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(255,255,255,0.06)",
        }}
      >
        <div className="flex items-center gap-3 mb-6">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: "rgba(16,185,129,0.12)" }}
          >
            <Cpu className="size-4" style={{ color: "#34D399" }} />
          </div>
          <div>
            <h2 className="text-base font-semibold text-white">Model Configuration</h2>
            <p className="text-xs mt-0.5" style={{ color: "rgba(255,255,255,0.35)" }}>
              Your API keys are encrypted at rest and never shared.
            </p>
          </div>
        </div>

        {/* ── API Keys ── */}
        <div className="space-y-4 mb-8">
          <h3 className="text-xs font-semibold uppercase tracking-widest" style={{ color: "rgba(255,255,255,0.35)" }}>
            API Keys
          </h3>
          {providers.map(({ id, label, placeholder }) => {
            const keyStatus = settings?.[`${id}_api_key` as "anthropic_api_key" | "openai_api_key" | "dashscope_api_key"];
            const hasKey = typeof keyStatus === "object" && keyStatus.has_key === true;
            return (
              <div key={id} className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium" style={{ color: "rgba(255,255,255,0.6)" }}>
                    {label}
                  </label>
                  {hasKey ? (
                    <span
                      className="text-xs px-2 py-0.5 rounded-full font-medium"
                      style={{ background: "rgba(16,185,129,0.15)", color: "#34D399" }}
                    >
                      Configured
                    </span>
                  ) : (
                    <span
                      className="text-xs px-2 py-0.5 rounded-full font-medium"
                      style={{ background: "rgba(255,255,255,0.06)", color: "rgba(255,255,255,0.35)" }}
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
                    style={{ color: "rgba(255,255,255,0.35)" }}
                  >
                    {showKey[id] ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </button>
                </div>
                {hasKey && !apiKeys[id] && (
                  <p className="text-xs" style={{ color: "rgba(255,255,255,0.25)" }}>
                    Leave empty to keep your existing key.
                  </p>
                )}
              </div>
            );
          })}
        </div>

        {/* ── Model Selection ── */}
        <div className="space-y-4 mb-8">
          <h3 className="text-xs font-semibold uppercase tracking-widest" style={{ color: "rgba(255,255,255,0.35)" }}>
            Model Selection
          </h3>

          {/* Chat Model */}
          <div className="space-y-1.5">
            <label className="block text-sm font-medium" style={{ color: "rgba(255,255,255,0.6)" }}>
              Chat model
            </label>
            <select
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
              <div className="flex items-center gap-1.5 text-xs" style={{ color: "#FCD34D" }}>
                <AlertTriangle className="size-3.5" />
                Requires a {getProviderForModel(chatModel)} API key.
              </div>
            )}
          </div>

          {/* Ingestion Model */}
          <div className="space-y-1.5">
            <label className="block text-sm font-medium" style={{ color: "rgba(255,255,255,0.6)" }}>
              Ingestion model
            </label>
            <select
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
              <div className="flex items-center gap-1.5 text-xs" style={{ color: "#FCD34D" }}>
                <AlertTriangle className="size-3.5" />
                Requires a {getProviderForModel(ingestionModel)} API key.
              </div>
            )}
          </div>

          {/* Embedding Model */}
          <div className="space-y-1.5">
            <label className="block text-sm font-medium" style={{ color: "rgba(255,255,255,0.6)" }}>
              Embedding model
            </label>
            <select
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
              <div className="flex items-center gap-1.5 text-xs" style={{ color: "#FCD34D" }}>
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
            style={{ background: "linear-gradient(135deg, #059669, #10B981)" }}
          >
            {isSaving ? (
              <Loader2 className="size-4 animate-spin" />
            ) : modelSaveSuccess ? (
              <Check className="size-4" />
            ) : null}
            {isSaving ? "Saving..." : modelSaveSuccess ? "Saved" : "Save Model Settings"}
          </button>

          {modelError && (
            <span className="text-xs" style={{ color: "#FCA5A5" }}>
              {modelError}
            </span>
          )}
        </div>
      </div>

      {/* Preferences Section */}
      <div
        className="rounded-2xl p-6"
        style={{
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(255,255,255,0.06)",
        }}
      >
        <div className="flex items-center gap-3 mb-6">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: "rgba(168,85,247,0.12)" }}
          >
            <Bell className="size-4" style={{ color: "#C084FC" }} />
          </div>
          <h2 className="text-base font-semibold text-white">Preferences</h2>
        </div>

        <div className="space-y-4">
          {["Email Notifications", "Auto-process Documents", "Show Citations in Chat"].map(
            (pref) => (
              <div key={pref} className="flex items-center justify-between">
                <span className="text-sm" style={{ color: "rgba(255,255,255,0.6)" }}>
                  {pref}
                </span>
                <div
                  className="w-11 h-6 rounded-full relative cursor-pointer"
                  style={{ background: "rgba(99,102,241,0.3)" }}
                >
                  <div
                    className="w-5 h-5 rounded-full absolute top-0.5 right-0.5"
                    style={{ background: "#6366F1" }}
                  />
                </div>
              </div>
            )
          )}
        </div>
        <p className="mt-4 text-xs" style={{ color: "rgba(255,255,255,0.25)" }}>
          Preference toggles are coming soon.
        </p>
      </div>

      {/* Danger Zone */}
      <div
        className="rounded-2xl p-6"
        style={{
          background: "rgba(239,68,68,0.03)",
          border: "1px solid rgba(239,68,68,0.1)",
        }}
      >
        <div className="flex items-center gap-3 mb-4">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: "rgba(239,68,68,0.12)" }}
          >
            <Shield className="size-4" style={{ color: "#FCA5A5" }} />
          </div>
          <h2 className="text-base font-semibold" style={{ color: "#FCA5A5" }}>
            Danger Zone
          </h2>
        </div>
        <p className="text-sm mb-4" style={{ color: "rgba(255,255,255,0.4)" }}>
          Sign out of your account on this device.
        </p>
        <button
          onClick={logout}
          className="h-10 px-4 rounded-xl text-sm font-semibold transition-all hover:opacity-80"
          style={{
            background: "rgba(239,68,68,0.15)",
            color: "#FCA5A5",
            border: "1px solid rgba(239,68,68,0.2)",
          }}
        >
          Sign Out
        </button>
      </div>
    </div>
  );
}

