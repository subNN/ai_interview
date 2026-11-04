from interview_assistant.logging_utils import redact_sensitive


def test_redacts_keys_and_tokens():
    text = (
        "Authorization: Bearer abcdefghijklmnop "
        "api_key=fixture-key token=fixture-token fixture-bearer"
    )
    redacted = redact_sensitive(text)
    assert "fixture-key" not in redacted
    assert "fixture-token" not in redacted
    assert "1234567890abcdef" not in redacted
    assert "[REDACTED]" in redacted
