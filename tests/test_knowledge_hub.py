from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from opswitness.console.knowledge_hub import KnowledgeHubConflict, KnowledgeHubStore
from opswitness.console.schemas import (
    LibraryCardDecisionRequestV1,
    LibraryCardJobRequestV1,
    LibraryCollectionCreateV1,
    LibraryCollectionPolicyV1,
    LibraryH5ExportPolicyV1,
    LibraryH5ExportRequestV1,
    LibraryImportCommitRequestV1,
    LibraryImportCreateRequestV1,
    LibraryImportEntryRequestV1,
    LibrarySearchRequestV1,
)


async def _bytes_stream(content: bytes):
    for start in range(0, len(content), 7):
        yield content[start : start + 7]


def _import_files(
    store: KnowledgeHubStore,
    collection_id: str,
    collection_revision: int,
    files: list[tuple[str, bytes, str]],
):
    batch = store.create_import(
        LibraryImportCreateRequestV1(
            collection_id=collection_id,
            expected_collection_revision=collection_revision,
            entries=[
                LibraryImportEntryRequestV1(
                    relative_path=name,
                    size_bytes=len(content),
                    media_type=media_type,
                )
                for name, content, media_type in files
            ],
        )
    )
    for entry, (_name, content, _media_type) in zip(
        batch.entries,
        files,
        strict=True,
    ):
        batch = asyncio.run(
            store.upload_import_entry(
                batch.import_id,
                entry.entry_id,
                _bytes_stream(content),
            )
        )
    assert batch.manifest_sha256
    return store.commit_import(
        batch.import_id,
        LibraryImportCommitRequestV1(
            expected_collection_revision=collection_revision,
            confirmed_manifest_sha256=batch.manifest_sha256,
            confirmed=True,
        ),
    )


def test_inbox_and_policy_revisions_are_versioned(tmp_path: Path) -> None:
    store = KnowledgeHubStore(tmp_path)
    rows = store.list_collections()
    assert len(rows) == 1
    assert rows[0].name == "Inbox"
    assert rows[0].is_inbox is True
    assert rows[0].revision == 1
    assert rows[0].policy_sha256 == hashlib.sha256(
        json.dumps(
            rows[0].policy.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def test_import_deduplicates_blob_and_tracks_source_aliases(tmp_path: Path) -> None:
    store = KnowledgeHubStore(tmp_path)
    collection = store.create_collection(
        LibraryCollectionCreateV1(
            name="Customer research",
            policy=LibraryCollectionPolicyV1(default_tags=["customer"]),
        )
    )
    content = "客户说希望下周开始，但价格和范围尚未确认。".encode()
    committed = _import_files(
        store,
        collection.collection_id,
        collection.revision,
        [
            ("research/a.md", content, "text/markdown"),
            ("research/b.md", content, "text/markdown"),
        ],
    )
    assert committed.status == "committed"
    documents = store.list_documents(collection_id=collection.collection_id)
    assert len(documents) == 2
    assert {document.sha256 for document in documents} == {
        hashlib.sha256(content).hexdigest()
    }
    blobs = list((tmp_path / "library" / "blobs" / "sha256").glob("*/*"))
    assert len(blobs) == 1


def test_same_relative_path_creates_immutable_new_version(tmp_path: Path) -> None:
    store = KnowledgeHubStore(tmp_path)
    collection = store.list_collections()[0]
    first = _import_files(
        store,
        collection.collection_id,
        collection.revision,
        [("notes/brief.txt", b"version one", "text/plain")],
    )
    second = _import_files(
        store,
        collection.collection_id,
        collection.revision,
        [("notes/brief.txt", b"version two", "text/plain")],
    )
    assert first.entries[0].document_version_id != second.entries[0].document_version_id
    history = store.list_documents(
        collection_id=collection.collection_id,
        include_history=True,
    )
    assert len(history) == 2
    active = [document for document in history if document.status == "active"]
    old = [document for document in history if document.status == "tombstoned"]
    assert len(active) == len(old) == 1
    assert active[0].previous_version_id == old[0].version_id
    assert active[0].document_id == old[0].document_id


def test_chinese_fts_returns_relevance_not_verification(tmp_path: Path) -> None:
    store = KnowledgeHubStore(tmp_path)
    collection = store.list_collections()[0]
    _import_files(
        store,
        collection.collection_id,
        collection.revision,
        [
            (
                "客户跟进.md",
                "客户希望了解每月网站维护包括什么，但尚未确认报价。".encode(),
                "text/markdown",
            )
        ],
    )
    result = store.search(
        LibrarySearchRequestV1(query="网站维护", mode="lexical")
    )
    assert result.mode_requested == "lexical"
    assert result.mode_used == "lexical"
    assert result.semantic_status == "not_requested"
    assert len(result.hits) == 1
    assert result.hits[0].evidence_status == "retained_input"
    assert "网站维护" in result.hits[0].snippet


def test_card_requires_exact_citation_and_human_approval(tmp_path: Path) -> None:
    store = KnowledgeHubStore(tmp_path)
    collection = store.list_collections()[0]
    committed = _import_files(
        store,
        collection.collection_id,
        collection.revision,
        [
            (
                "brief.md",
                "Scope is not confirmed. Ask which platform and monthly updates are needed.".encode(),
                "text/markdown",
            )
        ],
    )
    version_id = committed.entries[0].document_version_id
    assert version_id
    extraction = store.read_extraction(version_id)
    chunk = extraction["chunks"][0]
    disclosed = sum(len(row["text"]) for row in extraction["chunks"])
    job = store.create_card_job(
        LibraryCardJobRequestV1(
            collection_id=collection.collection_id,
            document_version_ids=[version_id],
            provider="openai",
            model="default",
            disclosed_character_count=disclosed,
            confirmed_source_disclosure=True,
        )
    )
    cards = store.create_cards_from_model_output(
        job.job_id,
        json.dumps(
            {
                "cards": [
                    {
                        "document_version_id": version_id,
                        "title": "Customer scope follow-up",
                        "summary": "The scope remains unconfirmed.",
                        "key_points": [
                            {
                                "statement": "Ask for platform and update requirements.",
                                "citations": [
                                    {
                                        "chunk_id": chunk["chunk_id"],
                                        "excerpt": "Ask which platform",
                                    }
                                ],
                            }
                        ],
                        "suggested_tags": ["customer"],
                        "coverage_scope": "One short source file.",
                        "coverage": "complete",
                    }
                ]
            }
        ),
    )
    assert cards[0].state == "candidate"
    approved = store.decide_card(
        cards[0].version_id,
        "approve",
        LibraryCardDecisionRequestV1(
            expected_card_sha256=cards[0].card_sha256,
            confirmed=True,
        ),
    )
    assert approved.state == "approved"
    with pytest.raises(KnowledgeHubConflict):
        store.decide_card(
            cards[0].version_id,
            "approve",
            LibraryCardDecisionRequestV1(
                expected_card_sha256=cards[0].card_sha256,
                confirmed=True,
            ),
        )


def test_safe_partner_export_is_offline_and_redacted(tmp_path: Path) -> None:
    store = KnowledgeHubStore(tmp_path)
    collection = store.list_collections()[0]
    committed = _import_files(
        store,
        collection.collection_id,
        collection.revision,
        [("brief.md", b"Secret launch plan for partner review.", "text/markdown")],
    )
    version_id = committed.entries[0].document_version_id
    assert version_id
    extraction = store.read_extraction(version_id)
    chunk = extraction["chunks"][0]
    job = store.create_card_job(
        LibraryCardJobRequestV1(
            collection_id=collection.collection_id,
            document_version_ids=[version_id],
            provider="openai",
            model="default",
            disclosed_character_count=len(chunk["text"]),
            confirmed_source_disclosure=True,
        )
    )
    card = store.create_cards_from_model_output(
        job.job_id,
        json.dumps(
            {
                "cards": [
                    {
                        "document_version_id": version_id,
                        "title": "<script>Secret plan</script>",
                        "summary": "Secret launch plan.",
                        "key_points": [
                            {
                                "statement": "Partner review is planned.",
                                "citations": [
                                    {
                                        "chunk_id": chunk["chunk_id"],
                                        "excerpt": "Secret launch plan",
                                    }
                                ],
                            }
                        ],
                        "suggested_tags": ["partner", "secret-partner"],
                        "coverage_scope": "One source.",
                        "coverage": "complete",
                    }
                ]
            }
        ),
    )[0]
    approved = store.decide_card(
        card.version_id,
        "approve",
        LibraryCardDecisionRequestV1(
            expected_card_sha256=card.card_sha256,
            confirmed=True,
        ),
    )
    policy = LibraryH5ExportPolicyV1(
        include_card_version_ids=[approved.version_id],
        custom_sensitive_terms=["Secret"],
    )
    preview = store.export_preview(collection.collection_id, collection.revision, policy)
    exported = store.create_export(
        LibraryH5ExportRequestV1(
            collection_id=collection.collection_id,
            expected_collection_revision=collection.revision,
            policy=policy,
            expected_preview_sha256=preview["preview_sha256"],
            confirmed=True,
        )
    )
    _, zip_path = store.export_download(exported.export_id)
    with zipfile.ZipFile(zip_path) as archive:
        assert set(archive.namelist()) == {
            "index.html",
            "manifest.json",
            "SHA256SUMS",
        }
        index = archive.read("index.html").decode()
        assert "https://" not in index
        assert "http://" not in index
        assert "connect-src 'none'" in index
        assert "Secret launch plan" not in index
        assert "secret-partner" not in index.casefold()
        assert "[REDACTED]" in index
        assert "<script>Secret plan</script>" not in index


def test_import_rejects_unsafe_relative_paths() -> None:
    with pytest.raises(ValidationError):
        LibraryImportEntryRequestV1(
            relative_path="../secret.txt",
            size_bytes=10,
            media_type="text/plain",
        )


def test_semantic_model_is_pinned_and_never_uses_remote_fallback(
    tmp_path: Path,
) -> None:
    runtime_cache = tmp_path / "runtime-cache"
    store = KnowledgeHubStore(tmp_path / "state", runtime_cache_root=runtime_cache)
    manifest = store._semantic_manifest()
    status = store.semantic_model_status()

    assert manifest["model_id"] == "intfloat/multilingual-e5-small"
    assert manifest["revision"] == "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    assert manifest["dimensions"] == 384
    assert manifest["max_tokens"] == 512
    assert status.state == "model_missing"
    assert status.bytes_total == sum(row["size_bytes"] for row in manifest["files"])
    assert status.manifest_sha256 == (
        "1a5411747858a58d60a5f3c03de5ecedb453eeb11b0843fc427375bde1958cfa"
    )

    result = store.search(
        LibrarySearchRequestV1(query="客户资料", mode="hybrid")
    )
    assert result.mode_requested == "hybrid"
    assert result.mode_used == "lexical"
    assert result.semantic_status == "model_missing"


def test_supplemental_authoritative_sources_are_indexed(tmp_path: Path) -> None:
    content_sha = hashlib.sha256(b"approved memory").hexdigest()
    store = KnowledgeHubStore(
        tmp_path,
        supplemental_index_provider=lambda: [
            {
                "title": "Approved customer operating note",
                "tags": ["customer", "approved"],
                "body": "客户偏好每周五接收一次简短进度更新。",
                "metadata": {
                    "hit_id": "workspace_memory:01TEST",
                    "source_type": "workspace_memory",
                    "collection_id": None,
                    "title": "Approved customer operating note",
                    "source_status": "approved",
                    "version_id": "01TEST",
                    "sha256": content_sha,
                    "evidence_status": "approved",
                    "tags": ["customer", "approved"],
                    "locator": "approved Workspace Memory",
                },
            }
        ],
    )
    result = store.search(
        LibrarySearchRequestV1(query="进度更新", mode="lexical")
    )
    assert len(result.hits) == 1
    assert result.hits[0].source_type == "workspace_memory"
    assert result.hits[0].evidence_status == "approved"


def test_semantic_index_metadata_rejects_unknown_fields(tmp_path: Path) -> None:
    store = KnowledgeHubStore(tmp_path)
    store._ensure()
    store.semantic_index_path.write_bytes(b"")
    connection = sqlite3.connect(store.semantic_index_path)
    try:
        connection.execute(
            "CREATE TABLE semantic_index_metadata(payload TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO semantic_index_metadata(payload) VALUES(?)",
            (
                json.dumps(
                    {
                        "schema_version": 1,
                        "semantic_index_version": 1,
                        "fts_index_version": 1,
                        "model_manifest_sha256": store._semantic_manifest_sha256(),
                        "entry_count": 0,
                        "unexpected": True,
                    }
                ),
            ),
        )
        connection.commit()
    finally:
        connection.close()
    assert store._semantic_index_is_current() is False
