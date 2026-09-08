# OPS-T03 Verification Evidence

- **Task:** Add the run fencing token and verify it at publication
- **Requirements:** `OPS-003`, `OPS-004`, `OPS-005`, `OPS-006`
- **Acceptance scenarios:** `OPS-A01`, `OPS-A02`, `OPS-A03`, `OPS-A10`
- **Date:** 8 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence

## The gap this closes

Before this task, `execute_and_publish_run` transitioned `FROZEN/FAILED → RUNNING` with `ReconciliationRun.objects.filter(id=run.id).update(...)` — filtered only by `id`, not by the `lifecycle` value it had just read. Two concurrent callers for the same frozen manifest could both pass the earlier `if run.lifecycle not in (FROZEN, FAILED)` check and both proceed to run and attempt to publish. This is exactly the gap `plan.md`'s constitution check names under "Runs publish atomically."

## Implemented contracts

- `ReconciliationRun.current_attempt_token` (nullable `CharField`), with a new check constraint (`run_attempt_token_only_while_running`) forbidding a lingering token on any row not currently `RUNNING`.
- `execute_and_publish_run(..., *, attempt_token=None)`: the `FROZEN/FAILED → RUNNING` transition is now a conditioned `.update()` whose affected-row count is checked; a losing concurrent caller (`attempt_token=None`, the local-Compose/legacy path used by every existing caller today) gets `RunStateConflict` instead of silently racing. A caller that *does* supply `attempt_token` has, by construction, already won an exclusive `jobs.WorkItem` lease (`OPS-T02`'s `SKIP LOCKED` claim), so it may reclaim a `RUNNING` row left behind by an attempt whose lease has since expired — that reclaim is safe specifically because `publish_run`'s token comparison is what actually stops the earlier attempt from publishing if it is still alive.
- `publish_run(..., *, attempt_token=None)`: inside the same `select_for_update` transaction that already locks the run row, a non-`None` `attempt_token` is compared against `run.current_attempt_token`; a mismatch raises `RunStateConflict` and writes nothing. `attempt_token=None` skips the check, preserving today's behavior for every caller not yet routed through the jobs claim (view code, existing tests) until `OPS-T04` wires it in.
- The token is cleared (`current_attempt_token=None`) on every terminal transition — `COMPLETED` (success) and `FAILED` (the exception handler, itself now scoped to the specific token that failed).

No existing method signature became mandatory-token; every call site in `foundation.views` and the existing test suite continues to call these methods with no token and gets exactly the behavior specs 004/005 already verified.

## Fencing proof

- **Stale attempt cannot publish (`OPS-A01`, `OPS-004`):** attempt A claims (`token-a`) and computes a result; attempt B reclaims the same run (`token-b`) before A publishes. A's `publish_run(..., attempt_token="token-a")` raises `RunStateConflict` and leaves the run `RUNNING` under `token-b` untouched. B's own `publish_run(..., attempt_token="token-b")` then succeeds and completes the run, clearing the token.
- **A `RUNNING` row left by an expired lease can be reclaimed (`OPS-A01`):** a run manually forced into `RUNNING`/`stuck-token` (simulating a crashed attempt) is successfully reclaimed and completed by `execute_and_publish_run(..., attempt_token="fresh-token")`.
- **Two untokened callers racing the same frozen run (`ThreadPoolExecutor`, `django_db(transaction=True)`, the house `close_old_connections()` pattern):** exactly one reaches `COMPLETED`; the other gets `RunStateConflict`.

## Pre-existing behavior re-verified unchanged (`OPS-A02`, `OPS-A03`)

This task's edits do not touch `_persist_result`, `_validate_result`, the freshness computation, or the exception-rollback path beyond scoping it to the failing token. The existing tests proving those invariants still pass unmodified:

- `test_changed_dependency_keeps_completed_facts_stale_without_advancing_pointer` (`OPS-A02`/`OPS-A10`: a dependency change during computation completes as `STALE` and does not advance `scope.current_run`).
- `test_publication_failure_rolls_back_every_fact_and_marks_failed` (`OPS-A03`: a forced publication failure leaves no partial completed result).
- `test_health_projection_rolls_back_with_failed_publication`, `test_stale_run_keeps_health_snapshot_without_replacing_current_projection`.

## Verification results

| Check | Result |
|---|---|
| `python manage.py makemigrations reconciliation` | One migration (`current_attempt_token` + shape constraint), no manual edits needed |
| `python manage.py migrate reconciliation` | Applied cleanly |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| `python manage.py check` | 0 issues |
| `tests/test_run_fencing.py` (new) | 3 passed in 2.88 seconds |
| `tests/test_reconciliation_runs.py` (pre-existing, unmodified) | 27 passed in 5.34 seconds |
| Full repository regression | 508 passed in 12.98 seconds |
| `git diff --check` (whitespace) | Passed |

## Scope boundary

`create_run_manifest` still does not create a `jobs.WorkItem`, and no caller yet supplies a real token — `attempt_token` is exercised here only by tests calling the service layer directly. Wiring the view/service to actually claim a `WorkItem`, generate the token via `jobs.services.claim_batch`, validate manifest resource ownership before any financial read, and apply `RetryPolicy` on failure begins in `OPS-T04`.
