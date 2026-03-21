# Dual Chat Processor Architecture

## Why Two AI Chat Processors?

DingDong RAG has two separate AI chat processing paths: a **Python backend processor** (primary) and a **frontend Next.js processor** (fallback). This document explains why both exist and when each is used.

---

## TL;DR

| | Backend Processor | Frontend Processor |
|---|---|---|
| **Location** | `backend/app/domain/agents/rag_agent.py` | `frontend/src/lib/claude-agent/agent.ts` |
| **Runtime** | Python (FastAPI) | Node.js (Next.js API route) |
| **LLM interface** | LiteLLM (native function calling) | `@anthropic-ai/claude-agent-sdk` |
| **Status** | Primary / Production | Experimental / Fallback |
| **Why it exists** | Core chat engine | Claude Code SDK was buggy; kept as alternative path |

---

## 1. Backend Processor (Primary)

**Entry point:** `POST /chat/stream`
**Code:** `backend/app/domain/agents/rag_agent.py` (`RAGAgent` class)

This is the **main AI chat engine**. It implements a native ReAct loop in Python:

1. Builds system prompt with tool descriptions
2. Calls LLM via LiteLLM with native `tools=` parameter
3. If tool calls are returned, executes them in parallel (`asyncio.gather`)
4. Appends tool results and loops (max 5 iterations)
5. Streams final answer with citations via SSE

**Why it's primary:**
- Full control over the ReAct loop, streaming, and tool execution
- Supports **any LLM provider** via LiteLLM (Anthropic, OpenAI, DashScope/Qwen, Gemini, OpenRouter)
- Per-request model override
- Direct database access for conversation persistence
- Parallel tool execution with real-time event streaming
- Robust error handling with automatic fallback models
- Cost tracking and usage analytics via Redis

**Tools available:**
- `hybrid_search` — combined graph + vector retrieval (Neo4j + embeddings)
- `fetch_document` — full document retrieval by ID
- `generate_document` — artifact creation with streamed content

---

## 2. Frontend Processor (Claude Code SDK)

**Entry point:** `POST /api/chat/stream` (Next.js API route)
**Code:** `frontend/src/lib/claude-agent/agent.ts` (`streamClaudeAgent()`)

This processor was built to leverage the `@anthropic-ai/claude-agent-sdk` for its native agentic capabilities. However, **the SDK introduced bugs** — issues with streaming reliability, tool execution lifecycle, and event handling that were difficult to debug in production.

**How it works:**
1. Creates/fetches conversation via backend API
2. Builds prompt from conversation history
3. Registers MCP tools (`hybrid_search`, `fetch_document`, `generate_document`)
4. Delegates the ReAct loop to the Claude Agent SDK's `query()` function
5. Processes stream events and re-emits them as SSE to the frontend
6. Saves the final message back to the backend

**Why it still exists:**
- Kept as an **opt-in alternative** behind a toggle (`use_claude_code` in user settings)
- Useful for testing Claude's native reasoning vs. our custom ReAct implementation
- May become viable again as the SDK matures

**Known issues that led to backend being primary:**
- Claude Agent SDK streaming was unreliable — dropped events, inconsistent `content_block_start`/`content_block_stop` lifecycle
- Tool execution through MCP had edge cases that broke the agentic loop
- Debugging was harder since the ReAct loop is opaque (managed by SDK internals)
- Limited to Anthropic models only (no multi-provider support)

---

## 3. How the Frontend Switches Between Them

The routing decision happens in `frontend/src/hooks/use-chat.ts`:

```typescript
if (useClaudeCode) {
  // Route to Next.js API: /api/chat/stream (frontend processor)
  await apiClient.streamAbsolute("/api/chat/stream", streamBody, onEvent, controller.signal);
} else {
  // Route directly to backend: /chat/stream (backend processor)
  await apiClient.stream("/chat/stream", streamBody, onEvent, controller.signal);
}
```

The `useClaudeCode` flag comes from user settings (`settings?.use_claude_code`), togglable via the Claude Code toggle switch in the settings page (`frontend/src/components/settings/claude-code-toggle.tsx`).

**Both processors emit the same SSE event types** (`token`, `tool_start`, `tool_result`, `citation`, `thinking`, `done`, `error`), so the frontend UI code handles both identically.

---

## 4. Architecture Diagram

```
                        Frontend (Next.js)
                              |
                    useChat() hook decides
                         /          \
                        /            \
           use_claude_code=false   use_claude_code=true
                      /                \
                     v                  v
          Backend FastAPI         Next.js API Route
          POST /chat/stream       POST /api/chat/stream
                |                       |
          RAGAgent (Python)      streamClaudeAgent (TS)
          Native ReAct loop      Claude Agent SDK
          LiteLLM (any model)    Anthropic SDK only
                |                       |
                v                       v
          Tools executed          MCP Tools executed
          (hybrid_search,         (same tools, via
           fetch_document,         backend proxy)
           generate_document)
                |                       |
                v                       v
          SSE stream              SSE stream
          (same event format)     (same event format)
                \                      /
                 \                    /
                  v                  v
              Frontend UI renders identically
```

---

## 5. When to Use Which

- **Default (backend):** Use for all production workloads. Supports all models, has full observability, and is battle-tested.
- **Claude Code SDK (frontend):** Enable only for experimentation or when testing Claude's native agent loop behavior. Expect occasional instability.

---

## 6. Future Direction

The frontend processor may be deprecated or promoted depending on:
- Stability improvements in `@anthropic-ai/claude-agent-sdk`
- Whether the SDK adds multi-provider support
- Performance comparisons between native ReAct vs. SDK-managed loops
