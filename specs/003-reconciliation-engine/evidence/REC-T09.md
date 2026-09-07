# REC-T09 Verification Evidence

- **Task:** Add read-only accepted-unmatched decision-health diagnostics
- **Requirements:** `REC-019`, `REC-022`
- **Acceptance scenario:** `REC-A10`
- **Date:** 7 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence; see Git history for `REC-T09`

## Implemented scope

- A separate `diagnose_accepted_unmatched` pass runs only after the complete primary reconciliation result exists.
- Accepted-unmatched identities remain reserved from reference matching, candidate evidence, assignment components, proposals, and confirmed pairs.
- Diagnostic candidate generation reuses the versioned blocking and exact scoring rules while leaving the primary candidate graph untouched.
- Plausibility requires the inclusive automatic score threshold, required evidence coverage, and no hard contradiction; global assignment is deliberately not rerun.
- Each diagnostic states the candidate identity, rule score, completeness, and whether the candidate is free or currently allocated.
- Current allocation is represented by a canonical `left:right` pair key and a factual partner explanation.
- The search enforces the per-record candidate limit and one shared diagnostic run-edge budget across all accepted-unmatched decisions.
- Truncation emits `INCOMPLETE_SEARCH` and explicitly says that absence of another diagnostic does not prove no candidate exists.
- Diagnostic contracts and `EngineResult` validate unique ordering, input membership, and current-allocation references to actual result pairs.

## Read-only identity evidence

For the free-candidate fixture, the primary result before diagnostic attachment contained:

- no pairs;
- L1 as `ACCEPTED_UNMATCHED`;
- R1 as `NO_CANDIDATE`;
- no primary candidates or assignment components.

The diagnostic pass returned L1 → R1 with score 10,000 and no current allocation. Comparing the primary tuple `(pairs, unpaired, candidates, components)` before and after the standalone diagnostic call produced exact equality. The enriched result adds only `diagnostics`.

## Diagnostic fixtures

| Scenario | Diagnostic evidence | Primary allocation effect |
|---|---|---|
| Plausible free R1 for accepted L1 | Candidate R1, score `10,000`, complete, no current pair | None |
| Plausible allocated R1 for accepted L1 | Candidate R1, current pair `L2:R1`, explanation names L2 | Existing L2–R1 pair unchanged |
| Accepted record on right side | Candidate L1 found symmetrically | None |
| Per-record limit reached | Retained candidate marked incomplete plus `INCOMPLETE_SEARCH` warning | None |
| Shared run budget exhausted | Later accepted decision receives explicit run-limit warning | None |
| Low-score candidate | No plausibility alert | None |
| Hard reference contradiction | No plausibility alert | None |
| Reordered inputs and decisions | Equal ordered diagnostics | None |

## Checks and results

| Check | Result | Evidence summary |
|---|---|---|
| Focused diagnostic/engine/contract/architecture suite | Pass | 47 checks passed for read-only behavior, allocation facts, limits, canonical ordering, result invariants, and framework isolation. |
| Full regression suite | Pass | 370 tests passed against the active local PostgreSQL stack in 17.40 seconds. |
| Free candidate | Pass | A newly plausible free counterpart was reported while both original unpaired outcomes and the empty assignment graph remained unchanged. |
| Allocated candidate | Pass | A counterpart already paired through trusted reference evidence reported canonical pair key `L2:R1` and current partner L2. |
| Reservation isolation | Pass | Accepted L1 never appeared in primary candidate, component, proposal, or pair evidence even when its diagnostic found a perfect candidate. |
| Incomplete search | Pass | Per-record truncation retained incomplete candidate evidence and added an explicit warning; exhausted shared run budget warned on the later decision without enumeration. |
| Factual filtering | Pass | Low-score and hard-contradiction candidates did not create plausibility alerts. |
| Direction and determinism | Pass | Left- and right-side accepted decisions worked symmetrically; reversed input and decision order produced equal results and canonical diagnostic order. |
| Mutation validation | Pass | Missing candidate IDs, falsely complete search warnings, foreign result identities, and stale allocation keys were rejected. |

## Scope boundary

Diagnostics identify evidence that may deserve reviewer attention. They cannot revoke accepted-unmatched decisions, reserve or release another identity, alter assignment, or create a pair. Durable alerts and reviewer actions remain in specification 004.
