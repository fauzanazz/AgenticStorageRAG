"""
Symmetric encryption for sensitive values (API keys).

Uses Fernet (AES-128-CBC + HMAC-SHA256) keyed from the app's JWT_SECRET_KEY.
The secret key is hashed with SHA-256 and base64url-encoded to produce a
valid 32-byte Fernet key.
"""

import base64
import hashlib

from cryptography.fernet import Fernet

from app.config import get_settings


def _get_fernet() -> Fernet:
    """Derive a Fernet instance from the app's encryption key (or JWT secret as fallback)."""
    settings = get_settings()
    key_material = settings.encryption_key or settings.jwt_secret_key
    # SHA-256 produces exactly 32 bytes → valid Fernet key when base64url-encoded
    raw_key = hashlib.sha256(key_material.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(raw_key)
    return Fernet(fernet_key)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string. Returns a URL-safe base64 token."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a previously encrypted token. Raises InvalidToken on failure."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()
