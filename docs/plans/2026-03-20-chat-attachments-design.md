# Chat Composer Attachments — Design Document

**Date:** 2026-03-20
**Status:** Draft

## Overview

Add file attachment support to the chat composer. Users can attach local files or browse Google Drive to attach files inline with their chat message. Files are processed server-side and sent as context to the LLM (not permanently ingested). Long pastes (500+ chars) are auto-converted to .txt attachments.

## Architecture

### Two-Step Upload Flow

```
┌─────────────┐     POST /chat/attachments     ┌──────────┐
│  Frontend   │ ──────────────────────────────> │ Backend  │
│  (file pick) │ <─────── { attachment_id }──── │          │
└─────────────┘                                 │ Store in │
       │                                        │ Supabase │
       │  POST /chat/stream                     │ Storage  │
       │  { message, attachment_ids: [...] }    │ (7-day   │
       └───────────────────────────────────────>│  TTL)    │
                                                │ Fetch    │
                                                │ from     │
                                                │ storage, │
                                                │ process, │
                                                │ inject   │
                                                │ into LLM │
                                                └──────────┘
```

### Drive File Attachment Flow

```
┌─────────────┐  GET /drive/browse?folder_id=   ┌──────────┐
│  Frontend   │ ──────────────────────────────> │ Backend  │
│ (Drive modal)│ <──── [{ id, name, ... }] ──── │ (Drive   │
└─────────────┘                                 │  API)    │
       │                                        └──────────┘
       │  POST /chat/attachments/from-drive
       │  { file_ids: ["..."] }
       │──────────────────────────────────────> Download from Drive,
       │ <────── [{ attachment_id, name }] ──── store in Supabase Storage
```

### File Processing at Chat Time

When `/chat/stream` receives `attachment_ids`:

1. Fetch file bytes from Redis by each attachment ID
2. For each file, based on MIME type:
   - **Images** (png, jpg, gif, webp): Convert to base64, add as `image_url` content block in LLM message
   - **PDF**: Use existing `PdfProcessor` to extract text
   - **DOCX**: Use existing `DocxProcessor` to extract text
   - **TXT**: Read as UTF-8 text
3. Prepend extracted text files as a "context" section in the user message
4. Add image content blocks to the multimodal message array

### LLM Message Format (with attachments)

```python
# Text files → prepended as context
messages = [
    {"role": "system", "content": system_prompt},
    # ... history ...
    {"role": "user", "content": [
        # Images as vision content blocks
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
        # Text content (user message + file context)
        {"type": "text", "text": "[Attached: report.pdf]\n<file_content>..extracted text..</file_content>\n\nUser's actual question here"},
    ]},
]
```

## Key Decisions

1. **Supabase Storage with 7-day TTL** — Files stored in Supabase Storage (same as personal document uploads). Consistent expiration behavior. Metadata tracked in a `chat_attachments` DB table.

2. **Reuse existing processors** — `PdfProcessor` and `DocxProcessor` already handle text extraction. We only need the extraction step, not chunking/embedding.

3. **Multimodal via content blocks** — LiteLLM supports the OpenAI content blocks format across providers (Anthropic, OpenAI, etc.). Images go as `image_url` type blocks.

4. **Drive browsing reuses `GoogleDriveConnector`** — The `list_folder_children` and `download_file` methods already exist. We add a thin router for the browse API.

5. **Extended thinking stays as pill** — Remains next to model selector, not in the attachment menu.

## API Endpoints

### `POST /chat/attachments` (multipart)
Upload a local file for attachment.
- Request: `multipart/form-data` with `file` field
- Response: `{ attachment_id, filename, size, mime_type }`
- Validation: max 10MB, supported types only

### `POST /chat/attachments/from-drive` (JSON)
Attach files from Google Drive.
- Request: `{ file_ids: ["drive_file_id_1", ...] }`
- Response: `[{ attachment_id, filename, size, mime_type }]`
- Downloads from Drive, stores in Redis

### `GET /drive/browse` (query params)
Browse Google Drive folders.
- Query: `?folder_id=xxx` (optional, default=root)
- Response: `[{ id, name, mime_type, size, is_folder, modified_time }]`
- Uses user's OAuth tokens

### `ChatRequest` schema update
- Add `attachment_ids: list[str] = []` field

## Component Design

### Frontend Components

1. **AttachmentButton** — `+` icon button in the chat input area. Opens a popover with "Upload files" and "Browse Drive" options.

2. **AttachmentChip** — Small pill showing attached file name, size, and remove button. Rendered below the textarea.

3. **DriveFileBrowser** — Modal with folder navigation, file list, and select/confirm buttons. Shows breadcrumb path.

4. **ChatInput updates** — Paste handler for 500+ char auto-conversion. Attachment state management. Pass attachment_ids to sendMessage.

### Backend Modules

1. **`app/domain/agents/attachments.py`** — Service for uploading, storing (Supabase), fetching, and processing attachments.

2. **`app/domain/agents/router.py`** updates — New attachment endpoints + ChatRequest schema change.

3. **`app/domain/ingestion/router.py`** updates — New `/drive/browse` endpoint using existing `GoogleDriveConnector`.
