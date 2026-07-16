from __future__ import annotations

import json

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


def test_valid_json_text_is_structurally_redacted_after_decoding() -> None:
    secret = 'quote"slash\\line\n\t雪'
    source = json.dumps(
        {secret: {"value": f"prefix {secret} suffix"}},
        ensure_ascii=True,
    )

    result = redact_tree(source, known_secrets={secret})

    assert json.loads(result) == {
        REDACTED: {"value": f"prefix {REDACTED} suffix"},
    }
    assert secret not in result


def test_malformed_text_redacts_literal_and_both_json_escaped_secret_forms() -> None:
    secret = 'quote"slash\\line\n\t雪'
    encodings = {
        secret,
        json.dumps(secret, ensure_ascii=False)[1:-1],
        json.dumps(secret, ensure_ascii=True)[1:-1],
    }

    for encoded in encodings:
        source = f"prefix::{encoded}::malformed{{"
        result = redact_tree(source, known_secrets={secret})
        assert encoded not in result
        assert REDACTED in result


def test_malformed_scanner_redacts_optional_slash_escape() -> None:
    secret = "alpha/beta"
    source = r"prefix::alpha\/beta::broken{"

    result = redact_tree(source, known_secrets={secret})

    assert result == f"prefix::{REDACTED}::broken{{"
    assert secret not in json.loads(f'"{result}"')


def test_malformed_scanner_redacts_per_character_and_mixed_unicode_escapes() -> None:
    secret = "alpha"
    sources = (
        r"prefix::\u0061\u006c\u0070\u0068\u0061::broken{",
        r"prefix::a\u006cph\u0061::broken{",
    )

    for source in sources:
        result = redact_tree(source, known_secrets={secret})
        assert result == f"prefix::{REDACTED}::broken{{"
        assert secret not in json.loads(f'"{result}"')


def test_malformed_scanner_redacts_quote_backslash_and_control_escapes() -> None:
    secret = 'quote"slash\\back\bform\fline\nreturn\rtab\t'
    encoded = json.dumps(secret, ensure_ascii=True)[1:-1]
    source = f"prefix::{encoded}::broken{{"

    result = redact_tree(source, known_secrets={secret})

    assert result == f"prefix::{REDACTED}::broken{{"
    assert secret not in json.loads(f'"{result}"')


def test_malformed_scanner_redacts_literal_secret_that_looks_like_json_escape() -> None:
    secret = r"alpha\nbeta"
    source = f"prefix::{secret}::broken{{"

    assert redact_tree(source, known_secrets={secret, "alpha"}) == (f"prefix::{REDACTED}::broken{{")


def test_malformed_scanner_redacts_valid_surrogate_pair() -> None:
    secret = "emoji-😀-done"
    source = r"prefix::emoji-\uD83D\uDE00-done::broken{"

    result = redact_tree(source, known_secrets={secret})

    assert result == f"prefix::{REDACTED}::broken{{"
    assert secret not in json.loads(f'"{result}"')


def test_malformed_scanner_prefers_longest_overlapping_secret_and_redacts_all_matches() -> None:
    source = r"alpha\/beta alpha beta alpha\/beta"

    result = redact_tree(
        source,
        known_secrets={"alpha", "beta", "alpha/beta"},
    )

    assert result == " ".join([REDACTED, REDACTED, REDACTED, REDACTED])
    decoded = json.loads(f'"{result}"')
    assert "alpha" not in decoded
    assert "beta" not in decoded


def test_malformed_scanner_preserves_invalid_escapes_as_ordinary_text() -> None:
    source = r"prefix::alpha\qbeta::\u12G4::\uD83D-tail"

    assert (
        redact_tree(
            source,
            known_secrets={"alphaqbeta", "ሴ", "😀"},
        )
        == source
    )


def test_malformed_scanner_preserves_non_secret_input_exactly() -> None:
    source = r"prefix::safe\/path::\u0062eta::\"quoted\"::broken{"

    assert redact_tree(source, known_secrets={"alpha/beta"}) == source
