# Design: Multilingual Chat Agent

**Date:** 2026-03-21
**Approach:** Prompt-Only (System Prompt Enhancement)

## Decision

Make the RAG agent multilingual by modifying only the `SYSTEM_PROMPT` in `rag_agent.py`. No new dependencies, no tool schema changes, no extra API calls.

## Why Prompt-Only

- Qwen3-max natively supports 100+ languages with strong instruction-following
- Cross-lingual retrieval is an LLM reasoning task (reformulate query in English before searching), not a systems task
- The embedding model (`text-embedding-3-small`) already has multilingual support — English queries against multilingual embeddings work well
- Minimal blast radius — if the prompt change causes issues, it's a one-line revert

## What Changes

### 1. System Prompt (`rag_agent.py:44-68`)

Add a `## Language` section to `SYSTEM_PROMPT` that instructs the agent to:

- **Detect** the user's language from their message
- **Respond** in that same language (narration, answer, citations, markdown formatting)
- **Search in English** — always formulate tool call queries in English (or the KB's dominant language) to maximize retrieval quality
- **Translate findings** — present English search results back in the user's language
- **Handle edge cases:**
  - Mixed-language input → respond in the dominant language
  - Short/ambiguous messages → match the conversation's established language, or default to the user's last clear language
  - Technical terms → keep them in their original form (don't translate "API", "PostgreSQL", etc.)

### 2. Test Updates (`test_rag_agent.py`)

- Add a test that verifies the system prompt contains multilingual instructions
- No behavioral test needed — the LLM's language output is non-deterministic and depends on the model

## What Does NOT Change

- Tool implementations (hybrid_search, vector_search, graph_search) — unchanged
- Tool schemas — no new parameters
- Frontend — stays English
- Config — no new settings
- Title generation — already says "Use the same language as the conversation"
