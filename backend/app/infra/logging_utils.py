"""Logging utilities for PII redaction."""


def redact_email(email: str) -> str:
    """Redact email for logging: 'user@example.com' -> 'u***@example.com'."""
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    return f"{local[0]}***@{domain}" if local else f"***@{domain}"
