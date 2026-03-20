# Chat Composer Attachments & Enhanced Input

## 1. One-Line Summary

Add an attachment button to the chat composer that supports local file uploads, Google Drive file browsing, and extended thinking toggle — plus auto-convert long pastes (500+ chars) into .txt file attachments.

## 2. Target Users

- All chat users who want to ask questions about specific files without permanently ingesting them into the knowledge base.

## 3. Success Criteria

### Attachment Button (+ icon in composer)
1. Clicking the attachment button opens a popover menu with three options:
   - **Upload files** — opens native file picker filtered to supported types (images: png, jpg, jpeg, gif, webp; documents: txt, pdf, docx, doc)
   - **Browse Drive** — opens a modal that live-browses the user's connected Google Drive, filtered to supported file types. User selects files which get downloaded and attached.
3. Extended thinking toggle stays with the model selector (current position as a pill button next to model chooser) — NOT in the attachment menu
2. Files are attached **inline** with the chat message — they are sent as context to the LLM, not permanently ingested
3. **Multimodal handling:**
   - Images → sent as vision content blocks (base64) to models that support it; skipped for non-vision models with a warning
   - Text files (PDF, DOCX, TXT) → parsed server-side using existing processors, extracted text injected into the LLM prompt
4. Max **10 MB per file**, max **5 files per message**
5. Attached files appear as removable chips/pills below the textarea, showing filename and size
6. The attachment menu has only two options: Upload files and Browse Drive

### Paste-to-Attachment (500+ chars)
7. When user pastes text longer than 500 characters into the textarea, it is silently auto-converted to an attached .txt file named `pasted-text.txt` (or `pasted-text-2.txt` etc. if multiple)
8. The pasted text does NOT appear in the textarea — it appears as an attachment chip
9. Pastes under 500 characters behave normally (inserted into textarea)

### Backend Changes
10. The `/chat/stream` endpoint accepts file attachments (multipart or base64-encoded in JSON)
11. Backend extracts text from PDF/DOCX using existing `PdfProcessor`/`DocxProcessor`
12. Images are forwarded as base64 content blocks in the LLM message
13. Text content from files is prepended to the user message as context blocks

### Drive File Browser
14. New endpoint to list files from the user's connected Google Drive (reuses `GoogleDriveConnector`)
15. Supports folder navigation and file type filtering
16. Selected files are downloaded server-side and returned as attachments
17. Only shows files of supported types (images, txt, pdf, docx)

## 4. Out of Scope

- Permanent ingestion of attached files into the knowledge base
- Drag-and-drop file upload onto the chat area
- File preview/viewer in the chat (files are context for the LLM only)
- Audio/video file support
- OCR for images (images use native vision, not text extraction)
- Clipboard image paste (only text paste is handled)

## 5. Constraints

- Frontend: Next.js 15 + TypeScript + Tailwind (no shadcn components — use custom styling with CSS vars)
- Backend: FastAPI + Python, existing processors for PDF/DOCX
- Must work with LiteLLM's `acompletion` — use content blocks format for multimodal
- Google Drive browsing requires the user to have connected their Drive (existing OAuth flow)
- File processing must not block the SSE stream — extract before starting the agent
