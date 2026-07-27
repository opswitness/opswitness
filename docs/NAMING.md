# OpsWitness Naming Standard

Status: canonical for new user-visible names and documentation.

This standard applies prospectively. It does not rewrite historical ledger events, IDs, hashes,
artifact names, paths, protocol fields, release evidence, or compatibility records.

## Canonical product forms

| Context | Canonical form | Rule |
|---|---|---|
| Product and App display name | **OpsWitness** | Use this exact capitalization in prose and UI. |
| Python distribution, import namespace, and primary CLI | `opswitness` | Use lowercase. New examples use `opswitness`, not `qd`. |
| macOS bundle identifier | `com.opswitness.app` | Machine identifier; do not display it as the product name. |
| Legacy CLI alias | `qd` | Compatibility only. It is not a second product or a preferred command. |
| Former working name | Quarterdeck | Historical or migration context only; do not use for new product-facing labels. |

The `qd` entry point remains available for legacy automation. New documentation, scripts,
screenshots, and support instructions must use `opswitness`. Compatibility does not authorize
renaming old events or paths.

## Product vocabulary

- **Work** — one operator-reviewed plan and its versioned execution history. Capitalize it when
  referring to the OpsWitness object, not ordinary work in a sentence.
- **Project Library** — the cross-Work local index of retained planning inputs and registered or
  observed outputs. It does not imply that every file is duplicated.
- **Docs Center** — the six-topic offline help surface included in the App.
- **artifact** — a file or structured result created or selected during a Work.
- **evidence** — a registered event and digest that identify exact bytes and provenance.
- **sign-off** — an explicit human record that the displayed evidence was reviewed. It is not a
  claim that a business, legal, compliance, or quality outcome is correct.
- **experience candidate** — a proposed process lesson derived from bounded evidence. It remains
  inert until a human explicitly approves its exact content.

Prefer concrete status language:

- use **Execution complete · Verification needed** when processes ended but a human has not
  reviewed the result;
- use **approved** only for the exact governed request or exact experience version that received an
  approval;
- do not replace these states with vague words such as “done,” “safe,” or “verified.”

## New human-facing display names

The API enforces these format rules for new template, team-blueprint, and memory display names:

1. be non-empty text and not a path marker;
2. contain no leading or trailing whitespace, path separators, control characters, repeated ASCII
   spaces, Unicode format characters (including bidirectional controls and zero-width formatting),
   or non-NFC Unicode;
3. remain within the field-specific length limit;
4. rely on the stable ID for identity. Display names are not required to be globally unique.

The API rejects a name that violates these mechanically provable format rules. It does not silently
normalize the submitted text.

The following are **human writing conventions**, not API-enforced semantic checks:

- use a useful human-readable name for the outcome or reusable purpose, rather than a path,
  machine ID, or vague label;
- do not write a display name that impersonates an execution status such as “verified” or
  “approved”; and
- prefer language a new operator can distinguish from Work IDs, agent roles, and evidence states.

OpsWitness does not claim to infer intent from arbitrary human text. Reviewers remain responsible
for these editorial conventions.

## Enforcement boundary

Naming validation is deliberately attached to **new mutation requests**, including new task
templates, saved team blueprints, and new workspace-memory candidates. Read models and historical
projections do not invoke it. This boundary guarantees that:

- an older record remains readable even if its display name would not be accepted today;
- ledger event payloads and event hashes never change;
- Work, run, artifact, and memory IDs remain authoritative;
- migration tools may retain legacy paths and identifiers without presenting them as new product
  names; and
- future naming-policy changes cannot rewrite evidence.

When displaying history, show the recorded name exactly as evidence requires. If a clearer label is
needed, create a new version or new object with a new stable ID and an explicit relationship to the
old one.
