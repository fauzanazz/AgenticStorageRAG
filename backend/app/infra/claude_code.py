"""Claude Code agent — wraps the local ``claude`` CLI binary via claude-agent-sdk.

Uses whatever authentication the CLI already has (``claude /login``).
No API keys needed — the SDK spawns the binary as a subprocess.

Uses ``include_partial_messages=True`` for real token-level streaming
via ``StreamEvent`` objects carrying ``content_block_delta`` / ``text_delta``.
Tool lifecycle is tracked via ``content_block_start`` / ``content_block_stop``.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
import traceback
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.agents.interfaces import IAgentTool, IChatService, IRAGAgent
from app.domain.agents.schemas import (
    AgentToolCall,
    ChatRequest,
    ChatStreamEvent,
    Citation,
    friendly_tool_name,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def check_claude_binary() -> tuple[bool, str | None]:
    """Check if the ``claude`` CLI binary is available.

    Returns ``(available, version_string)``.
    """
    path = shutil.which("claude")
    if not path:
        return False, None
    try:
        result = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        version = result.stdout.strip() or result.stderr.strip()
        return True, version
    except Exception:
        return True, None


def _wrap_tools_as_mcp(
    tools: list[IAgentTool],
    results_sink: list[dict[str, Any]],
    records_sink: list[AgentToolCall],
) -> list[Any]:
    """Dynamically create ``@tool``-decorated wrappers for each IAgentTool.

    Tool results are pushed into *results_sink* and *records_sink* as a
    side-channel so the agent can extract citations and emit ``tool_result``
    SSE events.

    Each handler catches *all* exceptions and returns an MCP error response
    instead of letting them propagate — this prevents the SDK's internal
    TaskGroup from crashing when one tool fails during parallel execution.
    """
    from claude_agent_sdk import tool as sdk_tool

    wrapped: list[Any] = []
    for agent_tool in tools:
        schema = agent_tool.parameters_schema
        props = schema.get("properties", {})
        param_types: dict[str, type] = {}
        type_map = {"string": str, "integer": int, "number": float, "boolean": bool}
        for param_name, param_def in props.items():
            json_type = param_def.get("type", "string")
            param_types[param_name] = type_map.get(json_type, str)

        _tool = agent_tool

        @sdk_tool(_tool.name, _tool.description, param_types)
        async def _handler(args: dict[str, Any], __tool: IAgentTool = _tool) -> dict[str, Any]:
            start = time.time()
            try:
                result = await __tool.execute(**args)
                elapsed = int((time.time() - start) * 1000)
                count = result.get("count", 0) if result else 0
                results_sink.append(result)
                records_sink.append(
                    AgentToolCall(
                        tool_name=__tool.name,
                        arguments=args,
                        result_summary=f"Found {count} results",
                        duration_ms=elapsed,
                        results=_truncate_items(result),
                    )
                )
                return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}
            except Exception as e:
                elapsed = int((time.time() - start) * 1000)
                logger.warning(
                    "MCP tool %s failed: %s\n%s",
                    __tool.name,
                    e,
                    traceback.format_exc(),
                )
                records_sink.append(
                    AgentToolCall(
                        tool_name=__tool.name,
                        arguments=args,
                        result_summary=f"Error: {e}",
                        duration_ms=elapsed,
                        results=[],
                    )
                )
                # Return error as content — do NOT raise, or the SDK's
                # TaskGroup will abort all sibling tool calls.
                return {
                    "content": [{"type": "text", "text": f"Error: {e}"}],
                    "is_error": True,
                }

        wrapped.append(_handler)
    return wrapped


def _truncate_items(result: dict[str, Any]) -> list[dict]:
    """Truncate content fields in tool results for SSE payloads."""
    raw_items = result.get("result", [])
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    truncated: list[dict] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        for key in ("content", "description"):
            if key in entry and isinstance(entry[key], str) and len(entry[key]) > 200:
                entry[key] = entry[key][:200] + "..."
        truncated.append(entry)
    return truncated


# Set of our RAG tool names — used to filter out SDK-internal tool calls.
_RAG_TOOL_NAMES = {"hybrid_search", "generate_document", "fetch_document"}


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are DriveRAG, an intelligent knowledge assistant. You have access to a knowledge graph and document embeddings to answer questions accurately.

## Your Capabilities
You have access to retrieval tools registered as MCP tools. Use them to search the knowledge base, fetch documents, and generate reports.

## Language
- **Detect the user's language** from their message and **always respond in that same language**.
- **Search queries must be in English.** Reformulate queries in English for best retrieval quality, then present results in the user's language.
- **Technical terms** should remain in their original form.

## Instructions
1. **Always narrate your reasoning.** Before calling any tool, briefly explain what you are about to do and why.
2. Always use `hybrid_search` — it combines both knowledge graph and vector results.
3. You may call the tool multiple times if needed for multi-hop reasoning.
4. ALWAYS cite your sources with document names, page numbers, and entity names.
5. If search results don't contain enough information, say so honestly.
6. Use `generate_document` for long-form content creation.
7. Use `fetch_document` to retrieve full document content.

## Response Format
- Be concise but thorough.
- Use markdown formatting where appropriate.
- Always mention your sources inline.
- Use LaTeX notation for math: $$E = mc^2$$"""


# ---------------------------------------------------------------------------
# ClaudeCodeAgent
# ---------------------------------------------------------------------------


class ClaudeCodeAgent(IRAGAgent):
    """RAG agent powered by the Claude Agent SDK.

    Delegates the full ReAct loop to the SDK, which spawns the local
    ``claude`` CLI binary. Our RAG tools are registered as MCP tools.

    Uses ``include_partial_messages=True`` for real token-level streaming
    via ``StreamEvent`` objects.
    """

    def __init__(
        self,
        chat_service: IChatService,
        tools: list[IAgentTool],
        db: AsyncSession | None = None,
    ) -> None:
        self._chat = chat_service
        self._tools = tools
        self._tools_by_name = {t.name: t for t in tools}
        self._db = db

    async def chat(
        self,
        request: ChatRequest,
        user_id: uuid.UUID,
    ) -> AsyncGenerator[ChatStreamEvent, None]:
        """Process a chat request via the Claude Agent SDK with real streaming."""
        from claude_agent_sdk import (
            ClaudeAgentOptions,
            ResultMessage,
            create_sdk_mcp_server,
            query,
        )
        from claude_agent_sdk.types import StreamEvent

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

            # Get conversation history
            history = await self._chat.get_messages(conversation_id, user_id, limit=20)

            # Save user message
            user_msg = await self._chat.add_message(
                conversation_id=conversation_id,
                role="user",
                content=request.message,
            )
            yield ChatStreamEvent(
                event="message_created",
                data=json.dumps(
                    {
                        "message_id": str(user_msg.id),
                        "role": "user",
                    }
                ),
            )

            # Build conversation context as a structured prompt
            prompt_parts: list[str] = []
            for hist_msg in history:
                prefix = "User" if hist_msg.role == "user" else "Assistant"
                prompt_parts.append(f"{prefix}: {hist_msg.content}")
            prompt_parts.append(f"User: {request.message}")
            full_prompt = "\n\n".join(prompt_parts)

            # Side-channel sinks — populated by MCP tool wrappers during execution
            all_tool_results: list[dict[str, Any]] = []
            tool_call_records: list[AgentToolCall] = []

            # Register RAG tools as MCP tools with side-channel capture
            mcp_tools = _wrap_tools_as_mcp(self._tools, all_tool_results, tool_call_records)
            rag_server = create_sdk_mcp_server(
                name="rag",
                version="1.0.0",
                tools=mcp_tools,
            )

            # Build allowed tool names
            allowed_tools = [f"mcp__rag__{t.name}" for t in self._tools]

            options = ClaudeAgentOptions(
                system_prompt=SYSTEM_PROMPT,
                max_turns=5,
                mcp_servers={"rag": rag_server},
                allowed_tools=allowed_tools,
                include_partial_messages=True,
            )

            # State for streaming tool lifecycle
            accumulated_answer = ""
            narrative_steps: list[dict[str, Any]] = []
            emitted_tool_idx = 0
            in_tool = False
            current_tool_name: str | None = None
            tool_input_json = ""

            try:
                async for msg in query(prompt=full_prompt, options=options):
                    # ── Real token-level streaming via StreamEvent ──
                    if isinstance(msg, StreamEvent):
                        event = msg.event
                        event_type = event.get("type")

                        if event_type == "content_block_start":
                            content_block = event.get("content_block", {})
                            if content_block.get("type") == "tool_use":
                                raw_name = content_block.get("name", "")
                                tool_name = raw_name.removeprefix("mcp__rag__")
                                if tool_name in _RAG_TOOL_NAMES:
                                    in_tool = True
                                    current_tool_name = tool_name
                                    tool_input_json = ""

                        elif event_type == "content_block_delta":
                            delta = event.get("delta", {})
                            delta_type = delta.get("type")

                            if delta_type == "text_delta" and not in_tool:
                                text = delta.get("text", "")
                                if text:
                                    accumulated_answer += text
                                    yield ChatStreamEvent(event="token", data=text)

                            elif delta_type == "input_json_delta" and in_tool:
                                tool_input_json += delta.get("partial_json", "")

                        elif event_type == "content_block_stop":
                            if in_tool and current_tool_name:
                                try:
                                    tool_args = (
                                        json.loads(tool_input_json) if tool_input_json else {}
                                    )
                                except json.JSONDecodeError:
                                    tool_args = {}

                                label = friendly_tool_name(current_tool_name)

                                # Flush pre-tool text as narration
                                if accumulated_answer.strip():
                                    narrative_steps.append(
                                        {"type": "narration", "content": accumulated_answer}
                                    )
                                    accumulated_answer = ""

                                narrative_steps.append(
                                    {
                                        "type": "tool_call",
                                        "tool_name": current_tool_name,
                                        "tool_label": label,
                                        "tool_args": tool_args,
                                        "tool_status": "running",
                                    }
                                )

                                yield ChatStreamEvent(
                                    event="tool_start",
                                    data=json.dumps(
                                        {
                                            "tool_name": current_tool_name,
                                            "tool_label": label,
                                            "arguments": tool_args,
                                        }
                                    ),
                                )

                                while emitted_tool_idx < len(tool_call_records):
                                    rec = tool_call_records[emitted_tool_idx]
                                    # Update the corresponding narrative step
                                    for step in reversed(narrative_steps):
                                        if (
                                            step["type"] == "tool_call"
                                            and step.get("tool_name") == rec.tool_name
                                            and step.get("tool_status") == "running"
                                        ):
                                            step["tool_status"] = "done"
                                            step["tool_summary"] = rec.result_summary
                                            step["tool_duration_ms"] = rec.duration_ms
                                            step["tool_results"] = rec.results
                                            break
                                    yield ChatStreamEvent(
                                        event="tool_result",
                                        data=json.dumps(
                                            {
                                                "tool_name": rec.tool_name,
                                                "tool_label": friendly_tool_name(rec.tool_name),
                                                "summary": rec.result_summary,
                                                "count": len(rec.results),
                                                "duration_ms": rec.duration_ms,
                                                "error": None,
                                                "results": rec.results,
                                            }
                                        ),
                                    )
                                    emitted_tool_idx += 1

                                in_tool = False
                                current_tool_name = None
                                tool_input_json = ""

                    elif isinstance(msg, ResultMessage):
                        logger.info(
                            "Claude Code query complete: cost=$%.4f, duration=%dms",
                            msg.total_cost_usd,
                            msg.duration_ms,
                        )
            except BaseException as sdk_err:
                # The SDK raises ExceptionGroup / CLIConnectionError when the
                # CLI subprocess transport tears down before all MCP responses
                # are relayed.  This is a known SDK issue — the content and
                # tool results have already been streamed successfully, so we
                # log the error and continue with what we have.
                is_transport_err = (
                    "CLIConnectionError" in str(type(sdk_err).__mro__)
                    or "ProcessTransport is not ready" in str(sdk_err)
                    or "TaskGroup" in str(sdk_err)
                )
                if is_transport_err:
                    logger.warning(
                        "SDK transport error (non-fatal, continuing with streamed content): %s",
                        sdk_err,
                    )
                else:
                    raise

            # Emit any remaining tool_result events
            while emitted_tool_idx < len(tool_call_records):
                rec = tool_call_records[emitted_tool_idx]
                for step in reversed(narrative_steps):
                    if (
                        step["type"] == "tool_call"
                        and step.get("tool_name") == rec.tool_name
                        and step.get("tool_status") == "running"
                    ):
                        step["tool_status"] = "done"
                        step["tool_summary"] = rec.result_summary
                        step["tool_duration_ms"] = rec.duration_ms
                        step["tool_results"] = rec.results
                        break
                yield ChatStreamEvent(
                    event="tool_result",
                    data=json.dumps(
                        {
                            "tool_name": rec.tool_name,
                            "tool_label": friendly_tool_name(rec.tool_name),
                            "summary": rec.result_summary,
                            "count": len(rec.results),
                            "duration_ms": rec.duration_ms,
                            "error": None,
                            "results": rec.results,
                        }
                    ),
                )
                emitted_tool_idx += 1

            # Extract and emit citations
            citations = self._extract_citations(all_tool_results)
            if self._db:
                await self._enrich_citations(citations)

            for citation in citations:
                yield ChatStreamEvent(
                    event="citation",
                    data=json.dumps(citation.model_dump(), default=str),
                )

            # Save assistant message
            assistant_msg = await self._chat.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=accumulated_answer,
                citations=citations if citations else None,
                tool_calls=[tc.model_dump() for tc in tool_call_records]
                if tool_call_records
                else None,
                steps=narrative_steps if narrative_steps else None,
            )
            yield ChatStreamEvent(
                event="message_created",
                data=json.dumps(
                    {
                        "message_id": str(assistant_msg.id),
                        "role": "assistant",
                    }
                ),
            )

            # Auto-generate title for first exchange
            if len(history) == 0:
                import asyncio

                asyncio.get_running_loop().create_task(
                    self._generate_title(
                        conversation_id=conversation_id,
                        user_message=request.message,
                        assistant_message=accumulated_answer,
                    )
                )

            yield ChatStreamEvent(
                event="done",
                data=json.dumps(
                    {
                        "conversation_id": str(conversation_id),
                        "citations_count": len(citations),
                        "tools_used": [tc.tool_name for tc in tool_call_records],
                    }
                ),
            )

        except Exception as e:
            logger.exception("Claude Code agent execution failed: %s", e)
            yield ChatStreamEvent(
                event="error",
                data=json.dumps({"error": str(e)}),
            )

    # ------------------------------------------------------------------
    # Citation extraction (reused from RAGAgent)
    # ------------------------------------------------------------------

    def _extract_citations(self, tool_results: list[dict[str, Any]]) -> list[Citation]:
        """Build Citation objects from accumulated tool results."""
        citations: list[Citation] = []

        for result in tool_results:
            items = result.get("result", [])
            if isinstance(items, dict):
                items = [items]
            for item in items:
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
    # Citation enrichment
    # ------------------------------------------------------------------

    async def _enrich_citations(self, citations: list[Citation]) -> None:
        """Populate document_name and source_url on each citation."""
        if not self._db or not citations:
            return

        from sqlalchemy import select

        from app.domain.documents.models import Document, DocumentSource
        from app.infra.storage import StorageClient

        doc_ids = list({c.document_id for c in citations if c.document_id})
        if not doc_ids:
            return

        result = await self._db.execute(select(Document).where(Document.id.in_(doc_ids)))
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
                    citation.source_url = f"https://drive.google.com/file/d/{drive_file_id}/view"
            elif doc.storage_path:
                try:
                    citation.source_url = await storage.get_signed_url(
                        doc.storage_path, expires_in=3600
                    )
                except Exception:
                    logger.warning("Failed to generate signed URL for %s", doc.storage_path)

    # ------------------------------------------------------------------
    # Title generation
    # ------------------------------------------------------------------

    async def _generate_title(
        self,
        conversation_id: uuid.UUID,
        user_message: str,
        assistant_message: str,
    ) -> None:
        """Generate a concise conversation title using the global LLM provider."""
        from app.domain.agents.chat_service import ChatService
        from app.infra.database import get_db_session
        from app.infra.llm import llm_provider

        title = user_message[:80]
        try:
            response = await llm_provider.complete(
                model=llm_provider.title_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Generate a short title (max 80 chars) summarizing this conversation. "
                            "Use the same language as the conversation. "
                            "Return ONLY the title, no quotes or extra text."
                        ),
                    },
                    {"role": "user", "content": user_message[:500]},
                    {"role": "assistant", "content": assistant_message[:500]},
                ],
                max_tokens=40,
                temperature=0.0,
                stream=False,
            )
            generated = response.choices[0].message.content.strip().strip("\"'")[:80]
            if generated:
                title = generated
        except Exception as e:
            logger.warning("Title generation failed, using fallback: %s", e)

        try:
            async for db in get_db_session():
                chat = ChatService(db=db)
                await chat.update_conversation_title(
                    conversation_id=conversation_id,
                    title=title,
                )
        except Exception as e:
            logger.warning("Title update failed: %s", e)
