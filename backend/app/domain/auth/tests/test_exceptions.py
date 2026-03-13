"""Tests for auth exceptions."""

from app.domain.auth.exceptions import (
    AuthError,
    EmailAlreadyExistsError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    UserNotFoundError,
)


class TestAuthExceptions:
    """Tests for typed auth exception hierarchy."""

    def test_auth_error_is_base(self) -> None:
        """All auth exceptions should be subclasses of AuthError."""
        assert issubclass(InvalidCredentialsError, AuthError)
        assert issubclass(EmailAlreadyExistsError, AuthError)
        assert issubclass(InvalidTokenError, AuthError)
        assert issubclass(UserNotFoundError, AuthError)
        assert issubclass(InactiveUserError, AuthError)

    def test_invalid_credentials_message(self) -> None:
        """InvalidCredentialsError should have default message."""
        error = InvalidCredentialsError()
        assert error.message == "Invalid email or password"

    def test_email_already_exists_includes_email(self) -> None:
        """EmailAlreadyExistsError should include the email."""
        error = EmailAlreadyExistsError("user@test.com")
        assert "user@test.com" in error.message
        assert error.email == "user@test.com"

    def test_invalid_token_custom_reason(self) -> None:
        """InvalidTokenError should accept custom reason."""
        error = InvalidTokenError("Token expired")
        assert error.message == "Token expired"

    def test_user_not_found_with_identifier(self) -> None:
        """UserNotFoundError should include identifier."""
        error = UserNotFoundError("abc-123")
        assert "abc-123" in error.message

    def test_user_not_found_without_identifier(self) -> None:
        """UserNotFoundError should work without identifier."""
        error = UserNotFoundError()
        assert error.message == "User not found"

    def test_inactive_user_message(self) -> None:
        """InactiveUserError should have default message."""
        error = InactiveUserError()
        assert "deactivated" in error.message
