# OPS-T04 Verification Evidence

- **Task:** Route reconciliation-run execution through claim-and-execute
- **Requirements:** `OPS-001`, `OPS-002`, `OPS-007`, `OPS-008`, `OPS-017`
- **Acceptance scenarios:** `OPS-A04`, `OPS-A09`, `OPS-A11`, `OPS-A12`, `OPS-A16`
- **Date:** 8 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence

## Implemented contracts

- `create_run_manifest` now enqueues its `WorkItem` via a new `jobs.services.enqueue()` helper, inside the same `transaction.atomic()` block that freezes the manifest — both the new-run branch and the duplicate-manifest (`existing`) branch call it, so a retry after a rollback or an unchanged-manifest resubmission resolves to exactly one `WorkItem` (`OPS-001`, `OPS-002`, `OPS-A09`).
- `FrozenRun` gained `work_item_id` so callers can claim exactly the item they just enqueued.
- `reconciliation.services.execute_claimed_run(work_item, token)` is the `JobKind.RECONCILIATION_RUN` executor for `jobs.services.claim_and_execute`. It derives `workspace_id` **only** from `work_item.workspace_id` — never from any other value — and calls the existing `execute_and_publish_run(workspace_id, work_item.reconciliation_run_id, attempt_token=str(token))`. Since every downstream query (`_get_run`, `RunInput.objects.owned_by(...)`, ...) already scopes through `owned_by(workspace_id)`, deriving the scope solely from the claimed `WorkItem` means a forged/inconsistent target fails at the first `_get_run` lookup — before `compute_run` reads a single `RunInput`/`TransactionObservation` row (`OPS-017`, `OPS-A16`).
- `execute_claimed_run` categorizes a lost fencing race (`RunStateConflict`) as `TransientJobFailure`; every other exception (validation, programming errors) propagates as permanent. `claim_and_execute` applies `RetryPolicy.decide()` to whichever category it receives and persists the outcome via `mark_failed` (`OPS-007`, `OPS-A11`).
- `jobs.services.claim_and_execute` gained a `work_item_id` parameter: with it, it claims exactly that item via the new `claim_one` (itself `_claim_row` shared with `claim_batch`) instead of pulling whatever is next system-wide. This closes a real correctness gap found while wiring the view — without it, a request could execute a *different* workspace's queued run instead of the one it just enqueued.
- `jobs.services.enqueue()` reserves `active_jobs` quota only when it actually creates a new `WorkItem`; `mark_succeeded` and a terminal (non-retry) `mark_failed` release it. A retrying `mark_failed` (state stays `READY`) does not release — the slot is legitimately still held.
- `foundation.views.reconciliation_run_start` now calls `claim_and_execute(..., work_item_id=frozen.work_item_id)` instead of `execute_and_publish_run` directly, and branches on the returned `list[ExecutionRecord]` rather than exceptions alone — `claim_and_execute` deliberately does not re-raise a `TransientJobFailure`, so relying on exceptions alone would have made the view redirect to `completed=1` after a silently-swallowed transient failure. Caught this in this task via a failing pre-existing test before it could ship (see below).

## Correctness issue found and fixed during this task

**Wrong-item execution:** `claim_batch` claims system-wide by kind with no target scoping. Calling it directly from the view after enqueueing one specific run would let the request execute an unrelated workspace's queued item while the user's own run sat unclaimed. Fixed by adding `claim_one`/`work_item_id` and refactoring `claim_batch` and `claim_one` to share one `_claim_row` helper, so both claim paths keep identical lease/token/attempt-count semantics.

**Swallowed transient failure:** initial view code used `try/except Exception` around `claim_and_execute` alone. Since `claim_and_execute` records a `TransientJobFailure` via `mark_failed` without re-raising, the `except` block never fired for that case, and the view fell through to an unconditional `completed=1` redirect even though nothing had completed. Fixed by inspecting the returned `records` instead of relying on exceptions for control flow.

## Quota semantics change

Wiring `enqueue()`'s reservation into `create_run_manifest` made `active_jobs` a *persistent* reservation (held until a `WorkItem` reaches `SUCCEEDED` or exhausts retries into `FAILED`) instead of the prior model, where nothing tracked "active" work across requests at all. Three pre-existing specification-004 tests (`test_manual_correction_preserves_authority_flags_health_and_reaffirm_resets_baseline`, `test_ambiguity_case_uses_complete_logical_members_and_reuses_unchanged_membership`, `test_pair_split_and_merge_preserve_every_predecessor_and_successor`) each call `create_run_manifest`/`execute_and_publish_run` directly (bypassing the jobs completion path entirely, by design — they test domain correctness, not job-queue mechanics) three times per test, so their reservations were never released and the previous default limit of 2 was exceeded on the third call. `WORKSPACE_ACTIVE_JOB_LIMIT`'s default was raised from 2 to 10 (`config/settings.py`) — a deliberate, user-visible change (the workspace usage panel now reads "0 / 10 Active jobs"), not a side effect: 2 only ever made sense modeling "concurrent in-flight requests," which this quota never actually tracked before; 10 is a real anti-abuse bound for an anonymous workspace's total outstanding enqueued work, matching `WORKSPACE_BOOK_LIMIT`'s existing default.

## Verification results

| Check | Result |
|---|---|
| `tests/test_run_job_wiring.py` (new) | 4 passed — end-to-end claim-and-execute success + quota release; duplicate-manifest reuse without double reservation; forged cross-workspace `WorkItem` rejected before any financial read; transient-failure retry-then-succeed |
| `tests/test_reconciliation_runs.py` (pre-existing, 3 required a settings fix, 1 required a monkeypatch signature fix — no behavioral test logic changed) | 27 passed |
| `tests/test_jobs_persistence.py` (2 tests updated to use `enqueue()` so reserve/release stay paired) | 16 passed |
| `tests/test_run_fencing.py` | 3 passed |
| Full repository regression | 513 passed in 13.33 seconds |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| `git diff --check` (whitespace) | Passed |
| Live browser rehearsal (rebuilt `web`/`worker`, real `docker compose`) | Clicked "Run again" on the existing demo book through the actual view; page showed "Reconciliation completed"; workspace usage panel showed "0 / 10 Active jobs" both before and after, confirming reserve/release symmetry end-to-end, not just in tests |

## Scope boundary

Import validation (`OPS-T06`) and workspace cleanup (`OPS-T07`) do not yet call `enqueue()`/`claim_and_execute` — only `RECONCILIATION_RUN` is wired. The standalone `worker` management command still only writes a heartbeat; it does not yet poll `claim_and_execute` for any kind (that begins in `OPS-T08`, per the `tasks.md` correction made at the start of this task).
