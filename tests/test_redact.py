"""Tests for the secret-redaction module.

The patterns are conservative — we'd rather miss an exotic token than mangle
the body of the scorecard. These tests pin the behaviours that matter.
"""

from claude_score.redact import redact


def test_empty_input_passes_through():
    assert redact("") == ""
    assert redact(None) is None  # type: ignore[arg-type]


def test_plain_text_untouched():
    text = "Please add a /health endpoint that returns {'status': 'ok'}."
    assert redact(text) == text


def test_github_pat():
    # Construct at runtime so the file doesn't contain a literal that looks
    # like a real GitHub PAT to push-protection scanners.
    sample = "ghp_" + "A" * 36
    out = redact(f"use this: {sample} ok")
    assert "ghp_" not in out
    assert "[REDACTED:github-pat]" in out


def test_aws_access_key_id():
    # AKIA + 16 chars. Constructed at runtime to avoid literal-key detection.
    sample = "AKIA" + "B" * 16
    out = redact(f"{sample} is the key")
    assert "AKIA" not in out
    assert "[REDACTED:aws-access-key-id]" in out


def test_jwt():
    # JWT shape: header.payload.signature — three base64url parts.
    jwt = "eyJ" + "A" * 20 + "." + "B" * 20 + "." + "C" * 20
    out = redact(f"Bearer {jwt} please")
    assert "eyJ" not in out
    assert "[REDACTED:jwt]" in out


def test_slack_token():
    sample = "xoxb-" + "1" * 12
    out = redact(sample)
    assert "xox" not in out
    assert "[REDACTED:slack-token]" in out


def test_stripe_key():
    sk = "sk_test_" + "X" * 24
    pk = "pk_live_" + "Y" * 24
    out = redact(f"{sk} and {pk} here")
    assert "sk_test_X" not in out
    assert "pk_live_Y" not in out
    assert out.count("[REDACTED:stripe-key]") == 2


def test_google_api_key():
    # Google API keys are exactly AIza + 35 chars from [A-Za-z0-9_-].
    sample = "AIza" + "B" * 35
    out = redact(f"key is {sample} thanks")
    assert "AIza" not in out
    assert "[REDACTED:google-api-key]" in out


def test_envvar_style_secret():
    # Construct a fake hex value at runtime so the file itself doesn't carry a
    # literal that looks like a real API key. (Earlier versions of this test
    # used a real-looking key as the sample, which is exactly the failure
    # mode the redactor exists to prevent.)
    fake_hex_key = "f" * 32
    out = redact(f"TMDB_API_KEY={fake_hex_key}")
    assert fake_hex_key not in out
    assert "TMDB_API_KEY" in out  # we keep the key name visible
    assert "[REDACTED:secret-value]" in out


def test_envvar_short_value_kept():
    # Values shorter than 16 chars are not redacted — avoid mangling toggles.
    out = redact("FEATURE_FLAG=on")
    assert out == "FEATURE_FLAG=on"


def test_envvar_unrelated_key_kept():
    # The key name has to look credential-ish.
    out = redact("FILE_PATH=somelongpathnamenotasecretreally1234567890")
    assert "REDACTED" not in out


def test_envvar_with_quotes_and_spacing():
    out = redact('CLIENT_SECRET: "abcd1234EFGH5678ijkl9012"')
    assert "abcd1234" not in out
    assert "[REDACTED:secret-value]" in out
    assert "CLIENT_SECRET" in out


def test_authorization_bearer_header():
    out = redact("Authorization: Bearer abc123def456ghi789jkl012mno345pqr678")
    assert "abc123def456" not in out
    assert "[REDACTED:bearer-token]" in out


def test_url_with_credentials():
    out = redact("clone from https://user:p4ssw0rd@github.com/foo/bar.git")
    assert "p4ssw0rd" not in out
    assert "[REDACTED:url-cred]" in out
    assert "github.com" in out  # host preserved


def test_database_uri_credentials():
    out = redact("DATABASE_URL=postgres://moviedeck:hunter2word@localhost:5432/moviedeck")
    assert "hunter2word" not in out
    # The DB-URI pattern fires AND the env-var pattern may also fire; both is fine.
    assert "REDACTED" in out


def test_uuid_and_hash_not_mangled():
    # We do not want false positives on UUIDs, git SHAs, etc.
    raw = (
        "session 7c2d9f10-1234-4abc-9def-0123456789ab "
        "commit 0e333470eae25ee656db51cb3dc7349b82c8585b "
        "file abc123_some_function.py"
    )
    assert redact(raw) == raw


def test_multiple_secrets_in_one_string():
    pat = "ghp_" + "A" * 36
    akia = "AKIA" + "B" * 16
    out = redact(f"GITHUB_TOKEN={pat} and AWS_ACCESS_KEY_ID={akia}")
    assert "ghp_" not in out
    assert "AKIA" not in out
    # Two redaction markers (one per secret).
    assert out.count("[REDACTED:") >= 2


def test_azure_account_key_in_connection_string():
    # The exact shape that slipped past v1 of the redactor: a connection
    # string with multiple ``Key=value`` pairs, only the first of which got
    # caught by the env-var pattern.
    key = "/" + "A" * 85 + "=="  # 88-char base64 ending in ==
    conn = (
        f"AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;"
        f"AccountName=foo;AccountKey={key};EndpointSuffix=core.windows.net"
    )
    out = redact(conn)
    assert key not in out
    # The base64 sweep also catches AccountName= preceded by '+' / '/' in real
    # transcripts. Either way, the actual secret value is gone and a redaction
    # marker is present.
    assert "[REDACTED:" in out


def test_base64_password_in_free_text():
    # The other shape that slipped past v1: a password mentioned in prose
    # ("the password is: ...") without a KEY=VALUE structure.
    secret = "WMZ/" + "A" * 30 + "+ACRDQIuTV"
    out = redact(f"No that one is the password2 password is: {secret}")
    assert secret not in out
    assert "[REDACTED:base64-secret]" in out


def test_long_alphanumeric_word_is_not_redacted():
    # Without a base64-distinctive character (+ / =), long alphanumeric runs
    # pass through. Avoids mangling model names, long identifiers, etc.
    raw = "claude-sonnet-4-5-20251022 and SomeVeryLongIdentifierNameWithNoPunctuation"
    assert redact(raw) == raw
