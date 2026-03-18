"use client";

import { useState, useCallback, useRef } from "react";
import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type { ChatSession, ChatMessage, Citation } from "@/types/chat";

// ── Query / mutation functions ─────────────────────────────────────────────

function fetchConversations(): Promise<ChatSession[]> {
  return apiClient.get<ChatSession[]>("/chat/conversations");
}

async function fetchMessages(conversationId: string): Promise<ChatMessage[]> {
  const data = await apiClient.get<
    (Omit<ChatMessage, "timestamp"> & { created_at: string })[]
  >(`/chat/conversations/${conversationId}/messages`);
  return data.map(({ created_at, ...rest }) => ({
    ...rest,
    citations: rest.citations ?? [],
    timestamp: created_at,
  }));
}

// ── Hook ───────────────────────────────────────────────────────────────────

export function useChat() {
  const queryClient = useQueryClient();

  // Active conversation is local UI state (not a server resource by itself).
  const [activeConversation, setActiveConversation] =
    useState<ChatSession | null>(null);

  // Streaming messages are kept in local state because SSE is push-based
  // and not a typical query/cache pattern.
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // ── Conversations query ──────────────────────────────────────────────────
  const conversationsQuery = useQuery({
    queryKey: queryKeys.conversations.lists(),
    queryFn: fetchConversations,
  });

  // ── Messages query (enabled only when a conversation is selected) ────────
  const messagesQuery = useQuery({
    queryKey: queryKeys.conversations.messages(activeConversation?.id ?? ""),
    queryFn: () => fetchMessages(activeConversation!.id),
    enabled: !!activeConversation,
    // Sync fetched messages into local state so streaming can append to them.
    select: (data) => data,
  });

  // Keep local messages in sync with the cache when a conversation is loaded.
  // We only reset local state when the conversation changes (not on every re-render).
  const lastConversationIdRef = useRef<string | null>(null);
  if (
    messagesQuery.data &&
    activeConversation?.id !== lastConversationIdRef.current
  ) {
    lastConversationIdRef.current = activeConversation?.id ?? null;
    setMessages(messagesQuery.data);
  }

  // ── Create conversation mutation ─────────────────────────────────────────
  const createMutation = useMutation({
    mutationFn: (title?: string) =>
      apiClient.post<ChatSession>("/chat/conversations", { title }),
    onSuccess: (newConversation) => {
      // Prepend the new conversation to the cached list immediately.
      queryClient.setQueryData<ChatSession[]>(
        queryKeys.conversations.lists(),
        (prev) => (prev ? [newConversation, ...prev] : [newConversation])
      );
      setActiveConversation(newConversation);
      setMessages([]);
      lastConversationIdRef.current = newConversation.id;
    },
  });

  // ── Delete conversation mutation ─────────────────────────────────────────
  const deleteMutation = useMutation({
    mutationFn: (conversationId: string) =>
      apiClient.delete(`/chat/conversations/${conversationId}`),
    onSuccess: (_, conversationId) => {
      // Remove from cache immediately — no stale key.
      queryClient.setQueryData<ChatSession[]>(
        queryKeys.conversations.lists(),
        (prev) => (prev ? prev.filter((c) => c.id !== conversationId) : [])
      );
      // Remove the messages cache entry for this conversation.
      queryClient.removeQueries({
        queryKey: queryKeys.conversations.messages(conversationId),
      });
      if (activeConversation?.id === conversationId) {
        setActiveConversation(null);
        setMessages([]);
        lastConversationIdRef.current = null;
      }
    },
  });

  // ── SSE streaming (remains imperative — TanStack Query doesn't model SSE) ─
  const sendMessage = useCallback(
    async (content: string, conversationId?: string) => {
      setIsStreaming(true);
      setError(null);

      const controller = new AbortController();
      abortRef.current = controller;

      const userMessage: ChatMessage = {
        id: `temp-${Date.now()}`,
        role: "user",
        content,
        citations: [],
        timestamp: new Date().toISOString(),
      };
      const assistantMessage: ChatMessage = {
        id: `temp-assistant-${Date.now()}`,
        role: "assistant",
        content: "",
        citations: [],
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMessage, assistantMessage]);

      try {
        let streamedContent = "";
        const citations: Citation[] = [];

        await apiClient.stream(
          "/chat/stream",
          {
            message: content,
            conversation_id: conversationId ?? activeConversation?.id,
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
                break;

              case "conversation_created":
                try {
                  const data = JSON.parse(sseEvent.data);
                  if (data.conversation_id) {
                    setActiveConversation((prev) =>
                      prev ? { ...prev, id: data.conversation_id } : prev
                    );
                    // Refresh the conversations list to include the new one.
                    queryClient.invalidateQueries({
                      queryKey: queryKeys.conversations.lists(),
                    });
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
                // Invalidate conversations list so updated titles appear.
                queryClient.invalidateQueries({
                  queryKey: queryKeys.conversations.lists(),
                });
                // Invalidate message cache for this conversation so a hard
                // refresh will load the persisted messages from the server.
                if (activeConversation?.id) {
                  queryClient.invalidateQueries({
                    queryKey: queryKeys.conversations.messages(
                      activeConversation.id
                    ),
                  });
                }
                break;
            }
          },
          controller.signal
        );
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "Failed to send message");
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last.role === "assistant" && !last.content) updated.pop();
          return updated;
        });
      } finally {
        abortRef.current = null;
        setIsStreaming(false);
      }
    },
    [activeConversation, queryClient]
  );

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setIsStreaming(false);
  }, []);

  const selectConversation = useCallback(
    async (conversation: ChatSession) => {
      setActiveConversation(conversation);
      lastConversationIdRef.current = null; // force sync on next render
    },
    []
  );

  // Legacy imperative refresh — kept for backward-compat with callers.
  const refreshConversations = useCallback(
    () =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.conversations.lists(),
      }),
    [queryClient]
  );

  return {
    conversations: conversationsQuery.data ?? [],
    activeConversation,
    messages,
    isStreaming,
    error,

    // mutations
    createConversation: (title?: string) => createMutation.mutateAsync(title),
    deleteConversation: (id: string) => deleteMutation.mutateAsync(id),
    sendMessage,
    stopStreaming,
    selectConversation,

    // legacy
    fetchConversations: refreshConversations,
    setError,
  };
}
