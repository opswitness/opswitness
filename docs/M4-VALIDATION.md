# M4 Artifact, Eval, and Signoff Validation

Date: 2026-07-12 America/Los_Angeles

Status: repository implementation and live Paperclip work-product acceptance pass.

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

## Live acceptance

- Canary run: `01KXCE6YVYPT31FC0FEAGWYBTC` (`com.tianyuzhou.register-trigger`).
- Registration event: `01KXCGTPEDZMYDRJ1K6C2N04VX`.
- SHA-256: `84f458d1adfbe78d021a866ff5387094ca50b8be384ddb45f972478726645e1c`;
  130 bytes; local verify passed.
- Paperclip work-product: `d7a1235c-b545-4fad-b243-2444d8382bc0`; matching externalId,
  title, and hash; remote match count exactly one.
- Explicit second drain: projected 0, reconciled 0, errors 0, pending 0; remote count stayed one.
- Production doctor remained fully green (including the new secret-free recovery template),
  and digest stayed green with execution and outcome sections separated.

The canary content was synthetic and non-sensitive. No launchd schedule changed.
