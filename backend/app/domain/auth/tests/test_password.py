"""Tests for password hashing service."""

from app.domain.auth.password import PasswordHasher


class TestPasswordHasher:
    """Tests for BCrypt password hashing."""

    def setup_method(self) -> None:
        self.hasher = PasswordHasher()

    def test_hash_returns_bcrypt_string(self) -> None:
        """hash() should return a bcrypt hash string."""
        result = self.hasher.hash("test_password")
        assert result.startswith("$2b$")
        assert len(result) == 60

    def test_hash_generates_different_hashes_for_same_password(self) -> None:
        """hash() should generate unique salts each time."""
        hash1 = self.hasher.hash("same_password")
        hash2 = self.hasher.hash("same_password")
        assert hash1 != hash2

    def test_verify_correct_password(self) -> None:
        """verify() should return True for matching password."""
        hashed = self.hasher.hash("correct_password")
        assert self.hasher.verify("correct_password", hashed) is True

    def test_verify_wrong_password(self) -> None:
        """verify() should return False for wrong password."""
        hashed = self.hasher.hash("correct_password")
        assert self.hasher.verify("wrong_password", hashed) is False

    def test_verify_empty_password_against_hash(self) -> None:
        """verify() should return False for empty password."""
        hashed = self.hasher.hash("some_password")
        assert self.hasher.verify("", hashed) is False
