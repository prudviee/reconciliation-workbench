# 004 Decisions and Stable Cases — Verification

- **Status:** Verified
- **Specification:** [spec.md](./spec.md)
- **Plan:** [plan.md](./plan.md)
- **Verified commit:** The commit containing this record
- **Environment:** Windows 11 host; Python 3.12.2; Django 5.2.17; PostgreSQL 17.6; clean container versions recorded in `REV-T11-runtime.json`

All 13 acceptance scenarios and 16 requirements have linked passing evidence. Task records and machine-readable runtime evidence live in [`evidence/`](./evidence/).

## Acceptance results

| Scenario | Result | Primary evidence |
|---|---|---|
| REV-A01 | Passed | REV-T07 manual-link correction fixture and REV-T11 combined correction/rerun corpus |
| REV-A02 | Passed | REV-T07 accepted-unmatched/new-candidate fixture |
| REV-A03 | Passed | REV-T07 persistent rejection/reference-conflict fixture |
| REV-A04 | Passed | REV-T04 concurrent PostgreSQL endpoint-claim test |
| REV-A05 | Passed | REV-T05 revocation history and REV-T10 labelled history query |
| REV-A06 | Passed | REV-T06 immutable run facts, REV-T08 occurrences, REV-T10 projections, and REV-T11 combined corpus |
| REV-A07 | Passed | REV-T09 two-to-one merge and one-to-two split fixture |
| REV-A08 | Passed | REV-T08 ambiguity key change and REV-T09 transition planning |
| REV-A09 | Passed | REV-T05 lifecycle and REV-T07 corrected rejection fixture |
| REV-A10 | Passed | REV-T01 action validation plus REV-T04/REV-T05 persisted action matrix |
| REV-A11 | Passed | REV-T05 exact replacement conflict set and REV-T10 preview projection |
| REV-A12 | Passed | REV-T02–REV-T10 ownership, mutation, run, case, and query isolation matrices |
| REV-A13 | Passed | REV-T07 exact four-state health matrix |

## Requirement traceability

| Requirement | Implementation | Acceptance/evidence | Result |
|---|---|---|---|
| REV-001 | REV-T01, REV-T03–REV-T05 | REV-A05, REV-A10 | Passed |
| REV-002 | REV-T01, REV-T03, REV-T04 | REV-A01–REV-A03 | Passed |
| REV-003 | REV-T03, REV-T04 | REV-A04 | Passed |
| REV-004 | REV-T03, REV-T05, REV-T10 | REV-A05, REV-A10 | Passed |
| REV-005 | REV-T01, REV-T06, REV-T07 | REV-A01, REV-A02, REV-A13 | Passed |
| REV-006 | REV-T06, REV-T07 | REV-A01 | Passed |
| REV-007 | REV-T04, REV-T06, REV-T07 | REV-A03 | Passed |
| REV-008 | REV-T04, REV-T06, REV-T07 | REV-A02 | Passed |
| REV-009 | REV-T01, REV-T03, REV-T05, REV-T10 | REV-A11 | Passed |
| REV-010 | REV-T02, REV-T06, REV-T08–REV-T10 | REV-A07, REV-A08 | Passed |
| REV-011 | REV-T02, REV-T06, REV-T08, REV-T10 | REV-A06 | Passed |
| REV-012 | REV-T01–REV-T05 | REV-A04, REV-A11 | Passed |
| REV-013 | REV-T01, REV-T08, REV-T09 | REV-A07, REV-A08 | Passed |
| REV-014 | REV-T01, REV-T09 | REV-A07, REV-A08 | Passed |
| REV-015 | REV-T01, REV-T05–REV-T07 | REV-A03, REV-A09 | Passed |
| REV-016 | REV-T02–REV-T06, REV-T08–REV-T10 | REV-A12 | Passed |

## End-to-end correction and rerun corpus

The closing corpus publishes a first immutable run, records a manual link afterward, confirms that the saved decision is labelled pending, corrects the right-side amount, and publishes a second run. The second run preserves the manual pair, uses the corrected observation, reports `EVIDENCE_CHANGED` with `COMPARISON_CHANGED`, and advances the stable case to a new current occurrence. The first run's counts, pairing origin, observations, comparisons, and case-occurrence snapshot remain byte-for-byte equal to their captured values.

Separate fixtures cover accepted-unmatched records with new candidates, unavailable partners, persistent rejected relationships, incomplete diagnostics, reaffirmation, revocation, exact replacement previews, ambiguity membership changes, pair splits/merges, and independently current scopes.

## Measured query and concurrency boundaries

| Boundary | Result |
|---|---|
| Decision page | 4 fixed PostgreSQL queries; page size capped at 100 |
| Decision history | 5 fixed PostgreSQL queries |
| Case page | 4 fixed PostgreSQL queries; page size capped at 100 |
| Case history/current/lineage | 4–5 fixed PostgreSQL queries per projection |
| Concurrent conflicting links | Exactly one of two writers commits; one decision, one revision, two claims, one generation increment |
| Reconciliation computation inside decision transaction | None |

## Automated release gates

| Gate | Result |
|---|---|
| All REV-A01–REV-A13 scenarios | Passed |
| All REV-001–REV-016 requirements | Passed |
| Full regression suite | 458 passed in 33.76 seconds |
| Concurrent PostgreSQL claim probe | Passed |
| Framework-free domain boundary | Passed |
| Django system check | Passed, 0 issues |
| Migration drift | Passed, no changes detected |
| Python compilation | Passed |
| Clean Compose startup | Passed in 29.89 seconds on isolated fresh volumes; recorded in `REV-T11-runtime.json` |
| Diff hygiene | Passed |

## Limitations and deferred work

Specification 004 exposes application services and immutable evidence; it intentionally adds no browser routes. The current runner is synchronous. Browser workbench pages and accessible review forms belong to specification 005. Work leasing, attempt fencing, retries, coalescing, retention execution, and production deployment belong to specification 006. Multi-user roles, approval chains, comments, and external case-management integrations remain outside the first release.

## Decision

Specification 004 is verified. Durable reviewer authority, correction-aware health, immutable runs, stable cases, merge/split lineage, scoped current projections, bounded reads, and workspace isolation are ready for the specification 005 browser workflow.
