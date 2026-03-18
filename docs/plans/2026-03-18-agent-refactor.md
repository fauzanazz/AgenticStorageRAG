# Agent Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove `IngestionSwarm` dead code, upgrade `RAGAgent` to a true native-tool-calling ReAct loop with parallel tool execution, and fix `IngestFileTool` to use the scoped LLM provider instead of the global singleton for KG extraction.

**Architecture:**
- `IngestionSwarm` and its tests are deleted entirely — the class is unreachable in production.
- `RAGAgent` is rewritten to use native function calling (`tools=tool_specs`) exactly like `IngestionOrchestrator` does, with `asyncio.gather` for parallel tool execution and a genuine observe→reason cycle (up to `MAX_ITERATIONS=5`).
- `IngestFileTool` receives `llm` in its constructor and passes it to `KGBuilder`, eliminating the global singleton import. `BatchIngestFilesTool` forwards it too. The Orchestrator already holds `self._llm` — it just needs to thread it through.

**Tech Stack:** Python 3.12, FastAPI, asyncio, LiteLLM (OpenAI-format function calling), SQLAlchemy async.

---

## Task 1: Delete `IngestionSwarm` and its tests

**Files:**
- Delete: `backend/app/domain/ingestion/swarm.py`
- Delete: `backend/app/domain/ingestion/tests/test_swarm.py`
- Modify: `backend/app/domain/ingestion/orchestrator.py` — remove docstring mention
- Modify: `backend/app/domain/ingestion/orchestrator_tools.py` — remove two comment references

**Step 1: Verify nothing imports swarm.py in production code**

```bash
cd backend && grep -r "from app.domain.ingestion.swarm" app/ --include="*.py"
```

Expected: only `app/domain/ingestion/tests/test_swarm.py` (the file we're about to delete).

**Step 2: Delete both files**

```bash
rm backend/app/domain/ingestion/swarm.py
rm backend/app/domain/ingestion/tests/test_swarm.py
```

**Step 3: Clean up the two comment references in `orchestrator.py`**

In `orchestrator.py:3`, the module docstring contains:
```
Replaces the pipeline-style `IngestionSwarm`...
```
Replace with a clean description of what the orchestrator is:
```
LLM-driven ReAct agent for Google Drive ingestion.
```
(Full docstring rewrite — just make it describe what the file actually does, not what it replaced.)

**Step 4: Clean up comment references in `orchestrator_tools.py`**

- Line 295: remove `"extracted from the old IngestionSwarm"` from the class docstring
- Line 522: remove the `# -- helpers (ported from IngestionSwarm) -----` section header comment

**Step 5: Run tests to confirm deletion didn't break anything**

```bash
cd backend && uv run pytest app/ -q --no-cov
```

Expected: all previously passing tests still pass (minus the deleted swarm tests).

**Step 6: Commit**

```bash
git add -A && git commit -m "refactor(ingestion): delete IngestionSwarm dead code and swarm tests"
```

---

## Task 2: Thread `llm` through `IngestFileTool` and `BatchIngestFilesTool`

The goal: `_extract_knowledge_graph` in `IngestFileTool` currently imports `llm_provider` (the global module singleton) instead of using the orchestrator's scoped LLM. This means per-user model settings are ignored for KG extraction. Fix: add `llm` to the constructor of both `IngestFileTool` and `BatchIngestFilesTool`.

**Files:**
- Modify: `backend/app/domain/ingestion/orchestrator_tools.py` — `IngestFileTool.__init__`, `_extract_knowledge_graph`, `BatchIngestFilesTool.__init__`, `BatchIngestFilesTool.execute`
- Modify: `backend/app/domain/ingestion/orchestrator.py` — where `IngestFileTool` and `BatchIngestFilesTool` are instantiated
- Modify: `backend/app/domain/ingestion/tests/test_orchestrator_tools.py` — update any `IngestFileTool(...)` instantiation calls

**Step 1: Write a failing test that confirms `_extract_knowledge_graph` uses the provided LLM**

In `backend/app/domain/ingestion/tests/test_orchestrator_tools.py`, add:

```python
def test_ingest_file_tool_passes_llm_to_kg_builder():
    """IngestFileTool must pass its constructor llm to KGBuilder, not the global."""
    from unittest.mock import MagicMock, AsyncMock, patch
    from app.domain.ingestion.orchestrator_tools import IngestFileTool

    mock_llm = MagicMock()
    tool = IngestFileTool(
        db=AsyncMock(),
        storage=MagicMock(),
        connector=MagicMock(),
        job=MagicMock(),
        llm=mock_llm,
    )
    assert tool._llm is mock_llm
```

Run: `cd backend && uv run pytest app/domain/ingestion/tests/test_orchestrator_tools.py::test_ingest_file_tool_passes_llm_to_kg_builder -v --no-cov`
Expected: **FAIL** — `IngestFileTool.__init__` doesn't accept `llm`.

**Step 2: Update `IngestFileTool.__init__` to accept `llm`**

In `orchestrator_tools.py`, `IngestFileTool.__init__` is at lines `300-310`. Change:

```python
def __init__(
    self,
    db: AsyncSession,
    storage: StorageClient,
    connector: SourceConnector,
    job: IngestionJob,
    llm: "LLMProvider",          # ← add this
) -> None:
    self._db = db
    self._storage = storage
    self._connector = connector
    self._job = job
    self._llm = llm              # ← add this
```

Add the import at the top of the file (already imported in the orchestrator but not in tools):
```python
from app.infra.llm import LLMProvider
```
(Use `TYPE_CHECKING` guard if it causes a circular import — in practice it won't since `orchestrator_tools.py` already imports from `app.infra`.)

**Step 3: Update `_extract_knowledge_graph` to use `self._llm`**

Current code at lines `598-634`:
```python
from app.infra.llm import llm_provider         # ← REMOVE this line
...
kg_builder = KGBuilder(graph_service=graph_service, llm=llm_provider)  # ← was global
```

Replace the two lines with:
```python
kg_builder = KGBuilder(graph_service=graph_service, llm=self._llm)
```

Remove the now-unused `from app.infra.llm import llm_provider` import inside this method.

**Step 4: Update `BatchIngestFilesTool.__init__` to accept and store `llm`**

`BatchIngestFilesTool` wraps `IngestFileTool`. Its constructor currently is at approximately `orchestrator_tools.py:660-680`. Add `llm` parameter and store as `self._llm`. When it instantiates `IngestFileTool` inside `execute()`, pass `llm=self._llm`.

**Step 5: Update `orchestrator.py` where tools are instantiated**

In `orchestrator.py`, the `ingest_tool` and `batch_tool` are built around lines `188-210`. Add `llm=self._llm` to both:

```python
ingest_tool = IngestFileTool(
    db=self._db,
    storage=self._storage,
    connector=self._connector,
    job=job,
    llm=self._llm,              # ← add
)
batch_tool = BatchIngestFilesTool(
    db=self._db,
    storage=self._storage,
    connector=self._connector,
    job=job,
    llm=self._llm,              # ← add
    file_concurrency=self._settings.file_concurrency,
)
```

**Step 6: Run the test**

```bash
cd backend && uv run pytest app/domain/ingestion/tests/test_orchestrator_tools.py -v --no-cov
```

Expected: all pass including the new test.

**Step 7: Run full suite**

```bash
cd backend && uv run pytest app/ -q --no-cov
```

Expected: all pass.

**Step 8: Commit**

```bash
git add backend/app/domain/ingestion/orchestrator_tools.py backend/app/domain/ingestion/orchestrator.py backend/app/domain/ingestion/tests/
git commit -m "fix(ingestion): thread scoped llm through IngestFileTool and BatchIngestFilesTool to KGBuilder"
```

---

## Task 3: Rewrite `RAGAgent` as a native-tool-calling ReAct loop with parallel execution

This is the largest task. The current `RAGAgent._execute_tool_phase` asks the LLM to produce a JSON array in response text, then executes tools sequentially in a `for` loop. We replace this with:

1. **Native function calling** — pass `tools=tool_specs` to `self._llm.complete()` like the `IngestionOrchestrator` does.
2. **Parallel execution** — `asyncio.gather` all tool calls from a single LLM response at once.
3. **ReAct loop** — after executing tools and seeing results, let the LLM decide if it needs more tool calls (up to `MAX_REACT_ITERATIONS=5`), before switching to final answer streaming.
4. **Delete `_parse_tool_calls`** — no longer needed.

**Files:**
- Modify: `backend/app/domain/agents/rag_agent.py`
- Modify: `backend/app/domain/agents/tests/test_rag_agent.py` — update tests that mock the old JSON planning approach

**Step 1: Write a failing test for native tool calling**

In `backend/app/domain/agents/tests/test_rag_agent.py`, add:

```python
@pytest.mark.asyncio
async def test_react_loop_uses_native_tool_calling():
    """RAGAgent must pass tools= to llm.complete(), not ask for JSON array."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.domain.agents.rag_agent import RAGAgent

    mock_llm = MagicMock()
    mock_tool = MagicMock()
    mock_tool.name = "hybrid_search"
    mock_tool.description = "hybrid search"
    mock_tool.execute = AsyncMock(return_value={"result": [], "count": 0, "source": "hybrid"})

    # Simulate: first LLM call returns a tool call, second returns text (done)
    first_response = MagicMock()
    first_response.choices = [MagicMock()]
    first_response.choices[0].message.tool_calls = [
        MagicMock(id="call_1", function=MagicMock(name="hybrid_search", arguments='{"query": "test"}'))
    ]
    first_response.choices[0].message.content = None

    second_response = MagicMock()
    second_response.choices = [MagicMock()]
    second_response.choices[0].message.tool_calls = None
    second_response.choices[0].message.content = "Final answer."

    mock_llm.complete = AsyncMock(side_effect=[first_response, second_response])
    mock_llm.complete_with_retry = AsyncMock(return_value=second_response)

    agent = RAGAgent(llm=mock_llm, chat_service=AsyncMock(), tools=[mock_tool])

    # Verify llm.complete was called with tools= kwarg
    # (collect call kwargs after running)
    ...  # implementation determines exact assertion
```

This test outlines the expectation. Write it to match how you implement.

**Step 2: Design the new `_react_loop` method**

Replace `_execute_tool_phase` entirely. The new method signature:

```python
async def _react_loop(
    self,
    messages: list[dict],
    request: ChatRequest,
) -> tuple[list[dict], list[AgentToolCall]]:
```

Where `messages` is the full in-flight message list (mutated across iterations) and the return is `(tool_results, tool_call_records)`.

**Algorithm:**

```python
MAX_REACT_ITERATIONS = 5
tool_specs = [self._tool_to_spec(tool) for tool in self._tools.values()]
tool_results: list[dict] = []
tool_call_records: list[AgentToolCall] = []

for iteration in range(MAX_REACT_ITERATIONS):
    response = await self._llm.complete(
        messages=messages,
        tools=tool_specs,
        tool_choice="auto",      # let the LLM decide
        temperature=0.0,
        max_tokens=1000,
    )
    msg = response.choices[0].message

    # Append the assistant turn to messages (required for tool result turn)
    assistant_msg = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        assistant_msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in msg.tool_calls
        ]
    messages.append(assistant_msg)

    if not msg.tool_calls:
        # LLM chose not to call any tool → ReAct loop done
        break

    # Execute all tool calls in parallel
    async def _call_tool(tc):
        tool_name = tc.function.name
        try:
            args = json.loads(tc.function.arguments)
        except json.JSONDecodeError:
            args = {}

        if tool_name not in self._tools:
            return tc.id, tool_name, args, None, "unknown tool"

        start = time.time()
        try:
            result = await self._tools[tool_name].execute(**args)
            return tc.id, tool_name, args, result, None
        except Exception as e:
            return tc.id, tool_name, args, None, str(e)

    outcomes = await asyncio.gather(*[_call_tool(tc) for tc in msg.tool_calls])

    for call_id, tool_name, args, result, error in outcomes:
        if result is not None:
            tool_results.append(result)
            tool_call_records.append(AgentToolCall(
                tool_name=tool_name,
                arguments=args,
                result_summary=f"{result.get('count', 0)} results from {result.get('source', 'unknown')}",
            ))
        else:
            tool_call_records.append(AgentToolCall(
                tool_name=tool_name,
                arguments=args,
                result_summary=f"Error: {error}",
            ))

        # Append tool result message so LLM sees the observation
        messages.append({
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps(result) if result else f"Error: {error}",
        })

# Fallback: if no tools were called at all, run hybrid_search once
if not tool_results and "hybrid_search" in self._tools:
    try:
        user_query = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            request.message,
        )
        result = await self._tools["hybrid_search"].execute(
            query=user_query, top_k=10, vector_weight=request.vector_weight
        )
        tool_results.append(result)
        tool_call_records.append(AgentToolCall(
            tool_name="hybrid_search",
            arguments={"query": user_query},
            result_summary=f"{result.get('count', 0)} results (fallback)",
        ))
    except Exception as e:
        logger.warning("Fallback hybrid search failed: %s", e)

return tool_results, tool_call_records
```

**Step 3: Add `_tool_to_spec` helper method**

Converts an `IAgentTool` to the OpenAI-format function spec:

```python
def _tool_to_spec(self, tool: IAgentTool) -> dict:
    """Convert an IAgentTool to an OpenAI-format function calling spec."""
    spec = {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
        },
    }
    # If the tool exposes a parameters_schema property, use it
    if hasattr(tool, "parameters_schema"):
        spec["function"]["parameters"] = tool.parameters_schema
    else:
        # Infer basic schema from description (fallback)
        spec["function"]["parameters"] = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "top_k": {"type": "integer", "description": "Max results"},
            },
            "required": ["query"],
        }
    return spec
```

**Note:** The three RAGAgent tools (`GraphSearchTool`, `VectorSearchTool`, `HybridSearchTool`) do **not** currently expose `parameters_schema`. You need to add it to each. Use the same format as `OrchestratorTool.parameters_schema` in `orchestrator_tools.py`. Add `parameters_schema` as an abstract property to `IAgentTool` in `interfaces.py` (or add it as an optional method with a default fallback as shown above).

Parameters for each tool:
- `GraphSearchTool`: `query` (str, required), `entity_types` (array of str, optional), `max_depth` (int, optional, default 2), `top_k` (int, optional, default 10)
- `VectorSearchTool`: `query` (str, required), `top_k` (int, optional, default 10), `document_id` (str, optional)
- `HybridSearchTool`: `query` (str, required), `top_k` (int, optional, default 10), `vector_weight` (number, optional, default 0.5)

**Step 4: Update `chat()` to use `_react_loop` instead of `_execute_tool_phase`**

In `chat()`, replace:
```python
tool_results, tool_call_records = await self._execute_tool_phase(llm_messages, request)
```
with:
```python
tool_results, tool_call_records = await self._react_loop(llm_messages, request)
```

**Step 5: Update `_generate_response_stream` — the messages list is now richer**

After the ReAct loop, `messages` already contains the full assistant + tool turns. The context for the final LLM call should append the retrieved context summary rather than re-inserting raw tool result JSON (which can be very large). Keep the existing context-building logic — it's correct. The Phase 2 call still gets `llm_messages` (the original messages before the ReAct loop started). The ReAct loop messages are separate.

Actually, the cleanest approach: `_react_loop` takes the `messages` list by reference (Python list is mutable), so after it returns, `llm_messages` in `chat()` contains the full conversation including all tool turns. Pass this enriched list to `_generate_response_stream` instead of the original `llm_messages`.

Revise: have `_react_loop` mutate the passed `messages` in place (append assistant + tool turns) and return `tool_results, tool_call_records`. The `_generate_response_stream` receives the now-enriched `messages`.

**Step 6: Delete `_parse_tool_calls` and `_execute_tool_phase`**

These methods are no longer called. Remove them.

Update the module docstring to accurately describe the native tool-calling ReAct loop (remove the LangChain reference on line 3).

**Step 7: Run the new tests**

```bash
cd backend && uv run pytest app/domain/agents/tests/ -v --no-cov
```

Expected: all pass.

**Step 8: Run full suite**

```bash
cd backend && uv run pytest app/ -q --no-cov
```

Expected: all pass.

**Step 9: Commit**

```bash
git add backend/app/domain/agents/
git commit -m "feat(agents): rewrite RAGAgent as native-tool-calling ReAct loop with parallel asyncio.gather"
```

---

## Task 4: Add `parameters_schema` to the three RAGAgent tools

Each tool file needs a `parameters_schema` property so `_tool_to_spec` produces proper JSON Schema for the LLM.

**Files:**
- Modify: `backend/app/domain/agents/tools/graph_search.py`
- Modify: `backend/app/domain/agents/tools/vector_search.py`
- Modify: `backend/app/domain/agents/tools/hybrid_search.py`
- Modify: `backend/app/domain/agents/interfaces.py` — add `parameters_schema` as abstract property to `IAgentTool`

**Step 1: Add abstract `parameters_schema` to `IAgentTool`**

In `interfaces.py`, `IAgentTool` currently has `name`, `description`, and `execute`. Add:

```python
@property
@abstractmethod
def parameters_schema(self) -> dict[str, Any]:
    """Return a JSON Schema dict describing this tool's parameters."""
    ...
```

**Step 2: Add `parameters_schema` to `GraphSearchTool`**

```python
@property
def parameters_schema(self) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Entity or relationship to search for."},
            "entity_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filter by entity type (e.g. ['Person', 'Course']).",
            },
            "max_depth": {"type": "integer", "description": "Relationship traversal depth.", "default": 2},
            "top_k": {"type": "integer", "description": "Max entities to return.", "default": 10},
        },
        "required": ["query"],
    }
```

**Step 3: Add `parameters_schema` to `VectorSearchTool`**

```python
@property
def parameters_schema(self) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Text to search for semantically similar chunks."},
            "top_k": {"type": "integer", "description": "Max chunks to return.", "default": 10},
            "document_id": {"type": "string", "description": "Restrict search to a specific document UUID."},
        },
        "required": ["query"],
    }
```

**Step 4: Add `parameters_schema` to `HybridSearchTool`**

```python
@property
def parameters_schema(self) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query combining graph and vector retrieval."},
            "top_k": {"type": "integer", "description": "Max results to return.", "default": 10},
            "vector_weight": {
                "type": "number",
                "description": "Weight for vector results vs graph (0.0–1.0). Default 0.5.",
                "default": 0.5,
            },
        },
        "required": ["query"],
    }
```

**Step 5: Run tests**

```bash
cd backend && uv run pytest app/domain/agents/ -q --no-cov
```

Expected: all pass.

**Step 6: Commit**

```bash
git add backend/app/domain/agents/
git commit -m "feat(agents): add parameters_schema to all RAGAgent tools for native function calling"
```

---

## Task 5: Final verification

**Step 1: Full test suite**

```bash
cd backend && uv run pytest app/ -q --no-cov
```

Expected: all pass.

**Step 2: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: clean.

**Step 3: Import smoke test**

```bash
cd backend && uv run python -c "
from app.domain.agents.rag_agent import RAGAgent, MAX_REACT_ITERATIONS
from app.domain.agents.tools.graph_search import GraphSearchTool
from app.domain.agents.tools.vector_search import VectorSearchTool
from app.domain.agents.tools.hybrid_search import HybridSearchTool
from app.domain.ingestion.orchestrator_tools import IngestFileTool, BatchIngestFilesTool
import app.domain.ingestion.swarm as swarm
print('Should not reach here — swarm.py was deleted')
"
```

Expected: `ModuleNotFoundError: No module named 'app.domain.ingestion.swarm'` (confirms deletion), all other imports succeed.

**Step 4: Commit**

```bash
git add -A && git commit -m "chore: verify agent refactor complete"
```

---

## Dependency graph (execution order)

```
Task 1 (delete swarm)        ← no deps, do first
Task 2 (llm in IngestFileTool) ← no deps, parallel with Task 1
Task 4 (parameters_schema)   ← no deps, parallel with Tasks 1 & 2
Task 3 (ReAct RAGAgent)      ← depends on Task 4 (needs parameters_schema to exist)
Task 5 (verify)              ← depends on all above
```

Wave 1: Tasks 1, 2, 4 in parallel
Wave 2: Task 3
Wave 3: Task 5
