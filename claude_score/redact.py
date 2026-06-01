"""Mask credentials in text that comes out of a Claude Code transcript.

Used by the report builder before any prompt or judge-output text reaches the
HTML scorecard, because: (a) developers sometimes paste secrets into prompts
to ask the agent about them, and (b) candidates may accidentally do the same
during an interview. We do not want either to end up in a sharable hiring
artifact (or get caught by GitHub push protection, which is how we discovered
this was a real problem).

Each pattern is conservative — false positives would mangle the scorecard.
The patterns target well-formed token formats and the very common shape of
``KEY=value`` / ``KEY: value`` where the key name implies a credential.

We deliberately do NOT try to detect arbitrary high-entropy strings; that
turns out to mangle UUIDs, git hashes, base64-encoded image data, and long
filenames, all of which appear constantly in transcripts.
"""

from __future__ import annotations

import re
from typing import Pattern


# Each entry: (compiled pattern, label used in the replacement marker).
# When a callable is needed (because the match has a structured "before" we
# want to preserve), we use a lambda — see the env-var pattern below.
_LITERAL_PATTERNS: list[tuple[Pattern[str], str]] = [
    # GitHub personal/app/server/refresh tokens.
    (re.compile(r"\bghp_[A-Za-z0-9]{36,}\b"), "github-pat"),
    (re.compile(r"\bgho_[A-Za-z0-9]{36,}\b"), "github-oauth"),
    (re.compile(r"\bghs_[A-Za-z0-9]{36,}\b"), "github-server"),
    (re.compile(r"\bghr_[A-Za-z0-9]{36,}\b"), "github-refresh"),

    # AWS access key id (well-formed, 20-char, AKIA prefix).
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "aws-access-key-id"),

    # Slack bot/user/app/refresh tokens.
    (re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"), "slack-token"),

    # Stripe live/test publishable & secret keys.
    (re.compile(r"\b(?:sk|pk|rk)_(?:test|live)_[0-9A-Za-z]{20,}\b"), "stripe-key"),

    # Google API keys.
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "google-api-key"),

    # Generic JWTs (header.payload.signature, all base64url).
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{8,}\b"), "jwt"),

    # Postgres / MySQL / Mongo URIs with embedded user:pass.
    (re.compile(
        r"\b((?:postgres(?:ql)?|mysql|mongodb)(?:\+[a-z]+)?://)([^:/\s@]+):([^@\s]+)@",
        re.IGNORECASE,
    ), "db-uri-cred"),

    # ``AccountKey=<base64>`` as it appears inside Azure connection strings.
    # The env-var pattern would only catch the first ``=value`` in a string
    # like ``...;AccountName=foo;AccountKey=...;Endpoint=...``; this catches
    # the embedded one explicitly.
    (re.compile(
        r"(?i)\bAccountKey\s*=\s*[A-Za-z0-9+/]{40,}={0,2}",
    ), "azure-storage-account-key"),
]


# Standalone base64-shaped strings that contain at least one of ``+``, ``/``,
# or ``=`` — those characters almost never appear together in normal English
# but are the hallmark of base64-encoded secrets (Azure storage keys, JWT
# signatures, AWS secrets, generic passwords). Requiring 32+ chars AND a
# base64-only character set AND at least one base64-distinctive char keeps
# the false-positive rate very low (UUIDs, git SHAs, filenames, normal words
# all fail at least one check).
_BASE64_SECRET_PATTERN = re.compile(
    r"(?<![A-Za-z0-9+/=])"      # left boundary not in base64 alphabet
    r"([A-Za-z0-9+/]{32,}={0,2})"
    r"(?![A-Za-z0-9+/=])"       # right boundary not in base64 alphabet
)


def _base64_secret_sub(match: "re.Match[str]") -> str:
    token = match.group(0)
    # Only redact strings that have at least one base64-only character.
    # Bare [A-Za-z0-9]+ runs are not secrets-by-default (could be a long
    # word, a git tag, a model name like "claude-sonnet-4-5-20251022").
    if "+" not in token and "/" not in token and "=" not in token:
        return token
    return _mask("base64-secret")


# `KEY=value` or `KEY: value` where the key name suggests a credential. Captures
# the prefix so we can keep it visible and mask only the value. We allow common
# secret characters (alphanumerics + a few symbols) and require at least 16
# chars so we don't redact trivial config like `KEY=on`.
_SENSITIVE_KEY = (
    r"[\w.-]*(?:api[_-]?key|secret|token|password|passwd|access[_-]?key|"
    r"client[_-]?secret|auth(?:orization)?|bearer|connection[_-]?string)[\w.-]*"
)
_ENVVAR_PATTERN = re.compile(
    rf"(?i)\b({_SENSITIVE_KEY})(\s*[:=]\s*[\"']?)([A-Za-z0-9+/_=.~-]{{16,}})",
)

# Authorization: Bearer <token> headers (case-insensitive).
_BEARER_PATTERN = re.compile(
    r"(?i)\b(authorization\s*:\s*bearer\s+)([A-Za-z0-9._~+/=-]{16,})",
)

# Generic URL with embedded user:pass (https://user:pass@host).
_URL_CRED_PATTERN = re.compile(
    r"(https?://)([^:/\s@]+):([^@\s]+)@",
    re.IGNORECASE,
)


def _mask(label: str) -> str:
    return f"[REDACTED:{label}]"


def redact(text: str) -> str:
    """Return ``text`` with credentials masked. Empty / non-string input passes through."""
    if not text or not isinstance(text, str):
        return text

    for pattern, label in _LITERAL_PATTERNS:
        text = pattern.sub(_mask(label), text)

    text = _ENVVAR_PATTERN.sub(
        lambda m: f"{m.group(1)}{m.group(2)}{_mask('secret-value')}",
        text,
    )
    text = _BEARER_PATTERN.sub(
        lambda m: f"{m.group(1)}{_mask('bearer-token')}",
        text,
    )
    text = _URL_CRED_PATTERN.sub(
        lambda m: f"{m.group(1)}{m.group(2)}:{_mask('url-cred')}@",
        text,
    )
    # Run the base64-shape sweep last so well-formed tokens (which the
    # literal patterns recognise more precisely) get their specific label.
    text = _BASE64_SECRET_PATTERN.sub(_base64_secret_sub, text)
    return text


def redact_many(items: list[str]) -> list[str]:
    return [redact(item) for item in items]
