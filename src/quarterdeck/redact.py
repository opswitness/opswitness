"""Best-effort redaction for ledger records (on by default, ADR-0001 v2).

The ledger lives on disk for years; argv and log tails routinely contain tokens.
Redaction is heuristic — it lowers blast radius, it is not a DLP guarantee.
"""

import re

_SENSITIVE_FLAG = re.compile(
    r"(?i)^--?(?:[a-z0-9-]*?)(token|secret|password|passwd|api-?key|apikey|auth|credential|bearer)"
)
# Common credential shapes: provider prefixes or long opaque strings.
# The generic class deliberately excludes '/' so filesystem paths and URLs survive;
# base64-with-slash secrets are the accepted miss (documented in ADR-0001).
_SECRET_SHAPES = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|xox[a-z]-[A-Za-z0-9-]{10,}"
    r"|AKIA[A-Z0-9]{16}|eyJ[A-Za-z0-9_-]{20,}|[A-Za-z0-9+_-]{40,})"
)
_MASK = "«redacted»"


def redact_text(text: str) -> str:
    return _SECRET_SHAPES.sub(_MASK, text)


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
