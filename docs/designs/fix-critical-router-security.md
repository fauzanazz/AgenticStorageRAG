# Fix Critical Router Security Bugs

## Context

Security audit found 4 router-level vulnerabilities that need immediate fixes:
1. OAuth token attributes accessed without decryption (broken feature + potential data leak)
2. `/documents/drive-tree` endpoint has no authentication
3. Tool proxy endpoints accept raw `dict` bodies — arbitrary kwargs injected into tool execution
4. `/health/detailed` exposes infra topology without authentication

## Requirements

- OAuth tokens must be decrypted before passing to `GoogleDriveConnector.from_user_tokens()`
- `GET /documents/drive-tree` must require authentication
- Tool proxy endpoints must validate request bodies with Pydantic schemas
- `GET /health/detailed` must require admin authentication
- All existing tests must continue to pass
- Add tests for the drive-tree auth check and proxy body validation

## Implementation

### 1. Fix OAuth token decryption in agents router

**File:** `backend/app/domain/agents/router.py`

At the top, add import:
```python
from app.infra.encryption import decrypt_value
```

Replace lines 306-308 (inside `attach_from_drive`):
```python
# BEFORE (broken — accesses non-existent attributes)
connector = GoogleDriveConnector.from_user_tokens(
    access_token=oauth.access_token,
    refresh_token=oauth.refresh_token,
)

# AFTER
connector = GoogleDriveConnector.from_user_tokens(
    access_token=decrypt_value(oauth.access_token_enc),
    refresh_token=decrypt_value(oauth.refresh_token_enc) if oauth.refresh_token_enc else None,
)
```

### 2. Fix OAuth token decryption in ingestion router

**File:** `backend/app/domain/ingestion/router.py`

At the top, add import:
```python
from app.infra.encryption import decrypt_value
```

Replace lines 324-326 (inside `browse_drive_for_attachments`):
```python
# BEFORE (broken)
connector = GoogleDriveConnector.from_user_tokens(
    access_token=oauth.access_token,
    refresh_token=oauth.refresh_token,
)

# AFTER
connector = GoogleDriveConnector.from_user_tokens(
    access_token=decrypt_value(oauth.access_token_enc),
    refresh_token=decrypt_value(oauth.refresh_token_enc) if oauth.refresh_token_enc else None,
)
```

### 3. Add authentication to drive-tree endpoint

**File:** `backend/app/domain/documents/router.py`

Add `get_current_user_id` dependency to the `get_drive_tree` function (already imported at top of file):

```python
@router.get(
    "/drive-tree",
    response_model=DriveTreeResponse,
    summary="Get Drive documents as a folder tree",
)
async def get_drive_tree(
    _user_id: uuid.UUID = Depends(get_current_user_id),  # ← ADD THIS
    service: DocumentService = Depends(_get_document_service),
) -> DriveTreeResponse:
    """Return all indexed Drive files organised into a folder tree."""
    return await service.get_drive_tree()
```

### 4. Add Pydantic schemas for tool proxy endpoints

**File:** `backend/app/domain/agents/schemas.py`

Add these schemas at the end of the file:

```python
# ---------------------------------------------------------------------------
# Tool proxy request schemas (validated bodies for /tools/* endpoints)
# ---------------------------------------------------------------------------

class FetchDocumentRequest(BaseModel):
    """Request body for the fetch-document tool proxy."""
    document_id: str = Field(..., description="UUID of the document to fetch")
    query: str | None = Field(None, description="User query for chunk ranking")
    chunk_offset: int = Field(0, ge=0, description="Pagination offset for large docs")

class GenerateDocumentRequest(BaseModel):
    """Request body for the generate-document tool proxy."""
    title: str = Field(..., min_length=1, max_length=500)
    instructions: str = Field(..., min_length=1, max_length=10000)
    context: str = Field("", max_length=50000)
    format: str = Field("markdown", pattern="^(markdown|report|analysis|comparison)$")

class EnrichCitationsRequest(BaseModel):
    """Request body for the enrich-citations endpoint."""
    citations: list[dict] = Field(default_factory=list)
```

**File:** `backend/app/domain/agents/router.py`

Update the three proxy endpoints to use the new schemas:

```python
from app.domain.agents.schemas import (
    # ... existing imports ...
    EnrichCitationsRequest,
    FetchDocumentRequest,
    GenerateDocumentRequest,
)

@router.post("/tools/fetch-document")
async def proxy_fetch_document(
    body: FetchDocumentRequest,  # ← was `dict`
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tool = FetchDocumentTool(db=db)
    return await tool.execute(**body.model_dump(exclude_none=True))

@router.post("/tools/generate-document")
async def proxy_generate_document(
    body: GenerateDocumentRequest,  # ← was `dict`
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    user_settings: UserModelSettings | None = Depends(get_user_model_settings),
) -> dict:
    effective_llm = (
        llm_provider.with_user_settings(user_settings)
        if user_settings is not None
        else llm_provider
    )
    tool = GenerateDocumentTool(llm=effective_llm)
    return await tool.execute(**body.model_dump(exclude_none=True))

@router.post("/tools/enrich-citations")
async def enrich_citations(
    body: EnrichCitationsRequest,  # ← was `dict`
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # ... rest of function uses body.citations instead of body.get("citations", [])
```

### 5. Require admin auth on detailed health check

**File:** `backend/app/main.py`

Move the detailed health check into a separate router or add inline admin check.
The simplest approach — add the dependency inline:

```python
from app.dependencies import get_current_user

@app.get(f"{settings.api_prefix}/health/detailed")
async def detailed_health_check(
    user: User = Depends(get_current_user),  # ← ADD
) -> dict[str, Any]:
    """Detailed health check with all service statuses. Requires auth."""
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    # ... rest unchanged
```

Add the necessary import at top:
```python
from app.domain.auth.models import User
```

## Testing Strategy

**Existing tests:** Run `cd backend && uv run pytest` — all must pass.

**New tests to add:**

**File:** `backend/app/domain/documents/tests/test_router.py` (create if not exists)
- `test_drive_tree_requires_auth` — call `GET /documents/drive-tree` without token, assert 401

**File:** `backend/app/domain/agents/tests/test_router_proxies.py` (create)
- `test_fetch_document_rejects_invalid_body` — send `{"bad_field": "x"}`, assert 422
- `test_generate_document_rejects_missing_title` — send `{}`, assert 422
- `test_enrich_citations_accepts_empty_list` — send `{"citations": []}`, assert 200

## Out of Scope

- Rate limiting on these endpoints (covered in separate design doc)
- Refactoring proxy endpoints into their own sub-router
- Full integration tests for Google Drive token decryption (requires live OAuth)
