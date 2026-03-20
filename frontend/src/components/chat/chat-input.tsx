"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { ArrowUp, Brain, ChevronDown, Square } from "lucide-react";
import type { ModelOption } from "@/types/settings";
import type { ChatAttachment } from "@/types/chat";
import { AttachmentButton } from "@/components/chat/attachment-button";
import { AttachmentChip } from "@/components/chat/attachment-chip";

const EMPTY_MODELS: ModelOption[] = [];
const EMPTY_ATTACHMENTS: ChatAttachment[] = [];
const PASTE_THRESHOLD = 500;

interface ChatInputProps {
  onSend: (message: string) => void;
  onStop?: () => void;
  isStreaming?: boolean;
  disabled?: boolean;
  placeholder?: string;
  models?: ModelOption[];
  selectedModel: string | null;
  onModelChange: (modelId: string) => void;
  enableThinking?: boolean;
  onThinkingChange?: (enabled: boolean) => void;
  supportsThinking?: boolean;
  attachments?: ChatAttachment[];
  onAddAttachment?: (file: File) => void;
  onBrowseDrive?: () => void;
  onRemoveAttachment?: (id: string) => void;
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
  enableThinking = false,
  onThinkingChange,
  supportsThinking = false,
  attachments = EMPTY_ATTACHMENTS,
  onAddAttachment,
  onBrowseDrive,
  onRemoveAttachment,
}: ChatInputProps) {
  const [input, setInput] = useState("");
  const [showModelMenu, setShowModelMenu] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const pasteCountRef = useRef(0);

  const handleSubmit = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed && attachments.length === 0) return;
    if (disabled || isStreaming) return;
    onSend(trimmed);
    setInput("");
    pasteCountRef.current = 0;
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [input, attachments.length, disabled, isStreaming, onSend]);

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

  const handlePaste = useCallback(
    (e: React.ClipboardEvent) => {
      if (!onAddAttachment) return;

      const text = e.clipboardData.getData("text/plain");
      if (text.length >= PASTE_THRESHOLD) {
        e.preventDefault();
        pasteCountRef.current += 1;
        const suffix = pasteCountRef.current > 1 ? `-${pasteCountRef.current}` : "";
        const filename = `pasted-text${suffix}.txt`;
        const file = new File([text], filename, { type: "text/plain" });
        onAddAttachment(file);
      }
    },
    [onAddAttachment]
  );

  const handleUploadFiles = useCallback(
    (files: FileList) => {
      if (!onAddAttachment) return;
      for (let i = 0; i < files.length; i++) {
        onAddAttachment(files[i]);
      }
    },
    [onAddAttachment]
  );

  // Close dropdown on outside click
  useEffect(() => {
    if (!showModelMenu) return;
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowModelMenu(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [showModelMenu]);

  const selectedLabel =
    models.find((m) => m.model_id === selectedModel)?.label ?? "Select model";

  // Group models by provider
  const grouped = models.reduce<Record<string, ModelOption[]>>((acc, m) => {
    (acc[m.provider] ??= []).push(m);
    return acc;
  }, {});

  const hasAttachments = attachments.length > 0;
  const canSend = (input.trim() || attachments.length > 0) && !disabled && !isStreaming;

  return (
    <div className="px-4 pb-4 pt-2">
      <div
        className="mx-auto max-w-3xl rounded-[20px] transition-shadow"
        style={{
          background: "var(--muted)",
          boxShadow: "0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)",
        }}
      >
        {/* Attachment chips */}
        {hasAttachments && (
          <div className="flex flex-wrap gap-1.5 px-4 pt-3">
            {attachments.map((a) => (
              <AttachmentChip
                key={a.id}
                attachment={a}
                onRemove={onRemoveAttachment ?? (() => {})}
              />
            ))}
          </div>
        )}

        {/* Textarea */}
        <div className="flex items-start gap-2 px-4 pt-3">
          {onAddAttachment && (
            <div className="pt-1.5">
              <AttachmentButton
                onUploadFiles={handleUploadFiles}
                onBrowseDrive={onBrowseDrive ?? (() => {})}
                disabled={isStreaming}
                attachmentCount={attachments.length}
              />
            </div>
          )}
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onInput={handleInput}
            onPaste={handlePaste}
            placeholder={placeholder}
            disabled={disabled}
            rows={1}
            aria-label="Chat message"
            className="max-h-[200px] min-h-[44px] flex-1 resize-none bg-transparent py-2 text-sm leading-relaxed outline-none placeholder:text-outline-variant"
          />
        </div>

        {/* Bottom toolbar — inside the composer */}
        <div className="flex items-center justify-between px-3 pb-3 pt-1">
          {/* Left: model selector */}
          {models.length > 0 && (
            <div className="relative" ref={menuRef}>
              <button
                type="button"
                onClick={() => setShowModelMenu((v) => !v)}
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

              {/* Model dropdown with thinking toggle */}
              {showModelMenu && (
                <div
                  className="absolute bottom-full left-0 z-50 mb-1.5 min-w-[240px] rounded-xl py-1"
                  style={{
                    background: "var(--card)",
                    boxShadow:
                      "0 4px 6px -1px rgba(0,0,0,0.07), 0 10px 15px -3px rgba(0,0,0,0.1)",
                    border: "1px solid var(--outline-variant)",
                  }}
                >
                  {/* Model groups */}
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

                  {/* Extended thinking toggle — at the bottom */}
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
                        {/* Toggle switch */}
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
          )}

          {/* Right: send / stop button */}
          <div className="ml-auto">
            {isStreaming ? (
              <button
                onClick={onStop}
                className="flex h-8 w-8 items-center justify-center rounded-full transition-all hover:opacity-80"
                style={{
                  background:
                    "color-mix(in srgb, var(--destructive) 15%, transparent)",
                  color: "var(--destructive)",
                }}
              >
                <Square className="size-3.5" />
              </button>
            ) : (
              <button
                onClick={handleSubmit}
                disabled={!canSend}
                className="flex h-8 w-8 items-center justify-center rounded-full text-white transition-all hover:opacity-90 disabled:opacity-30"
                style={{
                  background: canSend
                    ? "var(--primary)"
                    : "var(--surface-container-high, #e4e4e7)",
                  color: canSend ? "white" : "var(--outline)",
                }}
              >
                <ArrowUp className="size-4" strokeWidth={2.5} />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
