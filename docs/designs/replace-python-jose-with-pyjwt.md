# Replace python-jose with PyJWT and Remove Dead passlib Dependency

## Context

Security audit found two dependency issues:
1. `python-jose` has been unmaintained since 2022 and has known CVEs. The project should use `PyJWT` (actively maintained, same API surface).
2. `passlib[bcrypt]` is listed as a dependency but the code uses `bcrypt` directly (noted in `password.py` as "passlib has compatibility issues with Python 3.14+"). This is dead weight.

## Requirements

- Replace `python-jose[cryptography]` with `PyJWT[crypto]` in dependencies
- Update `token.py` to use PyJWT API instead of python-jose
- Remove `passlib[bcrypt]` from dependencies, add explicit `bcrypt>=4.0.0`
- Remove `types-passlib` and `types-python-jose` from dev dependencies
- All existing auth tests must continue to pass
- JWT behavior must remain identical (HS256, same claim structure)

## Implementation

### 1. Update dependencies

**File:** `backend/pyproject.toml`

In `[project] dependencies`, make these changes:

```diff
-    "python-jose[cryptography]>=3.3.0",
-    "passlib[bcrypt]>=1.7.4",
+    "PyJWT[crypto]>=2.9.0",
+    "bcrypt>=4.0.0",
```

In `[project.optional-dependencies] dev`, remove:

```diff
-    "types-passlib>=1.7.7",
-    "types-python-jose>=3.3.4",
```

### 2. Update token service

**File:** `backend/app/domain/auth/token.py`

Replace the import and update error handling:

```python
"""JWT token service.

Creates and verifies JWT access and refresh tokens.
Implements AbstractTokenService interface.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt  # PyJWT

from app.config import get_settings
from app.domain.auth.exceptions import InvalidTokenError
from app.domain.auth.interfaces import AbstractTokenService


class TokenService(AbstractTokenService):
    """JWT token service using PyJWT.

    Access tokens are short-lived (configurable, default 30 min).
    Refresh tokens are long-lived (configurable, default 7 days).
    Both use HS256 by default (configurable via settings).
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._secret_key = settings.jwt_secret_key
        self._algorithm = settings.jwt_algorithm
        self._access_expire_minutes = settings.jwt_access_token_expire_minutes
        self._refresh_expire_days = settings.jwt_refresh_token_expire_days

    def create_access_token(self, user_id: uuid.UUID) -> str:
        """Create a short-lived access token."""
        expire = datetime.now(UTC) + timedelta(minutes=self._access_expire_minutes)
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "exp": expire,
            "type": "access",
        }
        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def create_refresh_token(self, user_id: uuid.UUID) -> str:
        """Create a long-lived refresh token."""
        expire = datetime.now(UTC) + timedelta(days=self._refresh_expire_days)
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "exp": expire,
            "type": "refresh",
        }
        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def verify_token(self, token: str) -> dict[str, Any]:
        """Verify and decode a JWT token."""
        try:
            payload = jwt.decode(
                token,
                self._secret_key,
                algorithms=[self._algorithm],
            )
            if "sub" not in payload:
                raise InvalidTokenError("Token missing subject claim")
            return payload
        except jwt.ExpiredSignatureError as e:
            raise InvalidTokenError("Token has expired") from e
        except jwt.InvalidTokenError as e:
            raise InvalidTokenError(f"Token verification failed: {e}") from e

    @property
    def access_expire_seconds(self) -> int:
        """Get access token expiry in seconds (for API response)."""
        return self._access_expire_minutes * 60
```

Key API differences:
- Import: `import jwt` instead of `from jose import JWTError, jwt`
- `jwt.encode()` returns `str` in PyJWT (jose also returns `str`, so no change)
- Error types: `jwt.ExpiredSignatureError` and `jwt.InvalidTokenError` instead of `JWTError`
- `jwt.decode()` API is identical: `decode(token, key, algorithms=[...])`

### 3. Reinstall dependencies

After the changes, run:
```bash
cd backend && uv lock && uv sync
```

## Testing Strategy

**Run:** `cd backend && uv run pytest app/domain/auth/tests/` — all token tests must pass.

The existing test file `backend/app/domain/auth/tests/test_token.py` already covers:
- `test_create_access_token_contains_expected_claims`
- `test_create_refresh_token_contains_expected_claims`
- `test_verify_valid_access_token`
- `test_verify_expired_token_raises`
- `test_verify_invalid_token_raises`
- `test_verify_token_missing_sub_raises`

These tests verify JWT behavior by encoding/decoding tokens. Since PyJWT and python-jose produce identical HS256 tokens, all tests should pass without modification.

**Full suite:** `cd backend && uv run pytest` — ensure no other module imports from `jose`.

**Verification grep:** `rg "from jose|import jose" backend/` should return zero results after the change.

## Out of Scope

- Switching JWT algorithm from HS256 to RS256 (would require key pair management)
- Adding `jti` (JWT ID) claim for token revocation
- Token blocklist in Redis
