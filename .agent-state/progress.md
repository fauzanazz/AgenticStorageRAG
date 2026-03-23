# Progress — FAU-14: Auth Rate Limiting & Registration Toggle

## Status: All review feedback addressed (4 rounds)

## What was accomplished

### This session (revision run — round 4 feedback)
- Fixed case-sensitive email lookup in `_find_or_create_user` (oauth/service.py:118)
  - Changed `User.email == user_info.email.lower()` to `func.lower(User.email) == user_info.email.lower()`
  - Added test `test_callback_matches_existing_user_by_email_case_insensitive`
- All 64 tests pass

### Previous sessions
- Per-IP rate limiting on `/auth/login` (5/min), `/auth/register` (3/hr), `/auth/refresh` (10/min)
- `REGISTRATION_ENABLED` config (defaults `False`, `.env.example` sets `True` for dev)
- Registration check on both REST and OAuth paths
- `RATE_LIMIT_TRUST_PROXY_HEADERS` toggle for X-Forwarded-For trust
- OAuth link lookup before email match in `_find_or_create_user`
- `assert_awaited_once()` used in router tests
- Rate limiter tests isolated from environment settings
- Full test coverage: rate limiter, router wiring, registration toggle, OAuth service

## What's left
- Nothing — all 4 rounds of review feedback have been addressed

## Decisions
- Used `func.lower(User.email)` (SQLAlchemy) for case-insensitive DB comparison rather than changing the column collation, since it's a targeted fix with no schema migration needed
