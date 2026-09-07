# REC-T03 Verification Evidence

- **Task:** Generate a complete bounded union of blocking passes
- **Requirements:** `REC-005`, `REC-013`, `REC-022`
- **Acceptance scenarios:** `REC-A07`, `REC-A08`, `REC-A14`
- **Date:** 7 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence; see Git history for `REC-T03`

## Implemented scope

- Deterministic union of versioned blocking passes with every discovering pass retained as edge evidence.
- Indexed grouping and inclusive time-range lookup using compatible instrument, side, currency, and optional explicit shared alias.
- Active rejected relationships excluded from every pass.
- Independent search-window contract; candidate generation has no scoring-band or comparison-tolerance input.
- Per-record and per-run candidate boundaries that retain at most the configured amount and mark the affected blocking partition incomplete on the first omitted edge.
- Recursive incompleteness propagation through overlapping blocking partitions so a partial pass cannot create a false complete component in another pass.
- Canonical candidate edges, partition identities, limit reasons, and complete/limited record sets independent of input and policy tuple order.

## Checks and results

| Check | Result | Evidence summary |
|---|---|---|
| Focused candidate/reference/contract/architecture suite | Pass | 52 checks passed for pass union, compatibility keys, time boundaries, prohibitions, missingness, caps, propagation, canonical order, and framework independence. |
| Full regression suite | Pass | 281 tests passed against the active local PostgreSQL stack in 14.85 seconds. |
| Compilation and diff integrity | Pass | Reconciliation modules and focused candidate tests compiled without error; Git whitespace validation passed. |
| Inclusive search window | Pass | An edge exactly 24 hours apart was included; one microsecond beyond was excluded. Instrument, side, and currency mismatches were excluded from the general pass. |
| Versioned pass union | Pass | Edges found by either a one-hour general pass or a 48-hour explicit-alias pass were retained once with every discovering `pass@version` reason. |
| Rejection boundary | Pass | An active rejected relationship did not enter any candidate pass while another permitted relationship for the same counterpart remained discoverable. |
| Missing search fields | Pass | Missing required instrument, side, currency, or timestamp produced no candidate without falsely reporting a truncated search. |
| Per-record limit | Pass | Exactly the configured candidate count completed; the first additional edge retained only the bounded set and marked the entire partition incomplete. |
| Run limit | Pass | Exactly the configured run edge count completed; the first additional edge marked its partition and subsequent unexamined partitions limited. |
| Incompleteness propagation | Pass | A previously complete pass sharing a record with a later truncated pass became limited, preventing a partial pass union from appearing complete. |
| Determinism | Pass | Reversing left rows, right rows, and blocking-pass declarations produced the same canonical result. |
| Policy separation | Pass | Candidate generation consumed the 24-hour search window and had no comparison-policy input; 10-minute similarity and 60-second comparison settings remained independent. |

## Scope boundary

Candidate inclusion is search evidence only. REC-T04 calculates compatibility, feature evidence, and rule scores. REC-T05 applies component limits and assignment only after confirming candidate graph completeness.
