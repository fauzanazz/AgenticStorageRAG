"""Ingestion orchestrator -- ReAct agent for Google Drive ingestion.

LLM-powered orchestrator that dynamically explores folder structures,
classifies file metadata, and ingests documents incrementally.

Architecture
~~~~~~~~~~~~
The orchestrator is a ReAct (Reason + Act) agent loop:

1.  The LLM receives a system prompt describing the task and available tools.
2.  At each step the LLM either:
    a. Calls one or more tools (scan_folder, classify_file, ingest_file,
       update_progress), OR
    b. Emits a final text message indicating the job is done.
3.  Tool results are appended to the conversation and the loop repeats.
4.  A hard cap on iterations prevents runaway loops.

Because the LLM drives the traversal, the agent adapts to ANY folder
structure -- no hardcoded rules about Major/Year/Course paths.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ingestion.exceptions import IngestionError
from app.domain.ingestion.interfaces import SourceConnector
from app.domain.ingestion.models import IngestionJob, IngestionStatus
from app.domain.ingestion.orchestrator_tools import (
    BatchIngestFilesTool,
    ClassifyFileTool,
    IngestFileTool,
    OrchestratorTool,
    ScanFolderTool,
    UpdateProgressTool,
)
from app.infra.llm import LLMProvider
from app.infra.storage import StorageClient

logger = logging.getLogger(__name__)

# Hard cap to prevent infinite agent loops
MAX_ITERATIONS = 500

ORCHESTRATOR_SYSTEM_PROMPT = """You are an ingestion orchestrator agent. Your job is to systematically explore a Google Drive folder tree, discover all ingestible documents (PDFs, DOCX, Google Docs), classify their metadata from folder context, and ingest each one.

## Your Tools

1. **scan_folder** -- List all children (files + subfolders) of a folder. Start here with the root folder.
2. **classify_file** -- For each ingestible file, classify its metadata (major, course code, course name, year, category) from the folder path context. This uses AI to infer the structure -- no hardcoded rules.
3. **ingest_file** -- Download, process, embed, and extract knowledge from a single file. Use this for one-off files.
4. **batch_ingest_files** -- Ingest multiple files IN PARALLEL. Accepts a list of files (each with file_id, file_name, mime_type, folder_path, classification). Processes them concurrently -- MUCH FASTER than calling ingest_file in a loop. Use this whenever you have 2+ files ready.
5. **update_progress** -- Save current progress counts to the database so the admin can track your work. Call this after finishing each folder's files.

## Strategy (optimised for speed)

1. **Scan the root folder** to see its children.
2. For each subfolder, scan it recursively to explore the tree.
3. For each folder containing ingestible files:
   a. Call **classify_file** for ALL files in the folder (can batch multiple classify_file calls).
   b. Collect all the classifications.
   c. Call **batch_ingest_files** with the full list of files + their classifications to ingest them in parallel.
4. Skip files that are not PDF, DOCX, or Google Docs (images, spreadsheets, etc.).
5. Skip Google Drive shortcuts (mime type: application/vnd.google-apps.shortcut).
6. After finishing a folder's files, call **update_progress**.
7. Continue until all folders have been explored and all files processed.

## Important Rules

- Process ALL files -- do not stop early.
- **Prefer batch_ingest_files over ingest_file for 2+ files** -- it is parallel and faster.
- Work folder-by-folder: scan a folder, classify all its files, batch ingest them, then move to the next subfolder.
- The admin_user_id for ingest_file and batch_ingest_files is: {admin_user_id}
- The root folder ID is: {root_folder_id}
- Supported MIME types for ingestion: application/pdf, application/vnd.openxmlformats-officedocument.wordprocessingml.document, application/vnd.google-apps.document
- When you have finished exploring all folders and ingesting all files, send a final text message summarizing what was done.
- Call update_progress periodically (at least after finishing each major folder).

## Folder Path Convention

When calling classify_file and ingest_file/batch_ingest_files, build the folder_path as a slash-separated breadcrumb from the root folder to the file's parent folder. For example, if you scanned "Root" > "Informatika" > "Semester 3" > "IF2120 - Probabilitas" > "Referensi", the folder_path for a file in Referensi would be: "Informatika/Semester 3/IF2120 - Probabilitas/Referensi"
"""


class IngestionOrchestrator:
    """LLM-driven orchestrator for Google Drive ingestion.

    Uses a ReAct agent loop with tools to explore folder trees,
    classify file metadata via LLM, and ingest files incrementally.
    """

    def __init__(
        self,
        db: AsyncSession,
        storage: StorageClient,
        connector: SourceConnector,
        llm: LLMProvider,
        user_settings: "Any | None" = None,
    ) -> None:
        from app.config import get_settings
        self._db = db
        self._storage = storage
        self._connector = connector
        # Use a scoped provider (user's model + API key) when settings are present
        self._llm = llm.with_user_settings(user_settings) if user_settings is not None else llm
        self._settings = get_settings()

    async def _update_job_status(
        self,
        job: IngestionJob,
        status: IngestionStatus,
        error_message: str | None = None,
        completed: bool = False,
    ) -> None:
        """Persist job status using a direct SQL UPDATE to avoid ORM dirty-tracking issues.

        pgbouncer transaction mode + long-running sessions can cause ORM state
        to drift. Direct SQL UPDATE guarantees the write goes through.

        Uses SQLAlchemy's ``update()`` construct to handle type casts and
        parameter binding portably (works with both asyncpg and pgbouncer).
        """
        from sqlalchemy import update as sa_update

        values: dict[str, Any] = {"status": status}

        if error_message is not None:
            values["error_message"] = error_message

        if completed:
            values["completed_at"] = datetime.now(timezone.utc)

        stmt = (
            sa_update(IngestionJob)
            .where(IngestionJob.id == job.id)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        await self._db.execute(stmt)
        await self._db.commit()

        # Keep the in-memory object in sync
        job.status = status
        if error_message is not None:
            job.error_message = error_message
        if completed:
            job.completed_at = datetime.now(timezone.utc)

    async def run(
        self,
        job: IngestionJob,
        admin_user_id: uuid.UUID,
        force: bool = False,
    ) -> IngestionJob:
        """Execute an ingestion job using the orchestrator agent.

        Args:
            job: The IngestionJob to track progress on.
            admin_user_id: User ID to associate ingested documents with.
            force: If True, re-ingest files even if already processed.

        Returns:
            Updated IngestionJob with final status.
        """
        try:
            # Phase 1: Authenticate with Drive
            await self._update_job_status(job, IngestionStatus.SCANNING)

            authenticated = await self._connector.authenticate()
            if not authenticated:
                await self._update_job_status(
                    job,
                    IngestionStatus.FAILED,
                    error_message="Google Drive authentication failed",
                    completed=True,
                )
                return job

            # Phase 2: Set up tools
            file_concurrency = self._settings.file_concurrency
            ingest_tool = IngestFileTool(
                db=self._db,
                storage=self._storage,
                connector=self._connector,
                job=job,
                llm=self._llm,
            )
            batch_tool = BatchIngestFilesTool(
                db=self._db,
                storage=self._storage,
                connector=self._connector,
                job=job,
                llm=self._llm,
                file_concurrency=file_concurrency,
            )
            tools: list[OrchestratorTool] = [
                ScanFolderTool(connector=self._connector),
                ClassifyFileTool(llm=self._llm),
                ingest_tool,
                batch_tool,
                UpdateProgressTool(db=self._db, job=job),
            ]
            tool_map = {t.name: t for t in tools}
            tool_specs = [t.to_tool_spec() for t in tools]

            # Phase 3: Build initial messages
            root_folder = job.folder_id or "root"
            system_prompt = ORCHESTRATOR_SYSTEM_PROMPT.format(
                admin_user_id=str(admin_user_id),
                root_folder_id=root_folder,
            )

            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Begin ingestion. Scan the root folder '{root_folder}' "
                        f"and process all ingestible files recursively."
                    ),
                },
            ]

            # Phase 4: Agent loop
            await self._update_job_status(job, IngestionStatus.PROCESSING)

            iteration = 0
            while iteration < MAX_ITERATIONS:
                iteration += 1

                try:
                    response = await self._llm.complete(
                        messages=messages,
                        temperature=0.0,
                        max_tokens=4096,
                        tools=tool_specs,
                    )
                except Exception as e:
                    logger.error(
                        "LLM call failed at iteration %d: %s", iteration, e
                    )
                    # Try once more with fallback model
                    try:
                        response = await self._llm.complete(
                            messages=messages,
                            model=self._llm.fallback_model,
                            temperature=0.0,
                            max_tokens=4096,
                            tools=tool_specs,
                        )
                    except Exception as e2:
                        logger.error("Fallback LLM also failed: %s", e2)
                        break

                choice = response.choices[0]
                message = choice.message

                # Check for tool calls
                if message.tool_calls:
                    # Append the assistant message with tool calls
                    messages.append(message.model_dump())

                    # Execute tool calls -- run independent calls concurrently
                    # classify_file and scan_folder are safe to run in parallel.
                    # ingest_file and batch_ingest_files serialize themselves
                    # internally via BatchIngestFilesTool's semaphore.
                    async def _run_tool_call(tool_call) -> tuple[str, dict]:
                        fn = tool_call.function
                        tool_name = fn.name
                        tool_args = json.loads(fn.arguments) if fn.arguments else {}

                        tool = tool_map.get(tool_name)
                        if tool is None:
                            logger.warning("Unknown tool requested: %s", tool_name)
                            return tool_call.id, {"error": f"Unknown tool: {tool_name}"}

                        try:
                            # Inject admin_user_id for file-ingesting tools
                            if tool_name in ("ingest_file", "batch_ingest_files"):
                                tool_args["admin_user_id"] = str(admin_user_id)

                            result = await tool.execute(**tool_args)
                        except Exception as e:
                            logger.exception("Tool %s failed: %s", tool_name, e)
                            result = {
                                "error": f"Tool execution failed: {str(e)[:200]}"
                            }

                        logger.info(
                            "Iteration %d: %s -> %s",
                            iteration,
                            tool_name,
                            _summarise_result(result),
                        )
                        return tool_call.id, result

                    # Run all tool calls in this response concurrently
                    results = await asyncio.gather(
                        *[_run_tool_call(tc) for tc in message.tool_calls],
                        return_exceptions=True,
                    )

                    for i, outcome in enumerate(results):
                        tool_call = message.tool_calls[i]
                        if isinstance(outcome, Exception):
                            tool_result = {"error": str(outcome)[:200]}
                            call_id = tool_call.id
                        else:
                            call_id, tool_result = outcome  # type: ignore[misc]

                        messages.append({
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": json.dumps(tool_result, default=str),
                        })

                elif message.content:
                    # Agent sent a text message -- done
                    logger.info(
                        "Orchestrator finished after %d iterations. Summary: %s",
                        iteration,
                        message.content[:300],
                    )
                    job.metadata_["orchestrator_summary"] = message.content[:2000]
                    break

                else:
                    # No tool calls and no content -- unexpected, break
                    logger.warning(
                        "Orchestrator returned empty response at iteration %d",
                        iteration,
                    )
                    break

                # Prune message history if it's getting too long
                # Keep system + last N messages to avoid token limits
                if len(messages) > 100:
                    messages = _prune_messages(messages)

            else:
                logger.warning(
                    "Orchestrator hit max iterations (%d)", MAX_ITERATIONS
                )
                job.metadata_["orchestrator_warning"] = (
                    f"Hit max iterations ({MAX_ITERATIONS})"
                )

            # Phase 5: Finalise job
            error_msg = None
            if job.failed_files > 0:
                error_msg = f"{job.failed_files} files failed during ingestion"

            await self._update_job_status(
                job,
                IngestionStatus.COMPLETED,
                error_message=error_msg,
                completed=True,
            )

            logger.info(
                "Ingestion orchestrator complete (job %s): "
                "%d processed, %d failed, %d skipped, %d iterations",
                job.id,
                job.processed_files,
                job.failed_files,
                job.skipped_files,
                iteration,
            )
            return job

        except Exception as e:
            await self._update_job_status(
                job,
                IngestionStatus.FAILED,
                error_message=str(e)[:500],
                completed=True,
            )
            logger.exception("Ingestion orchestrator failed (job %s)", job.id)
            raise IngestionError(str(e)) from e


def _summarise_result(result: dict[str, Any]) -> str:
    """One-line summary of a tool result for logging."""
    status = result.get("status", "")
    if "children_count" in result:
        return (
            f"{result['children_count']} children "
            f"({len(result.get('folders', []))} folders, "
            f"{len(result.get('files', []))} files)"
        )
    if "classification" in result:
        c = result["classification"]
        return (
            f"classified -> {c.get('course_code') or 'unknown course'} / "
            f"{c.get('category') or 'unknown category'}"
        )
    if "document_id" in result:
        return (
            f"ingested {result.get('file_name', '')} "
            f"({result.get('chunk_count', 0)} chunks, "
            f"{result.get('embeddings_created', 0)} embeddings)"
        )
    if "ingested_count" in result:
        return (
            f"batch: {result.get('ingested_count', 0)} ingested, "
            f"{result.get('failed_count', 0)} failed, "
            f"{result.get('skipped_count', 0)} skipped"
        )
    if status:
        return status
    return json.dumps(result, default=str)[:120]


def _prune_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the system prompt and last 80 messages to stay within token limits.

    Inserts a summary message so the agent knows context was pruned.
    """
    system = messages[0]
    recent = messages[-80:]

    pruned_count = len(messages) - 81
    summary_msg = {
        "role": "user",
        "content": (
            f"[CONTEXT NOTE: {pruned_count} earlier messages were pruned to save "
            f"context space. Continue where you left off -- scan remaining folders "
            f"and ingest remaining files.]"
        ),
    }

    return [system, summary_msg] + recent
