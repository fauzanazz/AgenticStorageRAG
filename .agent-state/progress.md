# Progress — FAU-14 Auth Rate Limiting

## Status: Complete

## What was accomplished

This is a revision session addressing review feedback from cubic-dev-ai across 3 review rounds.

### Review issues addressed in prior commits (verified still correct):
- OAuth registration bypass blocked when `REGISTRATION_ENABLED=false` (oauth/service.py)
- OAuth link lookup happens before email match in `_find_or_create_user` (prevents provider email change issues)
- `X-Forwarded-For` only trusted when `RATE_LIMIT_TRUST_PROXY_HEADERS=true`
- `registration_enabled` defaults to `False` (secure by default)
- `.env.example` comment clearly explains code default vs dev override
- `assert_awaited_once()` used instead of `assert_called_once()` in router tests
- `mock_rate_limiter` fixture is NOT autouse — only applied where needed

### Fixed in this session:
- **test_rate_limiter.py**: Added module-level `_isolate_settings` autouse fixture to patch `get_settings` in `TestCheckRateLimit`, ensuring tests don't depend on environment variables like `RATE_LIMIT_TRUST_PROXY_HEADERS`

## Test results
- All 24 tests pass (rate limiter + auth router)

## What's left
- Nothing — all review feedback addressed

## Decisions
- Used a module-level autouse fixture rather than per-test patches in `TestCheckRateLimit` since all rate limiter tests need settings isolation. `TestGetClientIp` tests still have their own per-method patches that override this fixture with specific values.
