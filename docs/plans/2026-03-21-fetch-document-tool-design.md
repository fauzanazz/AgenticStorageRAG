# Fetch Document Tool — Design Doc

**Date:** 2026-03-21
**Spec:** `.planning/spec.md`

## Overview

Add a `fetch_document` agent tool that retrieves the full text content of a document and injects it into the LLM context. When the full text exceeds 100k characters, it falls back to chunk-based retrieval scoped to that document.

## Architecture

### Single Tool Approach

One new file: `backend/app/domain/agents/tools/fetch_document.py`

The tool follows the existing `IAgentTool` pattern. Dependencies are injected via constructor:
- `AsyncSession` — to query the Document model and chunks
- `VectorService` — for chunk fallback (similarity-ranked retrieval scoped to document_id)
- `StorageClient` — to download user-uploaded files from Supabase Storage

For Google Drive files, the tool instantiates `GoogleDriveConnector` and authenticates using server-level credentials (same as ingestion pipeline). This is acceptable because:
- The tool fetches files already ingested into the system (we have the drive_file_id)
- No per-user OAuth is needed — these are base KG files shared with the service account

### Tool Parameters

```json
{
  "type": "object",
  "properties": {
    "document_id": {
      "type": "string",
      "description": "UUID of the document to fetch (from search results or citations)"
    },
    "query": {
      "type": "string",
      "description": "The user's query — used for chunk ranking if fallback is needed"
    },
    "chunk_offset": {
      "type": "integer",
      "description": "Offset for paginated chunk retrieval (default 0). Use when the LLM needs more chunks from a large document."
    }
  },
  "required": ["document_id"]
}
```

### Execution Flow

```
1. Look up Document by ID in DB
2. Check document exists and is READY
3. Determine source (GOOGLE_DRIVE vs UPLOAD)
4. Download raw file bytes:
   - Drive: GoogleDriveConnector.download_file(drive_file_id)
   - Upload: StorageClient.download(storage_path)
5. Extract text using existing processors (PdfProcessor / DocxProcessor)
6. Check text length:
   - <= 100k chars: return full text + source URL
   - > 100k chars: fall back to VectorService chunk retrieval
     - 5 chunks at a time, ranked by similarity to `query`
     - Respect `chunk_offset` for pagination
7. Return result with:
   - content (full text or chunks)
   - document_name
   - source_url (Drive link or signed Storage URL)
   - mode: "full" | "chunks"
   - total_chunks (if chunked)
   - chunk_offset (if chunked)
```

### Tool Result Schema

```python
{
    "result": {
        "content": "...",           # Full text or concatenated chunks
        "document_name": "report.pdf",
        "source_url": "https://drive.google.com/file/d/.../view",
        "mode": "full",             # "full" | "chunks"
        "total_chunks": null,       # Only set in chunks mode
        "chunk_offset": null,       # Only set in chunks mode
        "chunks_returned": null,    # Only set in chunks mode
    },
    "count": 1,
    "source": "fetch_document",
}
```

### Wiring

In `router.py` `_build_agent()`:
1. Import `FetchDocumentTool`
2. Add to tools list: `FetchDocumentTool(db=db, vector_service=vector_service)`

In `tools/__init__.py`:
1. Add export for `FetchDocumentTool`

In `schemas.py`:
1. Add `"fetch_document": "Fetching full document"` to `TOOL_FRIENDLY_NAMES`

In `rag_agent.py` system prompt:
1. Add instruction for when to use `fetch_document`

### Text Extraction

Reuse existing `BaseProcessor._chunk_text()` logic but skip the chunking step — just concatenate all extracted text. The processors already handle:
- PDF: page-by-page extraction via pypdf
- DOCX: paragraph + table extraction with heading preservation

For the fetch tool, we call the processor's `process()` method and concatenate all chunk contents, or more directly, use the internal `_extract_text()` step.

### Error Cases

- Document not found → `{"error": "Document not found"}`
- Document not ready → `{"error": "Document is still processing"}`
- Download failed → `{"error": "Failed to download file: ..."}`
- Unsupported type → `{"error": "Cannot extract text from this file type"}`

## Files Changed

1. **NEW** `backend/app/domain/agents/tools/fetch_document.py` — the tool
2. **EDIT** `backend/app/domain/agents/tools/__init__.py` — export
3. **EDIT** `backend/app/domain/agents/schemas.py` — friendly name
4. **EDIT** `backend/app/domain/agents/router.py` — wire into `_build_agent()`
5. **EDIT** `backend/app/domain/agents/rag_agent.py` — system prompt instruction
6. **NEW** `backend/app/domain/agents/tests/test_fetch_document.py` — tests
