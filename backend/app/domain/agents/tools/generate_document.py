"""Document generation tool for the RAG agent.

Creates structured markdown documents as artifacts, streaming
content via the emit_event callback.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from app.domain.agents.interfaces import EventEmitter, IAgentTool
from app.infra.llm import LLMProvider

logger = logging.getLogger(__name__)

DOCUMENT_SYSTEM_PROMPT = """You are a document writer. Generate a well-structured markdown document based on the user's instructions.

## Rules
1. Output ONLY the document content in markdown format.
2. Use proper markdown structure: headings, lists, tables, code blocks as appropriate.
3. Do NOT include meta-commentary like "Here is the document" — just write the document itself.
4. Make the document comprehensive, well-organized, and professional.
5. If context from prior searches is provided, incorporate that information with proper attribution."""


class GenerateDocumentTool(IAgentTool):
    """Generate a structured markdown document as an artifact.

    The agent calls this tool when it needs to produce a long-form
    document such as a report, summary, analysis, or guide. Content
    is streamed to the frontend via artifact SSE events.
    """

    def __init__(self, llm: LLMProvider, model_override: str | None = None) -> None:
        self._llm = llm
        self._model_override = model_override

    @property
    def name(self) -> str:
        return "generate_document"

    @property
    def description(self) -> str:
        return (
            "Generate a structured markdown document (report, summary, analysis, guide, etc.). "
            "Use this tool when the user asks you to write, create, draft, or generate a document, "
            "report, summary, or any long-form structured content. Also use it when your response "
            "would benefit from being a standalone document rather than a chat message "
            "(e.g., multi-section analysis, comparison tables, guides). "
            "Input: title (str), instructions (str describing what to write), "
            "context (optional str with information from prior searches to incorporate)"
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title of the document to generate.",
                },
                "instructions": {
                    "type": "string",
                    "description": "Detailed instructions for what the document should contain.",
                },
                "context": {
                    "type": "string",
                    "description": "Optional context from prior search results to incorporate.",
                },
            },
            "required": ["title", "instructions"],
        }

    async def execute(self, emit_event: EventEmitter = None, **kwargs: Any) -> dict[str, Any]:
        """Generate a markdown document, streaming content via emit_event.

        Emits artifact_start, artifact_delta (chunks), and artifact_end events.
        Returns artifact metadata for the agent to reference.
        """
        title = kwargs.get("title", "Untitled Document")
        instructions = kwargs.get("instructions", "")
        context = kwargs.get("context", "")

        if not instructions:
            return {"result": {"error": "No instructions provided"}, "count": 0, "source": "generate_document"}

        artifact_id = str(uuid.uuid4())

        # Emit artifact_start
        if emit_event:
            emit_event(
                "artifact_start",
                json.dumps({"artifact_id": artifact_id, "title": title, "type": "markdown"}),
            )

        # Build the generation prompt
        user_prompt = f"## Document Title\n{title}\n\n## Instructions\n{instructions}"
        if context:
            user_prompt += f"\n\n## Context (from prior searches)\n{context}"

        messages = [
            {"role": "system", "content": DOCUMENT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        full_content = ""

        try:
            stream = await self._llm.complete(
                messages=messages,
                model=self._model_override,
                temperature=0.3,
                max_tokens=4000,
                stream=True,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta or not delta.content:
                    continue

                full_content += delta.content

                if emit_event:
                    emit_event(
                        "artifact_delta",
                        json.dumps({"artifact_id": artifact_id, "content": delta.content}),
                    )

        except Exception as e:
            logger.error("Document generation failed: %s", e)
            if emit_event:
                emit_event(
                    "artifact_end",
                    json.dumps({
                        "artifact_id": artifact_id,
                        "title": title,
                        "type": "markdown",
                        "content_length": len(full_content),
                        "error": str(e),
                    }),
                )
            return {"result": {"error": str(e)}, "count": 0, "source": "generate_document"}

        # Emit artifact_end
        if emit_event:
            emit_event(
                "artifact_end",
                json.dumps({
                    "artifact_id": artifact_id,
                    "title": title,
                    "type": "markdown",
                    "content_length": len(full_content),
                }),
            )

        return {
            "result": {
                "artifact_id": artifact_id,
                "title": title,
                "content": full_content,
                "type": "markdown",
            },
            "count": 1,
            "source": "generate_document",
        }
