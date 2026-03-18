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

from app.domain.agents.exceptions import AgentExecutionError
from app.domain.agents.interfaces import IAgentTool, IChatService, IRAGAgent
from app.domain.agents.schemas import (
    AgentToolCall,
    ChatRequest,
    ChatStreamEvent,
    Citation,
)
from app.infra.llm import LLMProvider

logger = logging.getLogger(__name__)

# Maximum ReAct iterations before forcing a final answer.
MAX_REACT_ITERATIONS = 5

SYSTEM_PROMPT = """You are DingDong RAG, an intelligent knowledge assistant. You have access to a knowledge graph and document embeddings to answer questions accurately.

## Your Capabilities
You have access to the following retrieval tools:
{tool_descriptions}

## Instructions
1. When asked a question, search for relevant information using the appropriate tool(s).
2. Prefer `hybrid_search` as your primary retrieval method — it combines both graph and vector results.
3. Use `graph_search` when the question is about specific entities, relationships, or structured knowledge.
4. Use `vector_search` when you need raw document passages or factual details.
5. You may call multiple tools if needed for multi-hop reasoning.
6. After receiving tool results, decide if you have enough information to answer or if you need another search.
7. ALWAYS cite your sources. Include document names, page numbers, and entity names in your response.
8. If the search results don't contain enough information, say so honestly.

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
    ) -> None:
        self._llm = llm
        self._chat = chat_service
        self._tools = {tool.name: tool for tool in tools}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def chat(
        self,
        request: ChatRequest,
        user_id: uuid.UUID,
    ) -> AsyncGenerator[ChatStreamEvent, None]:
        """Process chat request with autonomous tool selection."""
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

            # ReAct loop — mutates messages in place
            tool_results, tool_call_records = await self._react_loop(
                messages=messages,
                tool_specs=tool_specs,
                request=request,
            )

            # Emit tool call events
            for tc in tool_call_records:
                yield ChatStreamEvent(
                    event="tool_call",
                    data=json.dumps(tc.model_dump()),
                )

            # Stream final answer
            accumulated = ""
            citations: list[Citation] = []

            async for event in self._generate_response_stream(messages, tool_results):
                if event["type"] == "token":
                    accumulated += event["token"]
                    yield ChatStreamEvent(event="token", data=event["token"])
                elif event["type"] == "citations":
                    citations = event["citations"]

            # Emit citations
            for citation in citations:
                yield ChatStreamEvent(
                    event="citation",
                    data=json.dumps(citation.model_dump(), default=str),
                )

            # Save assistant message
            await self._chat.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=accumulated,
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
    # ReAct loop
    # ------------------------------------------------------------------

    async def _react_loop(
        self,
        messages: list[dict[str, Any]],
        tool_specs: list[dict[str, Any]],
        request: ChatRequest,
    ) -> tuple[list[dict[str, Any]], list[AgentToolCall]]:
        """Run the native-tool-calling ReAct loop.

        Mutates *messages* in place by appending assistant and tool turns.
        Returns the accumulated tool results and call records for use in
        the streaming response phase.
        """
        tool_results: list[dict[str, Any]] = []
        tool_call_records: list[AgentToolCall] = []

        for _iteration in range(MAX_REACT_ITERATIONS):
            try:
                response = await self._llm.complete(
                    messages=messages,
                    tools=tool_specs,
                    tool_choice="auto",
                    temperature=0.0,
                    max_tokens=1000,
                )
            except Exception as e:
                logger.warning("LLM call failed in ReAct loop: %s", e)
                break

            msg = response.choices[0].message

            # Append the assistant turn (may include tool_calls)
            assistant_entry: dict[str, Any] = {
                "role": "assistant",
                "content": msg.content or "",
            }
            raw_tool_calls = getattr(msg, "tool_calls", None)
            if raw_tool_calls:
                assistant_entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in raw_tool_calls
                ]
            messages.append(assistant_entry)

            if not raw_tool_calls:
                # LLM chose not to call any tool — loop done
                break

            # Execute all tool calls in parallel
            outcomes = await asyncio.gather(
                *[self._call_tool(tc) for tc in raw_tool_calls],
                return_exceptions=False,
            )

            for call_id, tool_name, args, result, error in outcomes:
                if result is not None:
                    tool_results.append(result)
                    tool_call_records.append(
                        AgentToolCall(
                            tool_name=tool_name,
                            arguments=args,
                            result_summary=f"{result.get('count', 0)} results from {result.get('source', 'unknown')}",
                        )
                    )
                else:
                    tool_call_records.append(
                        AgentToolCall(
                            tool_name=tool_name,
                            arguments=args,
                            result_summary=f"Error: {error}",
                        )
                    )

                # Append tool result so LLM sees the observation
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(result) if result is not None else f"Error: {error}",
                })

        # Fallback: if no tools were called, run hybrid_search once
        if not tool_results and "hybrid_search" in self._tools:
            try:
                user_query = next(
                    (m["content"] for m in reversed(messages) if m.get("role") == "user"),
                    request.message,
                )
                result = await self._tools["hybrid_search"].execute(
                    query=user_query,
                    top_k=10,
                    vector_weight=request.vector_weight,
                )
                tool_results.append(result)
                tool_call_records.append(
                    AgentToolCall(
                        tool_name="hybrid_search",
                        arguments={"query": user_query},
                        result_summary=f"{result.get('count', 0)} results (fallback)",
                    )
                )
            except Exception as e:
                logger.warning("Fallback hybrid search failed: %s", e)

        return tool_results, tool_call_records

    async def _call_tool(
        self,
        tc: Any,
    ) -> tuple[str, str, dict[str, Any], dict[str, Any] | None, str | None]:
        """Execute a single tool call. Returns (call_id, name, args, result, error)."""
        tool_name = tc.function.name
        call_id = tc.id

        try:
            args = json.loads(tc.function.arguments) if tc.function.arguments else {}
        except json.JSONDecodeError:
            args = {}

        if tool_name not in self._tools:
            logger.warning("Unknown tool requested: %s", tool_name)
            return call_id, tool_name, args, None, f"unknown tool: {tool_name}"

        start = time.time()
        try:
            result = await self._tools[tool_name].execute(**args)
            elapsed_ms = int((time.time() - start) * 1000)
            logger.debug("Tool %s completed in %dms", tool_name, elapsed_ms)
            return call_id, tool_name, args, result, None
        except Exception as e:
            logger.warning("Tool %s failed: %s", tool_name, e)
            return call_id, tool_name, args, None, str(e)

    # ------------------------------------------------------------------
    # Response streaming
    # ------------------------------------------------------------------

    async def _generate_response_stream(
        self,
        messages: list[dict[str, Any]],
        tool_results: list[dict[str, Any]],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream the final answer.

        Appends a context synthesis request to messages, calls the LLM
        with streaming, and yields token / citations events.
        """
        # Build context text and collect citations from tool results
        context_parts: list[str] = []
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
                    context_parts.append(content)

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
                    if item.get("metadata", {}).get("page_number"):
                        citation.page_number = item["metadata"]["page_number"]

                    citations.append(citation)

        context_text = (
            "\n\n---\n\n".join(context_parts)
            if context_parts
            else "No relevant information found."
        )

        # Append final synthesis request
        response_messages = messages + [
            {
                "role": "user",
                "content": (
                    f"Here is the retrieved context from the knowledge base:\n\n"
                    f"{context_text}\n\n"
                    f"Using this context, provide a comprehensive answer to the user's "
                    f"question. Cite your sources inline. If the context doesn't contain "
                    f"enough information, say so honestly."
                ),
            }
        ]

        try:
            stream_response = await self._llm.complete(
                messages=response_messages,
                temperature=0.3,
                max_tokens=2000,
                stream=True,
            )
            async for chunk in stream_response:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield {"type": "token", "token": delta.content}

        except Exception as e:
            logger.error("Streaming response failed, falling back: %s", e)
            response = await self._llm.complete_with_retry(
                messages=response_messages,
                temperature=0.3,
                max_tokens=2000,
            )
            text = response.choices[0].message.content or "I couldn't generate a response."
            yield {"type": "token", "token": text}

        yield {"type": "citations", "citations": citations}

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
