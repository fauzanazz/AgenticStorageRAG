# Agents Domain

Handles agentic RAG — autonomous retrieval, reasoning, and conversational interface.

## Responsibilities
- Autonomous retrieval strategy selection (graph, vector, hybrid, multi-hop)
- Tool orchestration (search, clarify, evaluate)
- Self-evaluation and retry logic
- Streaming chat responses
- Conversation history management
- Citation generation

## Key Files
- `interfaces.py` — `Agent`, `AgentTool` ABCs
- `rag_agent.py` — Main RAG agent (LangChain)
- `extraction_agent.py` — Document-to-KG extraction agent
- `tools/graph_search.py` — Graph traversal tool
- `tools/vector_search.py` — Vector similarity tool
- `tools/clarify.py` — Ask user for clarification tool
- `tools/evaluate.py` — Self-evaluation tool
- `schemas.py` — Chat message, citation schemas
- `router.py` — WebSocket chat endpoint
- `exceptions.py` — Typed agent errors

## Adding a New Agent Tool
1. Create `tools/your_tool.py`
2. Implement `YourTool(AgentTool)`
3. Register in `rag_agent.py` tool list
4. Write tests in `tests/test_your_tool.py`
