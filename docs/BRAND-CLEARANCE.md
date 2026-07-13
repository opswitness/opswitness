# Brand Clearance Gate

Snapshot: 2026-07-13 12:20 America/Los_Angeles

Status: `Quarterdeck` is rejected for public commercial release. `OpsWitness` is the
recommended replacement candidate, pending operator approval and a qualified similarity
search before publication.

## Knock-out result

| Candidate | Exact web/product search | PyPI | GitHub namespace | `.com` RDAP | Verdict |
| --- | --- | --- | --- | --- | --- |
| `Quarterdeck` | active software usage and US registration 7860652, class 42 | occupied/history risk | occupied | not relied on | reject |
| `AuditLoom` | active AI compliance/GRC platform and another audit business | not material | not material | occupied/used | reject |
| `RunWitness` | used by the adjacent 4QX agent-verification project | 404 | 404 | unregistered response | reject |
| `TaskNotary` | no exact product found | 404 | 404 | unregistered response | reject: implies legal notarization |
| `OpsWitness` | no exact product or indexed exact mark found | 404 | 404 | unregistered response | recommend |

Evidence was checked live on the snapshot date using exact-name web searches, PyPI and npm
registry endpoints, the shared GitHub user/organization namespace, and Verisign `.com` RDAP.
All four `OpsWitness` identifier checks returned `404`. A `404` proves only that the
identifier was unregistered at that moment; it does not reserve it.

## Official federal search checkpoint

The USPTO Trademark Search system returned **No results found** for each of these live
queries on the snapshot date:

- `CM:"opswitness"`
- `CM:"ops witness"`
- `CM:(/.*ops.*/ AND /.*witness.*/)`
- `FM:/op.*witness/`
- `FM:/witness.*op/`

These queries cover the exact joined and spaced forms, marks containing both component
words, and broader full-mark orderings beginning with `op` or `witness`. They materially
strengthen the knock-out result but do not search every phonetic equivalent, translation,
common-law use, jurisdiction, or related mark in crowded `ops` and `witness` fields.

## Why OpsWitness fits

- `Ops` keeps the platform horizontal: scheduled scripts, agent tools, approvals, artifacts,
  and future vertical cases all fit.
- `Witness` describes the product boundary accurately: it records independently verifiable
  evidence and does not claim to be the scheduler, agent runtime, or control plane.
- It avoids legal-certification language such as `notary`, and it does not inherit the
  maritime-software collision that blocks Quarterdeck.
- The public command can remain concise while the product name is legible in search and
  enterprise conversations.

## What this check does not prove

This is a preliminary knock-out search, not a legal opinion or final trademark clearance.
Before public commercial use, search confusingly similar spellings, phonetic equivalents,
common-law software usage, relevant international classes/markets, and obtain qualified
review if the product will be sold under the mark.

## Rename contract

After operator approval, perform the rename as one migration, not scattered wording edits:

1. reserve the domain and GitHub organization before announcing the name;
2. rename distribution metadata, repository URLs, docs, NOTICE, SBOM/provenance identity,
   synthetic showcase, and UI labels;
3. add a new public CLI name while retaining `qd` as a documented compatibility alias for
   one release;
4. support existing `QD_*` configuration and `~/.local/state/quarterdeck` data without
   copying or losing secrets, ledger events, CAS blobs, or pristine plist backups;
5. migrate Python package imports and tests mechanically, then run the complete suite and
   isolated backup/restore drill;
6. change launchd labels only after the active M2 soak, with byte-identical rollback and a
   single-instance check;
7. create the remote and enable `PUBLIC_RELEASE_APPROVED=true` only after CI, private
   vulnerability reporting, and the final name check pass.

No production path, launchd label, package name, or public identifier changes merely because
this document recommends a candidate.
