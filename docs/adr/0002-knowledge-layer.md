# ADR-0002: Vertical knowledge layer — deterministic-first split, vault as source, cited retrieval

Date: 2026-07-12 · Status: accepted (vertical knowledge-pack design)

This ADR governs signed domain corpora for vertical products. The Community platform's separate
candidate/approval/version policy for process and knowledge memory is implemented by
[ADR-0008](0008-repeatable-work-and-auditable-workspace-memory.md). A Markdown file does not become
planning memory merely because it exists in either vault.

## Context

Vertical case packs (first: the practitioner workbench) need domain knowledge. The lazy
shape — dump the corpus into a vector store and RAG everything — fails three of this
project's laws at once: it retrieves what should be computed, it makes "why this
passage" unanswerable, and it turns the paid content into an unversioned blob.
Monetization requires the corpus to be signed, versioned, updatable content; the trust
DNA requires every interpretive claim to be traceable.

## Decision

### 1. Knowledge splits three ways before any retrieval is designed

| Kind | Examples | Home |
|---|---|---|
| Computable rules | element interactions, derivation tables, pattern predicates | **deterministic engine code / lookup tables** — never retrieved, never an LLM call |
| Interpretive corpus | classical passages, judgment texts, modern commentary | **retrieval** (see §3) |
| Per-client records | client charts, past readings, practitioner notes | **isolated per-practitioner encrypted store**; retrieval scoped strictly within; birth data is sensitive PII and never enters the shared corpus or its indexes |

### 2. Corpus source format: a markdown vault (Obsidian-compatible)

Frontmatter carries feature tags, provenance, and confidence class; wikilinks carry the
citation graph (passage ↔ concept). The vault is the source of truth: git-versioned,
PR-reviewed, per-file sha256. Editors may maintain it in Obsidian; **the runtime never
touches Obsidian** — it sees a folder of markdown.

### 3. Retrieval is structured-first, vectors last

- **Primary**: exact match on deterministic chart-engine feature tags — the engine
  computes features, retrieval pulls passages tagged with those features. "Why was this
  passage cited?" has a deterministic answer.
- **Secondary**: lexical FTS (SQLite FTS5) for free-text questions.
- **Fallback only**: vector embeddings (sqlite-vec) if lexical+tags prove insufficient —
  never the primary path, never a separate vector database.

The runtime index is compiled from the vault by an ingest step and is **disposable** —
the same source-of-truth/disposable-index worldview as the run ledger and its SQLite
index. Agents query it through an MCP tool.

### 4. Citations are mandatory and verifiable

Every interpretive claim in a generated report carries a rule/passage ID plus the
corpus version hash. This extends the P4 artifact chain from "this report was not
altered" to "this claim is grounded in passage N of signed corpus vX". A practitioner
signs off on a report whose every sentence is checkable — that is the paid difference
from confident black-box prose.

### 5. Distribution: signed, content-addressed bundles

`vault → build → bundle (sha256 manifest, signed)` is the paid update channel.
Subscribers verify every update. The vault is the source code; the bundle is the release.

## Consequences

- Design law 6 holds: the platform layer stays retrieval-free; RAG exists only inside
  case packs, where the corpus is itself the product.
- Wheel test: only three thin components get built — ingest compiler, retrieval MCP
  tool, bundle signer. No vector DB, no Obsidian plugin, no self-hosted embedding
  service.
- The same shape serves the quant Contract Pack (the 7-layer audit framework becomes
  its first vault); the practitioner workbench is simply its first public skin.
- Client-data isolation is a compliance boundary (PIPL/GDPR), not just a preference.
