"""Attachment service for chat file uploads.

Handles uploading, storing, fetching, and processing file attachments
that are sent inline with chat messages. Files are stored in Supabase
Storage with a 7-day TTL.
"""

from __future__ import annotations

import base64
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.agents.models import ChatAttachment

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "text/plain",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

EXTENSION_TO_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_ATTACHMENTS_PER_MESSAGE = 5
ATTACHMENT_TTL_DAYS = 7
ATTACHMENT_STORAGE_BUCKET = "documents"  # reuse existing bucket

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AttachmentError(Exception):
    """Base exception for attachment errors."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class AttachmentTooLargeError(AttachmentError):
    def __init__(self, filename: str, size: int, max_size: int) -> None:
        super().__init__(f"File '{filename}' is {size} bytes, max allowed is {max_size}")


class UnsupportedAttachmentTypeError(AttachmentError):
    def __init__(self, filename: str, mime_type: str) -> None:
        super().__init__(f"File type '{mime_type}' is not supported for '{filename}'")


class AttachmentNotFoundError(AttachmentError):
    def __init__(self, attachment_id: str) -> None:
        super().__init__(f"Attachment not found: {attachment_id}")


class TooManyAttachmentsError(AttachmentError):
    def __init__(self, count: int, max_count: int) -> None:
        super().__init__(f"Too many attachments: {count}, max is {max_count}")


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class AttachmentService:
    """Manages chat file attachments (upload, fetch, process for LLM)."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # -- Upload -------------------------------------------------------------

    async def upload(
        self,
        user_id: uuid.UUID,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
    ) -> ChatAttachment:
        """Upload a file attachment to Supabase Storage.

        Validates size and type, stores in Supabase at
        ``attachments/{user_id}/{attachment_id}/{filename}``,
        and saves metadata to DB with 7-day TTL.
        """
        if len(file_bytes) > MAX_FILE_SIZE:
            raise AttachmentTooLargeError(filename, len(file_bytes), MAX_FILE_SIZE)
        if mime_type not in SUPPORTED_MIME_TYPES:
            raise UnsupportedAttachmentTypeError(filename, mime_type)

        attachment_id = uuid.uuid4()
        safe_filename = os.path.basename(filename).replace("..", "")
        storage_path = f"attachments/{user_id}/{attachment_id}/{safe_filename}"

        # Upload to Supabase Storage
        from app.infra.storage import storage_client

        await storage_client.upload_file(storage_path, file_bytes, mime_type)

        # Save metadata to DB
        expires_at = datetime.now(UTC) + timedelta(days=ATTACHMENT_TTL_DAYS)
        attachment = ChatAttachment(
            id=attachment_id,
            user_id=user_id,
            filename=filename,
            mime_type=mime_type,
            size=len(file_bytes),
            storage_path=storage_path,
            expires_at=expires_at,
        )
        self._db.add(attachment)
        await self._db.flush()
        return attachment

    # -- Fetch --------------------------------------------------------------

    async def get(self, attachment_id: uuid.UUID, user_id: uuid.UUID) -> ChatAttachment:
        """Fetch an attachment with ownership check."""
        result = await self._db.execute(
            select(ChatAttachment).where(
                ChatAttachment.id == attachment_id,
                ChatAttachment.user_id == user_id,
            )
        )
        attachment = result.scalar_one_or_none()
        if not attachment:
            raise AttachmentNotFoundError(str(attachment_id))
        return attachment

    async def get_many(self, attachment_ids: list[str], user_id: uuid.UUID) -> list[ChatAttachment]:
        """Batch fetch attachments with ownership check."""
        if not attachment_ids:
            return []
        uuids = [uuid.UUID(aid) for aid in attachment_ids]
        result = await self._db.execute(
            select(ChatAttachment).where(
                ChatAttachment.id.in_(uuids),
                ChatAttachment.user_id == user_id,
            )
        )
        attachments = list(result.scalars().all())
        if len(attachments) != len(attachment_ids):
            found_ids = {str(a.id) for a in attachments}
            missing = [aid for aid in attachment_ids if aid not in found_ids]
            raise AttachmentNotFoundError(", ".join(missing))
        return attachments

    # -- LLM processing -----------------------------------------------------

    async def process_for_llm(self, attachments: list[ChatAttachment]) -> tuple[str, list[dict]]:
        """Process attachments into LLM-ready content.

        Returns:
            Tuple of (text_context, image_content_blocks)
            - text_context: extracted text from PDF/DOCX/TXT files, formatted
            - image_content_blocks: list of image content block dicts
        """
        from app.infra.storage import storage_client

        text_parts: list[str] = []
        image_blocks: list[dict] = []

        for attachment in attachments:
            file_bytes = await storage_client.download_file(attachment.storage_path)

            if attachment.mime_type in IMAGE_MIME_TYPES:
                b64 = base64.b64encode(file_bytes).decode("utf-8")
                image_blocks.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{attachment.mime_type};base64,{b64}"},
                    }
                )
            elif attachment.mime_type == "application/pdf":
                from app.domain.documents.processors.pdf import PdfProcessor

                processor = PdfProcessor()
                text = await processor.extract_text(file_bytes)
                text_parts.append(
                    f"[Attached: {attachment.filename}]\n<file_content>\n{text}\n</file_content>"
                )
            elif (
                attachment.mime_type
                == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ):
                from app.domain.documents.processors.docx import DocxProcessor

                docx_processor = DocxProcessor()
                text = await docx_processor.extract_text(file_bytes)
                text_parts.append(
                    f"[Attached: {attachment.filename}]\n<file_content>\n{text}\n</file_content>"
                )
            elif attachment.mime_type == "text/plain":
                text = file_bytes.decode("utf-8", errors="replace")
                text_parts.append(
                    f"[Attached: {attachment.filename}]\n<file_content>\n{text}\n</file_content>"
                )

        text_context = "\n\n".join(text_parts) if text_parts else ""
        return text_context, image_blocks

    # -- Google Drive import ------------------------------------------------

    async def upload_from_drive(
        self,
        user_id: uuid.UUID,
        file_ids: list[str],
        drive_connector: object,
    ) -> list[ChatAttachment]:
        """Download files from Google Drive and store as attachments."""
        attachments: list[ChatAttachment] = []
        for file_id in file_ids:
            file_bytes, filename = await drive_connector.download_file(file_id)  # type: ignore[attr-defined]
            ext = os.path.splitext(filename)[1].lower()
            mime_type = EXTENSION_TO_MIME.get(ext, "application/octet-stream")
            if mime_type not in SUPPORTED_MIME_TYPES:
                logger.warning(
                    "Skipping unsupported Drive file type: %s (%s)",
                    filename,
                    mime_type,
                )
                continue
            attachment = await self.upload(user_id, file_bytes, filename, mime_type)
            attachments.append(attachment)
        return attachments
