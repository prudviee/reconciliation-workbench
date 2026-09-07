# REC-T05 Verification Evidence

- **Task:** Solve bounded optional-unmatched one-to-one assignment
- **Requirements:** `REC-008`, `REC-010`, `REC-013`, `REC-017`, `REC-022`
- **Acceptance scenarios:** `REC-A02`, `REC-A04`, `REC-A07`, `REC-A08`
- **Date:** 7 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence; see Git history for `REC-T05`

## Implemented scope

- Deterministic connected components over candidate edges strictly above the assignment floor.
- Replaceable domain solver protocol and separately packaged SciPy 1.18.1 rectangular linear-assignment adapter using integer NumPy matrices.
- Optional-unmatched matrix with one zero-cost dummy column per left record, positive forbidden-real-edge costs, and utility `score_bp - assignment_floor_bp`.
- Frozen solver version in the matching policy and validation of solver output shape, indices, uniqueness, forbidden selections, and objective totals.
- Explicit component node and edge limits, incomplete-candidate-graph withholding, limited-member evidence, graph digests, and globally one-to-one selected edges.
- Pinned SciPy 1.18.1 and NumPy 2.5.3 runtime/development dependencies.

## Checks and results

| Check | Result | Evidence summary |
|---|---|---|
| Focused assignment/scoring/candidate/reference/contract/architecture suite | Pass | 89 checks passed for components, matrices, unmatched choices, limits, solver validation, determinism, prior stages, and framework independence. |
| Full regression suite | Pass | 318 tests passed against the active local PostgreSQL stack at the final task state in 17.10 seconds. |
| Exhaustive oracle | Pass | SciPy objectives matched an independent recursive enumeration on more than 200 deterministic sparse/dense graphs with one to four records per side. |
| Greedy counterexample | Pass | Scores `[[94,92],[93,20]]` selected L1–R2 and L2–R1 with 4,500 utility basis points instead of greedy L1–R1. |
| Optional unmatched | Pass | Edges at or below the 7,000 floor created no real selection; rectangular fixtures left unused right records and excess left records unmatched through dummy columns. |
| Matrix encoding | Pass | A captured sparse 2×4 matrix contained negative real-edge utility, a 20,003 positive forbidden cell, and two zero-cost dummy columns. |
| Limits | Pass | Exact node/edge boundaries solved; the first excess produced an explicit component limit and the test double proved the numerical solver was never invoked. |
| Incomplete candidate graph | Pass | A truncated component selected no edge; source limitations remained visible even when every retained edge was at or below the assignment floor. |
| Solver boundary | Pass | Version mismatch, malformed selection rows/columns, ragged matrices, and boolean/noninteger costs were rejected. |
| Dependency integrity | Pass | Host environment reported NumPy 2.5.3 and SciPy 1.18.1 with no broken requirements. |
| Container build/runtime | Pass | Fresh web and worker images installed the exact locks; the web container reported `scipy-1.18.1-linear-sum-assignment-v1`. Database, web, and worker became healthy and Django reported no system-check issues. |
| Domain isolation | Pass | Importing `reconciliation.domain` loaded neither NumPy nor SciPy; only the explicit solver adapter imports them. |
| Determinism and provenance | Pass | Reordered candidates produced equal components/selections, graph digests were canonical, and combined limited identities equalled source plus component limitations. |

## Scope boundary

This task records the optimal proposed assignment for each complete bounded component. REC-T06 computes counterfactual global gaps and applies every automatic-acceptance gate once.
