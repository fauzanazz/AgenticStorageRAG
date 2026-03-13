"""RAG agent with autonomous tool selection.

Uses LangChain to orchestrate an agent that autonomously selects
retrieval strategies (graph, vector, hybrid), performs multi-hop
reasoning, and generates responses with citations.
"""

from __future__ import annotations

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

SYSTEM_PROMPT = """You are DingDong RAG, an intelligent knowledge assistant. You have access to a knowledge graph and document embeddings to answer questions accurately.

## Your Capabilities
You have access to the following tools:
{tool_descriptions}

## Instructions
1. When asked a question, FIRST search for relevant information using the appropriate tool(s).
2. Prefer `hybrid_search` as your primary retrieval method -- it combines both graph and vector results.
3. Use `graph_search` when the question is about specific entities, relationships, or structured knowledge.
4. Use `vector_search` when you need raw document passages or factual details.
5. You may call multiple tools if needed for multi-hop reasoning.
6. ALWAYS cite your sources. Include document names, page numbers, and entity names in your response.
7. If the search results don't contain enough information, say so honestly.
8. If the question is ambiguous, ask for clarification.

## Response Format
- Be concise but thorough.
- Use markdown formatting where appropriate.
- Always mention your sources inline (e.g., "According to [Document Name, p.3]...").
- If you used the knowledge graph, mention the entities and relationships you found."""


class RAGAgent(IRAGAgent):
    """Agentic RAG with autonomous tool selection and multi-hop reasoning.

    Flow:
    1. Receive user message + conversation history
    2. Build system prompt with tool descriptions
    3. Let LLM decide which tools to call
    4. Execute tool calls and collect results
    5. Let LLM synthesize a response with citations
    6. Stream response tokens to the client
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
            messages = await self._chat.get_messages(
                conversation_id, user_id, limit=20
            )

            # Build tool descriptions
            tool_desc = "\n".join(
                f"- **{name}**: {tool.description}"
                for name, tool in self._tools.items()
            )
            system_prompt = SYSTEM_PROMPT.format(tool_descriptions=tool_desc)

            # Build message history for LLM
            llm_messages: list[dict[str, str]] = [
                {"role": "system", "content": system_prompt}
            ]
            for msg in messages:
                llm_messages.append({"role": msg.role, "content": msg.content})

            # Phase 1: Let LLM decide on tool calls
            tool_results, tool_call_records = await self._execute_tool_phase(
                llm_messages, request
            )

            # Emit tool call events
            for tc in tool_call_records:
                yield ChatStreamEvent(
                    event="tool_call",
                    data=json.dumps(tc.model_dump()),
                )

            # Phase 2: Generate response with context
            response_text, citations = await self._generate_response(
                llm_messages, tool_results
            )

            # Stream the response token by token (simulate streaming for now)
            # In production, use actual LLM streaming
            words = response_text.split(" ")
            accumulated = ""
            for i, word in enumerate(words):
                token = word if i == 0 else f" {word}"
                accumulated += token
                yield ChatStreamEvent(event="token", data=token)

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

            # Update conversation title from first message
            if len(messages) <= 1:
                title = request.message[:80]
                # We'd update title here, but keeping service simple for now

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

    async def _execute_tool_phase(
        self,
        llm_messages: list[dict[str, str]],
        request: ChatRequest,
    ) -> tuple[list[dict[str, Any]], list[AgentToolCall]]:
        """Phase 1: Ask LLM what tools to call, then execute them."""
        tool_results: list[dict[str, Any]] = []
        tool_call_records: list[AgentToolCall] = []

        # Ask LLM to decide which tools to use
        planning_messages = llm_messages + [
            {
                "role": "user",
                "content": (
                    f"Based on the conversation, decide which tools to call to answer "
                    f"the latest question. Respond with a JSON array of tool calls:\n"
                    f'[{{"tool": "tool_name", "args": {{"query": "..."}}}}]\n'
                    f"If no tools are needed, respond with an empty array: []"
                ),
            },
        ]

        try:
            planning_response = await self._llm.complete(
                messages=planning_messages,
                temperature=0.0,
                max_tokens=500,
            )

            content = planning_response.choices[0].message.content or "[]"
            planned_calls = self._parse_tool_calls(content)

            # Execute each tool call
            for call in planned_calls:
                tool_name = call.get("tool", "")
                tool_args = call.get("args", {})

                if tool_name not in self._tools:
                    logger.warning("Unknown tool: %s", tool_name)
                    continue

                tool = self._tools[tool_name]
                start_time = time.time()

                try:
                    result = await tool.execute(**tool_args)
                    duration_ms = int((time.time() - start_time) * 1000)

                    tool_results.append(result)
                    tool_call_records.append(
                        AgentToolCall(
                            tool_name=tool_name,
                            arguments=tool_args,
                            result_summary=f"{result.get('count', 0)} results from {result.get('source', 'unknown')}",
                            duration_ms=duration_ms,
                        )
                    )
                except Exception as e:
                    logger.warning("Tool %s failed: %s", tool_name, e)
                    tool_call_records.append(
                        AgentToolCall(
                            tool_name=tool_name,
                            arguments=tool_args,
                            result_summary=f"Error: {e}",
                            duration_ms=int((time.time() - start_time) * 1000),
                        )
                    )

        except Exception as e:
            logger.warning("Tool planning phase failed: %s", e)

        # If no tools were called, do a default hybrid search
        if not tool_results and "hybrid_search" in self._tools:
            try:
                result = await self._tools["hybrid_search"].execute(
                    query=llm_messages[-1]["content"],
                    top_k=10,
                    vector_weight=request.vector_weight,
                )
                tool_results.append(result)
                tool_call_records.append(
                    AgentToolCall(
                        tool_name="hybrid_search",
                        arguments={"query": llm_messages[-1]["content"]},
                        result_summary=f"{result.get('count', 0)} results (fallback)",
                    )
                )
            except Exception as e:
                logger.warning("Fallback hybrid search failed: %s", e)

        return tool_results, tool_call_records

    async def _generate_response(
        self,
        llm_messages: list[dict[str, str]],
        tool_results: list[dict[str, Any]],
    ) -> tuple[str, list[Citation]]:
        """Phase 2: Generate response using tool results as context."""
        # Build context from tool results
        context_parts = []
        citations: list[Citation] = []

        for result in tool_results:
            for item in result.get("result", []):
                if isinstance(item, dict):
                    content = item.get("content", "")
                    if not content and item.get("entity_name"):
                        content = f"{item['entity_name']} ({item.get('entity_type', '')}): {item.get('description', '')}"

                    if content:
                        context_parts.append(content)

                        # Build citation
                        citation = Citation(
                            content_snippet=content[:200],
                            source_type=result.get("source", "unknown"),
                            relevance_score=item.get("similarity", item.get("score", item.get("relevance", 0.0))),
                        )
                        if item.get("document_id"):
                            citation.document_id = uuid.UUID(item["document_id"]) if isinstance(item["document_id"], str) else item["document_id"]
                        if item.get("chunk_id"):
                            citation.chunk_id = uuid.UUID(item["chunk_id"]) if isinstance(item["chunk_id"], str) else item["chunk_id"]
                        if item.get("entity_id"):
                            citation.entity_id = uuid.UUID(item["entity_id"]) if isinstance(item["entity_id"], str) else item["entity_id"]
                        if item.get("entity_name"):
                            citation.entity_name = item["entity_name"]
                        if item.get("metadata", {}).get("page_number"):
                            citation.page_number = item["metadata"]["page_number"]

                        citations.append(citation)

        # Build response messages
        context_text = "\n\n---\n\n".join(context_parts) if context_parts else "No relevant information found."

        response_messages = llm_messages + [
            {
                "role": "user",
                "content": (
                    f"Here is the retrieved context from the knowledge base:\n\n"
                    f"{context_text}\n\n"
                    f"Using this context, provide a comprehensive answer to the user's question. "
                    f"Cite your sources inline. If the context doesn't contain enough information, "
                    f"say so honestly."
                ),
            },
        ]

        response = await self._llm.complete_with_retry(
            messages=response_messages,
            temperature=0.3,
            max_tokens=2000,
        )

        response_text = response.choices[0].message.content or "I couldn't generate a response."
        return response_text, citations

    def _parse_tool_calls(self, text: str) -> list[dict[str, Any]]:
        """Parse tool calls from LLM response."""
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
            return []
        except json.JSONDecodeError:
            pass

        # Try extracting from code block
        if "```" in text:
            try:
                start = text.index("```") + 3
                if text[start:].startswith("json"):
                    start += 4
                end = text.index("```", start)
                result = json.loads(text[start:end].strip())
                if isinstance(result, list):
                    return result
            except (json.JSONDecodeError, ValueError):
                pass

        # Try finding JSON array
        bracket_start = text.find("[")
        bracket_end = text.rfind("]") + 1
        if bracket_start >= 0 and bracket_end > bracket_start:
            try:
                result = json.loads(text[bracket_start:bracket_end])
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass

        return []
