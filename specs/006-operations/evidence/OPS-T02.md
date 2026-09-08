# OPS-T02 Verification Evidence

- **Task:** Persist `WorkItem`/`JobAttempt` and the claim query
- **Requirements:** `OPS-001`, `OPS-002`, `OPS-003`, `OPS-017`
- **Acceptance scenarios:** `OPS-A04`, `OPS-A09` (claim-concurrency portion; enqueue-transaction portion closes with the caller in OPS-T04/OPS-T06)
- **Date:** 8 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence

## Implemented contracts

- New `jobs` app: `WorkItem` (workspace, kind, state, one exact-shape `OneToOneField` target per kind — `import_attempt`, `reconciliation_run`, or `cleanup_request` — available_at, lease_until, current_token, attempt_count, max_attempts) and `JobAttempt` (workspace, work_item, unique token, leased_at, lease_until, completed_at, outcome, failure_category).
- `jobs.services.claim_batch`: the `select_for_update(skip_locked=True)` claim query described in `plan.md`, generating one `LeaseToken` per claimed row, writing one `JobAttempt` grant row per claim, and incrementing `attempt_count`.
- `jobs.services.mark_succeeded`/`mark_failed`: the completion-side persistence primitives. Both re-lock the `WorkItem` and compare `current_token` against the caller's token before writing — a mismatched token (the lease was reclaimed) writes the calling attempt's own `JobAttempt` row as `EXPIRED` and leaves the `WorkItem` untouched, closing OPS-004 at the persistence layer for every job kind, not only reconciliation runs.
- `JobAttempt`'s grant fields (`work_item`, `token`, `leased_at`, `lease_until`) are permanently fixed at creation; only its trailing outcome fields accept one later write, mirroring `ReconciliationRun`'s own FROZEN-then-transitioned pattern (`RunOwnedQuerySet.update()`) rather than a fully immutable row that could never record an outcome.

## Exact-shape and lease-shape constraint matrix

| Case | Expected | Result |
|---|---|---|
| `IMPORT_VALIDATION` with `import_attempt` set, others null | Accepted | Pass |
| `RECONCILIATION_RUN` with `reconciliation_run` set, others null | Accepted | Pass |
| `WORKSPACE_CLEANUP` with `cleanup_request` set, others null | Accepted | Pass |
| Any kind with zero targets set | `IntegrityError` | Pass |
| `IMPORT_VALIDATION` with both `import_attempt` and `cleanup_request` set | `IntegrityError` | Pass |
| A second `WorkItem` reusing an already-claimed target (`OneToOneField`) | `IntegrityError` | Pass |
| `state=LEASED` created without `lease_until`/`current_token` | `IntegrityError` | Pass |

## Claim-concurrency proof

- Two `ThreadPoolExecutor` workers call `claim_batch` against one `READY` row at the same instant (`django_db(transaction=True)`, `close_old_connections()` per the house pattern from `test_resolution_commands.py`): exactly one claims it, matching `SKIP LOCKED`'s guarantee.
- A lease that has not yet expired is not reclaimed (`claim_batch` at `now + 5s` against a 10s lease returns nothing); the same call at `now + 11s` reclaims it with a new token and `attempt_count` incremented to 2 — the exact `OPS-A01` shape, exercised here at the generic claim-query level ahead of the reconciliation-run-specific proof in OPS-T03.
- The original (now-fenced) attempt's `mark_succeeded` call is rejected (`False`) once a second attempt has reclaimed the item; its own `JobAttempt` row is written `EXPIRED`, and the `WorkItem` keeps the second attempt's token untouched.

## Verification results

| Check | Result |
|---|---|
| `python manage.py makemigrations jobs` | One migration, no manual edits needed |
| `python manage.py migrate jobs` | Applied cleanly against PostgreSQL |
| `python manage.py makemigrations --check --dry-run` | No changes detected (model/migration parity) |
| `python manage.py check` | 0 issues |
| `tests/test_jobs_persistence.py` | 15 passed in 2.80 seconds |
| Full repository regression | 505 passed in 12.26 seconds |
| `git diff --check` (whitespace) | Passed |

## Scope boundary

`claim_batch`/`mark_succeeded`/`mark_failed` are generic, workspace-agnostic primitives with no knowledge of reconciliation runs or imports. Wiring `create_run_manifest` to enqueue inside its own freeze transaction, calling `RetryPolicy.decide()` on failure, and validating manifest resource ownership before any financial read begin in OPS-T03/OPS-T04. Import validation wiring begins in OPS-T06. Workspace cleanup's own claim-time re-verification (workspace still `REVOKED`/`DELETED`, zero live references) begins in OPS-T07.
