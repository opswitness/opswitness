#!/usr/bin/env python3
"""Download the pinned local model and exercise lexical/semantic/hybrid search."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from opswitness.console.knowledge_hub import KnowledgeHubStore
from opswitness.console.schemas import (
    LibraryImportCommitRequestV1,
    LibraryImportCreateRequestV1,
    LibraryImportEntryRequestV1,
    LibrarySearchRequestV1,
)


async def _content(value: bytes):
    yield value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        raise SystemExit("semantic smoke root must be new or empty")
    store = KnowledgeHubStore(
        root / "state" / "console",
        runtime_cache_root=root / "runtime-cache",
    )
    download = store.download_semantic_model()
    print(json.dumps(download.model_dump(mode="json"), sort_keys=True), flush=True)
    if download.state != "ready":
        raise SystemExit(f"semantic model is not ready: {download.state}")

    collection = store.list_collections()[0]
    sources = [
        (
            "客户付款安排.md",
            "客户选择按月付款。每月第一周发送发票，付款期限为十四天。".encode(),
        ),
        (
            "support.md",
            b"Support requests are reviewed each weekday and urgent outages are escalated.",
        ),
    ]
    batch = store.create_import(
        LibraryImportCreateRequestV1(
            collection_id=collection.collection_id,
            expected_collection_revision=collection.revision,
            entries=[
                LibraryImportEntryRequestV1(
                    relative_path=name,
                    size_bytes=len(content),
                    media_type="text/markdown",
                )
                for name, content in sources
            ],
        )
    )
    for entry, (_name, content) in zip(batch.entries, sources, strict=True):
        batch = asyncio.run(
            store.upload_import_entry(
                batch.import_id,
                entry.entry_id,
                _content(content),
            )
        )
    if batch.manifest_sha256 is None:
        raise SystemExit("import manifest was not finalized")
    store.commit_import(
        batch.import_id,
        LibraryImportCommitRequestV1(
            expected_collection_revision=collection.revision,
            confirmed_manifest_sha256=batch.manifest_sha256,
            confirmed=True,
        ),
    )

    semantic = store.search(
        LibrarySearchRequestV1(query="客户如何支付费用", mode="semantic")
    )
    hybrid = store.search(
        LibrarySearchRequestV1(query="付款期限", mode="hybrid")
    )
    if (
        semantic.mode_used != "semantic"
        or hybrid.mode_used != "hybrid"
        or not semantic.hits
        or not hybrid.hits
    ):
        raise SystemExit("semantic or hybrid search did not return a local result")
    print(
        json.dumps(
            {
                "semantic": semantic.model_dump(mode="json"),
                "hybrid": hybrid.model_dump(mode="json"),
                "root": str(root),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
