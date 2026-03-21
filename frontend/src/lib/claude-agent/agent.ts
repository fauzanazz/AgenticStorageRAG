import { query, createSdkMcpServer } from "@anthropic-ai/claude-agent-sdk";
import type { SDKMessage, Options } from "@anthropic-ai/claude-agent-sdk";
import { SYSTEM_PROMPT, friendlyToolName } from "./system-prompt";
import { createTools } from "./tools";
import type { ToolCallRecord, CitationData, StreamRequest } from "./types";
import { BACKEND_URL } from "./config";

const RAG_TOOL_NAMES = new Set(["hybrid_search", "generate_document", "fetch_document"]);

function sseChunk(event: string, data: string): string {
  const dataLines = data.split("\n").map((line) => `data: ${line}`).join("\n");
  return `event: ${event}\n${dataLines}\n\n`;
}

async function backendFetch(
  path: string,
  authToken: string,
  options: { method?: string; body?: unknown } = {},
): Promise<Response> {
  return fetch(`${BACKEND_URL}${path}`, {
    method: options.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      Authorization: authToken,
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
}

async function backendJson<T>(path: string, authToken: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const res = await backendFetch(path, authToken, options);
  if (!res.ok) {
    throw new Error(`Backend ${path} failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

interface MessageFromBackend {
  id: string;
  role: string;
  content: string;
}

interface ConversationFromBackend {
  id: string;
  title: string;
}

export async function streamClaudeAgent(
  request: StreamRequest,
  authToken: string,
): Promise<ReadableStream<Uint8Array>> {
  const encoder = new TextEncoder();

  return new ReadableStream<Uint8Array>({
    async start(controller) {
      try {
        // 1. Get or create conversation + save user message + get history
        let conversationId = request.conversation_id;

        if (!conversationId) {
          const conv = await backendJson<ConversationFromBackend>(
            "/chat/conversations",
            authToken,
            { method: "POST", body: { title: "New conversation" } },
          );
          conversationId = conv.id;
          controller.enqueue(
            encoder.encode(sseChunk("conversation_created", JSON.stringify({ conversation_id: conversationId }))),
          );
        }

        // Get history
        const history = await backendJson<MessageFromBackend[]>(
          `/chat/conversations/${conversationId}/messages?limit=20`,
          authToken,
        );

        // Save user message
        const userMsg = await backendJson<MessageFromBackend>(
          `/chat/conversations/${conversationId}/messages`,
          authToken,
          { method: "POST", body: { role: "user", content: request.message } },
        );
        controller.enqueue(
          encoder.encode(sseChunk("message_created", JSON.stringify({ message_id: userMsg.id, role: "user" }))),
        );

        // 2. Build prompt from history
        const promptParts: string[] = [];
        for (const msg of history) {
          const prefix = msg.role === "user" ? "User" : "Assistant";
          promptParts.push(`${prefix}: ${msg.content}`);
        }
        promptParts.push(`User: ${request.message}`);
        const fullPrompt = promptParts.join("\n\n");

        // 3. Create MCP tools with side-channel sinks
        const toolCallRecords: ToolCallRecord[] = [];
        const allToolResults: Record<string, unknown>[] = [];
        const mcpTools = createTools(authToken, toolCallRecords, allToolResults);

        const mcpServer = createSdkMcpServer({
          name: "rag",
          version: "1.0.0",
          tools: mcpTools,
        });

        const options: Options = {
          systemPrompt: SYSTEM_PROMPT,
          maxTurns: 100,
          mcpServers: { rag: mcpServer },
          allowedTools: ["mcp__rag__hybrid_search", "mcp__rag__generate_document", "mcp__rag__fetch_document"],
          includePartialMessages: true,
          permissionMode: "bypassPermissions",
        };

        // 4. Process SDK stream
        let accumulatedAnswer = "";
        let sdkResultText: string | null = null;
        let emittedToolIdx = 0;
        let inTool = false;
        let currentToolName: string | null = null;
        let toolInputJson = "";

        try {
          for await (const msg of query({ prompt: fullPrompt, options }) as AsyncIterable<SDKMessage>) {
            if (msg.type === "stream_event") {
              const event = (msg as unknown as { event: Record<string, unknown> }).event;
              const eventType = event.type as string | undefined;

              if (eventType === "content_block_start") {
                const contentBlock = event.content_block as Record<string, unknown> | undefined;
                if (contentBlock?.type === "tool_use") {
                  const rawName = (contentBlock.name as string) ?? "";
                  const toolName = rawName.replace(/^mcp__rag__/, "");
                  if (RAG_TOOL_NAMES.has(toolName)) {
                    inTool = true;
                    currentToolName = toolName;
                    toolInputJson = "";
                  }
                }
              } else if (eventType === "content_block_delta") {
                const delta = event.delta as Record<string, unknown> | undefined;
                const deltaType = delta?.type as string | undefined;

                if (deltaType === "text_delta" && !inTool) {
                  const text = (delta?.text as string) ?? "";
                  if (text) {
                    accumulatedAnswer += text;
                    controller.enqueue(encoder.encode(sseChunk("token", text)));
                  }
                } else if (deltaType === "input_json_delta" && inTool) {
                  toolInputJson += (delta?.partial_json as string) ?? "";
                }
              } else if (eventType === "content_block_stop") {
                if (inTool && currentToolName) {
                  let toolArgs: Record<string, unknown> = {};
                  try {
                    if (toolInputJson) toolArgs = JSON.parse(toolInputJson);
                  } catch {
                    // ignore parse errors
                  }

                  const label = friendlyToolName(currentToolName);
                  controller.enqueue(
                    encoder.encode(
                      sseChunk(
                        "tool_start",
                        JSON.stringify({
                          tool_name: currentToolName,
                          tool_label: label,
                          arguments: toolArgs,
                        }),
                      ),
                    ),
                  );

                  // Emit tool results that have accumulated
                  while (emittedToolIdx < toolCallRecords.length) {
                    const rec = toolCallRecords[emittedToolIdx];
                    controller.enqueue(
                      encoder.encode(
                        sseChunk(
                          "tool_result",
                          JSON.stringify({
                            tool_name: rec.tool_name,
                            tool_label: friendlyToolName(rec.tool_name),
                            summary: rec.result_summary,
                            count: rec.results.length,
                            duration_ms: rec.duration_ms,
                            error: null,
                            results: rec.results,
                          }),
                        ),
                      ),
                    );
                    emittedToolIdx++;
                  }

                  inTool = false;
                  currentToolName = null;
                  toolInputJson = "";
                }
              }
            } else if (msg.type === "result") {
              const result = msg as unknown as {
                subtype?: string;
                result?: string;
                total_cost_usd?: number;
                duration_ms?: number;
                num_turns?: number;
                errors?: string[];
                is_error?: boolean;
              };
              console.log(
                `Claude Code query complete: subtype=${result.subtype}, turns=${result.num_turns}, cost=$${result.total_cost_usd?.toFixed(4)}, duration=${result.duration_ms}ms`,
              );

              if (result.subtype === "success" && result.result) {
                // The SDK result contains the final answer text.
                // Use it as fallback if streaming didn't capture it.
                sdkResultText = result.result;
              } else if (result.is_error) {
                const reason = result.subtype ?? "unknown";
                const errMsgs = result.errors?.join("; ") ?? "";
                console.warn(`Claude Code query ended with error: ${reason}`, errMsgs);
              }
            } else if (msg.type === "assistant") {
              // Complete assistant message — extract text content as fallback
              const assistantMsg = msg as unknown as {
                message?: { content?: Array<{ type: string; text?: string }> };
              };
              if (assistantMsg.message?.content) {
                for (const block of assistantMsg.message.content) {
                  if (block.type === "text" && block.text) {
                    // If this text wasn't already captured via stream_event,
                    // it means stream events were incomplete. Use as fallback.
                    if (!accumulatedAnswer.includes(block.text.slice(0, 100))) {
                      sdkResultText = block.text;
                    }
                  }
                }
              }
            }
          }
        } catch (sdkErr: unknown) {
          // Handle known SDK transport errors as non-fatal
          const errStr = String(sdkErr);
          const isTransportErr =
            errStr.includes("CLIConnectionError") ||
            errStr.includes("ProcessTransport") ||
            errStr.includes("TaskGroup");
          if (!isTransportErr) {
            throw sdkErr;
          }
          console.warn("SDK transport error (non-fatal):", errStr);
          // If we had tool calls but no answer, signal a partial failure
          if (!accumulatedAnswer.trim() && toolCallRecords.length > 0) {
            console.warn("SDK terminated before producing final answer after", toolCallRecords.length, "tool calls");
          }
        }

        // Emit remaining tool results
        while (emittedToolIdx < toolCallRecords.length) {
          const rec = toolCallRecords[emittedToolIdx];
          controller.enqueue(
            encoder.encode(
              sseChunk(
                "tool_result",
                JSON.stringify({
                  tool_name: rec.tool_name,
                  tool_label: friendlyToolName(rec.tool_name),
                  summary: rec.result_summary,
                  count: rec.results.length,
                  duration_ms: rec.duration_ms,
                  error: null,
                  results: rec.results,
                }),
              ),
            ),
          );
          emittedToolIdx++;
        }

        // 4b. Fallback: if streaming didn't capture the final answer,
        // use the result text from the SDK result message or assistant message.
        // The accumulatedAnswer may contain only narration text from intermediate
        // tool-calling turns. The sdkResultText contains the actual final answer.
        if (sdkResultText && !accumulatedAnswer.trim()) {
          // Streaming didn't capture any content — use SDK result as fallback
          accumulatedAnswer = sdkResultText;
          controller.enqueue(encoder.encode(sseChunk("token", sdkResultText)));
        }

        // 5. Extract and enrich citations
        const citations = extractCitations(allToolResults);
        if (citations.length > 0) {
          try {
            const enriched = await backendJson<{ citations: CitationData[] }>(
              "/chat/tools/enrich-citations",
              authToken,
              { method: "POST", body: { citations } },
            );
            for (const c of enriched.citations) {
              controller.enqueue(encoder.encode(sseChunk("citation", JSON.stringify(c))));
            }
          } catch (e) {
            // Emit unenriched citations on failure
            for (const c of citations) {
              controller.enqueue(encoder.encode(sseChunk("citation", JSON.stringify(c))));
            }
            console.warn("Citation enrichment failed:", e);
          }
        }

        // 6. Save assistant message
        const assistantMsg = await backendJson<MessageFromBackend>(
          `/chat/conversations/${conversationId}/messages`,
          authToken,
          {
            method: "POST",
            body: {
              role: "assistant",
              content: accumulatedAnswer,
              citations: citations.length > 0 ? citations : undefined,
              tool_calls: toolCallRecords.length > 0 ? toolCallRecords : undefined,
            },
          },
        );
        controller.enqueue(
          encoder.encode(sseChunk("message_created", JSON.stringify({ message_id: assistantMsg.id, role: "assistant" }))),
        );

        // 7. Auto-generate title for first exchange
        if (history.length === 0) {
          // Fire-and-forget title update
          backendJson<void>(
            `/chat/conversations/${conversationId}/title`,
            authToken,
            { method: "PATCH", body: { title: request.message.slice(0, 80) } },
          ).catch(() => {});
        }

        // 8. Done
        controller.enqueue(
          encoder.encode(
            sseChunk(
              "done",
              JSON.stringify({
                conversation_id: conversationId,
                citations_count: citations.length,
                tools_used: toolCallRecords.map((tc) => tc.tool_name),
              }),
            ),
          ),
        );
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        console.error("Claude agent streaming failed:", msg);
        controller.enqueue(encoder.encode(sseChunk("error", JSON.stringify({ error: msg }))));
      } finally {
        controller.close();
      }
    },
  });
}

function extractCitations(toolResults: Record<string, unknown>[]): CitationData[] {
  const citations: CitationData[] = [];

  for (const result of toolResults) {
    let items = result.result;
    if (!items) continue;
    if (!Array.isArray(items)) items = [items];

    for (const item of items as Record<string, unknown>[]) {
      if (typeof item !== "object" || !item) continue;

      let content = (item.content as string) ?? "";
      if (!content && item.entity_name) {
        content = `${item.entity_name} (${item.entity_type ?? ""}): ${item.description ?? ""}`;
      }

      if (content) {
        const citation: CitationData = {
          content_snippet: content.slice(0, 200),
          source_type: (result.source as string) ?? "unknown",
          relevance_score: (item.similarity ?? item.score ?? item.relevance ?? 0) as number,
        };

        if (item.document_id) citation.document_id = String(item.document_id);
        if (item.chunk_id) citation.chunk_id = String(item.chunk_id);
        if (item.entity_id) citation.entity_id = String(item.entity_id);
        if (item.entity_name) citation.entity_name = String(item.entity_name);
        const metadata = item.metadata as Record<string, unknown> | undefined;
        if (metadata?.page_number) citation.page_number = metadata.page_number as number;

        citations.push(citation);
      }
    }
  }

  return citations;
}
