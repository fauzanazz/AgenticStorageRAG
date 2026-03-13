# Auth Domain

Handles user authentication and authorization.

## Responsibilities
- User registration and login
- JWT token issuance and validation
- Password hashing and verification
- Protected route middleware

## Key Files
- `interfaces.py` — ABC contracts for auth operations
- `service.py` — AuthService implementation
- `models.py` — SQLAlchemy User model (multi-tenant ready with org_id)
- `schemas.py` — Pydantic request/response schemas
- `router.py` — FastAPI endpoints: register, login, refresh, me
- `exceptions.py` — Typed auth errors

## Adding a New Auth Feature
1. Define the interface method in `interfaces.py`
2. Implement in `service.py`
3. Add Pydantic schemas in `schemas.py`
4. Add endpoint in `router.py`
5. Write tests in `tests/`
