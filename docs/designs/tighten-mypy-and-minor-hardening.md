# Tighten MyPy Config and Apply Minor Security Hardening

## Context

Security audit found several lower-severity issues that can be fixed in one pass:
1. MyPy is configured to ignore 11 error categories — effectively a no-op. The OAuth token bug (#2 in audit) would have been caught by `attr-defined`.
2. Refresh token stored in `localStorage` is XSS-vulnerable (vs httpOnly cookie). For now, at minimum add a comment explaining the risk and a `TODO`.
3. Frontend OAuth callback stores refresh token under a different key (`"refresh_token"`) than the auth provider (`"refresh_token"`) — they match, but the callback page doesn't use the `REFRESH_KEY` constant.
4. No log sanitization for PII (emails logged in auth service).

## Requirements

- Re-enable the most critical mypy error codes: `attr-defined`, `return-value`, `assignment`
- Fix any type errors that surface from re-enabling those codes
- Unify the refresh token localStorage key to use a shared constant in the callback page
- Redact email addresses in auth service log messages
- Add `TODO` comments documenting the localStorage refresh token XSS risk
- All existing tests must continue to pass

## Implementation

### 1. Tighten mypy config

**File:** `backend/pyproject.toml`

Update the `disable_error_code` list — remove `attr-defined`, `return-value`, and `assignment`:

```python
disable_error_code = [
    # Re-enabled: "attr-defined", "return-value", "assignment"
    "no-untyped-def",
    "import-untyped",
    "method-assign",
    "arg-type",
    "union-attr",
    "override",
    "var-annotated",
    "misc",
    "func-returns-value",
]
```

### 2. Fix type errors surfaced by stricter mypy

After re-enabling the three codes, run `cd backend && uv run mypy app/` and fix any errors. Expected fixes:

**Likely `attr-defined` errors (the OAuth bug is in a separate design doc, but check for others):**
- Any access to non-existent model attributes will surface
- Fix by using the correct attribute names

**Likely `return-value` errors:**
- Functions declared as returning `X` but returning `None` in some paths
- Fix by adding explicit return statements or adjusting return types

**Likely `assignment` errors:**
- Variables reassigned to incompatible types
- Fix by adding type annotations or adjusting logic

Note: The agent should run `uv run mypy app/` after making the config change and fix each reported error. The exact errors will depend on current codebase state. Do not suppress errors with `# type: ignore` unless absolutely necessary — fix the underlying code.

### 3. Unify refresh token key in OAuth callback

**File:** `frontend/src/app/auth/callback/page.tsx`

Replace the direct `localStorage.setItem("refresh_token", ...)` with the shared constant:

```typescript
// At top of file, add import:
import { REFRESH_KEY } from "@/hooks/use-auth";  // Won't work — not exported

// Alternative: extract the constant to a shared location
```

Actually, the `REFRESH_KEY` constant is defined inside `use-auth.tsx` but not exported. The fix is:

**File:** `frontend/src/lib/token-store.ts`

Move the constant here (it's the canonical place for token storage):

```typescript
/**
 * In-memory access token store.
 *
 * Keeps the short-lived access token out of localStorage to limit XSS impact.
 * The token is lost on page reload — the auth layer refreshes it automatically.
 *
 * TODO: The refresh token is stored in localStorage, which is vulnerable to XSS.
 * A more secure approach would be to store it in an httpOnly cookie via a BFF pattern.
 * See: https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html
 */

let accessToken: string | null = null;

/** localStorage key for the refresh token. */
export const REFRESH_TOKEN_KEY = "refresh_token";

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}
```

**File:** `frontend/src/hooks/use-auth.tsx`

Replace the local `REFRESH_KEY` constant:

```typescript
import { setAccessToken, REFRESH_TOKEN_KEY } from "@/lib/token-store";

// Remove: const REFRESH_KEY = "refresh_token";
// Replace all occurrences of REFRESH_KEY with REFRESH_TOKEN_KEY
```

**File:** `frontend/src/app/auth/callback/page.tsx`

```typescript
import { setAccessToken, REFRESH_TOKEN_KEY } from "@/lib/token-store";

// Replace line 59:
localStorage.setItem(REFRESH_TOKEN_KEY, response.tokens.refresh_token);
```

### 4. Redact PII in auth logs

**File:** `backend/app/domain/auth/service.py`

Add a helper function and update log messages:

```python
def _redact_email(email: str) -> str:
    """Redact email for logging: 'user@example.com' → 'u***@example.com'."""
    local, domain = email.split("@", 1)
    return f"{local[0]}***@{domain}" if local else f"***@{domain}"
```

Update the three log lines:

```python
# Line 86 (register):
logger.info("User registered: %s (%s)", user.id, _redact_email(data.email))

# Line 121 (login):
logger.info("User logged in: %s (%s)", user.id, _redact_email(data.email))

# Line 203 (update_profile):
logger.info("User profile updated: %s", user_id)  # Already fine — no email
```

**File:** `backend/app/domain/auth/oauth/service.py`

```python
# Line 82-87:
logger.info(
    "OAuth login (%s): user=%s email=%s",
    self._provider.provider_name,
    user.id,
    _redact_email(user.email),  # ← import the helper or inline
)

# Line 116:
logger.info("Created new user via OAuth: %s (%s)", user.id, _redact_email(user.email))
```

Add the redact function to a shared location:

**File:** `backend/app/infra/logging_utils.py` (NEW)

```python
"""Logging utilities for PII redaction."""


def redact_email(email: str) -> str:
    """Redact email for logging: 'user@example.com' → 'u***@example.com'."""
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    return f"{local[0]}***@{domain}" if local else f"***@{domain}"
```

Then import in both service files:
```python
from app.infra.logging_utils import redact_email
```

## Testing Strategy

**MyPy check:** `cd backend && uv run mypy app/` — should report zero errors after fixes.

**Full test suite:** `cd backend && uv run pytest` — all existing tests must pass.

**Frontend build:** `cd frontend && pnpm build` — verify no TypeScript errors from the constant rename.

**New tests:**

**File:** `backend/app/infra/tests/test_logging_utils.py` (NEW)
```
- test_redact_email_standard — "user@example.com" → "u***@example.com"
- test_redact_email_single_char — "a@b.com" → "a***@b.com"
- test_redact_email_no_at — "invalid" → "***"
```

## Out of Scope

- Moving refresh token to httpOnly cookie (requires backend BFF endpoint — larger change)
- Enabling ALL mypy error codes at once (gradual rollout)
- Structured logging (JSON format with PII auto-redaction)
