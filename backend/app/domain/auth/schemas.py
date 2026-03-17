"""Auth domain Pydantic schemas.

Request/response schemas for auth endpoints.
Strict separation: schemas are for API boundaries only.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# --- Request Schemas ---


class RegisterRequest(BaseModel):
    """User registration request."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    """User login request."""

    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """Token refresh request."""

    refresh_token: str


class UpdateProfileRequest(BaseModel):
    """User profile update request."""

    full_name: str | None = Field(None, min_length=1, max_length=255)
    email: EmailStr | None = None


# --- Response Schemas ---


class UserResponse(BaseModel):
    """Public user profile response."""

    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """JWT token pair response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class AuthResponse(BaseModel):
    """Combined auth response (tokens + user)."""

    user: UserResponse
    tokens: TokenResponse
