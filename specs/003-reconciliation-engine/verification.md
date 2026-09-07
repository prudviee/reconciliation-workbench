# 003 Reconciliation Engine — Verification

- **Status:** Verified
- **Specification:** [spec.md](./spec.md)
- **Plan:** [plan.md](./plan.md)
- **Verified commit:** The commit containing this record
- **Environment:** Windows 11 host; Python 3.12.2; NumPy 2.5.3; SciPy 1.18.1; Python 3.12.14 clean container; Django 5.2.17; PostgreSQL 17.6

All 18 acceptance scenarios and 22 requirements have linked passing evidence. Task records and machine-readable measurements live in [`evidence/`](./evidence/).

## Acceptance results

| Scenarios | Result | Primary evidence |
|---|---|---|
| REC-A01, REC-A06, REC-A16 | Passed | REC-T07 exact field comparison and authoritative discrepancy boundaries |
| REC-A02, REC-A04, REC-A08, REC-A12 | Passed | REC-T05 assignment and REC-T08 complete orchestration |
| REC-A03, REC-A05, REC-A07, REC-A09, REC-A11 | Passed | REC-T04–REC-T06 scoring, limits, and counterfactual gates |
| REC-A10 | Passed | REC-T09 read-only accepted-unmatched diagnostics |
| REC-A13, REC-A17, REC-A18 | Passed | REC-T02–REC-T04 reservation and reference semantics |
| REC-A14, REC-A15 | Passed | REC-T03–REC-T04 blocking union and complete factual evidence |

## Requirement traceability

| Requirements | Implementation/evidence | Result |
|---|---|---|
| REC-001–REC-004 | REC-T01, REC-T02, REC-T07, REC-T08 | Passed |
| REC-005–REC-007 | REC-T03, REC-T04 | Passed |
| REC-008–REC-010 | REC-T05, REC-T06 | Passed |
| REC-011–REC-015 | REC-T01, REC-T04, REC-T07, REC-T08 | Passed |
| REC-016–REC-018 | REC-T04–REC-T06 | Passed |
| REC-019 | REC-T09 | Passed |
| REC-020–REC-021 | REC-T02, REC-T04 | Passed |
| REC-022 | REC-T01, REC-T03, REC-T05, REC-T09, REC-T10 | Passed |

## Automated checks

| Check | Result | Notes |
|---|---|---|
| Unit/integration | Passed | Complete pure stage and orchestration suite |
| Property/oracle | Passed | 576 input permutations and exhaustive assignment/gap parity |
| Framework isolation | Passed | Django, filesystem, clock, and network access blocked in subprocess |
| Synthetic evaluation | Passed | Explicit precision/recall denominators; results labelled synthetic |
| Capacity safeguard | Passed | Dense 10,000-by-10,000 input bounded at 200 retained candidates and zero automatic pairs |
| Full regression | Passed | See REC-T10 evidence for final count and duration |
| Clean Compose | Passed | See `REC-T10-runtime.json` for clean build, health, migration, worker, and volume probes |

## Measured synthetic results

The 35-by-35 labelled corpus has 30 automation-eligible truth pairs, including 20 heuristic truth pairs. Exact-reference baseline precision/recall was 10/10 and 10/30. Greedy weighted precision/recall was 20/30 and 20/30 with 10 false automatic matches. Weighted global assignment with abstention was 20/20 precision, 20/30 recall, and 20/20 candidate recall, with zero false automatic matches. These are deterministic synthetic results, not production accuracy or model calibration.

The dense capacity fixture contained 10,000 records per side and 100,000,000 possible relationships. Limits retained 200 candidates, marked one component incomplete, withheld every automatic pair, and classified all 20,000 records as computation-limited. The tracemalloc-instrumented host run took 44.957 seconds with 8.318 MiB traced Python allocation peak. This exceeds the future under-10-second planning target; profiling and asynchronous execution remain required before making a production latency claim.

## Limitations and residual risk

- Demo weights, thresholds, and tolerances are versioned hypotheses rather than financial standards.
- The small synthetic corpus demonstrates deterministic behavior and denominator correctness, not real-world accuracy.
- The capacity run measures the safe bounding path on a 16-logical-CPU Windows host, not the planned two-vCPU/four-GiB deployment environment.
- Dense-limit classification currently dominates the instrumented runtime and should be profiled before specification 006.
- Run persistence, durable decisions, UI workflows, and deployment operations remain in specifications 004–006.

## Release decision

Specification 003 is verified for its stated pure-domain scope. The engine is ready to be integrated into persisted run lifecycle work in specification 004; no production latency or real-world accuracy claim is made.
