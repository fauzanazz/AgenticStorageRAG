"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { MessageBubble } from "@/components/chat/message-bubble";
import { ChatInput } from "@/components/chat/chat-input";
import { ConversationList } from "@/components/chat/conversation-list";
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
    createConversation,
    deleteConversation,
    sendMessage,
    stopStreaming,
    setError,
  } = useChat(conversationId);

  const { settings, availableModels } = useModelSettings();

  const [showSidebar, setShowSidebar] = useState(false);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Sync selectedModel from settings (render-time, no useEffect needed)
  if (settings?.chat_model && !selectedModel) {
    setSelectedModel(settings.chat_model);
  }

  // Navigate to the conversation URL when backend creates a new conversation during streaming.
  const lastNavigatedIdRef = useRef<string | undefined>(conversationId);
  useEffect(() => {
    if (
      activeConversation?.id &&
      activeConversation.id !== lastNavigatedIdRef.current &&
      activeConversation.id !== conversationId
    ) {
      lastNavigatedIdRef.current = activeConversation.id;
      router.replace(`/chat/${activeConversation.id}`);
    }
  }, [activeConversation?.id, conversationId, router]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async (content: string) => {
    if (!activeConversation) {
      await createConversation();
    }
    sendMessage(content, undefined, selectedModel ?? undefined);
  };

  const handleNewChat = () => {
    router.push("/chat");
    setShowSidebar(false);
  };

  const handleSelectConversation = (conv: { id: string }) => {
    router.push(`/chat/${conv.id}`);
    setShowSidebar(false);
  };

  const handleDeleteConversation = (id: string) => {
    deleteConversation(id);
    if (activeConversation?.id === id) {
      router.replace("/chat");
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

      {/* Main chat area */}
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
        <div className="flex-1 overflow-y-auto px-4 py-6">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-4">
              <div
                className="flex h-16 w-16 items-center justify-center rounded-2xl text-2xl font-bold text-white"
                style={{ background: "var(--primary)" }}
              >
                D
              </div>
              <div className="text-center">
                <h3 className="text-lg font-semibold">DingDong RAG</h3>
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
              {messages.map((msg, i) => (
                <MessageBubble
                  key={msg.id}
                  message={msg}
                  isStreaming={
                    isStreaming &&
                    i === messages.length - 1 &&
                    msg.role === "assistant"
                  }
                />
              ))}
              <div ref={messagesEndRef} />
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
          onModelChange={setSelectedModel}
        />
      </div>
    </div>
  );
}
