"use client";

import { useState, useRef, useCallback } from "react";
import { ChevronDown, Send, Square } from "lucide-react";
import type { ModelOption } from "@/types/settings";

const EMPTY_MODELS: ModelOption[] = [];

interface ChatInputProps {
  onSend: (message: string) => void;
  onStop?: () => void;
  isStreaming?: boolean;
  disabled?: boolean;
  placeholder?: string;
  models?: ModelOption[];
  selectedModel: string | null;
  onModelChange: (modelId: string) => void;
}

export function ChatInput({
  onSend,
  onStop,
  isStreaming = false,
  disabled = false,
  placeholder = "Ask a question about your knowledge base...",
  models = EMPTY_MODELS,
  selectedModel,
  onModelChange,
}: ChatInputProps) {
  const [input, setInput] = useState("");
  const [showModelMenu, setShowModelMenu] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const handleSubmit = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || disabled || isStreaming) return;
    onSend(trimmed);
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [input, disabled, isStreaming, onSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit]
  );

  const handleInput = useCallback(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, []);

  const selectedLabel =
    models.find((m) => m.model_id === selectedModel)?.label ?? "Select model";

  // Group models by provider
  const grouped = models.reduce<Record<string, ModelOption[]>>((acc, m) => {
    (acc[m.provider] ??= []).push(m);
    return acc;
  }, {});

  return (
    <div className="p-4" style={{ borderTop: "1px solid var(--border)" }}>
      {/* Model selector pill */}
      {models.length > 0 && (
        <div className="relative mb-2" ref={menuRef}>
          <button
            type="button"
            onClick={() => setShowModelMenu((v) => !v)}
            className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs transition-colors hover:bg-black/[0.05]"
            style={{
              background: "var(--muted)",
              border: "1px solid var(--outline-variant)",
              color: "var(--on-surface-variant)",
            }}
          >
            <span className="max-w-[180px] truncate">{selectedLabel}</span>
            <ChevronDown className="size-3" />
          </button>

          {showModelMenu && (
            <>
              {/* Backdrop */}
              <div
                className="fixed inset-0 z-40"
                onClick={() => setShowModelMenu(false)}
              />
              {/* Dropdown */}
              <div
                className="absolute bottom-full left-0 z-50 mb-1 min-w-[220px] rounded-xl py-1 shadow-xl"
                style={{
                  background: "var(--card)",
                  border: "1px solid var(--outline-variant)",
                  boxShadow: "var(--shadow-popover)",
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
                          setShowModelMenu(false);
                        }}
                        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors hover:bg-black/[0.05]"
                        style={{
                          color:
                            m.model_id === selectedModel
                              ? "var(--primary-dim)"
                              : "var(--muted-foreground)",
                        }}
                      >
                        {m.model_id === selectedModel && (
                          <span className="text-[10px]">&#10003;</span>
                        )}
                        <span className={m.model_id === selectedModel ? "" : "ml-4"}>
                          {m.label}
                        </span>
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      <div
        className="flex items-end gap-3 rounded-2xl px-4 py-3"
        style={{
          background: "var(--muted)",
          border: "1px solid var(--outline-variant)",
        }}
      >
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
          className="max-h-[200px] min-h-[40px] flex-1 resize-none bg-transparent py-2 text-sm outline-none placeholder:text-outline-variant"
        />

        {isStreaming ? (
          <button
            onClick={onStop}
            className="shrink-0 w-10 h-10 rounded-xl flex items-center justify-center transition-all hover:opacity-80"
            style={{ background: "color-mix(in srgb, var(--destructive) 20%, transparent)", color: "var(--destructive)" }}
          >
            <Square className="size-4" />
          </button>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={!input.trim() || disabled}
            className="shrink-0 w-10 h-10 rounded-xl flex items-center justify-center text-white transition-all hover:opacity-90 disabled:opacity-30"
            style={{ background: "var(--primary)" }}
          >
            <Send className="size-4" />
          </button>
        )}
      </div>
    </div>
  );
}
