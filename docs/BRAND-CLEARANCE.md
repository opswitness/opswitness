# OpsWitness Brand Clearance Gate

Snapshot refreshed: 2026-07-18 America/Los_Angeles

Status: **candidate approved for source migration; identifier reservation and final legal review
remain release blockers.** No GitHub organization, package, domain, or trademark right is created by
this document.

## Why the former name was rejected

The former working name, Quarterdeck, has active software usage and an active US class-42 software
registration. It is retained only where compatibility with an existing local installation requires
an old path, environment variable, launchd label, Keychain service, CLI alias, or historical record.
It is not the public product identity.

## OpsWitness knock-out search

On 2026-07-18, the exact lowercase identifier was checked through the public endpoints for PyPI,
GitHub's shared user/organization namespace, npm, and Verisign `.com` RDAP. Each returned HTTP 404.
Earlier exact and broader USPTO searches recorded no result for the joined or spaced name.

A 404 means only that the endpoint did not expose a matching registration at that moment. It does
not reserve the identifier, establish priority, or prove freedom to operate. Search results can
change before publication.

## Product fit

- `Ops` keeps the product horizontal across scheduled jobs, AI workers, approvals, and artifacts.
- `Witness` describes the trust boundary: the product preserves evidence without pretending to be
  every scheduler, runtime, or control plane below it.
- The name avoids claims of legal notarization or certification.

## Hard release gate

Before any public tag or announcement, all of the following must be true:

1. repeat exact-name package, web, GitHub, domain, and relevant trademark searches;
2. complete a qualified confusing-similarity review for the intended markets;
3. reserve the exact `opswitness` GitHub organization and intended domain;
4. create `opswitness/opswitness` as a private repository first;
5. enable private vulnerability reporting, Dependabot, minimum Actions permissions, and required
   checks on `main`;
6. run the release workflow in validation mode against the private remote, where it builds and
   verifies the distributions without publication credentials;
7. make the repository public, or separately verify GitHub Enterprise Cloud attestation support,
   before creating the approved public tag;
8. inspect every Release asset and attestation; and
9. set `PUBLIC_RELEASE_APPROVED=true` only after the preceding evidence is recorded.

GitHub documents [artifact attestations for private repositories](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
as an Enterprise Cloud feature.
The ordinary private-repository validation run therefore stops after the verified build artifact;
the `publish` job, OIDC token, attestation permissions, and GitHub Release exist only on the final
approved tag.

If the exact name fails any hard gate, stop. Do not publish under an improvised suffix.

## Migration contract

The source migration uses these compatibility rules:

- public product, distribution, module, repository metadata, UI, SBOM, and provenance use
  `OpsWitness` / `opswitness`;
- `opswitness` is the primary CLI and `qd` remains a compatibility alias through at least `v0.2.0`;
- `OPSWITNESS_*` is canonical while `QD_*` remains accepted; conflicting values fail closed;
- a fresh install uses OpsWitness paths, while an existing Quarterdeck-only installation continues
  in place without copying secrets, ledger events, plans, CAS blobs, or pristine backups;
- simultaneous new and old state/config roots are ambiguous and fail closed unless explicitly
  resolved;
- new launchd services use `com.opswitness.*`; old `com.quarterdeck.*` services remain readable and
  runnable, but matching old and new services must never run together;
- historical ledger events, plan hashes, artifact hashes, protocol markers, and external references
  are immutable and are never rewritten for branding.

This is a preliminary product and engineering gate, not legal advice.
