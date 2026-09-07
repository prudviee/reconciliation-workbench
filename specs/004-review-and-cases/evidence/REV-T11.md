# REV-T11 Evidence — Durable Review and Stable-Case Release Closure

- **Task:** REV-T11
- **Requirements:** `REV-001`–`REV-016`
- **Acceptance scenarios:** `REV-A01`–`REV-A13`
- **Date:** 7 September 2026
- **Result:** Pass for specification 004 scope
- **Task commit:** The commit containing this evidence

## Acceptance closure

Every scenario is mapped in `verification.md` to focused domain, PostgreSQL, correction/rerun, immutable-history, lineage, pagination, or isolation evidence. The closing end-to-end corpus proves the main story in one sequence: immutable first run → durable manual authority → corrected observation → current rerun → changed-health attention → stable case occurrence history, while the first run remains unchanged.

## Concurrency and query measurements

The two-writer PostgreSQL test still permits exactly one conflicting link and leaves one decision, one revision, two endpoint claims, and one resolution-generation increment. Decision mutation never invokes reconciliation computation.

REV-T10 measurements remain part of this release: decision and case pages use four fixed queries, decision history and case history/current/lineage use at most five, page size is capped at 100, and keyset pagination produced no duplicate or omitted identities.

## Release gates

| Gate | Result |
|---|---|
| End-to-end correction/rerun corpus | Passed |
| All REV-A01–REV-A13 scenarios | Passed |
| All REV-001–REV-016 requirements | Passed |
| Concurrent PostgreSQL claims | Passed |
| Full automated regression | **458 passed in 33.76 seconds** |
| Django system check | Passed, 0 issues |
| Migration drift | Passed, no changes detected |
| Domain architecture boundary | Passed |
| Python compilation | Passed |
| Clean Compose startup | Passed in **29.89 seconds** using an isolated fresh Compose project; recorded in `REV-T11-runtime.json` |
| Diff hygiene | Passed |

## Limitations

The reviewed behavior is exposed through application services rather than browser pages. Execution is synchronous. The polished workbench belongs to specification 005; background jobs, leases, fencing, retries, cleanup, observability, and deployment belong to specification 006.

## Decision

Specification 004 is verified for durable decisions, immutable run facts, correction-aware health, stable cases, lineage, bounded scoped reads, and workspace isolation.
