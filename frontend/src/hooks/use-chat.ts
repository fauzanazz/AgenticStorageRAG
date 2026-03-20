"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type {
  ChatSession,
  ChatMessage,
  Citation,
  NarrativeStep,
  ToolStartPayload,
  ToolResultPayload,
  ConversationCreatedPayload,
  CitationPayload,
  ErrorPayload,
} from "@/types/chat";

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
    steps: rest.steps ?? [],
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
  const pendingContentRef = useRef("");
  const rafIdRef = useRef<number | null>(null);

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
  });

  // Keep local messages in sync with the cache when a conversation is loaded.
  // We only reset local state when the conversation changes (not on every re-render).
  const lastConversationIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (messagesQuery.data && activeConversation?.id !== lastConversationIdRef.current) {
      lastConversationIdRef.current = activeConversation?.id ?? null;
      setMessages(messagesQuery.data);
    }
  }, [messagesQuery.data, activeConversation?.id]);

  // ── Create conversation mutation ─────────────────────────────────────────
  const createMutation = useMutation<ChatSession, Error, string | undefined>({
    mutationFn: (title) =>
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
  const deleteMutation = useMutation<void, Error, string>({
    mutationFn: (conversationId) =>
      apiClient.delete<void>(`/chat/conversations/${conversationId}`),
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
    async (content: string, conversationId?: string, model?: string) => {
      setIsStreaming(true);
      setError(null);

      const controller = new AbortController();
      abortRef.current = controller;

      const userMessage: ChatMessage = {
        id: `temp-${Date.now()}`,
        role: "user",
        content,
        citations: [],
        steps: [],
        timestamp: new Date().toISOString(),
      };
      const assistantMessage: ChatMessage = {
        id: `temp-assistant-${Date.now()}`,
        role: "assistant",
        content: "",
        citations: [],
        steps: [],
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMessage, assistantMessage]);

      let streamedContent = "";
      try {
        const citations: Citation[] = [];

        await apiClient.stream(
          "/chat/stream",
          {
            message: content,
            conversation_id: conversationId ?? activeConversation?.id,
            ...(model ? { model } : {}),
          },
          (sseEvent) => {
            switch (sseEvent.event) {
              case "thinking": {
                // Full thinking text for this iteration (emitted after
                // the backend confirms tool_calls are present).
                const text = sseEvent.data;
                if (!text) break;
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last.role !== "assistant") return prev;
                  const step: NarrativeStep = { type: "thinking", content: text };
                  updated[updated.length - 1] = {
                    ...last,
                    steps: [...last.steps, step],
                  };
                  return updated;
                });
                break;
              }

              case "tool_start": {
                try {
                  const data: ToolStartPayload = JSON.parse(sseEvent.data);
                  const step: NarrativeStep = {
                    type: "tool_call",
                    tool_name: data.tool_name,
                    tool_label: data.tool_label,
                    tool_args: data.arguments,
                    tool_status: "running",
                  };
                  setMessages((prev) => {
                    const updated = [...prev];
                    const last = updated[updated.length - 1];
                    if (last.role !== "assistant") return prev;
                    updated[updated.length - 1] = {
                      ...last,
                      steps: [...last.steps, step],
                    };
                    return updated;
                  });
                } catch {
                  // Ignore malformed data
                }
                break;
              }

              case "tool_result": {
                try {
                  const data: ToolResultPayload = JSON.parse(sseEvent.data);
                  setMessages((prev) => {
                    const updated = [...prev];
                    const last = updated[updated.length - 1];
                    if (last.role !== "assistant") return prev;
                    const steps = [...last.steps];
                    for (let i = steps.length - 1; i >= 0; i--) {
                      if (steps[i].type === "tool_call" && steps[i].tool_status === "running") {
                        steps[i] = {
                          ...steps[i],
                          tool_status: data.error ? "error" : "done",
                          tool_summary: data.summary,
                          tool_count: data.count,
                          tool_duration_ms: data.duration_ms,
                        };
                        break;
                      }
                    }
                    updated[updated.length - 1] = { ...last, steps };
                    return updated;
                  });
                } catch {
                  // Ignore malformed data
                }
                break;
              }

              case "token": {
                // Final answer content — set directly on message.content
                streamedContent += sseEvent.data;
                pendingContentRef.current = streamedContent;
                if (rafIdRef.current === null) {
                  rafIdRef.current = requestAnimationFrame(() => {
                    const content = pendingContentRef.current;
                    rafIdRef.current = null;
                    setMessages((prev) => {
                      const updated = [...prev];
                      const last = updated[updated.length - 1];
                      if (last.role === "assistant") {
                        updated[updated.length - 1] = { ...last, content };
                      }
                      return updated;
                    });
                  });
                }
                break;
              }

              case "citation": {
                try {
                  const raw: CitationPayload = JSON.parse(sseEvent.data);
                  const citation: Citation = {
                    document_id: raw.document_id ?? "",
                    document_name: raw.document_name ?? raw.entity_name ?? "Source",
                    chunk_text: raw.content_snippet ?? "",
                    page_number: raw.page_number ?? undefined,
                    relevance_score: raw.relevance_score ?? 0,
                    source_url: raw.source_url ?? null,
                  };
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
              }

              case "tool_call":
                // Legacy event from old backend — ignore
                break;

              case "conversation_created": {
                try {
                  const data: ConversationCreatedPayload = JSON.parse(sseEvent.data);
                  if (data.conversation_id) {
                    setActiveConversation((prev) =>
                      prev ? { ...prev, id: data.conversation_id } : prev
                    );
                    queryClient.invalidateQueries({
                      queryKey: queryKeys.conversations.lists(),
                    });
                  }
                } catch {
                  // Ignore parse errors
                }
                break;
              }

              case "error": {
                try {
                  const errData: ErrorPayload = JSON.parse(sseEvent.data);
                  setError(errData.error || "An error occurred");
                } catch {
                  setError(sseEvent.data || "An error occurred");
                }
                break;
              }

              case "done": {
                queryClient.invalidateQueries({
                  queryKey: queryKeys.conversations.lists(),
                });
                if (activeConversation?.id) {
                  queryClient.invalidateQueries({
                    queryKey: queryKeys.conversations.messages(
                      activeConversation.id
                    ),
                  });
                }
                break;
              }
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
        if (rafIdRef.current !== null) {
          cancelAnimationFrame(rafIdRef.current);
          rafIdRef.current = null;
        }
        // Final flush — ensure content is set from streamed data
        if (streamedContent) {
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last.role === "assistant" && !last.content) {
              updated[updated.length - 1] = {
                ...last,
                content: streamedContent,
              };
            }
            return updated;
          });
        }
        pendingContentRef.current = "";
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
