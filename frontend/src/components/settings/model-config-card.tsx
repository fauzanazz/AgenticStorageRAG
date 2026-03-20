"use client";

import { useState } from "react";
import { useModelSettings } from "@/hooks/use-model-settings";
import { Cpu, Eye, EyeOff, AlertTriangle, Check, Loader2 } from "lucide-react";
import type { ModelOption } from "@/types/settings";

const PROVIDER_KEY_FIELD: Record<string, "anthropic" | "openai" | "dashscope" | "openrouter"> = {
  Anthropic: "anthropic",
  OpenAI: "openai",
  DashScope: "dashscope",
  OpenRouter: "openrouter",
};

function groupByProvider<T extends { provider: string }>(items: T[]): { provider: string; items: T[] }[] {
  const map = new Map<string, T[]>();
  for (const item of items) {
    if (!map.has(item.provider)) map.set(item.provider, []);
    map.get(item.provider)!.push(item);
  }
  return Array.from(map.entries()).map(([provider, items]) => ({ provider, items }));
}

export function ModelConfigCard() {
  const { settings, catalog, isSaving, isSuccess: modelSaveSuccess, error: modelError, updateSettings } = useModelSettings();

  const [chatModel, setChatModel] = useState<string>("");
  const [ingestionModel, setIngestionModel] = useState<string>("");
  const [embeddingModel, setEmbeddingModel] = useState<string>("");
  const [claudeSetupToken, setClaudeSetupToken] = useState<string>("");
  const [showSetupToken, setShowSetupToken] = useState(false);

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

  const [modelsInitialized, setModelsInitialized] = useState(false);
  if (settings && !modelsInitialized) {
    setChatModel(settings.chat_model);
    setIngestionModel(settings.ingestion_model);
    setEmbeddingModel(settings.embedding_model);
    setModelsInitialized(true);
  }

  const handleSave = async () => {
    await updateSettings({
      chat_model: chatModel || undefined,
      ingestion_model: ingestionModel || undefined,
      embedding_model: embeddingModel || undefined,
      anthropic_api_key: apiKeys.anthropic,
      openai_api_key: apiKeys.openai,
      dashscope_api_key: apiKeys.dashscope,
      openrouter_api_key: apiKeys.openrouter,
      claude_setup_token: claudeSetupToken,
    });
    setApiKeys({ anthropic: "", openai: "", dashscope: "", openrouter: "" });
    setClaudeSetupToken("");
  };

  const getProviderForModel = (modelId: string): string => {
    if (modelId.startsWith("anthropic/")) return "Anthropic";
    if (modelId.startsWith("openai/")) return "OpenAI";
    if (modelId.startsWith("dashscope/")) return "DashScope";
    if (modelId.startsWith("openrouter/")) return "OpenRouter";
    return "";
  };

  const hasKeyForModel = (modelId: string): boolean => {
    if (!settings) return true;
    const provider = getProviderForModel(modelId);
    const keyField = PROVIDER_KEY_FIELD[provider];
    if (!keyField) return true;
    if (apiKeys[keyField]) return true;
    // Claude setup token counts as having Anthropic credentials
    if (keyField === "anthropic" && settings.claude_setup_token?.has_token) return true;
    const keyStatus = settings[`${keyField}_api_key` as "anthropic_api_key" | "openai_api_key" | "dashscope_api_key" | "openrouter_api_key"];
    return typeof keyStatus === "object" && keyStatus.has_key === true;
  };

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

  const renderModelSelect = (
    id: string,
    label: string,
    value: string,
    onChange: (v: string) => void,
    groups: { provider: string; items: ModelOption[] }[],
  ) => (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium" style={{ color: "var(--on-surface-variant)" }}>
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={selectClassName}
        style={selectStyle}
        disabled={!catalog}
      >
        {groups.map(({ provider, items }) => (
          <optgroup key={provider} label={provider}>
            {items.map((m) => (
              <option key={m.model_id} value={m.model_id}>
                {m.label}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      {value && !hasKeyForModel(value) && (
        <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--warning)" }}>
          <AlertTriangle className="size-3.5" />
          Requires a {getProviderForModel(value)} API key.
        </div>
      )}
    </div>
  );

  return (
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

      {/* API Keys */}
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

              {/* Claude Setup Token — shown only for Anthropic */}
              {id === "anthropic" && (
                <div
                  className="mt-3 rounded-xl p-3 space-y-2"
                  style={{ background: "var(--surface-container-high)", border: "1px solid var(--outline-variant)" }}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium" style={{ color: "var(--on-surface-variant)" }}>
                        Claude Pro / Max (Setup Token)
                      </p>
                      <p className="text-xs mt-0.5" style={{ color: "var(--outline)" }}>
                        Run <code className="px-1 py-0.5 rounded text-xs" style={{ background: "var(--surface-container-highest)" }}>claude setup-token</code> in your terminal, then paste the token here
                      </p>
                    </div>
                    {settings?.claude_setup_token?.has_token && (
                      <span
                        className="text-xs px-2 py-0.5 rounded-full font-medium"
                        style={{ background: "var(--success-container)", color: "var(--success)" }}
                      >
                        Configured
                      </span>
                    )}
                  </div>
                  <div className="relative">
                    <input
                      type={showSetupToken ? "text" : "password"}
                      value={claudeSetupToken}
                      onChange={(e) => setClaudeSetupToken(e.target.value)}
                      placeholder={settings?.claude_setup_token?.has_token ? "Enter new token to replace..." : "Paste setup token..."}
                      className={`${inputClassName} pr-12`}
                      style={inputStyle}
                    />
                    <button
                      type="button"
                      onClick={() => setShowSetupToken(!showSetupToken)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 p-1 rounded-lg transition-opacity hover:opacity-70"
                      style={{ color: "var(--outline)" }}
                    >
                      {showSetupToken ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Model Selection */}
      <div className="space-y-4 mb-8">
        <h3 className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--outline)" }}>
          Model Selection
        </h3>
        {renderModelSelect("settings-chat-model", "Chat model", chatModel, setChatModel, chatGroups)}
        {renderModelSelect("settings-ingestion-model", "Ingestion model", ingestionModel, setIngestionModel, chatGroups)}
        {renderModelSelect("settings-embedding-model", "Embedding model", embeddingModel, setEmbeddingModel, embeddingGroups)}
      </div>

      {/* Save button */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
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
  );
}
