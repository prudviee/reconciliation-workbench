# REV-T08 Verification Evidence

- **Task:** Create stable cases, immutable occurrences, and per-scope projections
- **Requirements:** `REV-010`, `REV-011`, `REV-013`, `REV-016`
- **Acceptance scenarios:** `REV-A06`–`REV-A08`, `REV-A12`
- **Date:** 7 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence

## Stable identity and occurrence rules

| Result | Stable identity | Immutable occurrence target |
|---|---|---|
| Pair | Book + ordered left/right logical transaction IDs | Exact `run_pair` |
| Unpaired | Book + side + logical transaction ID | Exact `run_unpaired` |
| Ambiguity | Book + scope + policy digest + complete sorted left/right logical member sets | Exact `assignment_component` |

Every case stores the canonical key and SHA-256 digest plus identity metadata needed to audit it. Database shape constraints require pair, unpaired, and ambiguity cases to carry only the fields valid for their kind. An occurrence points to exactly one matching run result and is unique per case/run.

Correcting a transaction creates a new observation but keeps its logical transaction identity. Pair and unpaired fixtures therefore reused one case across two runs and appended a second occurrence. The first occurrence and its state snapshot remained unchanged. An ambiguity fixture with unchanged members/policy also reused its case; adding a new policy revision created a distinct ambiguity key and case.

## Current projections

`case_scope_projection` is replaceable derived state unique per case/scope. It points to the current occurrence and run, carries any decision health/attention associated with that result, and records applied data/resolution generations.

- A fresh publication replaces only projections for its own scope and removes cases no longer current there.
- A stale publication appends immutable occurrences but does not alter current projections.
- Two scopes that produce the same stable pair case retain two independent current projection rows with their own run IDs.
- Accepted-unmatched case projection followed its corrected occurrence and carried `EVIDENCE_CHANGED` from the separate decision-health snapshot.

Case materialization runs inside the same atomic publication transaction as run facts and health. The injected publication failure left no occurrences or current projections.

## Persistence protections

- Stable cases and occurrences reject instance updates/deletes and bulk updates/deletes.
- Unique and check constraints protect stable keys, kind-specific identity shapes, occurrence result shapes, and per-scope projection uniqueness.
- Every case table carries direct workspace ownership, and materialization always filters through the authorized workspace and frozen run scope/book.
- The distribution package contract now explicitly includes the `cases` application.

## Verification results

| Check | Result |
|---|---|
| Focused review/run/case suite | 48 passed in 12.55 seconds |
| Full repository regression | 442 passed in 31.47 seconds |
| Django system check | Passed, 0 issues |
| Migration drift check | Passed, no changes detected |
| Diff whitespace check | Passed |

## Scope boundary

This task materializes stable cases and current occurrences without inferring transitions. REV-T09 will compare the previous scope projection set with the new occurrence set before replacement and append explicit many-to-many lineage edges for merges, splits, and changed ambiguity membership.

