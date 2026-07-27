"""Canonical product naming and validation for newly submitted display names.

Historical ledger fields and stable identifiers deliberately do not call these
validators.  They must remain readable byte-for-byte even when they predate the
current naming policy.
"""

from __future__ import annotations

import unicodedata

PRODUCT_DISPLAY_NAME = "OpsWitness"
PACKAGE_AND_CLI_NAME = "opswitness"
LEGACY_CLI_ALIAS = "qd"


def validate_new_display_name(value: str) -> str:
    """Validate one newly submitted human-facing name without rewriting it."""

    if not isinstance(value, str):
        raise TypeError("display name must be text")
    if not value:
        raise ValueError("display name must not be empty")
    if value != value.strip():
        raise ValueError("display name must not start or end with whitespace")
    if value in {".", ".."}:
        raise ValueError("display name must not be a path marker")
    if "/" in value or "\\" in value:
        raise ValueError("display name must not contain path separators")
    if any(unicodedata.category(character) in {"Cc", "Cf"} for character in value):
        raise ValueError("display name must not contain control or invisible format characters")
    if "  " in value:
        raise ValueError("display name must use single spaces")
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError("display name must use NFC Unicode normalization")
    return value


def validate_optional_new_display_name(value: str | None) -> str | None:
    """Validate an optional new display name while preserving ``None``."""

    return None if value is None else validate_new_display_name(value)
