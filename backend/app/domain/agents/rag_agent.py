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

SYSTEM_PROMPT = """You are OpenRAG, an intelligent knowledge assistant. You have access to a knowledge graph and document embeddings to answer questions accurately.

## Your Capabilities
You have access to the following retrieval tools:
{tool_descriptions}

## Language
- **Detect the user's language** from their message and **always respond in that same language** — including narration, final answer, and citation references.
- **Search queries must be in English.** The knowledge base is primarily in English. When the user writes in a non-English language, reformulate your tool call queries in English to maximize retrieval quality. Present the results back in the user's language.
- **Technical terms** (API names, proper nouns, product names, code identifiers) should remain in their original form — do not translate them.
- **Mixed-language input** (e.g., English technical terms in an Indonesian sentence): respond in the dominant language of the message.
- **Short or ambiguous messages** (e.g., "OK", "hi", a single word): match the language established in the conversation history. If there is no history, default to English.

## Instructions
1. **Always narrate your reasoning.** Before calling any tool, briefly explain what you are about to do and why (1-2 sentences). After receiving results, briefly note what you found before deciding your next step.
2. Always use `hybrid_search` — it combines both knowledge graph and vector results for comprehensive retrieval.
3. You may call the tool multiple times if needed for multi-hop reasoning.
4. After receiving tool results, decide if you have enough information to answer or if you need another search.
5. ALWAYS cite your sources. Include document names, page numbers, and entity names in your response.
6. If the search results don't contain enough information, say so honestly.
7. Use `generate_document` when the user asks you to create, write, draft, or generate a report, summary, analysis, or any long-form structured document. Also use it when your response would be better served as a standalone document (multi-section content, comparison tables, guides). You can search for information first, then pass it as context to the document generator.
8. Use `fetch_document` when the user explicitly asks to see, read, or retrieve the full content of a specific document (e.g., "show me the full report", "read the entire file", "get the complete document"). Pass the `document_id` from your search results or citations. For very large documents, the tool returns chunks instead — you can request more by calling it again with an incremented `chunk_offset`.

## Narration Style
- Keep narration short and natural: "Let me search for..." / "I found several relevant passages. Let me also check..."
- Do NOT repeat the user's question back to them.
- When you have enough information, provide your final answer directly — no need to announce it.

## Response Format
- Be concise but thorough.
- Use markdown formatting where appropriate.
- Always mention your sources inline (e.g., "According to [Document Name, p.3]...").
- When your response includes mathematical expressions, formulas, or equations, use LaTeX notation wrapped in double dollar signs: $$E = mc^2$$ for inline math, or on separate lines for display math."""


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
        - ``token``: text tokens (narration + final answer)
        - ``thinking``: real extended thinking blocks from the API
        - ``tool_start``: tool call initiated
        - ``tool_result``: tool call completed
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

            # Get conversation history FIRST (before adding the new message)
            history = await self._chat.get_messages(
                conversation_id, user_id, limit=20
            )

            # Save user message
            user_msg = await self._chat.add_message(
                conversation_id=conversation_id,
                role="user",
                content=request.message,
            )
            yield ChatStreamEvent(
                event="message_created",
                data=json.dumps({
                    "message_id": str(user_msg.id),
                    "role": "user",
                }),
            )

            # Build tool descriptions for system prompt
            tool_desc = "\n".join(
                f"- **{name}**: {tool.description}"
                for name, tool in self._tools.items()
            )
            system_prompt = SYSTEM_PROMPT.format(tool_descriptions=tool_desc)

            # Process attachments if present
            attachment_text = ""
            attachment_image_blocks: list[dict[str, Any]] = []
            if request.attachment_ids:
                if self._db is None:
                    raise ValueError("Database session required for processing attachments")
                from app.domain.agents.attachments import AttachmentService

                attachment_svc = AttachmentService(self._db)
                attachments = await attachment_svc.get_many(
                    request.attachment_ids, user_id
                )
                attachment_text, attachment_image_blocks = (
                    await attachment_svc.process_for_llm(attachments)
                )

            # Build initial message list
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt}
            ]
            for msg in history:
                messages.append({"role": msg.role, "content": msg.content})

            # Append current user message — use content blocks if attachments present
            if attachment_image_blocks or attachment_text:
                user_text = (
                    f"{attachment_text}\n\n{request.message}"
                    if attachment_text
                    else request.message
                )
                content_blocks: list[dict[str, Any]] = [
                    *attachment_image_blocks,
                    {"type": "text", "text": user_text},
                ]
                messages.append({"role": "user", "content": content_blocks})
            else:
                messages.append({"role": "user", "content": request.message})

            # Build native tool specs once
            tool_specs = [self._tool_to_spec(t) for t in self._tools.values()]

            # Narrative ReAct loop — yields SSE events in real-time.
            # Mutable lists are populated by the generator as a side-channel
            # (avoids JSON round-tripping internal events).
            accumulated_answer = ""
            all_tool_results: list[dict[str, Any]] = []
            tool_call_records: list[AgentToolCall] = []
            thinking_blocks: list[str] = []

            async for event in self._narrative_react_loop(
                messages=messages,
                tool_specs=tool_specs,
                tool_results_out=all_tool_results,
                tool_records_out=tool_call_records,
                enable_thinking=request.enable_thinking,
            ):
                if event.event == "token":
                    accumulated_answer += event.data
                elif event.event == "thinking":
                    thinking_blocks.append(event.data)
                yield event

            logger.debug(
                "react loop done: answer_len=%d, tool_results=%d, thinking=%d",
                len(accumulated_answer), len(all_tool_results), len(thinking_blocks),
            )

            # Extract and emit citations from tool results
            citations = self._extract_citations(all_tool_results)
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
                tool_calls=[tc.model_dump() for tc in tool_call_records] if tool_call_records else None,
                thinking_blocks=thinking_blocks if thinking_blocks else None,
            )
            yield ChatStreamEvent(
                event="message_created",
                data=json.dumps({
                    "message_id": str(assistant_msg.id),
                    "role": "assistant",
                }),
            )

            # Persist any generated artifacts
            for tr in all_tool_results:
                result_data = tr.get("result", {})
                if isinstance(result_data, dict) and result_data.get("artifact_id"):
                    try:
                        await self._chat.create_artifact(
                            conversation_id=conversation_id,
                            user_id=user_id,
                            title=result_data.get("title", "Untitled"),
                            content=result_data.get("content", ""),
                            type=result_data.get("type", "markdown"),
                            message_id=assistant_msg.id,
                        )
                    except Exception as e:
                        logger.warning("Failed to persist artifact: %s", e)

            # Auto-generate title from first exchange using a cheap mini model
            if len(history) == 0:
                asyncio.get_running_loop().create_task(
                    self._generate_title(
                        conversation_id=conversation_id,
                        user_message=request.message,
                        assistant_message=accumulated_answer,
                    )
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
            logger.debug("Agent execution FAILED: %s", e)
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
        enable_thinking: bool = False,
    ) -> AsyncGenerator[ChatStreamEvent, None]:
        """ReAct loop that yields SSE events as they happen.

        For each iteration the LLM response is **buffered** first so we
        can determine whether tool_calls are present before emitting:

        * tool_calls present → emit buffered text as ``token`` (narration),
          then ``tool_start`` / ``tool_result`` for each tool.
        * no tool_calls → emit buffered text as ``token`` (final answer).

        When ``enable_thinking`` is True, the LLM is called with extended
        thinking enabled.  Real reasoning tokens from the API are streamed
        as ``thinking`` SSE events.

        Side-channel outputs (tool results for citation extraction and
        tool call records) are appended to the caller-provided mutable
        lists instead of being smuggled through internal SSE events.
        """
        # Track whether thinking can be used. LiteLLM/Anthropic drops
        # thinking when the last assistant message has tool_calls but no
        # thinking_blocks, which causes hangs if max_tokens is too high.
        can_think = enable_thinking

        for iteration in range(MAX_REACT_ITERATIONS):
            thinking_kwargs: dict[str, Any] = {}
            if can_think:
                thinking_kwargs["thinking"] = {"type": "enabled", "budget_tokens": 10000}

            iter_max_tokens = 32000 if can_think else 8192

            logger.debug("=== ReAct iteration %d (thinking=%s, max_tokens=%d) ===", iteration, can_think, iter_max_tokens)
            try:
                stream = await self._llm.complete(
                    messages=messages,
                    model=self._model_override,
                    tools=tool_specs,
                    tool_choice="auto",
                    temperature=1.0 if can_think else 0.0,
                    max_tokens=iter_max_tokens,
                    stream=True,
                    **thinking_kwargs,
                )
            except Exception as e:
                logger.debug("LLM call FAILED iter %d: %s", iteration, e)
                logger.warning("LLM call failed in ReAct loop: %s", e)
                break

            # ── Stream the response, deciding event types on the fly ──
            #
            # Content tokens are streamed as `token` events immediately.
            # If the stream ends with tool_calls (finish_reason="tool_calls"),
            # we retroactively know the content was narration — emit a
            # `narration_end` marker so the frontend can reclassify.
            # If no tool_calls, the content was the final answer and was
            # already streamed incrementally.
            content_text = ""
            reasoning_text = ""
            tool_calls_by_index: dict[int, dict[str, Any]] = {}
            finish_reason: str | None = None
            streamed_any_content = False

            try:
                async for chunk in stream:
                    if chunk.choices:
                        fr = chunk.choices[0].finish_reason
                        if fr:
                            finish_reason = fr

                    delta = chunk.choices[0].delta if chunk.choices else None
                    if not delta:
                        continue

                    if delta.content:
                        content_text += delta.content
                        # Stream content tokens immediately
                        yield ChatStreamEvent(event="token", data=delta.content)
                        streamed_any_content = True

                    # Real extended thinking from the API (e.g. Anthropic reasoning_content)
                    reasoning_chunk = getattr(delta, "reasoning_content", None)
                    if reasoning_chunk and isinstance(reasoning_chunk, str):
                        reasoning_text += reasoning_chunk

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
            except Exception as stream_err:
                logger.warning("Stream error in ReAct loop iter %d: %s", iteration, stream_err)
                break

            # ── Emit real thinking blocks if present ──
            if reasoning_text:
                yield ChatStreamEvent(event="thinking", data=reasoning_text)

            # ── Now we know what this iteration produced ──
            raw_tool_calls = list(tool_calls_by_index.values()) if tool_calls_by_index else None

            # Build assistant message entry for the conversation history
            assistant_entry: dict[str, Any] = {
                "role": "assistant",
                "content": content_text,
            }
            if reasoning_text:
                assistant_entry["thinking"] = reasoning_text
            if raw_tool_calls:
                assistant_entry["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": tc["function"],
                    }
                    for tc in raw_tool_calls
                ]
                # Disable thinking for next iteration if this one had
                # tool_calls without thinking (LiteLLM will drop it).
                if not reasoning_text:
                    can_think = False
            messages.append(assistant_entry)

            if not raw_tool_calls:
                # Final answer — content was already streamed as `token` events
                if finish_reason == "length":
                    logger.warning("LLM response truncated (finish_reason=length)")
                break

            # ── Tool iteration: content was narration, tell frontend ──
            if streamed_any_content:
                yield ChatStreamEvent(
                    event="narration_end",
                    data=content_text,
                )

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

            # Execute all tool calls in parallel.
            # Tools that stream (e.g. generate_document) push SSE events
            # into a shared queue via the emit_event callback.
            tool_event_queue: asyncio.Queue[ChatStreamEvent] = asyncio.Queue()

            def _emit_tool_event(event_type: str, data_json: str) -> None:
                tool_event_queue.put_nowait(
                    ChatStreamEvent(event=event_type, data=data_json)
                )

            async def _exec(call_id: str, name: str, args: dict, label: str) -> tuple[str, str, dict, str, dict[str, Any] | None, str | None, int]:
                start = time.time()
                if name not in self._tools:
                    logger.warning("Unknown tool requested: %s", name)
                    return call_id, name, args, label, None, f"unknown tool: {name}", 0
                try:
                    result = await self._tools[name].execute(
                        emit_event=_emit_tool_event, **args
                    )
                    elapsed = int((time.time() - start) * 1000)
                    return call_id, name, args, label, result, None, elapsed
                except Exception as e:
                    elapsed = int((time.time() - start) * 1000)
                    logger.warning("Tool %s failed: %s", name, e)
                    return call_id, name, args, label, None, str(e), elapsed

            # Run tools and drain queued events concurrently
            async def _run_tools():
                return await asyncio.gather(
                    *[_exec(cid, n, a, l) for cid, n, a, l in parsed_calls],
                )

            tool_task = asyncio.create_task(_run_tools())

            # Drain tool-emitted SSE events while tools are running
            queue_get: asyncio.Task[ChatStreamEvent] | None = None
            while True:
                if queue_get is None:
                    queue_get = asyncio.create_task(tool_event_queue.get())
                done, _ = await asyncio.wait(
                    {tool_task, queue_get},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if queue_get in done:
                    yield queue_get.result()
                    queue_get = None
                if tool_task in done:
                    if queue_get is not None:
                        queue_get.cancel()
                    break

            outcomes = await tool_task

            # Drain any remaining queued events
            while not tool_event_queue.empty():
                yield tool_event_queue.get_nowait()

            # Emit tool_result events and collect side-channel data
            for call_id, tool_name, args, label, result, error, elapsed_ms in outcomes:
                count = result.get("count", 0) if result else 0
                summary = f"Found {count} results" if result else f"Error: {error}"

                # Truncate content fields for the SSE payload to keep it lean
                raw_items = result.get("result", []) if result else []
                if isinstance(raw_items, dict):
                    raw_items = [raw_items]
                truncated_items: list[dict] = []
                for item in raw_items:
                    entry = dict(item)
                    for key in ("content", "description"):
                        if key in entry and isinstance(entry[key], str) and len(entry[key]) > 200:
                            entry[key] = entry[key][:200] + "..."
                    truncated_items.append(entry)

                yield ChatStreamEvent(
                    event="tool_result",
                    data=json.dumps({
                        "tool_name": tool_name,
                        "tool_label": label,
                        "summary": summary,
                        "count": count,
                        "duration_ms": elapsed_ms,
                        "error": error,
                        "results": truncated_items,
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
                    results=truncated_items,
                ))

                # Append tool result to messages so LLM sees the observation
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(result) if result is not None else f"Error: {error}",
                })

    # ------------------------------------------------------------------
    # Title generation
    # ------------------------------------------------------------------

    async def _generate_title(
        self,
        conversation_id: uuid.UUID,
        user_message: str,
        assistant_message: str,
    ) -> None:
        """Generate a concise conversation title using a cheap mini model.

        Fire-and-forget — uses its own DB session since this runs as a
        background task after the request-scoped session is closed.
        """
        from app.domain.agents.chat_service import ChatService
        from app.infra.database import get_db_session

        title = user_message[:80]  # fallback
        try:
            response = await self._llm.complete(
                model=self._llm.title_model,
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
            generated = response.choices[0].message.content.strip().strip('"\'')[:80]
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

    # ------------------------------------------------------------------
    # Citation extraction from tool results
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
