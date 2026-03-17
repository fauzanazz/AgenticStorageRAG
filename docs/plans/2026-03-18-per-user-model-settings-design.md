# Design: Per-User Model Settings

**Date:** 2026-03-18  
**Status:** Approved

---

## Summary

Add per-user model configuration so each user can bring their own API keys and select their preferred models for chat completions, document ingestion, and embeddings. Supports Anthropic, OpenAI, and DashScope (Alibaba) providers. Server-level model defaults remain as fallbacks for admin/system jobs.

---

## Requirements

- Per-user (not global/admin)
- Users own their own API keys (stored encrypted server-side)
- Supported providers: Anthropic, OpenAI, DashScope
- Model selection via curated dropdowns (not freeform input)
- API keys never returned in plaintext — only `has_key: bool` exposed via API

---

## Data Model

New table: `user_model_settings` (one row per user, created lazily on first save)

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID` | PK |
| `user_id` | `UUID` | FK → `users.id`, unique, indexed |
| `chat_model` | `String` | e.g. `anthropic/claude-sonnet-4-20250514` |
| `ingestion_model` | `String` | e.g. `dashscope/qwen3-max` |
| `embedding_model` | `String` | e.g. `openai/text-embedding-3-small` |
| `anthropic_api_key_enc` | `Text` (nullable) | AES-256 Fernet encrypted |
| `openai_api_key_enc` | `Text` (nullable) | AES-256 Fernet encrypted |
| `dashscope_api_key_enc` | `Text` (nullable) | AES-256 Fernet encrypted |
| `created_at` | `DateTime(tz)` | Auto-set |
| `updated_at` | `DateTime(tz)` | Auto-updated |

Encryption: `cryptography` Fernet symmetric, keyed from `settings.jwt_secret_key` (padded/hashed to 32 bytes for Fernet compatibility).

---

## API Endpoints

New domain prefix: `/api/v1/settings`

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/settings/models` | JWT (any user) | Get current user's model settings |
| `PUT` | `/api/v1/settings/models` | JWT (any user) | Upsert model settings + API keys |
| `GET` | `/api/v1/settings/models/catalog` | Public | Returns provider → model list mapping |

### GET `/settings/models` response
```json
{
  "chat_model": "anthropic/claude-sonnet-4-20250514",
  "ingestion_model": "dashscope/qwen3-max",
  "embedding_model": "openai/text-embedding-3-small",
  "anthropic_api_key": { "has_key": true },
  "openai_api_key": { "has_key": false },
  "dashscope_api_key": { "has_key": true }
}
```

### PUT `/settings/models` request
```json
{
  "chat_model": "openai/gpt-4o",
  "ingestion_model": "openai/gpt-4o",
  "embedding_model": "openai/text-embedding-3-small",
  "anthropic_api_key": "sk-ant-...",
  "openai_api_key": "sk-...",
  "dashscope_api_key": null
}
```
- Omit a key field to leave it unchanged
- Pass `null` to clear a stored key

---

## Model Catalog

### Chat & Ingestion Models

| Provider | Model ID |
|---|---|
| Anthropic | `anthropic/claude-opus-4-5` |
| Anthropic | `anthropic/claude-sonnet-4-20250514` |
| Anthropic | `anthropic/claude-haiku-3-5` |
| OpenAI | `openai/gpt-4o` |
| OpenAI | `openai/gpt-4o-mini` |
| OpenAI | `openai/o3` |
| OpenAI | `openai/o4-mini` |
| DashScope | `dashscope/qwen3-max` |
| DashScope | `dashscope/qwen3-plus` |
| DashScope | `dashscope/qwen3-turbo` |

### Embedding Models

| Provider | Model ID | Dimensions |
|---|---|---|
| OpenAI | `openai/text-embedding-3-small` | 1536 |
| OpenAI | `openai/text-embedding-3-large` | 3072 |
| DashScope | `dashscope/text-embedding-v3` | 1024 |

---

## Backend Architecture

### New domain: `backend/app/domain/settings/`

```
settings/
├── __init__.py
├── README.md
├── interfaces.py         # AbstractSettingsService ABC
├── service.py            # SettingsService (upsert, get, encrypt/decrypt)
├── models.py             # UserModelSettings SQLAlchemy model
├── schemas.py            # Pydantic schemas + MODEL_CATALOG constant
├── router.py             # FastAPI router
├── exceptions.py         # SettingsNotFoundError
└── tests/
    ├── __init__.py
    └── test_settings_router.py
```

### New infra helper: `backend/app/infra/encryption.py`

Thin Fernet wrapper:
```python
def encrypt(plaintext: str) -> str
def decrypt(ciphertext: str) -> str
```
Keyed from `settings.jwt_secret_key` (base64url-encoded SHA-256 hash to produce a valid 32-byte Fernet key).

### LLM integration changes

**`backend/app/infra/llm.py`** — Add:
```python
def with_user_settings(self, user_settings: UserModelSettings) -> ScopedLLMProvider
```
`ScopedLLMProvider` is a lightweight wrapper that:
- Overrides `default_model` / `fallback_model` with user's `chat_model` / `ingestion_model`
- Injects the user's decrypted API keys into LiteLLM `api_key` kwargs per call
- Does NOT mutate the global `llm_provider` singleton

**`backend/app/domain/knowledge/vector_service.py`** — Accept optional `embedding_model: str` and `openai_api_key: str` constructor args. Falls back to module-level defaults when absent.

**`backend/app/domain/agents/rag_agent.py`** — Accept optional `user_settings: UserModelSettings`. Instantiates `ScopedLLMProvider` when present.

**`backend/app/domain/ingestion/orchestrator.py`** — Accept optional `user_settings: UserModelSettings`. Passes scoped provider to all LLM calls.

**`backend/app/dependencies.py`** — Add `get_user_model_settings` FastAPI dependency (loads from DB, cached per-request via `Depends`).

### Migration

New Alembic migration: `add_user_model_settings_table`

---

## Frontend Architecture

### Modified: `frontend/src/app/(dashboard)/settings/page.tsx`

New "Model Configuration" section inserted between Profile and Preferences, containing three subsections:

**1. API Keys**
- Three rows: Anthropic, OpenAI, DashScope
- Masked password input with show/hide toggle
- `has_key` badge (green checkmark / "Not configured")
- Save button per provider row

**2. Model Selection**
- `chat_model` dropdown — chat & ingestion model list, grouped by provider
- `ingestion_model` dropdown — same list
- `embedding_model` dropdown — embedding model list
- Inline warning if selected model's provider has no API key configured

**3. Save**
- "Save model settings" button → `PUT /api/v1/settings/models`

### New hook: `frontend/src/hooks/use-model-settings.ts`

```ts
useModelSettings() => {
  settings: ModelSettings | null
  isLoading: boolean
  error: string | null
  updateSettings: (data: UpdateModelSettingsRequest) => Promise<void>
  updateApiKey: (provider: Provider, key: string | null) => Promise<void>
}
```

### New types: `frontend/src/types/settings.ts`

```ts
ModelSettings, UpdateModelSettingsRequest, ModelCatalog, ProviderKeyStatus
```

---

## Security Considerations

- API keys encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256)
- Keys never returned in API responses — only `has_key: bool`
- Encryption key derived from `JWT_SECRET_KEY` (already required to be strong)
- Users can only access their own settings (enforced by `get_current_user` dependency)

---

## Fallback Behavior

If a user has no `user_model_settings` row, or the row exists but a specific model/key is not set:
- LLM calls fall back to server's `DEFAULT_MODEL` / `FALLBACK_MODEL`
- Embeddings fall back to server's `EMBEDDING_MODEL` env var
- Existing behavior for all system/admin jobs (ingestion triggered by admin) is unchanged
