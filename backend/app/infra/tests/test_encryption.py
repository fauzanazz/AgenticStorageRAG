import pytest

from app.infra.encryption import decrypt_value, encrypt_value


def test_encrypt_decrypt_roundtrip():
    plaintext = "sk-ant-api03-testkey"
    ciphertext = encrypt_value(plaintext)
    assert ciphertext != plaintext
    assert decrypt_value(ciphertext) == plaintext


def test_encrypt_produces_different_values():
    # Fernet includes random IV so each encryption differs
    plaintext = "sk-test"
    assert encrypt_value(plaintext) != encrypt_value(plaintext)


def test_decrypt_invalid_raises():
    with pytest.raises(Exception):
        decrypt_value("not-valid-ciphertext")
