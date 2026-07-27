# Knowledge Hub

Knowledge Hub is OpsWitness's private, cross-Work material layer. Its source of truth is local
descriptors plus a content-addressed input store; search indexes are disposable projections.
Search relevance helps the operator find material. It never proves that a statement is correct,
that a business outcome succeeded, or that an artifact passed verification.

## Release stages

| Capability | Source status | Release target | Enforcement boundary |
|---|---|---|---|
| Named collections and versioned collection policy | Implemented | `v0.1.0-alpha.2` | Server revision and policy hash |
| File/folder snapshot, limits, staging, SHA-256 dedupe | Implemented | `v0.1.0-alpha.2` | Server digest, manifest confirmation, input CAS |
| Citation-bound knowledge-card candidate and human review | Implemented | `v0.1.0-alpha.2` | Closed schema; no model may approve |
| Chinese/English FTS5 search | Implemented | `v0.1.0-alpha.2` | Disposable local index; authority remains CAS/descriptors |
| Use exact library versions in a new Work | Implemented | `v0.1.0-alpha.2` | Server revalidation and unconfirmed Plan hash binding |
| Manifest-pinned local semantic search | Implemented, opt-in | `v0.1.0-alpha.3` | Local ONNX only; explicit lexical fallback |
| Redacted offline H5 export | Implemented | `v0.1.0-alpha.3` | Selected approved cards and `safe_partner` field policy |

“Implemented” here means present in source and covered by local tests. Neither release target is a
published or approved binary. Each exact candidate still requires its own wheel/App/DMG build,
inside-out signing, notarization, clean macOS 14 install, first Work, recovery drill, backup/restore
round trip, packaging review, and 24–48 hour Canary.

## Intake and authority

The Inbox is created automatically, and the operator may create additional named collections.
Each import binds the exact immutable collection-policy version and hash. Folder selection is a
one-time snapshot; OpsWitness does not watch or take over the source directory.

The browser scans relative names and sizes, then streams each accepted file to a private staging
area. The service calculates SHA-256 while receiving bytes. Before commit, the operator reviews
the manifest identity plus duplicate, version, skipped, and failed entries. Commit places one copy
of each unique body under `library/blobs/sha256/`; another filename becomes an alias, while changed
content at the same relative path becomes a new immutable document version.

The default batch limits are 500 files, 1 GiB total, and 50 MiB per file. Commit requires at least
2 GiB free afterward. Hidden files, package directories, symbolic links, unsafe relative paths,
unsupported formats, unsafe Office relationships, and suspicious compressed archives fail closed
or appear as skipped/error entries. Images, encrypted PDFs, scanned PDFs without text, and failed
extractors remain `metadata_only`; Alpha does not perform OCR.

## Knowledge cards

A connected Codex or Anthropic provider may generate a candidate only after the operator confirms
which extracted source text will be sent to that provider. Provider choice never silently changes.
The model returns a closed JSON object. Every key point must cite a real document version, source
digest, deterministic chunk/locator, and excerpt hash. Missing or stale citations reject the
candidate.

Cards remain `candidate` until a human approves the exact body hash. Approval also binds the source
manifest, collection policy, provider/model identity, and generator version. Superseded, dismissed,
revoked, and historical cards are excluded from normal recommendation. Approved cards do not
automatically become Workspace Memory.

## Retrieval and Work binding

FTS5 with the trigram tokenizer indexes active retained inputs, registered outputs, approved cards,
and approved active Workspace Memory. The result includes a snippet, source/status, version, SHA,
evidence label, and index version. Exact title/tag hits precede BM25 relevance.

The opt-in semantic model is `intfloat/multilingual-e5-small` at commit
`614241f622f53c4eeff9890bdc4f31cfecc418b3`. The local runtime uses 384-dimensional embeddings,
512-token inputs, ONNX Runtime 1.27.0, and sqlite-vec 0.1.9. Every downloaded file is checked against
the bundled manifest. Missing/offline/tampered runtime state is shown as “lexical only”; OpsWitness
does not call ChatGPT, Claude, or a remote embedding endpoint as a fallback. Model and vector-index
versions never mix.

“Use in new Work” revalidates every selected document version and SHA, then creates read-only
private material copies plus `LibraryInputBindingV1`. Only Plans with library inputs include that
binding in their canonical hash, preserving historical Plan bytes. The result is an ordinary
unconfirmed draft: the operator can inspect or remove material and must confirm again before any
dispatch.

## Offline export is not access control

`safe_partner` export creates an offline ZIP containing `index.html`, `manifest.json`, and
`SHA256SUMS`. It has no CDN, analytics, API, font download, or network request. The default payload
contains only explicitly selected approved cards, labels, and citation excerpts after a
field-by-field include/exclude/redact preview. It excludes original files, absolute paths, prompts,
logs, Memory, provider/account/device/session identifiers, and unapproved content.

The local operator controls creation and included fields. Once the ZIP is copied elsewhere it
cannot be revoked, expired, or protected by RBAC. Online accounts, TTL, recipient identity, and
revocation require a future authenticated Viewer and are not claimed by this export.

## Backups and privacy

Encrypted backup schema 2 includes collection policies, document/card versions, input CAS, and
Workspace Memory. It excludes staging, exports, lexical/vector indexes, and downloaded models.
Restore rebuilds search indexes from authoritative data.

Ledger and Paperclip projections record hashes, states, counts, and version identities—not source
bodies, filenames, absolute paths, card text, or Memory text. H5 bodies do not enter CAS.
