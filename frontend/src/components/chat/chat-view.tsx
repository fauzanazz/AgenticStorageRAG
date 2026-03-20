"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { MessageBubble } from "@/components/chat/message-bubble";
import { ChatInput } from "@/components/chat/chat-input";
import { ConversationList } from "@/components/chat/conversation-list";
import { ArtifactPanel } from "@/components/chat/artifact-panel";
import { ArtifactCard } from "@/components/chat/artifact-card";
import { DriveFileBrowser } from "@/components/chat/drive-file-browser";
import { useChat } from "@/hooks/use-chat";
import { useModelSettings } from "@/hooks/use-model-settings";

interface ChatViewProps {
  conversationId?: string;
}

export function ChatView({ conversationId }: ChatViewProps) {
  const router = useRouter();

  const {
    conversations,
    activeConversation,
    messages,
    isStreaming,
    error,
    artifacts,
    activeArtifactId,
    setActiveArtifactId,
    createConversation,
    deleteConversation,
    sendMessage,
    stopStreaming,
    resetChat,
    setError,
    attachments,
    addAttachment,
    addDriveAttachments,
    removeAttachment,
  } = useChat(conversationId);

  const activeArtifact = activeArtifactId ? artifacts.get(activeArtifactId) ?? null : null;

  const { settings, availableModels, defaultModel } = useModelSettings();

  const [showSidebar, setShowSidebar] = useState(false);
  const [userSelectedModel, setUserSelectedModel] = useState<string | null>(null);
  const [enableThinking, setEnableThinking] = useState(false);
  const [showDriveBrowser, setShowDriveBrowser] = useState(false);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const hasScrolledRef = useRef<string | undefined>(undefined);

  // --- Resizable artifact panel ---
  const MIN_PANEL_WIDTH = 320;
  const [artifactWidth, setArtifactWidth] = useState(480);

  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = artifactWidth;

    const onMouseMove = (ev: MouseEvent) => {
      const maxWidth = window.innerWidth * 0.4;
      const delta = startX - ev.clientX; // dragging left = wider
      const next = Math.min(maxWidth, Math.max(MIN_PANEL_WIDTH, startWidth + delta));
      setArtifactWidth(next);
    };

    const onMouseUp = () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  }, [artifactWidth]);

  // Resolve selected model: user's explicit pick > saved setting > provider-aware default
  const selectedModel = useMemo(() => {
    if (userSelectedModel && availableModels.some((m) => m.model_id === userSelectedModel)) {
      return userSelectedModel;
    }
    const saved = settings?.chat_model;
    if (saved && availableModels.some((m) => m.model_id === saved)) {
      return saved;
    }
    return defaultModel;
  }, [userSelectedModel, settings?.chat_model, availableModels, defaultModel]);

  // Update the URL when backend creates a new conversation during streaming.
  // Uses history API to avoid a full page navigation / re-render.
  const lastNavigatedIdRef = useRef<string | undefined>(conversationId);
  useEffect(() => {
    if (
      activeConversation?.id &&
      activeConversation.id !== lastNavigatedIdRef.current &&
      activeConversation.id !== conversationId
    ) {
      lastNavigatedIdRef.current = activeConversation.id;
      window.history.replaceState(null, "", `/chat/${activeConversation.id}`);
    }
  }, [activeConversation?.id, conversationId]);


  // Scroll to bottom once when opening a history conversation
  useEffect(() => {
    if (
      conversationId &&
      conversationId !== hasScrolledRef.current &&
      messages.length > 0 &&
      messagesContainerRef.current
    ) {
      hasScrolledRef.current = conversationId;
      messagesContainerRef.current.scrollTop =
        messagesContainerRef.current.scrollHeight;
    }
  }, [conversationId, messages]);

  const supportsThinking = availableModels?.find(
    (m) => m.model_id === selectedModel
  )?.supports_thinking ?? false;

  const handleSend = async (content: string) => {
    if (!activeConversation) {
      await createConversation();
    }
    sendMessage(content, undefined, selectedModel ?? undefined, enableThinking);
  };

  const handleNewChat = () => {
    resetChat();
    lastNavigatedIdRef.current = undefined;
    window.history.pushState(null, "", "/chat");
    setShowSidebar(false);
  };

  const handleSelectConversation = (conv: { id: string }) => {
    router.push(`/chat/${conv.id}`);
    setShowSidebar(false);
  };

  const handleDeleteConversation = (id: string) => {
    deleteConversation(id);
    if (activeConversation?.id === id) {
      lastNavigatedIdRef.current = undefined;
      window.history.replaceState(null, "", "/chat");
    }
  };

  return (
    <div className="flex flex-1 min-h-0 overflow-hidden">
      {/* Conversation sidebar — on mobile: fixed below the 64px top nav; on desktop: relative */}
      <div
        className={`fixed top-16 bottom-0 left-0 z-40 w-72 md:relative md:top-auto md:bottom-auto md:z-auto transition-transform duration-200 ${
          showSidebar ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        }`}
        style={{
          background: "var(--card)",
          borderRight: "1px solid var(--border)",
        }}
      >
        <ConversationList
          conversations={conversations}
          activeId={activeConversation?.id}
          onSelect={handleSelectConversation}
          onDelete={handleDeleteConversation}
          onNew={handleNewChat}
        />
      </div>

      {/* Overlay for mobile sidebar — sits below top nav (top-16) */}
      {showSidebar && (
        <div
          role="button"
          tabIndex={0}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " " || e.key === "Escape") { e.preventDefault(); setShowSidebar(false); } }}
          className="fixed top-16 inset-x-0 bottom-0 z-30 md:hidden"
          style={{ background: "rgba(0,0,0,0.6)" }}
          onClick={() => setShowSidebar(false)}
        />
      )}

      {/* Main content area: chat + optional artifact panel */}
      <div className="flex flex-1 min-w-0">
        {/* Chat column */}
        <div className="flex flex-1 flex-col min-w-0">
          {/* Chat header */}
          <div
            className="flex items-center gap-3 px-4 py-3"
            style={{ borderBottom: "1px solid var(--border)" }}
          >
            <button
              className="md:hidden rounded-lg p-1.5 hover:bg-black/5"
              style={{ color: "var(--muted-foreground)" }}
              onClick={() => setShowSidebar(true)}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect width="18" height="18" x="3" y="3" rx="2" />
                <path d="M9 3v18" />
              </svg>
            </button>
            <h2 className="text-sm font-medium">
              {activeConversation?.title || "New Chat"}
            </h2>
          </div>

          {/* Messages area */}
          <div ref={messagesContainerRef} className="flex-1 overflow-y-auto px-4 py-6">
            {messages.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center gap-4">
                <div
                  className="flex h-16 w-16 items-center justify-center rounded-2xl text-2xl font-bold text-white"
                  style={{ background: "var(--primary)" }}
                >
                  D
                </div>
                <div className="text-center">
                  <h3 className="text-lg font-semibold">OpenRAG</h3>
                  <p className="mt-1 text-sm" style={{ color: "var(--muted-foreground)" }}>
                    Ask questions about your knowledge base.
                    <br />
                    I&apos;ll search the graph and documents to find answers.
                  </p>
                </div>
                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  {[
                    "What entities are in my knowledge graph?",
                    "Summarize the key relationships",
                    "What documents have been uploaded?",
                    "Find connections between topics",
                  ].map((suggestion) => (
                    <button
                      key={suggestion}
                      onClick={() => handleSend(suggestion)}
                      className="rounded-xl px-4 py-3 text-left text-sm transition-all hover:bg-black/[0.04]"
                      style={{
                        border: "1px solid var(--outline-variant)",
                        color: "var(--on-surface-variant)",
                      }}
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="mx-auto max-w-3xl space-y-4">
                {messages.map((msg, i) => {
                  // Find artifacts linked to this message by checking tool results
                  const messageArtifacts = Array.from(artifacts.values()).filter(
                    (a) => a.message_id === msg.id
                  );
                  return (
                    <div key={msg.id}>
                      <MessageBubble
                        message={msg}
                        isStreaming={
                          isStreaming &&
                          i === messages.length - 1 &&
                          msg.role === "assistant"
                        }
                      />
                      {/* Artifact cards for this message */}
                      {messageArtifacts.length > 0 && (
                        <div className="mt-2 space-y-2 ml-12">
                          {messageArtifacts.map((artifact) => (
                            <ArtifactCard
                              key={artifact.id}
                              title={artifact.title}
                              type={artifact.type}
                              onClick={() => setActiveArtifactId(artifact.id)}
                            />
                          ))}
                        </div>
                      )}
                      {/* Show artifact card during streaming when artifact_start fires */}
                      {isStreaming &&
                        i === messages.length - 1 &&
                        msg.role === "assistant" &&
                        activeArtifact &&
                        messageArtifacts.length === 0 && (
                          <div className="mt-2 ml-12">
                            <ArtifactCard
                              title={activeArtifact.title}
                              type={activeArtifact.type}
                              onClick={() => setActiveArtifactId(activeArtifact.id)}
                            />
                          </div>
                        )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Error banner */}
          {error && (
            <div
              className="mx-4 mb-2 flex items-center justify-between rounded-xl px-4 py-3 text-sm"
              style={{
                background: "var(--error-container)",
                border: "1px solid color-mix(in srgb, var(--destructive) 20%, transparent)",
                color: "var(--destructive)",
              }}
            >
              <span>{error}</span>
              <button
                onClick={() => setError(null)}
                className="ml-2 hover:opacity-70"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* Input */}
          <ChatInput
            onSend={handleSend}
            onStop={stopStreaming}
            isStreaming={isStreaming}
            models={availableModels}
            selectedModel={selectedModel}
            onModelChange={setUserSelectedModel}
            enableThinking={enableThinking}
            onThinkingChange={setEnableThinking}
            supportsThinking={supportsThinking}
            attachments={attachments}
            onAddAttachment={addAttachment}
            onBrowseDrive={() => setShowDriveBrowser(true)}
            onRemoveAttachment={removeAttachment}
          />

          {/* Drive file browser modal */}
          <DriveFileBrowser
            open={showDriveBrowser}
            onClose={() => setShowDriveBrowser(false)}
            onAttach={addDriveAttachments}
          />
        </div>

        {/* Artifact side panel — Claude-style */}
        {activeArtifact && (
          <>
            {/* Desktop: resizable side panel */}
            <div className="hidden md:flex shrink-0 relative" style={{ width: artifactWidth }}>
              {/* Drag handle */}
              <div
                className="absolute left-0 top-0 bottom-0 w-1 cursor-col-resize z-10 hover:bg-primary/30 active:bg-primary/40 transition-colors"
                onMouseDown={handleResizeStart}
              />
              <ArtifactPanel
                artifact={activeArtifact}
                isStreaming={isStreaming}
                onClose={() => setActiveArtifactId(null)}
              />
            </div>
            {/* Mobile: full-screen overlay */}
            <div className="fixed inset-0 z-50 flex flex-col md:hidden" style={{ background: "var(--background)" }}>
              <ArtifactPanel
                artifact={activeArtifact}
                isStreaming={isStreaming}
                onClose={() => setActiveArtifactId(null)}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
