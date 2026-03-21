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
  Artifact,
  ArtifactStartPayload,
  ArtifactDeltaPayload,
  ArtifactEndPayload,
  ChatAttachment,
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
  generate_document: "Generating document",
  fetch_document: "Fetching full document",
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

async function fetchArtifacts(conversationId: string): Promise<Artifact[]> {
  return apiClient.get<Artifact[]>(
    `/chat/conversations/${conversationId}/artifacts`,
  );
}

// ── Hook ───────────────────────────────────────────────────────────────────

export function useChat(conversationId?: string, useClaudeCode = false) {
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

  // Artifact state
  const [artifacts, setArtifacts] = useState<Map<string, Artifact>>(new Map());
  const [activeArtifactId, setActiveArtifactId] = useState<string | null>(null);
  const pendingArtifactContentRef = useRef<Map<string, string>>(new Map());
  const artifactRafIdRef = useRef<number | null>(null);
  const currentAssistantIdRef = useRef<string>("");

  // Attachment state
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);

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
    setArtifacts(new Map());
    setActiveArtifactId(null);
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

  // ── Artifacts query (load persisted artifacts on conversation open) ──────
  const artifactsQuery = useQuery({
    queryKey: queryKeys.conversations.artifacts(activeConversation?.id ?? ""),
    queryFn: () => fetchArtifacts(activeConversation!.id),
    enabled: !!activeConversation,
  });

  const lastArtifactSyncIdRef = useRef<string | null>(null);
  if (artifactsQuery.data && activeConversation?.id && activeConversation.id !== lastArtifactSyncIdRef.current) {
    lastArtifactSyncIdRef.current = activeConversation.id;
    const map = new Map<string, Artifact>();
    for (const a of artifactsQuery.data) {
      map.set(a.id, a);
    }
    setArtifacts(map);
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

  // ── Attachment helpers ────────────────────────────────────────────────────
  const addAttachment = useCallback(async (file: File) => {
    const tempId = `temp-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const pending: ChatAttachment = {
      id: tempId,
      filename: file.name,
      size: file.size,
      mime_type: file.type || "application/octet-stream",
      status: "uploading",
    };
    setAttachments((prev) => [...prev, pending]);

    try {
      const formData = new FormData();
      formData.append("file", file);
      const result = await apiClient.upload<{
        id: string;
        filename: string;
        size: number;
        mime_type: string;
      }>("/chat/attachments", formData);

      setAttachments((prev) =>
        prev.map((a) =>
          a.id === tempId
            ? { ...a, id: result.id, status: "ready" as const }
            : a
        )
      );
    } catch (err) {
      setAttachments((prev) =>
        prev.map((a) =>
          a.id === tempId
            ? {
                ...a,
                status: "error" as const,
                error: err instanceof Error ? err.message : "Upload failed",
              }
            : a
        )
      );
    }
  }, []);

  const addDriveAttachments = useCallback(async (fileIds: string[]) => {
    const tempEntries: ChatAttachment[] = fileIds.map((fid) => ({
      id: `temp-drive-${fid}`,
      filename: `Drive file...`,
      size: 0,
      mime_type: "application/octet-stream",
      status: "uploading" as const,
    }));
    setAttachments((prev) => [...prev, ...tempEntries]);

    try {
      const results = await apiClient.post<
        { id: string; filename: string; size: number; mime_type: string }[]
      >("/chat/attachments/from-drive", { file_ids: fileIds });

      setAttachments((prev) => {
        const withoutTemp = prev.filter(
          (a) => !fileIds.some((fid) => a.id === `temp-drive-${fid}`)
        );
        return [
          ...withoutTemp,
          ...results.map((r) => ({
            ...r,
            status: "ready" as const,
          })),
        ];
      });
    } catch (err) {
      const tempIds = new Set(fileIds.map((fid) => `temp-drive-${fid}`));
      setAttachments((prev) =>
        prev.map((a) =>
          tempIds.has(a.id)
            ? {
                ...a,
                status: "error" as const,
                error:
                  err instanceof Error ? err.message : "Drive import failed",
              }
            : a
        )
      );
    }
  }, []);

  const removeAttachment = useCallback((id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  }, []);

  const clearAttachments = useCallback(() => {
    setAttachments([]);
  }, []);

  // ── SSE streaming (remains imperative — TanStack Query doesn't model SSE) ─
  const sendMessage = useCallback(
    async (content: string, conversationId?: string, model?: string, enableThinking?: boolean) => {
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
      currentAssistantIdRef.current = tempAssistantId;
      setMessages((prev) => [...prev, userMessage, assistantMessage]);
      // Close artifact panel when sending a new message
      setActiveArtifactId(null);

      const readyAttachmentIds = attachments
        .filter((a) => a.status === "ready")
        .map((a) => a.id);

      let streamedContent = "";
      try {
        const citations: Citation[] = [];

        const streamBody = {
          message: content,
          conversation_id: conversationId ?? activeConversation?.id,
          ...(model ? { model } : {}),
          ...(enableThinking ? { enable_thinking: true } : {}),
          ...(readyAttachmentIds.length > 0
            ? { attachment_ids: readyAttachmentIds }
            : {}),
        };

        const onEvent = (sseEvent: { event: string; data: string }) => {
            switch (sseEvent.event) {
              case "thinking": {
                // Real extended thinking from the API (e.g. Anthropic reasoning_content).
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

                  // Flush any accumulated text as a narration step before
                  // the tool call so interleaved ordering is preserved.
                  const flushedContent = streamedContent.trim() ? streamedContent : null;
                  if (flushedContent) {
                    streamedContent = "";
                    pendingContentRef.current = "";
                    if (rafIdRef.current !== null) {
                      cancelAnimationFrame(rafIdRef.current);
                      rafIdRef.current = null;
                    }
                  }

                  setMessages((prev) => {
                    const updated = [...prev];
                    const last = updated[updated.length - 1];
                    if (last.role !== "assistant") return prev;
                    const newSteps = [...last.steps];
                    if (flushedContent) {
                      newSteps.push({ type: "narration", content: flushedContent });
                    }
                    newSteps.push(step);
                    updated[updated.length - 1] = {
                      ...last,
                      steps: newSteps,
                      ...(flushedContent ? { content: "" } : {}),
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
                    for (let i = 0; i < steps.length; i++) {
                      if (steps[i].type === "tool_call" && steps[i].tool_name === data.tool_name && steps[i].tool_status === "running") {
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
                // Content tokens — streamed in real-time.
                // Could be final answer OR narration (determined later
                // when narration_end arrives).
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

              case "narration_end": {
                // The previously streamed tokens were narration, not the
                // final answer. Move them into a narration step and reset
                // content so tool calls render after the narration.
                const narrationText = sseEvent.data;
                streamedContent = "";
                pendingContentRef.current = "";
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last.role !== "assistant") return prev;
                  const step: NarrativeStep = {
                    type: "narration",
                    content: narrationText,
                  };
                  updated[updated.length - 1] = {
                    ...last,
                    content: "",
                    steps: [...last.steps, step],
                  };
                  return updated;
                });
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
                  if (data.role === "assistant") {
                    const oldId = currentAssistantIdRef.current;
                    currentAssistantIdRef.current = data.message_id;
                    // Update message_id on any artifacts that were created with the temp ID
                    setArtifacts((prev) => {
                      let changed = false;
                      const next = new Map(prev);
                      for (const [key, art] of next) {
                        if (art.message_id === oldId) {
                          next.set(key, { ...art, message_id: data.message_id });
                          changed = true;
                        }
                      }
                      return changed ? next : prev;
                    });
                  }
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

              case "artifact_start": {
                try {
                  const data: ArtifactStartPayload = JSON.parse(sseEvent.data);
                  const newArtifact: Artifact = {
                    id: data.artifact_id,
                    conversation_id: activeConversation?.id ?? "",
                    message_id: currentAssistantIdRef.current,
                    user_id: "",
                    type: data.type,
                    title: data.title,
                    content: "",
                    created_at: new Date().toISOString(),
                    updated_at: new Date().toISOString(),
                  };
                  setArtifacts((prev) => {
                    const next = new Map(prev);
                    next.set(data.artifact_id, newArtifact);
                    return next;
                  });
                  setActiveArtifactId(data.artifact_id);
                  pendingArtifactContentRef.current.set(data.artifact_id, "");
                } catch {
                  // Ignore parse errors
                }
                break;
              }

              case "artifact_delta": {
                try {
                  const data: ArtifactDeltaPayload = JSON.parse(sseEvent.data);
                  const current = pendingArtifactContentRef.current.get(data.artifact_id) ?? "";
                  pendingArtifactContentRef.current.set(data.artifact_id, current + data.content);

                  if (artifactRafIdRef.current === null) {
                    artifactRafIdRef.current = requestAnimationFrame(() => {
                      artifactRafIdRef.current = null;
                      setArtifacts((prev) => {
                        const next = new Map(prev);
                        for (const [id, content] of pendingArtifactContentRef.current) {
                          const existing = next.get(id);
                          if (existing) {
                            next.set(id, { ...existing, content });
                          }
                        }
                        return next;
                      });
                    });
                  }
                } catch {
                  // Ignore parse errors
                }
                break;
              }

              case "artifact_end": {
                try {
                  const data: ArtifactEndPayload = JSON.parse(sseEvent.data);
                  // Final flush of content
                  const finalContent = pendingArtifactContentRef.current.get(data.artifact_id) ?? "";
                  pendingArtifactContentRef.current.delete(data.artifact_id);
                  setArtifacts((prev) => {
                    const next = new Map(prev);
                    const existing = next.get(data.artifact_id);
                    if (existing) {
                      next.set(data.artifact_id, {
                        ...existing,
                        content: finalContent,
                        title: data.title,
                        updated_at: new Date().toISOString(),
                      });
                    }
                    return next;
                  });
                } catch {
                  // Ignore parse errors
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
        };

        if (useClaudeCode) {
          // Route through Next.js API route — reuse apiClient.stream with
          // absolute URL so SSE parsing stays in one place.
          await apiClient.streamAbsolute("/api/chat/stream", streamBody, onEvent, controller.signal);
        } else {
          await apiClient.stream("/chat/stream", streamBody, onEvent, controller.signal);
        }
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
        if (artifactRafIdRef.current !== null) {
          cancelAnimationFrame(artifactRafIdRef.current);
          artifactRafIdRef.current = null;
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
        // Only clear attachments that were actually sent — keep in-flight uploads
        const sentIds = new Set(readyAttachmentIds);
        setAttachments((prev) => prev.filter((a) => !sentIds.has(a.id)));
      }
    },
    [activeConversation, attachments, queryClient, useClaudeCode]
  );

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setIsStreaming(false);
  }, []);

  // Reset chat to empty state (for "new chat" without page navigation).
  const resetChat = useCallback(() => {
    // Cancel in-flight RAFs to prevent stale flushes into the new chat.
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
    if (artifactRafIdRef.current !== null) {
      cancelAnimationFrame(artifactRafIdRef.current);
      artifactRafIdRef.current = null;
    }
    pendingContentRef.current = "";
    pendingArtifactContentRef.current.clear();

    syncedConversationIdRef.current = undefined;
    lastConversationIdRef.current = null;
    setActiveConversation(null);
    setMessages((prev) => (prev.length === 0 ? prev : []));
    setArtifacts((prev) => (prev.size === 0 ? prev : new Map()));
    setActiveArtifactId(null);
    setAttachments((prev) => (prev.length === 0 ? prev : []));
    setError(null);
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

    // artifacts
    artifacts,
    activeArtifactId,
    setActiveArtifactId,

    // attachments
    attachments,
    addAttachment,
    addDriveAttachments,
    removeAttachment,
    clearAttachments,

    // mutations
    createConversation: (title?: string) => createMutation.mutateAsync(title),
    deleteConversation: (id: string) => deleteMutation.mutate(id),
    sendMessage,
    stopStreaming,

    // state management
    resetChat,

    // legacy
    fetchConversations: refreshConversations,
    setError,
  };
}
