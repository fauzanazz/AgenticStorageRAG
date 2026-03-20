# Plan: Show Tool Call Results in Chat UI

**Approach:** Inline results in existing `tool_result` SSE event (Approach A)

## Task 1: Backend — Add `results` to `ToolResultData` and `AgentToolCall`

**Files:**
- `backend/app/domain/agents/schemas.py`
- `backend/app/domain/agents/rag_agent.py`

**Changes:**
1. Add `results: list[dict] = []` to `ToolResultData` schema (schemas.py:157-165)
2. Add `results: list[dict] = []` to `AgentToolCall` schema (schemas.py:119-125) — for persistence
3. In `rag_agent.py` (~line 376), add `results` to the `tool_result` SSE event JSON:
   - Extract result items from `result.get("result", [])`
   - Truncate `content` fields to 200 chars max server-side
   - Include the truncated results list in both the SSE event and the `AgentToolCall` record

## Task 2: Frontend — Extend types

**File:** `frontend/src/types/chat.ts`

**Changes:**
1. Add `tool_results?: ToolResultItem[]` to `NarrativeStep` interface
2. Add `ToolResultItem` type:
   ```ts
   export interface ToolResultItem {
     content?: string;
     entity_name?: string;
     entity_type?: string;
     description?: string;
     source?: string;
     score?: number;
     similarity?: number;
     relevance?: number;
     document_id?: string;
     relationships?: { type: string; target: string }[];
   }
   ```
3. Add `results?: ToolResultItem[]` to `ToolResultPayload`

## Task 3: Frontend — Parse results from SSE and persisted data

**File:** `frontend/src/hooks/use-chat.ts`

**Changes:**
1. In the `tool_result` SSE handler (~line 242-268), capture `data.results` and set it on the step as `tool_results`
2. In `fetchMessages` (~line 46-53), map `tc.results` to `tool_results` in the reconstructed steps

## Task 4: Frontend — Render results in ToolCallBlock

**File:** `frontend/src/components/chat/tool-call-block.tsx`

**Changes:**
1. In the expanded section, render `step.tool_results` as a list of result items
2. For vector/hybrid results: show truncated content snippet + score
3. For graph results: show entity name, type, description, and relationships
4. Auto-detect type based on which fields are present (entity_name → graph, content → vector/hybrid)
5. Style consistently with existing card/border design tokens
