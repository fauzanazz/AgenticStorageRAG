"use client";

import { useState, useCallback, useRef } from "react";
import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { toast } from "sonner";
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
  MessageCreatedPayload,
  CitationPayload,
  ErrorPayload,
} from "@/types/chat";

// ── Query / mutation functions ─────────────────────────────────────────────

function fetchConversations(): Promise<ChatSession[]> {
  return apiClient.get<ChatSession[]>("/chat/conversations");
}

interface MessageFromAPI {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations?: Citation[];
  steps?: NarrativeStep[];
  tool_calls?: { tool_name: string; arguments?: Record<string, unknown>; result_summary?: string; duration_ms?: number; results?: Record<string, unknown>[] }[] | null;
  thinking_blocks?: string[] | null;
  created_at: string;
}

/** Mirrors backend TOOL_FRIENDLY_NAMES for reconstructed steps. */
const TOOL_FRIENDLY_NAMES: Record<string, string> = {
  hybrid_search: "Searching documents and knowledge graph",
  vector_search: "Searching documents",
  graph_search: "Searching knowledge graph",
};

function friendlyToolName(name: string): string {
  return TOOL_FRIENDLY_NAMES[name] ?? `Using ${name}`;
}

async function fetchMessages(conversationId: string): Promise<ChatMessage[]> {
  const data = await apiClient.get<MessageFromAPI[]>(
    `/chat/conversations/${conversationId}/messages`,
  );
  return data.map(({ created_at, tool_calls, thinking_blocks, ...rest }) => {
    // Reconstruct steps from persisted tool_calls and thinking_blocks
    const stepsFromToolCalls: NarrativeStep[] = (tool_calls ?? []).map((tc) => ({
      type: "tool_call" as const,
      tool_name: tc.tool_name,
      tool_label: friendlyToolName(tc.tool_name),
      tool_args: tc.arguments,
      tool_status: "done" as const,
      tool_summary: tc.result_summary,
      tool_duration_ms: tc.duration_ms,
      tool_results: tc.results as import("@/types/chat").ToolResultItem[],
    }));

    const stepsFromThinking: NarrativeStep[] = (thinking_blocks ?? []).map((text) => ({
      type: "thinking" as const,
      content: text,
    }));

    // Interleave: each thinking block preceded its tool calls in the
    // original stream, so place thinking[i] before the tool calls that
    // followed it. When counts don't match, append remaining steps.
    const reconstructedSteps: NarrativeStep[] = [];
    const maxLen = Math.max(stepsFromThinking.length, stepsFromToolCalls.length);
    for (let i = 0; i < maxLen; i++) {
      if (i < stepsFromThinking.length) reconstructedSteps.push(stepsFromThinking[i]);
      if (i < stepsFromToolCalls.length) reconstructedSteps.push(stepsFromToolCalls[i]);
    }

    return {
      ...rest,
      citations: rest.citations ?? [],
      steps: rest.steps?.length ? rest.steps : reconstructedSteps,
      timestamp: created_at,
    };
  });
}

// ── Hook ───────────────────────────────────────────────────────────────────

export function useChat(conversationId?: string) {
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

  // Sync active conversation from URL param when conversations load.
  const syncedConversationIdRef = useRef<string | undefined>(undefined);
  if (
    conversationId &&
    conversationId !== syncedConversationIdRef.current &&
    conversationsQuery.data
  ) {
    const match = conversationsQuery.data.find((c) => c.id === conversationId);
    if (match) {
      syncedConversationIdRef.current = conversationId;
      setActiveConversation(match);
    }
  }
  // Clear when navigating to /chat (no ID).
  if (!conversationId && syncedConversationIdRef.current) {
    syncedConversationIdRef.current = undefined;
    setActiveConversation(null);
    setMessages([]);
  }

  // ── Messages query (enabled only when a conversation is selected) ────────
  const messagesQuery = useQuery({
    queryKey: queryKeys.conversations.messages(activeConversation?.id ?? ""),
    queryFn: () => fetchMessages(activeConversation!.id),
    enabled: !!activeConversation,
  });

  // Keep local messages in sync with the cache when a conversation is loaded.
  // Render-time state adjustment (React-recommended pattern for derived state).
  const lastConversationIdRef = useRef<string | null>(null);
  if (messagesQuery.data && activeConversation?.id && activeConversation.id !== lastConversationIdRef.current) {
    lastConversationIdRef.current = activeConversation.id;
    setMessages(messagesQuery.data);
  }

  // ── Create conversation mutation ─────────────────────────────────────────
  const createMutation = useMutation<ChatSession, Error, string | undefined>({
    mutationFn: (title) =>
      apiClient.post<ChatSession>("/chat/conversations", { title }),
    onSuccess: (newConversation: ChatSession) => {
      // Prepend the new conversation to the cached list immediately.
      queryClient.setQueryData<ChatSession[]>(
        queryKeys.conversations.lists(),
        (prev: ChatSession[] | undefined) =>
          prev ? [newConversation, ...prev] : [newConversation]
      );
      setActiveConversation(newConversation);
      setMessages([]);
      lastConversationIdRef.current = newConversation.id;
    },
  });

  // ── Delete conversation mutation ─────────────────────────────────────────
  const deleteMutation = useMutation<void, Error, string, { previous: ChatSession[] | undefined }>({
    mutationFn: (conversationId: string) =>
      apiClient.delete<void>(`/chat/conversations/${conversationId}`),
    onMutate: async (conversationId: string) => {
      // Cancel any in-flight refetch so it doesn't overwrite our optimistic update.
      await queryClient.cancelQueries({ queryKey: queryKeys.conversations.lists() });
      const previous = queryClient.getQueryData<ChatSession[]>(queryKeys.conversations.lists());
      // Optimistically remove from cache.
      queryClient.setQueryData<ChatSession[]>(
        queryKeys.conversations.lists(),
        (prev: ChatSession[] | undefined) =>
          prev ? prev.filter((c: ChatSession) => c.id !== conversationId) : []
      );
      if (activeConversation?.id === conversationId) {
        setActiveConversation(null);
        setMessages([]);
        lastConversationIdRef.current = null;
      }
      return { previous };
    },
    onSuccess: (_: void, conversationId: string) => {
      queryClient.removeQueries({
        queryKey: queryKeys.conversations.messages(conversationId),
      });
      toast.success("Conversation deleted");
    },
    onError: (err: Error, _conversationId: string, context) => {
      // Roll back the optimistic update.
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.conversations.lists(), context.previous);
      }
      toast.error(err.message || "Failed to delete conversation");
    },
  });

  // ── SSE streaming (remains imperative — TanStack Query doesn't model SSE) ─
  const sendMessage = useCallback(
    async (content: string, conversationId?: string, model?: string) => {
      setIsStreaming(true);
      setError(null);

      const controller = new AbortController();
      abortRef.current = controller;

      const tempUserId = `temp-user-${Date.now()}`;
      const tempAssistantId = `temp-assistant-${Date.now()}`;

      const userMessage: ChatMessage = {
        id: tempUserId,
        role: "user",
        content,
        citations: [],
        steps: [],
        timestamp: new Date().toISOString(),
      };
      const assistantMessage: ChatMessage = {
        id: tempAssistantId,
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
                          tool_results: data.results,
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

              case "message_created": {
                try {
                  const data: MessageCreatedPayload = JSON.parse(sseEvent.data);
                  const tempId = data.role === "user" ? tempUserId : tempAssistantId;
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === tempId ? { ...m, id: data.message_id } : m
                    )
                  );
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
    deleteConversation: (id: string) => deleteMutation.mutate(id),
    sendMessage,
    stopStreaming,

    // legacy
    fetchConversations: refreshConversations,
    setError,
  };
}
