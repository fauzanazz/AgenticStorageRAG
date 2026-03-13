"use client";

import { useEffect, useRef, useState } from "react";
import { MobileHeader } from "@/components/layout/mobile-header";
import { MessageBubble } from "@/components/chat/message-bubble";
import { ChatInput } from "@/components/chat/chat-input";
import { ConversationList } from "@/components/chat/conversation-list";
import { Button } from "@/components/ui/button";
import { useChat } from "@/hooks/use-chat";
import { cn } from "@/lib/utils";

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

  // Auto-scroll to bottom on new messages
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
    <>
      <MobileHeader title="Chat" />

      <div className="flex flex-1 overflow-hidden">
        {/* Conversation sidebar -- hidden on mobile by default */}
        <div
          className={cn(
            "bg-background border-r transition-all duration-200",
            "fixed inset-y-0 left-0 z-40 w-72 md:relative md:z-auto",
            showSidebar ? "translate-x-0" : "-translate-x-full md:translate-x-0"
          )}
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

        {/* Overlay for mobile sidebar */}
        {showSidebar && (
          <div
            className="bg-background/50 fixed inset-0 z-30 md:hidden"
            onClick={() => setShowSidebar(false)}
          />
        )}

        {/* Main chat area */}
        <div className="flex flex-1 flex-col">
          {/* Chat header */}
          <div className="flex items-center gap-2 border-b px-4 py-2">
            <Button
              variant="ghost"
              size="sm"
              className="md:hidden"
              onClick={() => setShowSidebar(true)}
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <rect width="18" height="18" x="3" y="3" rx="2" />
                <path d="M9 3v18" />
              </svg>
            </Button>
            <h2 className="text-sm font-medium">
              {activeConversation?.title || "New Chat"}
            </h2>
          </div>

          {/* Messages area */}
          <div className="flex-1 overflow-y-auto px-4 py-6">
            {messages.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center gap-4">
                <div className="bg-primary/10 text-primary flex h-16 w-16 items-center justify-center rounded-2xl text-2xl font-bold">
                  DD
                </div>
                <div className="text-center">
                  <h3 className="text-lg font-semibold">DingDong RAG</h3>
                  <p className="text-muted-foreground mt-1 text-sm">
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
                      className="hover:bg-muted rounded-xl border px-4 py-3 text-left text-sm transition-colors"
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
            <div className="bg-destructive/10 text-destructive border-destructive/20 mx-4 mb-2 flex items-center justify-between rounded-lg border px-3 py-2 text-sm">
              <span>{error}</span>
              <button
                onClick={() => setError(null)}
                className="hover:text-destructive/80 ml-2"
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
    </>
  );
}
