"""Auth API router.

All auth endpoints live here. Routers delegate to AuthService --
no business logic in this file.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.dependencies import get_current_user_id, get_db
from app.domain.auth.exceptions import (
    EmailAlreadyExistsError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    OAuthLoginRequiredError,
    UserNotFoundError,
)
from app.domain.auth.schemas import (
    AuthResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
)
from app.domain.auth.service import AuthService
from app.infra.rate_limiter import (
    LOGIN_LIMIT,
    REFRESH_LIMIT,
    REGISTER_LIMIT,
    check_rate_limit,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    """Create AuthService with injected dependencies."""
    return AuthService(db=db)


AuthServiceDep = Annotated[AuthService, Depends(_get_auth_service)]


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(
    data: RegisterRequest,
    request: Request,
    auth_service: AuthServiceDep,
) -> AuthResponse:
    """Register a new user account.

    Returns user profile and JWT tokens on success.
    """
    settings = get_settings()
    if not settings.registration_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is currently disabled",
        )
    await check_rate_limit(request, REGISTER_LIMIT, "rl:register")
    try:
        return await auth_service.register(data)
    except EmailAlreadyExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=e.message,
        ) from e


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Login with email and password",
)
async def login(
    data: LoginRequest,
    request: Request,
    auth_service: AuthServiceDep,
) -> AuthResponse:
    """Authenticate user with email and password.

    Returns user profile and JWT tokens on success.
    """
    await check_rate_limit(request, LOGIN_LIMIT, "rl:login")
    try:
        return await auth_service.login(data)
    except InvalidCredentialsError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.message,
        ) from e
    except InactiveUserError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.message,
        ) from e
    except OAuthLoginRequiredError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
        ) from e


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
)
async def refresh_token(
    data: RefreshRequest,
    request: Request,
    auth_service: AuthServiceDep,
) -> TokenResponse:
    """Get new tokens using a valid refresh token."""
    await check_rate_limit(request, REFRESH_LIMIT, "rl:refresh")
    try:
        return await auth_service.refresh_tokens(data.refresh_token)
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.message,
        ) from e
    except (UserNotFoundError, InactiveUserError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.message,
        ) from e


CurrentUserIdDep = Annotated[uuid.UUID, Depends(get_current_user_id)]


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
)
async def get_me(
    auth_service: AuthServiceDep,
    current_user_id: CurrentUserIdDep,
) -> UserResponse:
    """Get the authenticated user's profile.

    Requires a valid access token (via get_current_user dependency).
    """
    try:
        return await auth_service.get_current_user(current_user_id)
    except UserNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message,
        ) from e


@router.patch(
    "/me",
    response_model=UserResponse,
    summary="Update current user profile",
)
async def update_me(
    data: UpdateProfileRequest,
    auth_service: AuthServiceDep,
    current_user_id: CurrentUserIdDep,
) -> UserResponse:
    """Update the authenticated user's profile.

    Only provided (non-null) fields are updated.
    """
    try:
        return await auth_service.update_profile(current_user_id, data)
    except UserNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message,
        ) from e
    except EmailAlreadyExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=e.message,
        ) from e
