from __future__ import annotations

import tarfile

from opswitness.backup import _backup_filter


def _member(name: str) -> tarfile.TarInfo:
    return tarfile.TarInfo(name)


def test_knowledge_hub_backup_keeps_authority_and_excludes_derived_state() -> None:
    retained = [
        "opswitness_state/console/library/collections/collection.json",
        "opswitness_state/console/library/documents/version.json",
        "opswitness_state/console/library/cards/card.json",
        "opswitness_state/console/library/blobs/sha256/aa/digest",
        "opswitness_state/console/workspace-memory/versions/version.json",
    ]
    excluded = [
        "opswitness_state/console/library/staging/import/file.part",
        "opswitness_state/console/library/indexes/library-fts-v1.sqlite3",
        "opswitness_state/console/library/indexes/library-semantic-v1.sqlite3",
        "opswitness_state/console/library/exports/export.zip",
        "opswitness_state/console/ephemeral/session.json",
    ]

    assert all(_backup_filter(_member(name)) is not None for name in retained)
    assert all(_backup_filter(_member(name)) is None for name in excluded)
