"""Additional redaction edge cases (separate file to keep test_security_redaction tight)."""

from core.security.redaction import redact_for_feed


def test_handles_deeply_nested_dict() -> None:
    payload = {"a": {"b": {"c": {"private_key": "pem"}}}}
    out = redact_for_feed(payload)
    assert out["a"]["b"]["c"]["private_key"] == "[REDACTED]"


def test_handles_list_of_lists() -> None:
    payload = [[{"token": "t"}], [{"data": 1}]]
    out = redact_for_feed(payload)
    assert out[0][0]["token"] == "[REDACTED]"
    assert out[1][0]["data"] == 1


def test_short_string_unchanged() -> None:
    out = redact_for_feed({"text": "hello"})
    assert out["text"] == "hello"
