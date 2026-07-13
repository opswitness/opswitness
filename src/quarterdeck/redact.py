"""Best-effort redaction for ledger records (on by default, ADR-0001 v2).

The ledger lives on disk for years; argv and log tails routinely contain tokens.
Redaction is heuristic — it lowers blast radius, it is not a DLP guarantee.
"""

import re

_SECRET_KEY_PART = r"(?:token|secret|password|passwd|api[-_]?key|apikey|credential)"
_SECRET_NAME = (
    rf"(?:[A-Za-z0-9_-]*{_SECRET_KEY_PART}[A-Za-z0-9_-]*|"
    r"auth|authorization|authentication)"
)
_SENSITIVE_FLAG = re.compile(rf"(?i)^--?{_SECRET_NAME}(?:=|$)")
# Common credential shapes: provider prefixes or long opaque strings.
# The generic class deliberately excludes '/' so filesystem paths and URLs survive;
# base64-with-slash secrets are the accepted miss (documented in ADR-0001).
_SECRET_SHAPES = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|xox[a-z]-[A-Za-z0-9-]{10,}"
    r"|AKIA[A-Z0-9]{16}|eyJ[A-Za-z0-9_-]{20,}|[A-Za-z0-9+_-]{40,})"
)
_MASK = "«redacted»"

_SHELL_VALUE = r'''(?:"[^"\n]*"|'[^'\n]*'|[^\s;&|,"']+)'''

# Persisted shell commands need contextual redaction too: short credentials do not match
# provider prefixes or the generic 40-character shape above.
_SECRET_ASSIGNMENT = re.compile(
    rf"(?i)(?P<prefix>(?<![A-Za-z0-9_-])(?:export\s+)?{_SECRET_NAME}\s*=\s*)"
    rf"(?P<value>{_SHELL_VALUE})"
)
_SECRET_FLAG_VALUE = re.compile(
    rf"(?i)(?P<prefix>(?<!\S)--?{_SECRET_NAME}\s+)(?P<value>{_SHELL_VALUE})"
)
_SECRET_COLON_VALUE = re.compile(
    rf'''(?i)(?P<prefix>["']?(?!authorization["']?\s*:){_SECRET_NAME}["']?\s*:\s*)'''
    rf"(?P<value>{_SHELL_VALUE})"
)
_AUTHORIZATION_VALUE = re.compile(
    r"(?i)(?P<prefix>authorization\s*:\s*(?:bearer|basic)\s+)"
    r"(?P<value>[^\s'\";&|,]+)"
)


def _mask_match(match: re.Match[str]) -> str:
    """Keep surrounding quotes so evidence stays legible without retaining the value."""
    value = match.group("value")
    quote = value[0] if len(value) >= 2 and value[0] in {'"', "'"} else ""
    return match.group("prefix") + quote + _MASK + quote


def redact_text(text: str) -> str:
    redacted = text
    for pattern in (
        _AUTHORIZATION_VALUE,
        _SECRET_ASSIGNMENT,
        _SECRET_FLAG_VALUE,
        _SECRET_COLON_VALUE,
    ):
        redacted = pattern.sub(_mask_match, redacted)
    return _SECRET_SHAPES.sub(_MASK, redacted)


def redact_argv(argv: list[str]) -> list[str]:
    out: list[str] = []
    mask_next = False
    for arg in argv:
        if mask_next:
            out.append(_MASK)
            mask_next = False
            continue
        if "=" in arg and _SENSITIVE_FLAG.match(arg.split("=", 1)[0]):
            out.append(arg.split("=", 1)[0] + "=" + _MASK)
            continue
        if _SENSITIVE_FLAG.match(arg):
            out.append(arg)
            mask_next = True
            continue
        out.append(redact_text(arg))
    return out
