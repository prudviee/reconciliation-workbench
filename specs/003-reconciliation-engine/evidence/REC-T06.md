# REC-T06 Verification Evidence

- **Task:** Gate proposals by counterfactual global stability once
- **Requirements:** `REC-009`, `REC-010`, `REC-018`
- **Acceptance scenarios:** `REC-A03`, `REC-A05`, `REC-A07`, `REC-A09`, `REC-A11`
- **Date:** 7 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence; see Git history for `REC-T06`

## Implemented scope

- One forbid-edge counterfactual solve for each real edge in the original optimal assignment, against the unchanged complete component graph and optional-unmatched choices.
- Exact integer global gap evidence calculated as base optimal utility minus counterfactual optimal utility.
- Inclusive automatic score and global-gap boundaries, plus required-evidence, hard-contradiction, and complete-computation gates.
- Explicit abstention for equal optima, incomplete candidate graphs, and over-limit components.
- Immutable accepted-subset output evaluated once; a rejected proposal never removes an edge and starts another selection cycle.
- Stable factual gate reason codes, canonical proposal ordering, solver-version checks, graph-digest verification, and candidate/proposal consistency validation.

## Counterfactual decision table

| Scenario | Base proposal | Counterfactual fact | Gate result |
|---|---|---|---|
| Four equal 9,400 scores | One of two tied complete assignments | Forbidding either selected edge preserves the same optimal utility; gap `0` | Both proposals withheld as `GLOBAL_GAP_BELOW_MINIMUM` |
| Inclusive boundary | L1–R1 score `9,000` over L1–R2 score `8,200` | Base utility `2,000`; without L1–R1 utility `1,200`; gap `800` | Accepted |
| Immediately below score | L1–R1 score `8,999` | Gap is otherwise sufficient | Withheld as `SCORE_BELOW_AUTOMATIC_THRESHOLD` |
| Immediately below gap | L1–R1 score `9,000` over L1–R2 score `8,201` | Base utility `2,000`; counterfactual utility `1,201`; gap `799` | Withheld as `GLOBAL_GAP_BELOW_MINIMUM` |
| Greedy counterexample | L1–R2 and L2–R1 | Base utility `4,500`; each forbidden solve has utility `2,400`; both gaps `2,100` | Both accepted |
| Missing evidence and contradiction | Selected 9,500 edge | Counterfactual stability cannot override missing quantity or currency conflict | Withheld with both factual reasons |
| Rejected strongest edge | L1–R1 score `9,500`, with valid L1–R2 score `9,400` | L1–R1 fails evidence; exactly one counterfactual call occurs | No proposal is promoted or re-solved |
| Mixed component | L1–R1 fails evidence; L2–R2 passes every gate | Two original proposals receive two counterfactual solves | Only L2–R2 remains in the accepted subset |
| Over-limit component | Component exceeds the exact node limit | Base assignment contains no selected edge | No counterfactual solve and no automatic pair |

## Checks and results

| Check | Result | Evidence summary |
|---|---|---|
| Focused reconciliation and architecture suite | Pass | 104 checks passed across gating, assignment, scoring, candidates, references, contracts, and framework isolation. |
| Full regression suite | Pass | 331 tests passed against the active local PostgreSQL stack in 17.06 seconds. |
| Exhaustive counterfactual oracle | Pass | More than 100 selected proposals from deterministic sparse and dense graphs with one to four records per side matched independent recursive base and forbid-edge objectives exactly. |
| Equal optimum | Pass | Every selected edge in the four-edge 9,400 tie had gap zero and the accepted subset was empty, independent of solver tie choice. |
| Inclusive boundaries | Pass | Score 9,000 and gap 800 passed; score 8,999 and gap 799 failed with their exact gate reasons. |
| Single-pass behavior | Pass | Counting solver fixtures proved exactly one sensitivity solve per original proposal; an evidence-failing strongest edge did not promote its valid weaker alternative. |
| Accepted subset | Pass | A two-proposal component retained the passing proposal while withholding the failing proposal without recomputing assignment. |
| Completeness and limits | Pass | An over-limit component preserved its limit evidence and produced neither proposals nor solver calls. |
| Evidence gates | Pass | Missing required evidence and a hard contradiction were reported together and prevented acceptance despite a high score. |
| Provenance and determinism | Pass | Component graph digest, solver version, edge score/utility, candidate partition, counterfactual arithmetic, canonical ordering, and one-to-one accepted output are validated. |

## Scope boundary

This task decides which weighted-global proposals are safe to accept. REC-T07 compares the business fields of paired records; REC-T08 orchestrates all stages into terminal pair and unpaired outcomes.
