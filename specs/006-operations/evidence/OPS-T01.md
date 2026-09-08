# OPS-T01 Verification Evidence

- **Task:** Define pure job domain contracts
- **Requirements:** `OPS-003`, `OPS-007`, `OPS-017`
- **Date:** 8 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence

## Implemented contracts

- `JobKind`: `IMPORT_VALIDATION`, `RECONCILIATION_RUN`, `WORKSPACE_CLEANUP` — the three background-work targets named in `plan.md`.
- `JobState`: `READY`, `LEASED`, `SUCCEEDED`, `FAILED`, matching `docs/03-lld.md` §9's work-item state machine exactly.
- `FailureCategory`: `TRANSIENT`, `PERMANENT` — an explicit closed set a caller supplies; the domain never inspects exception types.
- `LeaseToken`: an opaque nonempty value; equality is the only operation the domain needs.
- `ClaimSnapshot`/`is_claimable`: a pure evaluation of the same rule the persistence layer's `SELECT ... FOR UPDATE SKIP LOCKED` `WHERE` clause enforces in SQL (`Q(state=READY, available_at__lte=now) | Q(state=LEASED, lease_until__lt=now)`), so the eligibility rule is unit-tested once instead of trusted to match the query by inspection.
- `RetryPolicy`/`RetryOutcome`: a pure function of `(attempt_count, max_attempts, failure_category, now)`. A permanent failure terminates on its first attempt; a transient failure retries with exponential backoff (`backoff * 2^(attempt_count-1)`) until `attempt_count` reaches `max_attempts`, then terminates.

No type touches money, time-comparison policy, or matching logic — `reconciliation.py`'s and `review.py`'s existing contracts are untouched.

## Claim-eligibility boundary matrix

| State | Offset from boundary | Claimable |
|---|---|---|
| READY | 1 microsecond before `available_at` | No |
| READY | exactly at `available_at` | Yes |
| READY | 1 microsecond after `available_at` | Yes |
| LEASED | 1 microsecond before `lease_until` | No |
| LEASED | exactly at `lease_until` | No |
| LEASED | 1 microsecond after `lease_until` | Yes |
| SUCCEEDED / FAILED | any | No |

`READY` is inclusive at the boundary (`available_at__lte=now`); `LEASED` is exclusive (`lease_until__lt=now`) — a lease is not yet expired at the instant it is due, matching the persistence-layer query this mirrors.

## Retry boundary matrix

| attempt_count | max_attempts | failure_category | Outcome |
|---:|---:|---|---|
| 1 | 3 | PERMANENT | `FAILED`, no `available_at` |
| 1 | 3 | TRANSIENT | `READY`, `available_at = now + backoff × 1` |
| 2 | 3 | TRANSIENT | `READY`, `available_at = now + backoff × 2` |
| 3 | 3 | TRANSIENT | `FAILED`, no `available_at` (limit reached) |

`RetryPolicy` rejects `max_attempts < 1`, a boolean passed as `max_attempts`, and a nonpositive `backoff` at construction; `decide()` rejects a nonpositive `attempt_count`.

## Verification results

| Check | Result |
|---|---|
| `tests/test_jobs_domain.py` + `tests/test_domain_boundary.py` | 22 passed in 0.31 seconds |
| Full repository regression | 490 passed in 12.53 seconds |
| Domain import without Django/settings/database (`reconciliation.domain.jobs` reachable, no `django`/`psycopg`/`numpy`/`scipy` loaded) | Passed |
| `git diff --check` (whitespace) | Passed |

## Scope boundary

This task defines pure values only — no database table, no claim query, no Django model. `WorkItem`/`JobAttempt` persistence, the `SKIP LOCKED` claim query, and every caller (`ReconciliationRunService`, `ArtifactIntakeService`, workspace cleanup) begin in OPS-T02 through OPS-T07.
