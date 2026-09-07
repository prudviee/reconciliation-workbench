# REV-T07 Verification Evidence

- **Task:** Project decision health without changing authority
- **Requirements:** `REV-005`–`REV-008`, `REV-015`
- **Acceptance scenarios:** `REV-A01`–`REV-A03`, `REV-A09`, `REV-A13`
- **Date:** 7 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence

## Pure health precedence

Health is derived from immutable decision authority plus one completed run. It never creates, removes, or moves an active claim.

| Condition | Health | Separate attention |
|---|---|---|
| Any required logical identity is absent from the frozen scope | `PARTNER_UNAVAILABLE` | Evidence-specific attention only when it can be established |
| Accepted-unmatched diagnostic finds a plausible candidate | `NEW_CANDIDATE` | `DIAGNOSTIC_INCOMPLETE` may coexist if the bounded search was incomplete |
| Reviewed observation fingerprint set changed | `EVIDENCE_CHANGED` | A link also receives `COMPARISON_CHANGED`; a rejected edge that now has an authoritative equal reference receives `AUTHORITATIVE_REFERENCE_CONFLICT` |
| Reviewed evidence is unchanged and no new candidate exists | `UNCHANGED` | `DIAGNOSTIC_INCOMPLETE` records uncertainty without claiming that no candidate exists |

The pure classifier validates that candidate/diagnostic fields are used only for accepted-unmatched authority, comparison-change attention only for links, and authoritative-reference conflicts only for rejected relationships.

## Persisted projections

`decision_health_snapshot` is append-only and unique per run/decision revision. It records exact current observation IDs, their evidence digest, endpoint availability, evidence-change fact, health, and ordered attention codes. Each completed historical run therefore retains the health conclusion made from its own frozen inputs.

`current_decision_health` is replaceable derived state unique per scope/decision. A current run updates it with the exact snapshot and applied generations. A stale run still receives immutable health snapshots but cannot add, replace, or remove current projections. A fresh run removes projections for authority that is no longer active.

Health snapshots publish in the same transaction as pairs, comparisons, candidates, diagnostics, run completion, and the scope pointer. A failure injected after projection rolled back both historical health and current projection rows.

## Correction and authority evidence

| Fixture | Result | Authority proof |
|---|---|---|
| Manual pair, then right gross amount corrected | Pair remains `MANUAL`; fresh comparison evidence; `EVIDENCE_CHANGED` plus `COMPARISON_CHANGED` | Original decision remains current and retains both endpoint claims |
| Same manual pair reaffirmed against corrected observations | New revision projects `UNCHANGED` with no attention | Reaffirmation advances the reviewed baseline and keeps the same authority |
| Accepted-unmatched record, then opposite instrument corrected into a plausible candidate | `NEW_CANDIDATE`; accepted record remains terminal `ACCEPTED_UNMATCHED` | Its single endpoint claim remains owned by the decision |
| Accepted-unmatched diagnostic explicitly incomplete | `UNCHANGED` plus `DIAGNOSTIC_INCOMPLETE` | No absence conclusion and no assignment change |
| Active link whose partner leaves the selected snapshot | `PARTNER_UNAVAILABLE` | Both stable identity claims remain intact |
| Rejected edge whose corrected records gain the same trusted reference | No pair; `EVIDENCE_CHANGED` plus `AUTHORITATIVE_REFERENCE_CONFLICT` | Rejection revision remains current; relationship stays prohibited |

The run diagnostic allocation reference was also corrected to store the engine's stable pair identifier as text. It is pair evidence, not an observation foreign key.

## Verification results

| Check | Result |
|---|---|
| Pure health plus run/correction integration suite | 44 passed in 9.34 seconds |
| Full repository regression | 438 passed in 27.50 seconds |
| Django system check | Passed, 0 issues |
| Migration drift check | Passed, no changes detected |
| Diff whitespace check | Passed |

## Scope boundary

This task derives and persists decision health only. Stable case identity, occurrences, and per-case projections begin in REV-T08; health and authority records remain their inputs and are not rewritten during case materialization.

