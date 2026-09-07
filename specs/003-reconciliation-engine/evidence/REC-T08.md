# REC-T08 Verification Evidence

- **Task:** Orchestrate deterministic complete engine results
- **Requirements:** `REC-001`, `REC-011`, `REC-013`
- **Acceptance scenarios:** `REC-A02`, `REC-A03`, `REC-A04`, `REC-A08`, `REC-A12`
- **Date:** 7 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence; see Git history for `REC-T08`

## Implemented scope

- Public pure `reconcile` entry point that runs reviewer/reference preprocessing, candidate generation, exact scoring, bounded global assignment, single-pass counterfactual gating, and field comparison in the approved order.
- Manual, authoritative-reference, and accepted weighted-global pairs receive the same complete comparison ledger without reopening identity selection.
- Every remaining input receives one explicit terminal classification: computation-limited, prohibited, no-candidate, below-assignment-floor, or ambiguous.
- `EngineResult` validates exact left/right terminal coverage, uniqueness, candidate/component input membership, proposal-to-candidate score consistency, and exact accepted-proposal-to-weighted-pair score/gap correspondence.
- Canonical candidate-graph and complete-result SHA-256 digests use stable ordering plus lossless tagged decimal, UTC timestamp, and elapsed-duration encodings.
- Canonical JSON serialization is independent of input row order and retains all evidence, versions, comparisons, reasons, proposals, and component facts.
- The engine depends on immutable values and an injected solver protocol; it performs no database, framework, filesystem, network, or clock access.

## Canonical golden fixtures

| Fixture | Result |
|---|---|
| One exact weighted pair | L1–R1, score `10,000`, global gap `3,000`, nine exact field comparisons |
| Manual plus authoritative pair | Both identities retained; manual currency mismatch makes money not comparable; authoritative `T-1011` keeps gross-amount difference `170` |
| Four equal candidates | No pairs; all four records `AMBIGUOUS`; selected mathematical proposals have gap zero |
| Candidate below floor | Both records `BELOW_ASSIGNMENT_FLOOR` |
| No compatible candidate | Both records `NO_CANDIDATE` |
| Active rejected relationship | Both endpoints `PROHIBITED` with related identity evidence |
| Component over limit | Every member `COMPUTATION_LIMITED`; incomplete component evidence retained |
| Feasible greedy counterexample | Global assignment retains the two off-diagonal pairs rather than the highest local edge |

## Digest evidence

| Artifact | SHA-256 |
|---|---|
| Isolated-process exact weighted result | `5978c24d74750144676ddad50046e8b1de753623af55154742450fa9f0acc4de` |
| Exact weighted candidate graph | `18f41d27e1d390c87dcefdeea2bd2f14600ba057e99152e9d11eca16b5f5e6e0` |

The isolated digest was reproduced twice after imports while Django imports, file opening, socket creation, and wall-clock reads raised immediately. The injected standard-library solver and the normal SciPy adapter produced the same result digest for the one-edge fixture.

## Checks and results

| Check | Result | Evidence summary |
|---|---|---|
| Focused engine/gating/comparison/contract/architecture suite | Pass | 71 checks passed for full orchestration, prior stage semantics, result invariants, and domain isolation. |
| Full regression suite | Pass | 361 tests passed against the active local PostgreSQL stack in 80.17 seconds. |
| Permutation property | Pass | Every one of 576 left/right row-order permutations over four independent pairs produced an equal canonical `EngineResult`. |
| Terminal partition | Pass | Mixed authoritative, cancelled, and no-candidate inputs each appeared exactly once; removing or duplicating one terminal outcome was rejected. |
| Cross-evidence mutation | Pass | Removing accepted component evidence from a weighted pair and replacing a candidate endpoint with a foreign input ID were rejected. |
| End-to-end abstention | Pass | Equal optimum, below-floor, prohibited, no-candidate, and component-limit scenarios produced no unsupported automatic pair and retained explicit reasons. |
| Pair comparison | Pass | Manual, authoritative, and weighted pair origins all carried nine deterministic comparisons while preserving their distinct origin metadata. |
| Canonical serialization | Pass | Candidate order and input order did not change digests; decimals and UTC timestamps retained explicit type tags and canonical values. |
| Isolated process | Pass | Two subprocess executions with framework and runtime I/O access blocked returned the recorded 64-character digest. |

## Scope boundary

This task returns the complete primary reconciliation result. REC-T09 adds a separate read-only health diagnostic for accepted-unmatched decisions without changing any pair or terminal outcome; REC-T10 adds synthetic evaluation and final release evidence.
