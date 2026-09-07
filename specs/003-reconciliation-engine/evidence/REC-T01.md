# REC-T01 Verification Evidence

- **Task:** Define immutable engine inputs, policies, and outcomes
- **Requirements:** `REC-001`, `REC-011`–`REC-017`, `REC-020`, `REC-022`
- **Acceptance scenarios:** `REC-A05`, `REC-A08`, `REC-A12`
- **Date:** 7 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence; see Git history for `REC-T01`

## Implemented scope

- Frozen, slot-based normalized record, two-sided snapshot, active decision, matching policy, comparison policy, evidence, pair, unpaired, component, diagnostic, and complete engine-result contracts.
- Strict nonblank identity, finite nonnegative decimal, aware timestamp, canonical tuple order, uniqueness, score-scale, policy-weight, threshold, reservation-conflict, and exactly-one-terminal-outcome invariants.
- UTC normalization for every present transaction timestamp without consulting a system timezone.
- Explicit reference contract, rule-score terminology, pair origins, unpaired reasons, comparison states, and diagnostic kinds.
- Versioned initial demo policy with quantity/timestamp/unit-price/gross-amount weights of 3,500/2,500/1,500/2,500 basis points; assignment floor 7,000; automatic threshold 9,000; minimum global gap 800.
- Independent 24-hour candidate search window, 10-minute timestamp similarity band, and 60-second comparison tolerance.
- Hard initial limits of 100 component nodes, 2,500 component edges, 250,000 run candidate edges, and 200 candidates per record.

## Checks and results

| Check | Result | Evidence summary |
|---|---|---|
| Focused contract and architecture suite | Pass | 26 checks passed for immutability, canonical ordering, UTC normalization, invalid values, policy boundaries, reservation conflicts, pair metadata, terminal coverage, and framework-independent imports. |
| Full regression suite | Pass | 255 tests passed against the active local PostgreSQL stack in 14.35 seconds. |
| Compilation | Pass | Reconciliation domain modules and the focused contract test compiled without error. |
| Initial policy | Pass | Weights were exactly 3,500/2,500/1,500/2,500 basis points and totalled 10,000; floor/threshold/gap were 7,000/9,000/800. |
| Window separation | Pass | Candidate search, similarity, and comparison retained distinct 24-hour, 10-minute, and 60-second values. |
| Capacity boundaries | Pass | Default 100/2,500/250,000/200 limits were retained and zero/boolean limits were rejected. |
| Decimal and time safety | Pass | NaN, infinity, negative financial values, and naive timestamps were rejected; aware times normalized to UTC. |
| Runtime type boundary | Pass | Untyped string enums and integer-as-boolean settings were rejected rather than relying only on Python annotations. |
| Terminal-outcome invariant | Pass | Missing, duplicate, wrong-side, and simultaneous pair/unpaired outcomes were rejected; reordered equivalent results compared equal. |

## Scope boundary

This task defines values and invariants only. Reservation/reference decisions, candidate enumeration, scoring, assignment, ambiguity gating, comparison logic, orchestration, and decision-health computation remain in REC-T02 through REC-T09.
