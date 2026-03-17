"use client";

import { useEffect, useRef, useState } from "react";
import { MessageBubble } from "@/components/chat/message-bubble";
import { ChatInput } from "@/components/chat/chat-input";
import { ConversationList } from "@/components/chat/conversation-list";
import { useChat } from "@/hooks/use-chat";

export default function ChatPage() {
  const {
    conversations,
    activeConversation,
    messages,
    isStreaming,
    error,
    fetchConversations,
    createConversation,
    deleteConversation,
    sendMessage,
    stopStreaming,
    selectConversation,
    setError,
  } = useChat();

  const [showSidebar, setShowSidebar] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async (content: string) => {
    if (!activeConversation) {
      await createConversation();
    }
    sendMessage(content);
  };

  const handleNewChat = async () => {
    await createConversation();
    setShowSidebar(false);
  };

  return (
    <div className="flex flex-1 min-h-0 overflow-hidden">
      {/* Conversation sidebar — on mobile: fixed below the 56px header; on desktop: relative */}
      <div
        className={`fixed top-14 bottom-0 left-0 z-40 w-72 md:relative md:top-auto md:bottom-auto md:z-auto transition-transform duration-200 ${
          showSidebar ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        }`}
        style={{
          background: "rgba(255,255,255,0.02)",
          borderRight: "1px solid rgba(255,255,255,0.06)",
        }}
      >
        <ConversationList
          conversations={conversations}
          activeId={activeConversation?.id}
          onSelect={(conv) => {
            selectConversation(conv);
            setShowSidebar(false);
          }}
          onDelete={deleteConversation}
          onNew={handleNewChat}
        />
      </div>

      {/* Overlay for mobile sidebar — sits below header (top-14) */}
      {showSidebar && (
        <div
          className="fixed top-14 inset-x-0 bottom-0 z-30 md:hidden"
          style={{ background: "rgba(0,0,0,0.6)" }}
          onClick={() => setShowSidebar(false)}
        />
      )}

      {/* Main chat area */}
      <div className="flex flex-1 flex-col min-w-0">
        {/* Chat header */}
        <div
          className="flex items-center gap-3 px-4 py-3"
          style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}
        >
          <button
            className="md:hidden rounded-lg p-1.5 hover:bg-white/5"
            style={{ color: "rgba(255,255,255,0.5)" }}
            onClick={() => setShowSidebar(true)}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect width="18" height="18" x="3" y="3" rx="2" />
              <path d="M9 3v18" />
            </svg>
          </button>
          <h2 className="text-sm font-medium text-white">
            {activeConversation?.title || "New Chat"}
          </h2>
        </div>

        {/* Messages area */}
        <div className="flex-1 overflow-y-auto px-4 py-6">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-4">
              <div
                className="flex h-16 w-16 items-center justify-center rounded-2xl text-2xl font-bold text-white"
                style={{ background: "linear-gradient(135deg, #6366F1, #A855F7)" }}
              >
                D
              </div>
              <div className="text-center">
                <h3 className="text-lg font-semibold text-white">DingDong RAG</h3>
                <p className="mt-1 text-sm" style={{ color: "rgba(255,255,255,0.4)" }}>
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
                    className="rounded-xl px-4 py-3 text-left text-sm transition-all hover:bg-white/[0.04]"
                    style={{
                      border: "1px solid rgba(255,255,255,0.08)",
                      color: "rgba(255,255,255,0.6)",
                    }}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-4">
              {messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} />
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
              background: "rgba(239,68,68,0.1)",
              border: "1px solid rgba(239,68,68,0.2)",
              color: "#FCA5A5",
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
        />
      </div>
    </div>
  );
}
