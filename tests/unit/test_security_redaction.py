from core.security.redaction import redact_for_feed


def test_redacts_top_level_sensitive_keys() -> None:
    out = redact_for_feed({"api_key": "sk-secret", "data": 1})
    assert out["api_key"] == "[REDACTED]"
    assert out["data"] == 1


def test_redacts_nested_sensitive_keys() -> None:
    out = redact_for_feed({"creds": {"password": "hunter2", "user": "alice"}})
    assert out["creds"]["password"] == "[REDACTED]"
    assert out["creds"]["user"] == "alice"


def test_case_insensitive_key_match() -> None:
    out = redact_for_feed({"AUTHORIZATION": "Bearer x", "Token": "y"})
    assert out["AUTHORIZATION"] == "[REDACTED]"
    assert out["Token"] == "[REDACTED]"


def test_long_string_truncated() -> None:
    out = redact_for_feed({"text": "x" * 3000})
    assert "[TRUNCATED]" in out["text"]
    assert len(out["text"]) < 3000


def test_blob_descriptor_for_huge_strings() -> None:
    out = redact_for_feed({"blob": "x" * 10_000})
    assert out["blob"].startswith("[BLOB:size=10000,sha256=")


def test_list_redaction() -> None:
    out = redact_for_feed([{"password": "p"}, {"data": 1}])
    assert out[0]["password"] == "[REDACTED]"
    assert out[1]["data"] == 1


def test_passes_through_primitives() -> None:
    assert redact_for_feed(42) == 42
    assert redact_for_feed(True) is True
    assert redact_for_feed(None) is None
