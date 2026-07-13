# ADR-0002: Artifact authority is CAS plus the local ledger

Status: accepted

## Context

Paperclip work-products are useful UI projections, but pinned v2026.707 stores
`externalId` under a normal non-unique index and inserts unconditionally. A mutable local
path is also not evidence: the bytes can change after a report is reviewed. Quarterdeck
therefore needs an authority that survives projection loss and proves the reviewed bytes.

## Decision

- Blob authority is local content-addressed storage at
  `~/.local/state/quarterdeck/artifacts/sha256/<prefix>/<sha256>`.
- Lineage and decisions are versioned append-only events:
  `artifact_registered`, `artifact_eval`, and `artifact_signoff`.
- Registration copies a regular file into a same-filesystem temporary inode, verifies the
  source did not change during capture, fsyncs, and publishes with hard-link no-clobber.
  An existing blob must hash and size-verify before it is reused.
- A registration binds run id, job, logical name, SHA-256, size, MIME, labels, and
  `cas+sha256://` URI. Multiple registrations may intentionally point to one blob; lineage
  is per event, not per digest.
- SQLite is rebuilt from JSONL and is never authoritative.
- Paperclip receives an `artifact` work-product with `externalId = registration event ULID`
  and the hash metadata. Projection lists and reconciles before create; `externalId` is a
  marker, never an idempotency guarantee. Eval and signoff are marker-bearing comments.
- Digest reports execution evidence and outcome evidence separately. Eval failure,
  `changes_requested`, or a `requires-signoff` artifact without signoff makes health red.
- Encrypted backup includes CAS and ledger together. Restore is valid only when blobs still
  verify against their registration events.

## Consequences

Source overwrite cannot alter registered evidence, and Paperclip can be rebuilt from local
authority. CAS corruption becomes visible instead of silently changing a report. Orphan
blobs may remain after a ledger write failure; they are harmless and can later be garbage
collected only through an explicit ledger-reachability tool. Automatic deletion is out of
scope for v0.1.
