"""RAG agent with autonomous tool selection via a native ReAct loop.

The agent runs a genuine Reason-Act-Observe cycle:

1. Receive user message + conversation history.
2. Call the LLM with native function-calling specs (``tools=`` parameter).
3. If the LLM returns tool calls, execute them all in parallel with
   ``asyncio.gather``, then append results to the message history.
4. Repeat until the LLM produces a text response or MAX_REACT_ITERATIONS
   is reached.
5. Stream the final answer and emit citation events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.agents.interfaces import IAgentTool, IChatService, IRAGAgent
from app.domain.agents.schemas import (
    AgentToolCall,
    ChatRequest,
    ChatStreamEvent,
    Citation,
    friendly_tool_name,
)
from app.domain.documents.models import Document, DocumentSource
from app.infra.llm import LLMProvider
from app.infra.storage import StorageClient

logger = logging.getLogger(__name__)

# Maximum ReAct iterations before forcing a final answer.
MAX_REACT_ITERATIONS = 5

SYSTEM_PROMPT = """You are DingDong RAG, an intelligent knowledge assistant. You have access to a knowledge graph and document embeddings to answer questions accurately.

## Your Capabilities
You have access to the following retrieval tools:
{tool_descriptions}

## Instructions
1. **Always narrate your reasoning.** Before calling any tool, briefly explain what you are about to do and why (1-2 sentences). After receiving results, briefly note what you found before deciding your next step.
2. Prefer `hybrid_search` as your primary retrieval method — it combines both graph and vector results.
3. Use `graph_search` when the question is about specific entities, relationships, or structured knowledge.
4. Use `vector_search` when you need raw document passages or factual details.
5. You may call multiple tools if needed for multi-hop reasoning.
6. After receiving tool results, decide if you have enough information to answer or if you need another search.
7. ALWAYS cite your sources. Include document names, page numbers, and entity names in your response.
8. If the search results don't contain enough information, say so honestly.

## Narration Style
- Keep narration short and natural: "Let me search for..." / "I found several relevant passages. Let me also check..."
- Do NOT repeat the user's question back to them.
- When you have enough information, provide your final answer directly — no need to announce it.

## Response Format
- Be concise but thorough.
- Use markdown formatting where appropriate.
- Always mention your sources inline (e.g., "According to [Document Name, p.3]...")."""


class RAGAgent(IRAGAgent):
    """Agentic RAG with native function calling and parallel tool execution.

    Flow per user message:
    1. Build system prompt with tool specs.
    2. ReAct loop (up to MAX_REACT_ITERATIONS):
       a. Call LLM with ``tools=tool_specs`` (native function calling).
       b. If LLM returns tool_calls → execute all in parallel with asyncio.gather.
       c. Append tool results to messages and loop.
       d. If LLM returns text → loop done.
    3. Stream the final answer from the LLM's last text response.
    4. Emit citation events extracted from tool results.
    """

    def __init__(
        self,
        llm: LLMProvider,
        chat_service: IChatService,
        tools: list[IAgentTool],
        db: AsyncSession | None = None,
        model_override: str | None = None,
    ) -> None:
        self._llm = llm
        self._chat = chat_service
        self._tools = {tool.name: tool for tool in tools}
        self._db = db
        self._model_override = model_override

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def chat(
        self,
        request: ChatRequest,
        user_id: uuid.UUID,
    ) -> AsyncGenerator[ChatStreamEvent, None]:
        """Process chat request with narrative streaming.

        Yields SSE events in real-time as the agent reasons:
        - ``thinking``: reasoning text tokens (streamed)
        - ``tool_start``: tool call initiated
        - ``tool_result``: tool call completed
        - ``token``: final answer tokens (streamed)
        - ``citation``: source citations
        - ``done``: completion metadata
        """
        try:
            # Get or create conversation
            conversation_id = request.conversation_id
            if not conversation_id:
                conv = await self._chat.create_conversation(user_id)
                conversation_id = conv.id
                yield ChatStreamEvent(
                    event="conversation_created",
                    data=json.dumps({"conversation_id": str(conversation_id)}),
                )

            # Save user message
            await self._chat.add_message(
                conversation_id=conversation_id,
                role="user",
                content=request.message,
            )

            # Get conversation history
            history = await self._chat.get_messages(
                conversation_id, user_id, limit=20
            )

            # Build tool descriptions for system prompt
            tool_desc = "\n".join(
                f"- **{name}**: {tool.description}"
                for name, tool in self._tools.items()
            )
            system_prompt = SYSTEM_PROMPT.format(tool_descriptions=tool_desc)

            # Build initial message list
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt}
            ]
            for msg in history:
                messages.append({"role": msg.role, "content": msg.content})

            # Build native tool specs once
            tool_specs = [self._tool_to_spec(t) for t in self._tools.values()]

            # Narrative ReAct loop — yields SSE events in real-time.
            # Mutable lists are populated by the generator as a side-channel
            # (avoids JSON round-tripping internal events).
            accumulated_answer = ""
            all_tool_results: list[dict[str, Any]] = []
            tool_call_records: list[AgentToolCall] = []

            async for event in self._narrative_react_loop(
                messages=messages,
                tool_specs=tool_specs,
                tool_results_out=all_tool_results,
                tool_records_out=tool_call_records,
            ):
                if event.event == "token":
                    accumulated_answer += event.data
                yield event

            # Extract and emit citations from tool results
            citations = self._extract_citations(all_tool_results)
            await self._enrich_citations(citations)

            for citation in citations:
                yield ChatStreamEvent(
                    event="citation",
                    data=json.dumps(citation.model_dump(), default=str),
                )

            # Save assistant message
            await self._chat.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=accumulated_answer,
                citations=citations if citations else None,
                tool_calls=[tc.model_dump() for tc in tool_call_records] if tool_call_records else None,
            )

            # Update conversation title from first user message
            if len(history) <= 1:
                await self._chat.update_conversation_title(
                    conversation_id=conversation_id,
                    title=request.message[:80],
                )

            yield ChatStreamEvent(
                event="done",
                data=json.dumps({
                    "conversation_id": str(conversation_id),
                    "citations_count": len(citations),
                    "tools_used": [tc.tool_name for tc in tool_call_records],
                }),
            )

        except Exception as e:
            logger.exception("Agent execution failed: %s", e)
            yield ChatStreamEvent(
                event="error",
                data=json.dumps({"error": str(e)}),
            )

    # ------------------------------------------------------------------
    # Narrative ReAct loop (streams events in real-time)
    # ------------------------------------------------------------------

    async def _narrative_react_loop(
        self,
        messages: list[dict[str, Any]],
        tool_specs: list[dict[str, Any]],
        tool_results_out: list[dict[str, Any]],
        tool_records_out: list[AgentToolCall],
    ) -> AsyncGenerator[ChatStreamEvent, None]:
        """ReAct loop that yields SSE events as they happen.

        For each iteration the LLM response is **buffered** first so we
        can determine whether tool_calls are present before emitting:

        * tool_calls present → emit buffered text as ``thinking``, then
          ``tool_start`` / ``tool_result`` for each tool.
        * no tool_calls → emit buffered text as ``token`` (final answer).

        Side-channel outputs (tool results for citation extraction and
        tool call records) are appended to the caller-provided mutable
        lists instead of being smuggled through internal SSE events.
        """
        for _ in range(MAX_REACT_ITERATIONS):
            try:
                stream = await self._llm.complete(
                    messages=messages,
                    model=self._model_override,
                    tools=tool_specs,
                    tool_choice="auto",
                    temperature=0.0,
                    max_tokens=2000,
                    stream=True,
                )
            except Exception as e:
                logger.warning("LLM call failed in ReAct loop: %s", e)
                break

            # ── Buffer the full response before deciding event types ──
            content_text = ""
            tool_calls_by_index: dict[int, dict[str, Any]] = {}

            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                if delta.content:
                    content_text += delta.content

                if getattr(delta, "tool_calls", None):
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_by_index:
                            tool_calls_by_index[idx] = {
                                "id": "",
                                "function": {"name": "", "arguments": ""},
                            }
                        entry = tool_calls_by_index[idx]
                        if tc_delta.id:
                            entry["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                entry["function"]["name"] += tc_delta.function.name
                            if tc_delta.function.arguments:
                                entry["function"]["arguments"] += tc_delta.function.arguments

            # ── Now we know what this iteration produced ──
            raw_tool_calls = list(tool_calls_by_index.values()) if tool_calls_by_index else None

            # Build assistant message entry for the conversation history
            assistant_entry: dict[str, Any] = {
                "role": "assistant",
                "content": content_text,
            }
            if raw_tool_calls:
                assistant_entry["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": tc["function"],
                    }
                    for tc in raw_tool_calls
                ]
            messages.append(assistant_entry)

            if not raw_tool_calls:
                # ── Final answer: emit buffered text as `token` ──
                if content_text:
                    yield ChatStreamEvent(event="token", data=content_text)
                break

            # ── Tool iteration: emit buffered text as `thinking` ──
            if content_text:
                yield ChatStreamEvent(event="thinking", data=content_text)

            # Parse tool call arguments
            parsed_calls: list[tuple[str, str, dict[str, Any], str]] = []
            for tc in raw_tool_calls:
                tool_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                label = friendly_tool_name(tool_name)
                parsed_calls.append((tc["id"], tool_name, args, label))

            # Emit all tool_start events up front
            for _, tool_name, args, label in parsed_calls:
                yield ChatStreamEvent(
                    event="tool_start",
                    data=json.dumps({
                        "tool_name": tool_name,
                        "tool_label": label,
                        "arguments": args,
                    }),
                )

            # Execute all tool calls in parallel
            async def _exec(call_id: str, name: str, args: dict, label: str) -> tuple[str, str, dict, str, dict[str, Any] | None, str | None, int]:
                start = time.time()
                if name not in self._tools:
                    logger.warning("Unknown tool requested: %s", name)
                    return call_id, name, args, label, None, f"unknown tool: {name}", 0
                try:
                    result = await self._tools[name].execute(**args)
                    elapsed = int((time.time() - start) * 1000)
                    return call_id, name, args, label, result, None, elapsed
                except Exception as e:
                    elapsed = int((time.time() - start) * 1000)
                    logger.warning("Tool %s failed: %s", name, e)
                    return call_id, name, args, label, None, str(e), elapsed

            outcomes = await asyncio.gather(
                *[_exec(cid, n, a, l) for cid, n, a, l in parsed_calls],
            )

            # Emit tool_result events and collect side-channel data
            for call_id, tool_name, args, label, result, error, elapsed_ms in outcomes:
                count = result.get("count", 0) if result else 0
                summary = f"Found {count} results" if result else f"Error: {error}"

                yield ChatStreamEvent(
                    event="tool_result",
                    data=json.dumps({
                        "tool_name": tool_name,
                        "tool_label": label,
                        "summary": summary,
                        "count": count,
                        "duration_ms": elapsed_ms,
                        "error": error,
                    }),
                )

                # Side-channel: populate caller's lists directly
                if result is not None:
                    tool_results_out.append(result)
                tool_records_out.append(AgentToolCall(
                    tool_name=tool_name,
                    arguments=args,
                    result_summary=summary,
                    duration_ms=elapsed_ms,
                ))

                # Append tool result to messages so LLM sees the observation
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(result) if result is not None else f"Error: {error}",
                })

    # ------------------------------------------------------------------
    # Citation extraction from tool results
    # ------------------------------------------------------------------

    def _extract_citations(self, tool_results: list[dict[str, Any]]) -> list[Citation]:
        """Build Citation objects from accumulated tool results."""
        citations: list[Citation] = []

        for result in tool_results:
            for item in result.get("result", []):
                if not isinstance(item, dict):
                    continue

                content = item.get("content", "")
                if not content and item.get("entity_name"):
                    content = (
                        f"{item['entity_name']} ({item.get('entity_type', '')}): "
                        f"{item.get('description', '')}"
                    )

                if content:
                    citation = Citation(
                        content_snippet=content[:200],
                        source_type=result.get("source", "unknown"),
                        relevance_score=item.get(
                            "similarity", item.get("score", item.get("relevance", 0.0))
                        ),
                    )
                    if item.get("document_id"):
                        citation.document_id = (
                            uuid.UUID(item["document_id"])
                            if isinstance(item["document_id"], str)
                            else item["document_id"]
                        )
                    if item.get("chunk_id"):
                        citation.chunk_id = (
                            uuid.UUID(item["chunk_id"])
                            if isinstance(item["chunk_id"], str)
                            else item["chunk_id"]
                        )
                    if item.get("entity_id"):
                        citation.entity_id = (
                            uuid.UUID(item["entity_id"])
                            if isinstance(item["entity_id"], str)
                            else item["entity_id"]
                        )
                    if item.get("entity_name"):
                        citation.entity_name = item["entity_name"]
                    if (item.get("metadata") or {}).get("page_number"):
                        citation.page_number = item["metadata"]["page_number"]

                    citations.append(citation)

        return citations

    # ------------------------------------------------------------------
    # (removed: _call_tool and _generate_response_stream — now inlined
    #  in _narrative_react_loop for real-time streaming)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Citation enrichment
    # ------------------------------------------------------------------

    async def _enrich_citations(self, citations: list[Citation]) -> None:
        """Populate document_name and source_url on each citation."""
        if not self._db or not citations:
            return

        doc_ids = list({c.document_id for c in citations if c.document_id})
        if not doc_ids:
            return

        result = await self._db.execute(
            select(Document).where(Document.id.in_(doc_ids))
        )
        docs_by_id = {doc.id: doc for doc in result.scalars().all()}

        storage = StorageClient()

        for citation in citations:
            doc = docs_by_id.get(citation.document_id)  # type: ignore[arg-type]
            if not doc:
                continue

            citation.document_name = doc.filename

            if doc.source == DocumentSource.GOOGLE_DRIVE:
                drive_file_id = (doc.metadata_ or {}).get("drive_file_id")
                if drive_file_id:
                    citation.source_url = (
                        f"https://drive.google.com/file/d/{drive_file_id}/view"
                    )
            elif doc.storage_path:
                try:
                    citation.source_url = await storage.get_signed_url(
                        doc.storage_path, expires_in=3600
                    )
                except Exception:
                    logger.warning(
                        "Failed to generate signed URL for %s", doc.storage_path
                    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _tool_to_spec(self, tool: IAgentTool) -> dict[str, Any]:
        """Convert an IAgentTool to an OpenAI-format function calling spec."""
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters_schema,
            },
        }
