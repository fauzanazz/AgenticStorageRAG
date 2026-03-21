"use client";

import { useState, useRef, useEffect } from "react";
import { Brain, ChevronDown } from "lucide-react";
import type { ModelOption } from "@/types/settings";

interface ModelSelectorDropdownProps {
  models: ModelOption[];
  selectedModel: string | null;
  onModelChange: (modelId: string) => void;
  enableThinking: boolean;
  onThinkingChange?: (enabled: boolean) => void;
  supportsThinking: boolean;
}

export function ModelSelectorDropdown({
  models,
  selectedModel,
  onModelChange,
  enableThinking,
  onThinkingChange,
  supportsThinking,
}: ModelSelectorDropdownProps) {
  const [showMenu, setShowMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showMenu) return;
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [showMenu]);

  const selectedLabel =
    models.find((m) => m.model_id === selectedModel)?.label ?? "Select model";

  const grouped = models.reduce<Record<string, ModelOption[]>>((acc, m) => {
    (acc[m.provider] ??= []).push(m);
    return acc;
  }, {});

  return (
    <div className="relative" ref={menuRef}>
      <button
        type="button"
        onClick={() => setShowMenu((v) => !v)}
        className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs transition-colors hover:bg-black/[0.05]"
        style={{
          background: enableThinking
            ? "color-mix(in srgb, var(--primary) 12%, transparent)"
            : "var(--surface-container-high, #e4e4e7)",
          color: enableThinking
            ? "var(--primary)"
            : "var(--on-surface-variant)",
        }}
      >
        {enableThinking && <Brain className="size-3" />}
        <span className="max-w-[180px] truncate">{selectedLabel}</span>
        <ChevronDown className="size-3 opacity-60" />
      </button>

      {showMenu && (
        <div
          className="absolute bottom-full left-0 z-50 mb-1.5 min-w-[240px] rounded-xl py-1"
          style={{
            background: "var(--card)",
            boxShadow:
              "0 4px 6px -1px rgba(0,0,0,0.07), 0 10px 15px -3px rgba(0,0,0,0.1)",
            border: "1px solid var(--outline-variant)",
          }}
        >
          {Object.entries(grouped).map(([provider, providerModels]) => (
            <div key={provider}>
              <div
                className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider"
                style={{ color: "var(--outline)" }}
              >
                {provider}
              </div>
              {providerModels.map((m) => (
                <button
                  key={m.model_id}
                  onClick={() => {
                    onModelChange(m.model_id);
                    setShowMenu(false);
                  }}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors hover:bg-black/[0.05]"
                  style={{
                    color:
                      m.model_id === selectedModel
                        ? "var(--primary)"
                        : "var(--muted-foreground)",
                  }}
                >
                  <span className="w-4 text-center text-[10px]">
                    {m.model_id === selectedModel ? "✓" : ""}
                  </span>
                  <span>{m.label}</span>
                </button>
              ))}
            </div>
          ))}

          {supportsThinking && (
            <>
              <div
                className="mx-2.5 my-1"
                style={{
                  height: "1px",
                  background: "var(--outline-variant)",
                  opacity: 0.5,
                }}
              />
              <button
                type="button"
                onClick={() => onThinkingChange?.(!enableThinking)}
                className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-xs transition-colors hover:bg-black/[0.05]"
                style={{
                  color: enableThinking
                    ? "var(--primary)"
                    : "var(--muted-foreground)",
                }}
              >
                <Brain
                  className="size-3.5"
                  style={{
                    color: enableThinking
                      ? "var(--primary)"
                      : "var(--outline)",
                  }}
                />
                <span className="flex-1">Extended thinking</span>
                <div
                  className="relative h-[18px] w-[32px] rounded-full transition-colors"
                  style={{
                    background: enableThinking
                      ? "var(--primary)"
                      : "var(--outline-variant)",
                  }}
                >
                  <div
                    className="absolute top-[2px] h-[14px] w-[14px] rounded-full bg-white transition-transform"
                    style={{
                      transform: enableThinking
                        ? "translateX(16px)"
                        : "translateX(2px)",
                    }}
                  />
                </div>
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
