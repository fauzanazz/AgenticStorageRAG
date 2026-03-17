# Per-User Model Settings Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `parallel-plan-execution` to implement this plan task-by-task.

**Goal:** Add per-user model configuration so each user can store their own API keys and choose their preferred models for chat completions, ingestion, and embeddings — with all three providers (Anthropic, OpenAI, DashScope) supported.

**Architecture:** A new `settings` domain handles CRUD for `user_model_settings` rows (one per user). A new `ScopedLLMProvider` wraps the global `LLMProvider` with per-user keys and model overrides. Services (`RAGAgent`, `IngestionOrchestrator`, `VectorService`) accept optional user settings and fall back to server defaults when absent. The frontend adds a "Model Configuration" section to the existing Settings page.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic, `cryptography` (Fernet), LiteLLM, Next.js 16, TanStack Query, shadcn/ui Select

---

## Task 1: Encryption helper

**Files:**
- Create: `backend/app/infra/encryption.py`
- Create: `backend/app/infra/tests/test_encryption.py`

### Step 1: Write the failing test

```python
# backend/app/infra/tests/test_encryption.py
import pytest
from app.infra.encryption import encrypt_value, decrypt_value


def test_encrypt_decrypt_roundtrip():
    plaintext = "sk-ant-api03-testkey"
    ciphertext = encrypt_value(plaintext)
    assert ciphertext != plaintext
    assert decrypt_value(ciphertext) == plaintext


def test_encrypt_produces_different_values():
    # Fernet includes random IV so each encryption differs
    plaintext = "sk-test"
    assert encrypt_value(plaintext) != encrypt_value(plaintext)


def test_decrypt_invalid_raises():
    with pytest.raises(Exception):
        decrypt_value("not-valid-ciphertext")
```

### Step 2: Run test to verify it fails

```bash
cd backend && uv run pytest app/infra/tests/test_encryption.py -v
```
Expected: FAIL — `ImportError: cannot import name 'encrypt_value'`

### Step 3: Implement encryption helper

```python
# backend/app/infra/encryption.py
"""
Symmetric encryption for sensitive values (API keys).

Uses Fernet (AES-128-CBC + HMAC-SHA256) keyed from the app's JWT_SECRET_KEY.
The secret key is hashed with SHA-256 and base64url-encoded to produce a
valid 32-byte Fernet key.
"""
import base64
import hashlib

from cryptography.fernet import Fernet

from app.config import get_settings


def _get_fernet() -> Fernet:
    """Derive a Fernet instance from the app's JWT_SECRET_KEY."""
    settings = get_settings()
    # SHA-256 produces exactly 32 bytes → valid Fernet key when base64url-encoded
    raw_key = hashlib.sha256(settings.jwt_secret_key.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(raw_key)
    return Fernet(fernet_key)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string. Returns a URL-safe base64 token."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a previously encrypted token. Raises InvalidToken on failure."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()
```

### Step 4: Run test to verify it passes

```bash
cd backend && uv run pytest app/infra/tests/test_encryption.py -v
```
Expected: 3 PASS

### Step 5: Commit

```bash
git add backend/app/infra/encryption.py backend/app/infra/tests/test_encryption.py
git commit -m "feat(settings): add Fernet encryption helper for API keys"
```

---

## Task 2: `settings` domain — model, schemas, exceptions

**Files:**
- Create: `backend/app/domain/settings/__init__.py`
- Create: `backend/app/domain/settings/exceptions.py`
- Create: `backend/app/domain/settings/models.py`
- Create: `backend/app/domain/settings/schemas.py`

### Step 1: Create the package and exceptions

```python
# backend/app/domain/settings/__init__.py
```

```python
# backend/app/domain/settings/exceptions.py
class SettingsNotFoundError(Exception):
    """Raised when a user has no model settings row yet."""
    pass
```

### Step 2: Create the SQLAlchemy model

```python
# backend/app/domain/settings/models.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.database import Base


class UserModelSettings(Base):
    __tablename__ = "user_model_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    # Model selections (stored as LiteLLM provider/model strings)
    chat_model: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="dashscope/qwen3-max",
    )
    ingestion_model: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="dashscope/qwen3-max",
    )
    embedding_model: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="openai/text-embedding-3-small",
    )

    # API keys (Fernet encrypted; None = not configured)
    anthropic_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    openai_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    dashscope_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
```

### Step 3: Create Pydantic schemas and model catalog

```python
# backend/app/domain/settings/schemas.py
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Model catalog — curated lists shown in frontend dropdowns
# ---------------------------------------------------------------------------

CHAT_MODELS: list[dict[str, str]] = [
    {"provider": "Anthropic", "model_id": "anthropic/claude-opus-4-5", "label": "Claude Opus 4.5"},
    {"provider": "Anthropic", "model_id": "anthropic/claude-sonnet-4-20250514", "label": "Claude Sonnet 4"},
    {"provider": "Anthropic", "model_id": "anthropic/claude-haiku-3-5", "label": "Claude Haiku 3.5"},
    {"provider": "OpenAI", "model_id": "openai/gpt-4o", "label": "GPT-4o"},
    {"provider": "OpenAI", "model_id": "openai/gpt-4o-mini", "label": "GPT-4o mini"},
    {"provider": "OpenAI", "model_id": "openai/o3", "label": "o3"},
    {"provider": "OpenAI", "model_id": "openai/o4-mini", "label": "o4-mini"},
    {"provider": "DashScope", "model_id": "dashscope/qwen3-max", "label": "Qwen3 Max"},
    {"provider": "DashScope", "model_id": "dashscope/qwen3-plus", "label": "Qwen3 Plus"},
    {"provider": "DashScope", "model_id": "dashscope/qwen3-turbo", "label": "Qwen3 Turbo"},
]

EMBEDDING_MODELS: list[dict[str, str]] = [
    {"provider": "OpenAI", "model_id": "openai/text-embedding-3-small", "label": "text-embedding-3-small"},
    {"provider": "OpenAI", "model_id": "openai/text-embedding-3-large", "label": "text-embedding-3-large"},
    {"provider": "DashScope", "model_id": "dashscope/text-embedding-v3", "label": "text-embedding-v3"},
]

# Maps provider name → required key field name
PROVIDER_KEY_MAP: dict[str, str] = {
    "Anthropic": "anthropic",
    "OpenAI": "openai",
    "DashScope": "dashscope",
}

# ---------------------------------------------------------------------------
# API response/request schemas
# ---------------------------------------------------------------------------

class ApiKeyStatus(BaseModel):
    has_key: bool


class ModelSettingsResponse(BaseModel):
    chat_model: str
    ingestion_model: str
    embedding_model: str
    anthropic_api_key: ApiKeyStatus
    openai_api_key: ApiKeyStatus
    dashscope_api_key: ApiKeyStatus

    model_config = {"from_attributes": True}


class UpdateModelSettingsRequest(BaseModel):
    chat_model: str | None = Field(None, max_length=200)
    ingestion_model: str | None = Field(None, max_length=200)
    embedding_model: str | None = Field(None, max_length=200)
    # Pass a string to set/update the key; pass None explicitly to clear it;
    # omit the field entirely to leave it unchanged.
    anthropic_api_key: str | None = Field(default=..., exclude=True)
    openai_api_key: str | None = Field(default=..., exclude=True)
    dashscope_api_key: str | None = Field(default=..., exclude=True)

    model_config = {"extra": "ignore"}


class ModelCatalogResponse(BaseModel):
    chat_models: list[dict[str, Any]]
    embedding_models: list[dict[str, Any]]
```

> **Note on `UpdateModelSettingsRequest`:** API key fields use `Field(default=...)` so they are required in the JSON body. Callers must pass a string, `null`, or the sentinel value. The service layer distinguishes "omitted" vs "null" by checking whether the value was explicitly provided. We use a simpler pattern: pass `""` (empty string) to mean "leave unchanged"; pass `null` to clear; pass a real key to set. Update schemas.py accordingly:

```python
# Revised key fields — use empty string "" as sentinel for "unchanged"
class UpdateModelSettingsRequest(BaseModel):
    chat_model: str | None = None
    ingestion_model: str | None = None
    embedding_model: str | None = None
    # "" = unchanged, None = clear, "sk-..." = set new value
    anthropic_api_key: str | None = Field(default="", description="Empty string = unchanged, null = clear")
    openai_api_key: str | None = Field(default="", description="Empty string = unchanged, null = clear")
    dashscope_api_key: str | None = Field(default="", description="Empty string = unchanged, null = clear")
```

### Step 4: Commit

```bash
git add backend/app/domain/settings/
git commit -m "feat(settings): add domain scaffolding — model, schemas, exceptions"
```

---

## Task 3: `settings` domain — interfaces and service

**Files:**
- Create: `backend/app/domain/settings/interfaces.py`
- Create: `backend/app/domain/settings/service.py`

### Step 1: Create the interface (ABC)

```python
# backend/app/domain/settings/interfaces.py
import uuid
from abc import ABC, abstractmethod

from app.domain.settings.models import UserModelSettings
from app.domain.settings.schemas import ModelSettingsResponse, UpdateModelSettingsRequest


class AbstractSettingsService(ABC):

    @abstractmethod
    async def get_model_settings(self, user_id: uuid.UUID) -> ModelSettingsResponse:
        """Return the user's current model settings (API keys as has_key bools)."""
        ...

    @abstractmethod
    async def upsert_model_settings(
        self,
        user_id: uuid.UUID,
        request: UpdateModelSettingsRequest,
    ) -> ModelSettingsResponse:
        """Create or update model settings for a user."""
        ...

    @abstractmethod
    async def get_raw_settings(self, user_id: uuid.UUID) -> UserModelSettings | None:
        """Return the raw ORM row with decrypted keys (internal use only)."""
        ...
```

### Step 2: Create the service

```python
# backend/app/domain/settings/service.py
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.settings.exceptions import SettingsNotFoundError
from app.domain.settings.interfaces import AbstractSettingsService
from app.domain.settings.models import UserModelSettings
from app.domain.settings.schemas import (
    ApiKeyStatus,
    ModelSettingsResponse,
    UpdateModelSettingsRequest,
)
from app.infra.encryption import decrypt_value, encrypt_value


class SettingsService(AbstractSettingsService):

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_model_settings(self, user_id: uuid.UUID) -> ModelSettingsResponse:
        row = await self._get_or_create(user_id)
        return self._to_response(row)

    async def upsert_model_settings(
        self,
        user_id: uuid.UUID,
        request: UpdateModelSettingsRequest,
    ) -> ModelSettingsResponse:
        row = await self._get_or_create(user_id)

        if request.chat_model is not None:
            row.chat_model = request.chat_model
        if request.ingestion_model is not None:
            row.ingestion_model = request.ingestion_model
        if request.embedding_model is not None:
            row.embedding_model = request.embedding_model

        row.anthropic_api_key_enc = self._apply_key(
            request.anthropic_api_key, row.anthropic_api_key_enc
        )
        row.openai_api_key_enc = self._apply_key(
            request.openai_api_key, row.openai_api_key_enc
        )
        row.dashscope_api_key_enc = self._apply_key(
            request.dashscope_api_key, row.dashscope_api_key_enc
        )

        await self._db.commit()
        await self._db.refresh(row)
        return self._to_response(row)

    async def get_raw_settings(self, user_id: uuid.UUID) -> UserModelSettings | None:
        """Return raw row with encrypted key fields — callers must decrypt."""
        result = await self._db.execute(
            select(UserModelSettings).where(UserModelSettings.user_id == user_id)
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_or_create(self, user_id: uuid.UUID) -> UserModelSettings:
        result = await self._db.execute(
            select(UserModelSettings).where(UserModelSettings.user_id == user_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = UserModelSettings(user_id=user_id)
            self._db.add(row)
            await self._db.flush()
        return row

    @staticmethod
    def _apply_key(new_value: str | None, existing_enc: str | None) -> str | None:
        """
        Determine the new encrypted value for an API key field.

        - "" (empty string) → leave unchanged (return existing_enc)
        - None             → clear the key (return None)
        - "sk-..."         → encrypt and store
        """
        if new_value == "":
            return existing_enc
        if new_value is None:
            return None
        return encrypt_value(new_value)

    @staticmethod
    def _to_response(row: UserModelSettings) -> ModelSettingsResponse:
        return ModelSettingsResponse(
            chat_model=row.chat_model,
            ingestion_model=row.ingestion_model,
            embedding_model=row.embedding_model,
            anthropic_api_key=ApiKeyStatus(has_key=row.anthropic_api_key_enc is not None),
            openai_api_key=ApiKeyStatus(has_key=row.openai_api_key_enc is not None),
            dashscope_api_key=ApiKeyStatus(has_key=row.dashscope_api_key_enc is not None),
        )
```

### Step 3: Commit

```bash
git add backend/app/domain/settings/interfaces.py backend/app/domain/settings/service.py
git commit -m "feat(settings): add SettingsService with encrypt/decrypt logic"
```

---

## Task 4: `settings` domain — router and registration

**Files:**
- Create: `backend/app/domain/settings/router.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/dependencies.py`

### Step 1: Create the router

```python
# backend/app/domain/settings/router.py
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user_id, get_db
from app.domain.settings.schemas import (
    CHAT_MODELS,
    EMBEDDING_MODELS,
    ModelCatalogResponse,
    ModelSettingsResponse,
    UpdateModelSettingsRequest,
)
from app.domain.settings.service import SettingsService

router = APIRouter(prefix="/settings", tags=["settings"])


def _get_settings_service(db: AsyncSession = Depends(get_db)) -> SettingsService:
    return SettingsService(db=db)


@router.get("/models", response_model=ModelSettingsResponse)
async def get_model_settings(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: SettingsService = Depends(_get_settings_service),
) -> ModelSettingsResponse:
    """Get the current user's model settings."""
    return await service.get_model_settings(user_id)


@router.put("/models", response_model=ModelSettingsResponse)
async def update_model_settings(
    request: UpdateModelSettingsRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: SettingsService = Depends(_get_settings_service),
) -> ModelSettingsResponse:
    """Upsert model settings for the current user."""
    return await service.upsert_model_settings(user_id, request)


@router.get("/models/catalog", response_model=ModelCatalogResponse)
async def get_model_catalog() -> ModelCatalogResponse:
    """Return the curated list of supported models per use-case."""
    return ModelCatalogResponse(
        chat_models=CHAT_MODELS,
        embedding_models=EMBEDDING_MODELS,
    )
```

### Step 2: Add `get_user_model_settings` dependency to `backend/app/dependencies.py`

Open `backend/app/dependencies.py` and add at the bottom (after the existing `get_current_user` dependency):

```python
# Add these imports at the top of dependencies.py:
from app.domain.settings.models import UserModelSettings
from app.domain.settings.service import SettingsService

# Add this function at the bottom:
async def get_user_model_settings(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> UserModelSettings | None:
    """Load the current user's raw model settings row (with encrypted keys).
    Returns None if the user has no settings configured yet."""
    service = SettingsService(db=db)
    return await service.get_raw_settings(user_id)
```

### Step 3: Register the router in `backend/app/main.py`

In `main.py`, find the block where routers are included (around line 199-203):

```python
# existing lines:
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(documents_router, prefix=settings.api_prefix)
app.include_router(knowledge_router, prefix=settings.api_prefix)
app.include_router(agents_router, prefix=settings.api_prefix)
app.include_router(ingestion_router, prefix=settings.api_prefix)
```

Add import and registration:

```python
# Add import at the top of main.py with the other router imports:
from app.domain.settings.router import router as settings_router

# Add registration in the router block:
app.include_router(settings_router, prefix=settings.api_prefix)
```

Also import `UserModelSettings` in `main.py`'s metadata section so Alembic can detect the new table:

```python
# Add alongside other model imports in main.py (or ensure it's imported somewhere in the app before alembic runs):
from app.domain.settings.models import UserModelSettings  # noqa: F401
```

### Step 4: Commit

```bash
git add backend/app/domain/settings/router.py backend/app/main.py backend/app/dependencies.py
git commit -m "feat(settings): add router and register with FastAPI app"
```

---

## Task 5: Alembic migration for `user_model_settings`

**Files:**
- Create: `backend/alembic/versions/<hash>_add_user_model_settings_table.py`

### Step 1: Generate migration

```bash
cd backend && uv run alembic revision --autogenerate -m "add_user_model_settings_table"
```

Expected: new file created at `backend/alembic/versions/<timestamp>_add_user_model_settings_table.py`

### Step 2: Verify the generated migration

Open the generated file and confirm it contains:
- `op.create_table("user_model_settings", ...)` with all 10 columns
- `op.create_index(...)` on `user_id`
- A `UniqueConstraint` on `user_id`
- Correct FK to `users.id`

If any column is missing, edit the migration to add it manually before continuing.

### Step 3: Apply migration

```bash
cd backend && uv run alembic upgrade head
```

Expected: `Running upgrade b2c4d6e8f0a1 -> <new_hash>, add_user_model_settings_table`

### Step 4: Commit

```bash
git add backend/alembic/versions/
git commit -m "feat(settings): add migration for user_model_settings table"
```

---

## Task 6: `cryptography` package dependency

**Files:**
- Modify: `backend/pyproject.toml`

### Step 1: Check if `cryptography` is already installed

```bash
cd backend && uv run python -c "import cryptography; print(cryptography.__version__)"
```

If it prints a version, skip to Step 3 (it is a transitive dep of `python-jose[cryptography]`).

### Step 2: Add explicit dependency

In `backend/pyproject.toml`, add to the `[project] dependencies` list:

```toml
"cryptography>=42.0.0",
```

Then sync:

```bash
cd backend && uv sync
```

### Step 3: Commit (only if pyproject.toml was changed)

```bash
git add backend/pyproject.toml
git commit -m "chore(deps): add explicit cryptography dependency"
```

---

## Task 7: Settings domain tests

**Files:**
- Create: `backend/app/domain/settings/tests/__init__.py`
- Create: `backend/app/domain/settings/tests/test_settings_router.py`

### Step 1: Write the tests

```python
# backend/app/domain/settings/tests/test_settings_router.py
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.domain.settings.schemas import (
    ApiKeyStatus,
    ModelSettingsResponse,
    UpdateModelSettingsRequest,
)
from app.domain.settings.service import SettingsService


# -----------------------------------------------------------------------
# Unit tests for SettingsService._apply_key
# -----------------------------------------------------------------------

class TestApplyKey:
    def test_empty_string_returns_existing(self):
        existing = "encrypted_value"
        assert SettingsService._apply_key("", existing) == existing

    def test_none_clears_key(self):
        assert SettingsService._apply_key(None, "some_enc") is None

    def test_new_value_encrypts(self):
        with patch("app.domain.settings.service.encrypt_value", return_value="enc") as mock_enc:
            result = SettingsService._apply_key("sk-new-key", None)
            mock_enc.assert_called_once_with("sk-new-key")
            assert result == "enc"


# -----------------------------------------------------------------------
# Unit tests for SettingsService._to_response
# -----------------------------------------------------------------------

class TestToResponse:
    def _make_row(self, anthropic=None, openai=None, dashscope=None):
        row = MagicMock()
        row.chat_model = "anthropic/claude-sonnet-4-20250514"
        row.ingestion_model = "dashscope/qwen3-max"
        row.embedding_model = "openai/text-embedding-3-small"
        row.anthropic_api_key_enc = anthropic
        row.openai_api_key_enc = openai
        row.dashscope_api_key_enc = dashscope
        return row

    def test_has_key_true_when_enc_present(self):
        row = self._make_row(anthropic="enc_key")
        resp = SettingsService._to_response(row)
        assert resp.anthropic_api_key.has_key is True
        assert resp.openai_api_key.has_key is False

    def test_has_key_false_when_none(self):
        row = self._make_row()
        resp = SettingsService._to_response(row)
        assert resp.anthropic_api_key.has_key is False
        assert resp.openai_api_key.has_key is False
        assert resp.dashscope_api_key.has_key is False


# -----------------------------------------------------------------------
# Integration-style test for the service upsert logic (mocked DB)
# -----------------------------------------------------------------------

class TestSettingsServiceUpsert:
    @pytest.mark.asyncio
    async def test_upsert_creates_row_if_not_exists(self):
        mock_db = AsyncMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        service = SettingsService(db=mock_db)
        user_id = uuid.uuid4()

        # Patch _get_or_create to return a mock row
        with patch.object(service, "_get_or_create", new_callable=AsyncMock) as mock_create:
            mock_row = MagicMock()
            mock_row.chat_model = "openai/gpt-4o"
            mock_row.ingestion_model = "openai/gpt-4o"
            mock_row.embedding_model = "openai/text-embedding-3-small"
            mock_row.anthropic_api_key_enc = None
            mock_row.openai_api_key_enc = None
            mock_row.dashscope_api_key_enc = None
            mock_create.return_value = mock_row

            request = UpdateModelSettingsRequest(
                chat_model="openai/gpt-4o",
                ingestion_model="openai/gpt-4o",
                embedding_model="openai/text-embedding-3-small",
                anthropic_api_key="",
                openai_api_key="sk-test-key",
                dashscope_api_key=None,
            )

            with patch("app.domain.settings.service.encrypt_value", return_value="enc_key"):
                result = await service.upsert_model_settings(user_id, request)

            assert result.openai_api_key.has_key is True
            assert result.dashscope_api_key.has_key is False
```

### Step 2: Run the tests

```bash
cd backend && uv run pytest app/domain/settings/tests/ -v
```
Expected: All tests PASS

### Step 3: Commit

```bash
git add backend/app/domain/settings/tests/
git commit -m "test(settings): add service and router tests"
```

---

## Task 8: `ScopedLLMProvider` — per-user LLM wrapper

**Files:**
- Modify: `backend/app/infra/llm.py`

### Step 1: Add `ScopedLLMProvider` class to `backend/app/infra/llm.py`

After the existing `LLMProvider` class (before the module-level singleton on line 353), add:

```python
class ScopedLLMProvider:
    """
    Lightweight wrapper around LLMProvider that overrides model names
    and injects per-user API keys into LiteLLM call kwargs.

    Does NOT mutate the global llm_provider singleton.
    """

    def __init__(
        self,
        base: "LLMProvider",
        chat_model: str,
        ingestion_model: str,
        anthropic_api_key: str | None = None,
        openai_api_key: str | None = None,
        dashscope_api_key: str | None = None,
    ) -> None:
        self._base = base
        self._chat_model = chat_model
        self._ingestion_model = ingestion_model
        self._api_keys: dict[str, str] = {}
        if anthropic_api_key:
            self._api_keys["anthropic"] = anthropic_api_key
        if openai_api_key:
            self._api_keys["openai"] = openai_api_key
        if dashscope_api_key:
            self._api_keys["dashscope"] = dashscope_api_key

    def _get_api_key_for_model(self, model: str) -> str | None:
        """Return the user's API key for the given model's provider prefix."""
        if model.startswith("anthropic/"):
            return self._api_keys.get("anthropic")
        if model.startswith("openai/"):
            return self._api_keys.get("openai")
        if model.startswith("dashscope/"):
            return self._api_keys.get("dashscope")
        return None

    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        stream: bool = False,
        **kwargs,
    ):
        """Chat completion using the user's model and API key."""
        effective_model = model or self._chat_model
        api_key = self._get_api_key_for_model(effective_model)
        if api_key:
            kwargs["api_key"] = api_key
        # For DashScope, always inject the API base
        if effective_model.startswith("dashscope/"):
            kwargs.setdefault("api_base", DASHSCOPE_API_BASE)
        return await self._base.complete(
            messages=messages,
            model=effective_model,
            stream=stream,
            **kwargs,
        )

    async def complete_for_ingestion(
        self,
        messages: list[dict],
        **kwargs,
    ):
        """Chat completion specifically for ingestion jobs (uses ingestion_model)."""
        return await self.complete(
            messages=messages,
            model=self._ingestion_model,
            **kwargs,
        )

    async def complete_with_retry(
        self,
        messages: list[dict],
        model: str | None = None,
        max_retries: int = 3,
        **kwargs,
    ):
        effective_model = model or self._chat_model
        api_key = self._get_api_key_for_model(effective_model)
        if api_key:
            kwargs["api_key"] = api_key
        if effective_model.startswith("dashscope/"):
            kwargs.setdefault("api_base", DASHSCOPE_API_BASE)
        return await self._base.complete_with_retry(
            messages=messages,
            model=effective_model,
            max_retries=max_retries,
            **kwargs,
        )
```

### Step 2: Add `with_user_settings` factory method to `LLMProvider`

Inside the `LLMProvider` class, after the last existing method, add:

```python
def with_user_settings(
    self,
    user_settings: "UserModelSettings",  # forward ref to avoid circular import
) -> "ScopedLLMProvider":
    """Return a ScopedLLMProvider using the user's models and decrypted API keys."""
    from app.domain.settings.models import UserModelSettings  # local import
    from app.infra.encryption import decrypt_value

    def _safe_decrypt(enc: str | None) -> str | None:
        if enc is None:
            return None
        try:
            return decrypt_value(enc)
        except Exception:
            return None

    return ScopedLLMProvider(
        base=self,
        chat_model=user_settings.chat_model,
        ingestion_model=user_settings.ingestion_model,
        anthropic_api_key=_safe_decrypt(user_settings.anthropic_api_key_enc),
        openai_api_key=_safe_decrypt(user_settings.openai_api_key_enc),
        dashscope_api_key=_safe_decrypt(user_settings.dashscope_api_key_enc),
    )
```

### Step 3: Commit

```bash
git add backend/app/infra/llm.py
git commit -m "feat(settings): add ScopedLLMProvider and LLMProvider.with_user_settings()"
```

---

## Task 9: Wire user settings into `RAGAgent`

**Files:**
- Modify: `backend/app/domain/agents/rag_agent.py`
- Modify: `backend/app/domain/agents/router.py`

### Step 1: Modify `RAGAgent.__init__` to accept optional user settings

In `backend/app/domain/agents/rag_agent.py`, update the constructor:

```python
# Add import at the top:
from app.domain.settings.models import UserModelSettings  # noqa: TC002
from app.infra.llm import LLMProvider, ScopedLLMProvider

# Update __init__ signature:
def __init__(
    self,
    llm: LLMProvider,
    chat_service: IChatService,
    tools: list[IAgentTool],
    user_settings: UserModelSettings | None = None,
) -> None:
    self._llm: LLMProvider | ScopedLLMProvider = (
        llm.with_user_settings(user_settings) if user_settings is not None else llm
    )
    self._chat_service = chat_service
    self._tools = {tool.name: tool for tool in tools}
```

### Step 2: Modify the agents router to inject user settings

In `backend/app/domain/agents/router.py`, find the chat endpoint and add the `get_user_model_settings` dependency:

```python
# Add import:
from app.dependencies import get_user_model_settings
from app.domain.settings.models import UserModelSettings

# Update the streaming chat endpoint to inject and pass user_settings:
# (Find the endpoint that creates RAGAgent and pass user_settings=user_settings)
```

> **Note:** Read the existing `backend/app/domain/agents/router.py` first to find the exact lines where `RAGAgent` is instantiated, then add `user_settings: UserModelSettings | None = Depends(get_user_model_settings)` to the endpoint signature and pass it through to `RAGAgent(llm=llm, ..., user_settings=user_settings)`.

### Step 3: Commit

```bash
git add backend/app/domain/agents/rag_agent.py backend/app/domain/agents/router.py
git commit -m "feat(settings): wire per-user settings into RAGAgent"
```

---

## Task 10: Wire user settings into `VectorService` and `IngestionOrchestrator`

**Files:**
- Modify: `backend/app/domain/knowledge/vector_service.py`
- Modify: `backend/app/domain/ingestion/orchestrator.py`
- Modify: `backend/app/domain/ingestion/orchestrator_tools.py`

### Step 1: Update `VectorService` to accept optional API key override

In `backend/app/domain/knowledge/vector_service.py`, update `__init__`:

```python
# Add import:
from app.infra.encryption import decrypt_value

# Update constructor:
def __init__(
    self,
    db: AsyncSession,
    embedding_model: str | None = None,
    embedding_api_key: str | None = None,
) -> None:
    self._db = db
    self._embedding_model = embedding_model or _get_embedding_model()
    self._embedding_api_key = embedding_api_key  # injected per-user key
```

Then in `_generate_embeddings()`, pass the key to LiteLLM if present:

```python
async def _generate_embeddings(self, texts: list[str]) -> list[list[float]]:
    kwargs: dict = {"model": self._embedding_model, "input": texts}
    if self._embedding_api_key:
        kwargs["api_key"] = self._embedding_api_key
    response = await litellm.aembedding(**kwargs)
    ...
```

### Step 2: Add a factory helper for user-scoped `VectorService`

```python
# Add to vector_service.py:
@classmethod
def for_user(
    cls,
    db: AsyncSession,
    user_settings: "UserModelSettings | None",
) -> "VectorService":
    """Factory that creates a VectorService scoped to the user's embedding model/key."""
    if user_settings is None:
        return cls(db=db)

    from app.infra.encryption import decrypt_value

    api_key: str | None = None
    if user_settings.openai_api_key_enc:
        try:
            api_key = decrypt_value(user_settings.openai_api_key_enc)
        except Exception:
            api_key = None

    # DashScope embeddings also use the dashscope key
    if user_settings.embedding_model.startswith("dashscope/") and user_settings.dashscope_api_key_enc:
        try:
            api_key = decrypt_value(user_settings.dashscope_api_key_enc)
        except Exception:
            api_key = None

    return cls(
        db=db,
        embedding_model=user_settings.embedding_model,
        embedding_api_key=api_key,
    )
```

### Step 3: Update `IngestionOrchestrator`

Read `backend/app/domain/ingestion/orchestrator.py` fully, then update its `__init__` to accept `user_settings: UserModelSettings | None = None` and create a scoped LLM provider if settings are present. Pass the scoped provider to all internal LLM calls.

### Step 4: Commit

```bash
git add backend/app/domain/knowledge/vector_service.py \
        backend/app/domain/ingestion/orchestrator.py \
        backend/app/domain/ingestion/orchestrator_tools.py
git commit -m "feat(settings): wire per-user settings into VectorService and IngestionOrchestrator"
```

---

## Task 11: Update `contracts/openapi.yaml`

**Files:**
- Modify: `contracts/openapi.yaml`

### Step 1: Add the three new endpoints to the OpenAPI contract

Add under a new `/settings` path group:

```yaml
/settings/models/catalog:
  get:
    operationId: getModelCatalog
    summary: Get model catalog
    tags: [settings]
    security: []
    responses:
      '200':
        description: Model catalog
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ModelCatalogResponse'

/settings/models:
  get:
    operationId: getModelSettings
    summary: Get current user model settings
    tags: [settings]
    security:
      - bearerAuth: []
    responses:
      '200':
        description: Model settings
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ModelSettingsResponse'
  put:
    operationId: updateModelSettings
    summary: Update model settings
    tags: [settings]
    security:
      - bearerAuth: []
    requestBody:
      required: true
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/UpdateModelSettingsRequest'
    responses:
      '200':
        description: Updated model settings
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ModelSettingsResponse'
```

Add the new schema components:

```yaml
ApiKeyStatus:
  type: object
  properties:
    has_key:
      type: boolean

ModelSettingsResponse:
  type: object
  properties:
    chat_model:
      type: string
    ingestion_model:
      type: string
    embedding_model:
      type: string
    anthropic_api_key:
      $ref: '#/components/schemas/ApiKeyStatus'
    openai_api_key:
      $ref: '#/components/schemas/ApiKeyStatus'
    dashscope_api_key:
      $ref: '#/components/schemas/ApiKeyStatus'

UpdateModelSettingsRequest:
  type: object
  properties:
    chat_model:
      type: string
      nullable: true
    ingestion_model:
      type: string
      nullable: true
    embedding_model:
      type: string
      nullable: true
    anthropic_api_key:
      type: string
      nullable: true
      description: "Empty string = unchanged, null = clear"
    openai_api_key:
      type: string
      nullable: true
    dashscope_api_key:
      type: string
      nullable: true

ModelCatalogResponse:
  type: object
  properties:
    chat_models:
      type: array
      items:
        type: object
    embedding_models:
      type: array
      items:
        type: object
```

### Step 2: Commit

```bash
git add contracts/openapi.yaml
git commit -m "docs(contract): add settings/models endpoints to OpenAPI spec"
```

---

## Task 12: Frontend — types and API hook

**Files:**
- Create: `frontend/src/types/settings.ts`
- Create: `frontend/src/hooks/use-model-settings.ts`

### Step 1: Create TypeScript types

```typescript
// frontend/src/types/settings.ts

export interface ApiKeyStatus {
  has_key: boolean;
}

export interface ModelSettings {
  chat_model: string;
  ingestion_model: string;
  embedding_model: string;
  anthropic_api_key: ApiKeyStatus;
  openai_api_key: ApiKeyStatus;
  dashscope_api_key: ApiKeyStatus;
}

export interface UpdateModelSettingsRequest {
  chat_model?: string | null;
  ingestion_model?: string | null;
  embedding_model?: string | null;
  /** Empty string = unchanged, null = clear the key */
  anthropic_api_key?: string | null;
  openai_api_key?: string | null;
  dashscope_api_key?: string | null;
}

export interface ModelOption {
  provider: string;
  model_id: string;
  label: string;
}

export interface ModelCatalog {
  chat_models: ModelOption[];
  embedding_models: ModelOption[];
}
```

### Step 2: Create the hook

```typescript
// frontend/src/hooks/use-model-settings.ts
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { ModelCatalog, ModelSettings, UpdateModelSettingsRequest } from "@/types/settings";

const SETTINGS_KEY = ["settings", "models"] as const;
const CATALOG_KEY = ["settings", "models", "catalog"] as const;

export function useModelSettings() {
  const queryClient = useQueryClient();

  const settingsQuery = useQuery<ModelSettings>({
    queryKey: SETTINGS_KEY,
    queryFn: () => apiClient.get<ModelSettings>("/settings/models"),
  });

  const catalogQuery = useQuery<ModelCatalog>({
    queryKey: CATALOG_KEY,
    queryFn: () => apiClient.get<ModelCatalog>("/settings/models/catalog"),
    staleTime: Infinity, // catalog never changes at runtime
  });

  const updateMutation = useMutation({
    mutationFn: (data: UpdateModelSettingsRequest) =>
      apiClient.put<ModelSettings>("/settings/models", data),
    onSuccess: (updated) => {
      queryClient.setQueryData(SETTINGS_KEY, updated);
    },
  });

  return {
    settings: settingsQuery.data ?? null,
    catalog: catalogQuery.data ?? null,
    isLoading: settingsQuery.isLoading,
    isSaving: updateMutation.isPending,
    error: settingsQuery.error?.message ?? updateMutation.error?.message ?? null,
    isSuccess: updateMutation.isSuccess,
    updateSettings: (data: UpdateModelSettingsRequest) => updateMutation.mutateAsync(data),
  };
}
```

### Step 3: Commit

```bash
git add frontend/src/types/settings.ts frontend/src/hooks/use-model-settings.ts
git commit -m "feat(settings): add TypeScript types and useModelSettings hook"
```

---

## Task 13: Frontend — Model Configuration UI section

**Files:**
- Modify: `frontend/src/app/(dashboard)/settings/page.tsx`

### Step 1: Read the current settings page

The current `frontend/src/app/(dashboard)/settings/page.tsx` has three sections:
- Profile (lines 57–128)
- Preferences (lines 130–171)
- Danger Zone (lines 173–206)

### Step 2: Add the Model Configuration section

Insert the following section between the closing `</div>` of the Profile card and the opening `<div>` of the Preferences card (between lines ~128 and ~130):

```tsx
{/* ------------------------------------------------------------------ */}
{/* Model Configuration Section                                         */}
{/* ------------------------------------------------------------------ */}
import { useModelSettings } from "@/hooks/use-model-settings";
// (add this import at the top of the file with the other hook imports)
```

Add the import at the top of the file:

```tsx
import { useModelSettings } from "@/hooks/use-model-settings";
import type { UpdateModelSettingsRequest } from "@/types/settings";
```

Add state and handlers inside the component (after the existing `updateProfileMutation`):

```tsx
const {
  settings: modelSettings,
  catalog,
  isLoading: isLoadingModels,
  isSaving: isSavingModels,
  isSuccess: modelSaveSuccess,
  error: modelError,
  updateSettings,
} = useModelSettings();

// Local state for the form
const [chatModel, setChatModel] = React.useState("");
const [ingestionModel, setIngestionModel] = React.useState("");
const [embeddingModel, setEmbeddingModel] = React.useState("");
const [anthropicKey, setAnthropicKey] = React.useState("");
const [openaiKey, setOpenaiKey] = React.useState("");
const [dashscopeKey, setDashscopeKey] = React.useState("");
const [showKeys, setShowKeys] = React.useState<Record<string, boolean>>({});

// Sync fetched settings into form state
React.useEffect(() => {
  if (modelSettings) {
    setChatModel(modelSettings.chat_model);
    setIngestionModel(modelSettings.ingestion_model);
    setEmbeddingModel(modelSettings.embedding_model);
  }
}, [modelSettings]);

// Warn when selected model's provider has no key
const getProviderForModel = (modelId: string): string => {
  if (modelId.startsWith("anthropic/")) return "anthropic";
  if (modelId.startsWith("openai/")) return "openai";
  if (modelId.startsWith("dashscope/")) return "dashscope";
  return "";
};

const hasKeyForModel = (modelId: string): boolean => {
  if (!modelSettings) return false;
  const prov = getProviderForModel(modelId);
  if (prov === "anthropic") return modelSettings.anthropic_api_key.has_key;
  if (prov === "openai") return modelSettings.openai_api_key.has_key;
  if (prov === "dashscope") return modelSettings.dashscope_api_key.has_key;
  return false;
};

const handleSaveModels = async () => {
  const payload: UpdateModelSettingsRequest = {
    chat_model: chatModel || undefined,
    ingestion_model: ingestionModel || undefined,
    embedding_model: embeddingModel || undefined,
    anthropic_api_key: anthropicKey || "",   // "" = unchanged
    openai_api_key: openaiKey || "",
    dashscope_api_key: dashscopeKey || "",
  };
  await updateSettings(payload);
  // Clear key inputs after save
  setAnthropicKey("");
  setOpenaiKey("");
  setDashscopeKey("");
};
```

Add the JSX section (insert between Profile card's closing `</div>` and Preferences card's opening `<div>`):

```tsx
{/* Model Configuration */}
<div className="rounded-lg border bg-card p-6 shadow-sm">
  <h2 className="text-lg font-semibold mb-1">Model Configuration</h2>
  <p className="text-sm text-muted-foreground mb-6">
    Configure the AI models used for chat, ingestion, and embeddings. Your API keys are encrypted and never exposed.
  </p>

  {isLoadingModels ? (
    <div className="text-sm text-muted-foreground">Loading model settings...</div>
  ) : (
    <div className="space-y-8">

      {/* API Keys */}
      <div>
        <h3 className="text-sm font-medium mb-3">API Keys</h3>
        <div className="space-y-3">
          {[
            { label: "Anthropic", field: "anthropic", value: anthropicKey, setter: setAnthropicKey, hasKey: modelSettings?.anthropic_api_key.has_key },
            { label: "OpenAI", field: "openai", value: openaiKey, setter: setOpenaiKey, hasKey: modelSettings?.openai_api_key.has_key },
            { label: "DashScope", field: "dashscope", value: dashscopeKey, setter: setDashscopeKey, hasKey: modelSettings?.dashscope_api_key.has_key },
          ].map(({ label, field, value, setter, hasKey }) => (
            <div key={field} className="flex items-center gap-3">
              <span className="w-24 text-sm font-medium shrink-0">{label}</span>
              <div className="relative flex-1">
                <input
                  type={showKeys[field] ? "text" : "password"}
                  placeholder={hasKey ? "••••••••  (stored)" : "Enter API key…"}
                  value={value}
                  onChange={(e) => setter(e.target.value)}
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm pr-10"
                />
                <button
                  type="button"
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  onClick={() => setShowKeys((prev) => ({ ...prev, [field]: !prev[field] }))}
                >
                  {showKeys[field] ? "Hide" : "Show"}
                </button>
              </div>
              {hasKey ? (
                <span className="text-xs text-green-600 font-medium shrink-0">✓ Configured</span>
              ) : (
                <span className="text-xs text-muted-foreground shrink-0">Not set</span>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Model Selection */}
      <div>
        <h3 className="text-sm font-medium mb-3">Model Selection</h3>
        <div className="space-y-4">
          {[
            { label: "Chat model", value: chatModel, setter: setChatModel, models: catalog?.chat_models ?? [] },
            { label: "Ingestion model", value: ingestionModel, setter: setIngestionModel, models: catalog?.chat_models ?? [] },
            { label: "Embedding model", value: embeddingModel, setter: setEmbeddingModel, models: catalog?.embedding_models ?? [] },
          ].map(({ label, value, setter, models }) => {
            const needsKey = value && !hasKeyForModel(value);
            const provider = getProviderForModel(value);
            return (
              <div key={label}>
                <label className="block text-sm text-muted-foreground mb-1">{label}</label>
                <select
                  value={value}
                  onChange={(e) => setter(e.target.value)}
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                >
                  {["Anthropic", "OpenAI", "DashScope"].map((prov) => {
                    const provModels = models.filter((m) => m.provider === prov);
                    if (provModels.length === 0) return null;
                    return (
                      <optgroup key={prov} label={prov}>
                        {provModels.map((m) => (
                          <option key={m.model_id} value={m.model_id}>
                            {m.label}
                          </option>
                        ))}
                      </optgroup>
                    );
                  })}
                </select>
                {needsKey && (
                  <p className="text-xs text-amber-600 mt-1">
                    Requires a {provider.charAt(0).toUpperCase() + provider.slice(1)} API key above.
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Save button + status */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={handleSaveModels}
          disabled={isSavingModels}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {isSavingModels ? "Saving…" : "Save model settings"}
        </button>
        {modelSaveSuccess && (
          <span className="text-sm text-green-600">Saved successfully.</span>
        )}
        {modelError && (
          <span className="text-sm text-destructive">{modelError}</span>
        )}
      </div>

    </div>
  )}
</div>
```

### Step 3: Add `React` import if not already present

Ensure `import React from "react"` (or `import * as React from "react"`) is at the top of the file.

### Step 4: Commit

```bash
git add frontend/src/app/(dashboard)/settings/page.tsx
git commit -m "feat(settings): add Model Configuration section to settings page"
```

---

## Task 14: End-to-end smoke test

### Step 1: Start the backend

```bash
cd backend && uv run alembic upgrade head
cd backend && uv run uvicorn app.main:app --port 8000 --reload
```

### Step 2: Verify endpoints are registered

```bash
curl -s http://localhost:8000/api/v1/settings/models/catalog | python3 -m json.tool
```
Expected: JSON with `chat_models` (10 items) and `embedding_models` (3 items)

### Step 3: Authenticate and test settings CRUD

```bash
# Login
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@dingdong.dev","password":"user123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['tokens']['access_token'])")

# GET (should return defaults with has_key: false for all)
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/settings/models | python3 -m json.tool

# PUT (save a model + fake key)
curl -s -X PUT http://localhost:8000/api/v1/settings/models \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"chat_model":"openai/gpt-4o","openai_api_key":"sk-test-123","anthropic_api_key":"","dashscope_api_key":""}' | python3 -m json.tool
# Expected: openai_api_key.has_key = true

# GET again — verify persistence
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/settings/models | python3 -m json.tool
# Expected: chat_model = "openai/gpt-4o", openai_api_key.has_key = true
```

### Step 4: Run the full backend test suite

```bash
cd backend && uv run pytest --tb=short -q
```
Expected: All tests pass (no regressions)

### Step 5: Start the frontend and verify UI

```bash
cd frontend && pnpm dev
```

Open http://localhost:3000/settings — the "Model Configuration" section should be visible between Profile and Preferences.

### Step 6: Final commit (if any fixups needed)

```bash
git add -A && git commit -m "feat(settings): per-user model settings complete"
```
