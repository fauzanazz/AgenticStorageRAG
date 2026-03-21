import { tool } from "@anthropic-ai/claude-agent-sdk";
import { z } from "zod/v4";
import type { ToolCallRecord } from "./types";
import { BACKEND_URL } from "./config";

function truncateItems(result: Record<string, unknown>): Record<string, unknown>[] {
  let rawItems = result.result;
  if (!rawItems) return [];
  if (!Array.isArray(rawItems)) rawItems = [rawItems];

  return (rawItems as Record<string, unknown>[]).map((item) => {
    const entry = { ...item };
    for (const key of ["content", "description"]) {
      if (typeof entry[key] === "string" && (entry[key] as string).length > 200) {
        entry[key] = (entry[key] as string).slice(0, 200) + "...";
      }
    }
    return entry;
  });
}

export function createTools(
  authToken: string,
  toolCallRecords: ToolCallRecord[],
  toolResults: Record<string, unknown>[],
) {
  async function callBackend(path: string, body: Record<string, unknown>): Promise<Record<string, unknown>> {
    const res = await fetch(`${BACKEND_URL}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: authToken,
      },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.text();
      throw new Error(`Backend ${path} failed (${res.status}): ${err}`);
    }
    return res.json();
  }

  const hybridSearch = tool(
    "hybrid_search",
    "Combined search across knowledge graph AND document embeddings. Use as the primary retrieval method for most questions.",
    { query: z.string(), top_k: z.number().optional(), vector_weight: z.number().optional() },
    async (args) => {
      const start = Date.now();
      try {
        const result = await callBackend("/knowledge/search/hybrid", {
          query: args.query,
          top_k: args.top_k ?? 10,
          vector_weight: args.vector_weight ?? 0.5,
        });
        // The hybrid search endpoint returns an array directly, wrap it
        const wrapped: Record<string, unknown> = Array.isArray(result)
          ? { result, count: (result as unknown[]).length, source: "hybrid" }
          : result;
        const elapsed = Date.now() - start;
        const count = (wrapped.count as number) ?? 0;
        toolResults.push(wrapped);
        toolCallRecords.push({
          tool_name: "hybrid_search",
          arguments: args,
          result_summary: `Found ${count} results`,
          duration_ms: elapsed,
          results: truncateItems(wrapped),
        });
        return { content: [{ type: "text" as const, text: JSON.stringify(wrapped) }] };
      } catch (e) {
        const elapsed = Date.now() - start;
        const msg = e instanceof Error ? e.message : String(e);
        toolCallRecords.push({
          tool_name: "hybrid_search",
          arguments: args,
          result_summary: `Error: ${msg}`,
          duration_ms: elapsed,
          results: [],
        });
        return { content: [{ type: "text" as const, text: `Error: ${msg}` }], isError: true };
      }
    },
  );

  const fetchDocument = tool(
    "fetch_document",
    "Fetch the FULL text content of a specific document. Use when the user asks to read or view a complete document.",
    { document_id: z.string(), query: z.string().optional(), chunk_offset: z.number().optional() },
    async (args) => {
      const start = Date.now();
      try {
        const result = await callBackend("/chat/tools/fetch-document", args);
        const elapsed = Date.now() - start;
        const count = (result.count as number) ?? 0;
        toolResults.push(result);
        toolCallRecords.push({
          tool_name: "fetch_document",
          arguments: args,
          result_summary: `Found ${count} results`,
          duration_ms: elapsed,
          results: truncateItems(result),
        });
        return { content: [{ type: "text" as const, text: JSON.stringify(result) }] };
      } catch (e) {
        const elapsed = Date.now() - start;
        const msg = e instanceof Error ? e.message : String(e);
        toolCallRecords.push({
          tool_name: "fetch_document",
          arguments: args,
          result_summary: `Error: ${msg}`,
          duration_ms: elapsed,
          results: [],
        });
        return { content: [{ type: "text" as const, text: `Error: ${msg}` }], isError: true };
      }
    },
  );

  const generateDocument = tool(
    "generate_document",
    "Generate a structured document as an artifact. Use for reports, summaries, or long-form content creation.",
    { title: z.string(), instructions: z.string(), format: z.string().optional(), context: z.string().optional() },
    async (args) => {
      const start = Date.now();
      try {
        const result = await callBackend("/chat/tools/generate-document", args);
        const elapsed = Date.now() - start;
        const count = (result.count as number) ?? 0;
        toolResults.push(result);
        toolCallRecords.push({
          tool_name: "generate_document",
          arguments: args,
          result_summary: `Found ${count} results`,
          duration_ms: elapsed,
          results: truncateItems(result),
        });
        return { content: [{ type: "text" as const, text: JSON.stringify(result) }] };
      } catch (e) {
        const elapsed = Date.now() - start;
        const msg = e instanceof Error ? e.message : String(e);
        toolCallRecords.push({
          tool_name: "generate_document",
          arguments: args,
          result_summary: `Error: ${msg}`,
          duration_ms: elapsed,
          results: [],
        });
        return { content: [{ type: "text" as const, text: `Error: ${msg}` }], isError: true };
      }
    },
  );

  return [hybridSearch, fetchDocument, generateDocument];
}
