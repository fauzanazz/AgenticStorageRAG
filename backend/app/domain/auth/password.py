"""Password hashing service.

Uses bcrypt directly for secure password hashing.
Implements AbstractPasswordHasher interface.
"""

from __future__ import annotations

import bcrypt

from app.domain.auth.interfaces import AbstractPasswordHasher


class PasswordHasher(AbstractPasswordHasher):
    """BCrypt password hasher.

    Uses the bcrypt library directly (passlib has compatibility issues
    with Python 3.14+). Configured with automatic salt generation.
    """

    def hash(self, password: str) -> str:
        """Hash a plaintext password with bcrypt.

        Args:
            password: The plaintext password to hash.

        Returns:
            BCrypt hash string.
        """
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a plaintext password against a bcrypt hash.

        Args:
            plain_password: The plaintext password to verify.
            hashed_password: The stored bcrypt hash.

        Returns:
            True if the password matches, False otherwise.
        """
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
