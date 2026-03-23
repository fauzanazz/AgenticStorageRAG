from app.infra.logging_utils import redact_email


def test_redact_email_standard():
    assert redact_email("user@example.com") == "u***@example.com"


def test_redact_email_single_char():
    assert redact_email("a@b.com") == "a***@b.com"


def test_redact_email_no_at():
    assert redact_email("invalid") == "***"


def test_redact_email_empty_local():
    assert redact_email("@domain.com") == "***@domain.com"
