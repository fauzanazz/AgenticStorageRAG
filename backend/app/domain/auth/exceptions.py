"""Auth domain typed exceptions.

Every auth error is a typed exception so callers can catch
specific cases without parsing error messages.
"""

from __future__ import annotations


class AuthError(Exception):
    """Base exception for all auth-related errors."""

    def __init__(self, message: str = "Authentication error") -> None:
        self.message = message
        super().__init__(self.message)


class InvalidCredentialsError(AuthError):
    """Raised when email/password combination is wrong."""

    def __init__(self) -> None:
        super().__init__("Invalid email or password")


class EmailAlreadyExistsError(AuthError):
    """Raised when trying to register with an existing email."""

    def __init__(self, email: str) -> None:
        self.email = email
        super().__init__(f"Email already registered: {email}")


class InvalidTokenError(AuthError):
    """Raised when a JWT token is invalid, expired, or malformed."""

    def __init__(self, reason: str = "Invalid or expired token") -> None:
        super().__init__(reason)


class UserNotFoundError(AuthError):
    """Raised when a user lookup fails."""

    def __init__(self, identifier: str = "") -> None:
        msg = f"User not found: {identifier}" if identifier else "User not found"
        super().__init__(msg)


class InactiveUserError(AuthError):
    """Raised when an inactive user tries to authenticate."""

    def __init__(self) -> None:
        super().__init__("User account is deactivated")


class OAuthLoginRequiredError(AuthError):
    """Raised when a Google-only user tries to use password login."""

    def __init__(self, provider: str = "google") -> None:
        self.provider = provider
        super().__init__(
            f"This account uses {provider.title()} Sign-In. "
            f"Please use the {provider.title()} button to log in."
        )


class OAuthError(AuthError):
    """Raised when an OAuth flow fails."""

    def __init__(self, provider: str, reason: str) -> None:
        self.provider = provider
        super().__init__(f"OAuth error ({provider}): {reason}")
