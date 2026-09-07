# REC-T10 Verification Evidence

- **Task:** Measure and close reconciliation acceptance
- **Requirements:** `REC-001`–`REC-022`
- **Acceptance scenarios:** `REC-A01`–`REC-A18`
- **Date:** 7 September 2026
- **Result:** Pass for specification 003 scope
- **Task commit:** The commit containing this evidence

## Reproducible artifacts

- `scripts/evaluate_reconciliation.py` builds the labelled corpus, evaluates all strategies, and measures the dense capacity path.
- `REC-T10-measurements.json` contains machine-readable synthetic metrics, denominators, runtime, component counts, and traced memory.
- `REC-T10-runtime.json` contains the clean Compose build and health evidence.
- `verification.md` consolidates all requirements, scenarios, limitations, and the release decision.

## Labelled synthetic evaluation

The deterministic corpus contains 35 records per side, 30 automation-eligible truth pairs, and 20 heuristic truth pairs. Ten pairs have unique trusted references, ten are clean heuristic pairs, ten hidden truth pairs sit inside five tied 2×2 groups, and ten noise records have no true counterpart. Ambiguous truth labels deliberately cross lexical edge order so greedy tie selection cannot appear correct by accident.

| Strategy | Automatic precision | Automatic recall | Candidate recall | False automatic matches | Review rate |
|---|---:|---:|---:|---:|---:|
| Exact/reference | 10/10 = 100% | 10/30 = 33.3333% | 0/20 = 0% | 0 | 50/70 = 71.4286% |
| Greedy weighted | 20/30 = 66.6667% | 20/30 = 66.6667% | 20/20 = 100% | 10 | 10/70 = 14.2857% |
| Weighted global with abstention | 20/20 = 100% | 20/30 = 66.6667% | 20/20 = 100% | 0 | 30/70 = 42.8571% |

Manual pairs are excluded from automatic predictions and eligible denominators. Candidate recall uses only eligible heuristic truth pairs. Workflow terminal coverage is 70/70 for every strategy. These are synthetic behavior measurements, not real-world accuracy or calibrated probabilities.

## 10,000-by-10,000 bounded workload

| Measurement | Result |
|---|---:|
| Records | 10,000 left + 10,000 right |
| Possible Cartesian relationships | 100,000,000 |
| Retained candidates | 200 |
| Components | 1 incomplete |
| Automatic pairs | 0 |
| Computation-limited outcomes | 20,000 |
| Instrumented runtime | 44.957201 s |
| Tracemalloc Python allocation peak | 8.318 MiB |
| Host | Windows 11, 16 logical CPUs |

The per-record limit stopped dense enumeration at 200 retained edges, propagated incompleteness to the whole partition, and withheld all automatic matching. The instrumented runtime exceeds the future under-10-second target and was not run on the planned two-vCPU/four-GiB environment. It is recorded as a profiling requirement for specification 006, not a passed latency claim.

## Final release gates

| Gate | Result |
|---|---|
| Synthetic metric denominator test | Passed |
| Full repository suite | 371 passed in 19.06 seconds |
| Clean Compose startup | Passed in 26.172 seconds |
| Services | PostgreSQL, web, and worker running and healthy |
| Readiness | HTTP readiness and database readiness passed |
| Worker | Heartbeat passed |
| Storage | Web/worker shared private artifact volume passed |
| Migrations | Fully applied by the single migration owner |
| Container versions | Python 3.12.14, Django 5.2.17, PostgreSQL 17.6 |
| Diff hygiene | No whitespace errors |

## Final traceability

Every row in `tasks.md` is complete. REC-T01 through REC-T09 contain task-specific contract, reference, candidate, scoring, assignment, counterfactual, comparison, orchestration, isolation, and diagnostic evidence. `verification.md` maps all 18 acceptance scenarios and all 22 requirements to those records.

## Release decision and limitations

Specification 003 is verified for its pure deterministic engine scope. The initial matching policy remains a demonstrative hypothesis. The corpus is small and synthetic, dense-limit classification needs profiling, and production persistence, reviewer workflows, browser UI, asynchronous execution, and deployment remain explicitly assigned to specifications 004–006.
