# Spec: Show Tool Call Results in Chat UI

## What are we building?
Display the actual results returned by tool calls (vector search, hybrid search, graph search) in the chat UI as collapsible sections, so end users can see what the AI found before it synthesized its answer.

## Who is this for?
End users of the DriveRAG chat app who want transparency into what sources/results the AI retrieved.

## What does success look like?
- When a tool call completes, the collapsible ToolCallBlock shows the actual result items (document snippets, entity names, relevance scores) — not just "Found 5 results"
- Users can expand/collapse to drill into details
- Results survive page refresh (persisted via the existing tool_calls mechanism)
- Different tool types render appropriately (vector search shows content snippets, graph search shows entities/relationships)

## Out of scope
- Users cannot re-run or modify tool calls (view-only)
- No new tool types — only displaying results for existing tools
- No changes to citation extraction or how the LLM uses results

## Constraints
- Tech stack: Next.js frontend (React, TanStack Query), Python/Hono backend
- Backend must add a `results` field to the `tool_result` SSE event payload
- Backend must also persist results in the `tool_calls` column so they survive refresh
- Keep result payloads reasonable — truncate long content if needed (e.g., max 200 chars per snippet)
- Must handle all three tool types: vector_search, hybrid_search, graph_search

## Data shapes (current backend tool outputs)

**Vector search result item:**
```json
{ "content": "...", "document_id": "uuid", "chunk_id": "uuid", "similarity": 0.87, "metadata": {} }
```

**Hybrid search result item:**
```json
{ "content": "...", "source": "vector|graph|both", "score": 0.85, "document_id": "uuid", "chunk_id": "uuid", "entity_id": "uuid", "metadata": {} }
```

**Graph search result item:**
```json
{ "entity_name": "...", "entity_type": "...", "description": "...", "relevance": 0.9, "relationships": [{ "type": "...", "target": "..." }] }
```
