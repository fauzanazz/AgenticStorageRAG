"use client";

import { useState, useRef, useCallback } from "react";
import { ArrowUp, Square } from "lucide-react";
import type { ModelOption } from "@/types/settings";
import type { ChatAttachment } from "@/types/chat";
import { AttachmentButton } from "@/components/chat/attachment-button";
import { AttachmentChip } from "@/components/chat/attachment-chip";
import { ModelSelectorDropdown } from "@/components/chat/model-selector-dropdown";

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
  const textareaRef = useRef<HTMLTextAreaElement>(null);
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
            <ModelSelectorDropdown
              models={models}
              selectedModel={selectedModel}
              onModelChange={onModelChange}
              enableThinking={enableThinking}
              onThinkingChange={onThinkingChange}
              supportsThinking={supportsThinking}
            />
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
