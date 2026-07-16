from __future__ import annotations

from ke_memory_demo.infra.redaction import REDACTED, redact_tree


def test_redaction_removes_sensitive_keys_and_known_secret_values() -> None:
    source = {
        "Authorization": "Bearer secret-value",
        "nested": {
            "api_key": "secret-value",
            "message": "prefix secret-value suffix",
        },
    }

    assert redact_tree(source, known_secrets={"secret-value"}) == {
        "Authorization": REDACTED,
        "nested": {"api_key": REDACTED, "message": f"prefix {REDACTED} suffix"},
    }


def test_redaction_is_recursive_case_insensitive_and_non_mutating() -> None:
    source = {
        "headers": [
            {"X-API-Key": "first"},
            {"set-COOKIE": {"session": "second"}},
            {"refreshToken": "third"},
            {"access_tokens": ["fourth"]},
        ],
        "tuple": ("safe", "secret-value"),
    }

    result = redact_tree(source, known_secrets={"secret-value"})

    assert result == {
        "headers": [
            {"X-API-Key": REDACTED},
            {"set-COOKIE": REDACTED},
            {"refreshToken": REDACTED},
            {"access_tokens": REDACTED},
        ],
        "tuple": ("safe", REDACTED),
    }
    assert source == {
        "headers": [
            {"X-API-Key": "first"},
            {"set-COOKIE": {"session": "second"}},
            {"refreshToken": "third"},
            {"access_tokens": ["fourth"]},
        ],
        "tuple": ("safe", "secret-value"),
    }


def test_redaction_preserves_token_usage_fields() -> None:
    source = {
        "input_tokens": 11,
        "output_tokens": 7,
        "total_tokens": 18,
        "max_output_tokens": 256,
        "token": "sensitive",
    }

    assert redact_tree(source) == {
        "input_tokens": 11,
        "output_tokens": 7,
        "total_tokens": 18,
        "max_output_tokens": 256,
        "token": REDACTED,
    }


def test_empty_known_secrets_are_ignored() -> None:
    assert redact_tree("unchanged", known_secrets={"", "   "}) == "unchanged"
