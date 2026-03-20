# Fetch Full Document Tool

## 1. One-Line Summary

Add a `fetch_document` agent tool that retrieves the full text of a document (from Google Drive or Supabase Storage) and injects it into the LLM context, with a smart fallback to chunk-based retrieval for large files.

## 2. Target Users

- Chat users who need the complete content of a specific document, not just RAG chunks (e.g., "show me the full report", "get me the entire document").

## 3. Success Criteria

### Core Behavior
1. New `fetch_document` tool available to the RAG agent, callable via native function calling
2. The LLM uses it when the user explicitly asks to see/read a full document (not autonomously)
3. Takes a `document_id` (UUID) as input — the ID returned from prior search results or citations
4. Returns the full extracted text of the document into the LLM context so it can reason over the entire file

### Source Support
5. Works for **Google Drive** files: re-downloads from Drive API using the stored `drive_file_id` in document metadata, then extracts text using existing document processors (PDF/DOCX)
6. Works for **user-uploaded** files: downloads from Supabase Storage using the stored `storage_path`, then extracts text
7. For both sources, reuses the existing `PdfProcessor` / `DocxProcessor` text extraction logic

### Drive Link in Results
8. The tool result includes a `drive_url` field (e.g., `https://drive.google.com/file/d/{id}/view`) for Drive-sourced documents, so the frontend can render a clickable link in the tool_result SSE event
9. For user uploads, includes a signed Supabase Storage URL instead

### Smart Size Fallback
10. If the full extracted text exceeds **100k characters** (~25k tokens), the tool does NOT inject the full text
11. Instead, it falls back to retrieving chunks from the DB for that specific `document_id` — starting with the top 5 most relevant chunks (by vector similarity to the user's query)
12. The tool result indicates it used the fallback, so the LLM knows it has partial content and can request more chunks if needed
13. The LLM can call the tool again with an `offset` parameter to get the next batch of 5 chunks

### Error Handling
14. Returns a clear error if the document_id doesn't exist or the user doesn't have access
15. Returns a clear error if the file can't be downloaded (Drive auth expired, storage file missing)
16. Gracefully handles unsupported file types by returning whatever text extraction is possible

## 4. Out of Scope

- Autonomous LLM decision to fetch full files (user-requested only)
- Downloading files to the user's browser (this is context injection for the LLM, not file serving)
- Modifying the existing search tools or citation system
- New frontend components (the existing tool_result SSE event + citation link handling is sufficient)

## 5. Constraints

- Tech stack: FastAPI + existing document processors (PdfProcessor, DocxProcessor) + GoogleDriveConnector + StorageClient — no new dependencies
- Must reuse existing `IAgentTool` interface pattern
- File re-download is acceptable (vs. caching) since this is user-triggered, not autonomous
- The fallback chunk retrieval reuses the existing `VectorService` for similarity-ranked chunks scoped to a specific document_id
- Must not break existing agent tools or the ReAct loop
