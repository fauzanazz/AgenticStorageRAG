import { Loader2, Zap } from "lucide-react";
import type { ClaudeCodeTestResult } from "@/types/settings";

interface ClaudeCodeToggleProps {
  enabled: boolean;
  onToggle: () => void;
  onTest: () => void;
  isTesting: boolean;
  testResult: ClaudeCodeTestResult | null;
}

export function ClaudeCodeToggle({ enabled, onToggle, onTest, isTesting, testResult }: ClaudeCodeToggleProps) {
  return (
    <div className="mb-8">
      <div
        className="rounded-xl p-4 space-y-3"
        style={{ background: "var(--surface-container-high)", border: "1px solid var(--outline-variant)" }}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Zap className="size-4" style={{ color: "var(--primary)" }} />
            <div>
              <p className="text-sm font-medium" style={{ color: "var(--on-surface-variant)" }}>
                Use Claude Code
              </p>
              <p className="text-xs mt-0.5" style={{ color: "var(--outline)" }}>
                Use the local <code className="px-1 py-0.5 rounded text-xs" style={{ background: "var(--surface-container-highest)" }}>claude</code> CLI for Anthropic models (no API key needed)
              </p>
            </div>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={enabled}
            onClick={onToggle}
            className="relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-offset-2"
            style={{
              background: enabled ? "var(--success)" : "var(--outline-variant)",
            }}
          >
            <span
              className="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
              style={{
                transform: enabled ? "translateX(1.25rem)" : "translateX(0.125rem)",
                marginTop: "0.125rem",
              }}
            />
          </button>
        </div>

        {enabled && (
          <div className="flex items-center gap-2">
            <button
              onClick={onTest}
              disabled={isTesting}
              className="h-8 px-3 rounded-lg text-xs font-medium transition-all hover:opacity-90 disabled:opacity-40 flex items-center gap-1.5"
              style={{
                background: "var(--primary)",
                color: "var(--primary-foreground)",
              }}
            >
              {isTesting ? (
                <Loader2 className="size-3 animate-spin" />
              ) : null}
              Test Connection
            </button>
            {testResult && (
              <span
                className="text-xs px-2 py-1 rounded-full font-medium"
                style={{
                  background: testResult.ok
                    ? "var(--success-container)"
                    : "var(--destructive)/10",
                  color: testResult.ok
                    ? "var(--success)"
                    : "var(--destructive)",
                }}
              >
                {testResult.ok
                  ? `Connected${testResult.version ? ` (${testResult.version})` : ""}`
                  : testResult.error || "Not available"}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
