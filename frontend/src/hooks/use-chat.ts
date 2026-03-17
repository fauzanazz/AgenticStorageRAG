"use client";

import { useState, useCallback, useRef } from "react";
import { apiClient } from "@/lib/api-client";
import type { ChatSession, ChatMessage, Citation } from "@/types/chat";

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
      // Backend returns `created_at`; frontend ChatMessage uses `timestamp`
      const data = await apiClient.get<
        (Omit<ChatMessage, "timestamp"> & { created_at: string })[]
      >(`/chat/conversations/${conversationId}/messages`);
      setMessages(
        data.map(({ created_at, ...rest }) => ({
          ...rest,
          citations: rest.citations ?? [],
          timestamp: created_at,
        }))
      );
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

      // Create abort controller for this stream
      const controller = new AbortController();
      abortRef.current = controller;

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
          "/chat/stream",
          {
            message: content,
            conversation_id: conversationId || activeConversation?.id,
          },
          (sseEvent) => {
            switch (sseEvent.event) {
              case "token":
                streamedContent += sseEvent.data;
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
                try {
                  const citation: Citation = JSON.parse(sseEvent.data);
                  citations.push(citation);
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
                } catch {
                  // Ignore malformed citation data
                }
                break;

              case "tool_call":
                // Tool calls are informational -- shown in UI as "thinking" indicators
                break;

              case "conversation_created":
                try {
                  const data = JSON.parse(sseEvent.data);
                  if (data.conversation_id) {
                    // Update active conversation with the backend-created ID
                    setActiveConversation((prev) =>
                      prev ? { ...prev, id: data.conversation_id } : prev
                    );
                    fetchConversations();
                  }
                } catch {
                  // Ignore parse errors
                }
                break;

              case "error":
                try {
                  const errData = JSON.parse(sseEvent.data);
                  setError(errData.error || "An error occurred");
                } catch {
                  setError(sseEvent.data || "An error occurred");
                }
                break;

              case "done":
                // Stream complete -- refresh conversations to get updated title
                fetchConversations();
                break;
            }
          },
          controller.signal,
        );
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          // User cancelled -- not an error
          return;
        }
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
        abortRef.current = null;
        setIsStreaming(false);
      }
    },
    [activeConversation, fetchConversations]
  );

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
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
