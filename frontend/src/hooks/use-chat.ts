"use client";

import { useState, useCallback, useRef } from "react";
import { apiClient } from "@/lib/api-client";
import type { ChatSession, ChatMessage, Citation } from "@/types/chat";

interface StreamEvent {
  type: "token" | "citation" | "tool_call" | "error" | "done";
  data?: string;
  citation?: Citation;
  tool?: string;
  conversation_id?: string;
}

export function useChat() {
  const [conversations, setConversations] = useState<ChatSession[]>([]);
  const [activeConversation, setActiveConversation] =
    useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetchConversations = useCallback(async () => {
    try {
      const data = await apiClient.get<ChatSession[]>("/chat/conversations");
      setConversations(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load conversations");
    }
  }, []);

  const fetchMessages = useCallback(async (conversationId: string) => {
    try {
      const data = await apiClient.get<ChatMessage[]>(
        `/chat/conversations/${conversationId}/messages`
      );
      setMessages(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load messages");
    }
  }, []);

  const createConversation = useCallback(async (title?: string) => {
    try {
      const data = await apiClient.post<ChatSession>("/chat/conversations", {
        title,
      });
      setConversations((prev) => [data, ...prev]);
      setActiveConversation(data);
      setMessages([]);
      return data;
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to create conversation"
      );
      return null;
    }
  }, []);

  const deleteConversation = useCallback(
    async (conversationId: string) => {
      try {
        await apiClient.delete(`/chat/conversations/${conversationId}`);
        setConversations((prev) =>
          prev.filter((c) => c.id !== conversationId)
        );
        if (activeConversation?.id === conversationId) {
          setActiveConversation(null);
          setMessages([]);
        }
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to delete conversation"
        );
      }
    },
    [activeConversation]
  );

  const sendMessage = useCallback(
    async (content: string, conversationId?: string) => {
      setIsStreaming(true);
      setError(null);

      // Add user message immediately
      const userMessage: ChatMessage = {
        id: `temp-${Date.now()}`,
        role: "user",
        content,
        citations: [],
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMessage]);

      // Create placeholder for assistant response
      const assistantMessage: ChatMessage = {
        id: `temp-assistant-${Date.now()}`,
        role: "assistant",
        content: "",
        citations: [],
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMessage]);

      try {
        let streamedContent = "";
        const citations: Citation[] = [];

        await apiClient.stream(
          "/chat/send",
          {
            message: content,
            conversation_id: conversationId || activeConversation?.id,
          },
          (chunk: string) => {
            try {
              const event: StreamEvent = JSON.parse(chunk);

              switch (event.type) {
                case "token":
                  streamedContent += event.data || "";
                  setMessages((prev) => {
                    const updated = [...prev];
                    const last = updated[updated.length - 1];
                    if (last.role === "assistant") {
                      updated[updated.length - 1] = {
                        ...last,
                        content: streamedContent,
                      };
                    }
                    return updated;
                  });
                  break;

                case "citation":
                  if (event.citation) {
                    citations.push(event.citation);
                    setMessages((prev) => {
                      const updated = [...prev];
                      const last = updated[updated.length - 1];
                      if (last.role === "assistant") {
                        updated[updated.length - 1] = {
                          ...last,
                          citations: [...citations],
                        };
                      }
                      return updated;
                    });
                  }
                  break;

                case "tool_call":
                  // Tool calls are informational -- shown in UI as "thinking" indicators
                  break;

                case "error":
                  setError(event.data || "An error occurred");
                  break;

                case "done":
                  if (event.conversation_id && !conversationId) {
                    // New conversation created by backend
                    fetchConversations();
                  }
                  break;
              }
            } catch {
              // Non-JSON chunk, treat as raw token
              streamedContent += chunk;
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last.role === "assistant") {
                  updated[updated.length - 1] = {
                    ...last,
                    content: streamedContent,
                  };
                }
                return updated;
              });
            }
          }
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to send message");
        // Remove the empty assistant placeholder on error
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last.role === "assistant" && !last.content) {
            updated.pop();
          }
          return updated;
        });
      } finally {
        setIsStreaming(false);
      }
    },
    [activeConversation, fetchConversations]
  );

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
    setIsStreaming(false);
  }, []);

  const selectConversation = useCallback(
    async (conversation: ChatSession) => {
      setActiveConversation(conversation);
      await fetchMessages(conversation.id);
    },
    [fetchMessages]
  );

  return {
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
  };
}
