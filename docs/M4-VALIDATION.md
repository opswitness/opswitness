# M4 Artifact, Eval, and Signoff Validation

Date: 2026-07-12 America/Los_Angeles

Status: repository implementation passes deterministic validation. Live Paperclip
work-product projection remains the final M4 acceptance step.

## Implemented

- Fixed local CAS layout under Quarterdeck state with fsync and atomic no-clobber publish.
- `qd artifacts register/list/show/verify/eval/signoff`.
- Append-only registration, eval, and named human signoff events.
- Rebuildable SQLite artifact/outcome indexes.
- Paperclip artifact work-product projection with list-and-reconcile on event ULID;
  eval/signoff project as body-marker comments under the least-privilege agent key.
- Digest outcome section independent from process execution status.
- Encrypted backup and isolated restore include the complete CAS tree.

## Failure matrix

Tests prove:

- overwriting the source file does not alter registered bytes;
- identical content can have multiple lineage events and one CAS blob;
- an existing corrupt blob is rejected and `qd artifacts verify` exits nonzero;
- required signoff is visible and unhealthy until a signoff event arrives;
- eval failure and changes requested are outcome problems;
- work-product POST failure leaves registration/eval pending in per-job commit order;
- a remote `externalId` after lost local ack reconciles without repost;
- artifact registration, eval, signoff, CLI show/list, and SQLite rebuild agree;
- encrypted backup -> isolated restore preserves the exact CAS bytes.

The local path is never placed in Paperclip metadata. Projection contains only logical name,
hash, size, MIME, labels, run id, event ULID, and `cas+sha256://` URI.

Full repository verification: 130 tests pass; ruff and mypy pass. Worktree and full-history
gitleaks scans are required again immediately before commit.

## Remaining live acceptance

Register one non-sensitive artifact against the register-trigger canary run, project it to
the existing `[qd] com.tianyuzhou.register-trigger` issue, verify one work-product with the
same event ULID/hash, then rerun projection to prove zero repost. This does not require M3
Claude login and does not change launchd scheduling.
