# OPS-T08 Verification Evidence

- **Task:** Extend health reporting and structured observability
- **Requirements:** `OPS-003`, `OPS-011`, `OPS-014`
- **Acceptance scenarios:** `OPS-A08`, `OPS-A13`, `OPS-A14`
- **Date:** 8 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence

## The worker command actually claims and executes work now

`foundation.management.commands.worker`'s loop, previously a heartbeat-only stub, now calls `jobs.services.claim_and_execute` for all three `JobKind`s every cycle (`RECONCILIATION_RUN`, `IMPORT_VALIDATION`, `WORKSPACE_CLEANUP`), each with its own lease/retry/backoff settings, before writing the heartbeat. This is the piece specs `OPS-T04`/`OPS-T06`/`OPS-T07` deliberately left undone: those tasks wired the *synchronous* view-driven path (claim a specific `work_item_id` inline in the request); workspace cleanup, and any reclaimed run/import whose original attempt's lease expired without the requesting process retrying it, had nothing to process them until this task.

## A real batch-processing bug fixed before it shipped

`claim_and_execute`'s per-item loop re-raised on a permanent failure, abandoning the rest of a claimed batch — harmless for the `work_item_id`-scoped single-item calls `OPS-T04`/`OPS-T06` use, but wrong for this task's `batch_size`-based polling loop: one bad item would silently strand every other already-leased item in the same batch until their leases separately expired. Fixed by having `claim_and_execute` log and record every item's outcome without re-raising, so one failure never stops the rest of a poll cycle. Verified no existing test relied on the old re-raise behavior (grepped every `pytest.raises` near `claim_and_execute` across the new job-wiring test files — all of them call the executor functions directly, not through `claim_and_execute`) before making the change; full regression suite stayed green throughout.

## Implemented contracts

- `jobs.models.WorkerHeartbeat`: one row per `worker_id`, upserted every poll cycle — the database-backed liveness signal a web process can read without sharing a filesystem with the worker (the existing `WORKER_HEARTBEAT_FILE` write is kept unchanged, since `docker compose`'s local healthcheck still polls it).
- `GET /health/ready` now reports `worker_status` (`healthy`/`stale`/`unknown`) and `worker_heartbeat_age_seconds`, computed from the most recent `WorkerHeartbeat` row and `settings.JOBS_WORKER_STALE_SECONDS` (30s default), alongside the unchanged `status`/`database` fields — independently of database readiness, per `OPS-014`/`OPS-A08`.
- `observability.logging.EVENT_FIELDS` gained `book_id`, `scope_id`, `run_id`, `import_id`, `job_id`, `stage`. `hash_workspace_ref()` was extracted from `observability.middleware.workspace_reference` into `observability.logging` (byte-identical output, verified by the untouched existing `test_observability.py` request-log tests) so job-side logging can reuse the same salted-HMAC reference without duplicating the salt.
- `jobs.services.claim_and_execute` now emits one `job_execution_completed` structured event per claimed item to the `reconciliation.jobs.events` logger (wired to the same `privacy_safe_json` console handler as request logs): `stage` (the `JobKind`), `job_id` (the `WorkItem` id), `run_id`/`import_id` (from the `WorkItem`'s own target FK, when applicable), the hashed `workspace_ref`, `duration_ms`, and `failure_category`. Only allowlisted fields survive `safe_event`; raw workspace UUIDs, financial rows, and secrets cannot reach the log by construction, not by care.

## Verification results

| Check | Result |
|---|---|
| `tests/test_worker_command.py` (new) | 3 passed: `worker --once` claims and completes a pending run; claims and purges a pending workspace cleanup; writes both the file and database-backed heartbeat |
| `tests/test_foundation_health.py` (2 pre-existing tests updated for the new response shape and worker-id parameter; 2 new) | 4 passed: unknown worker with no heartbeat yet; healthy worker for a fresh heartbeat; **a stale worker is distinguished from a healthy web/database** (`OPS-A08` directly); the `--once` heartbeat write covers both file and DB |
| `tests/test_observability.py` (1 pre-existing allowlist test updated for the new fields; 1 new) | 9 passed: the new `job_execution_completed` log carries `stage`/`job_id`/`duration_ms` and a hashed `workspace_ref`, with the raw workspace UUID absent from the serialized log entirely |
| Full repository regression | 537 passed in 18.51 seconds |
| `python manage.py makemigrations --check --dry-run` | No changes detected (the `WorkerHeartbeat` migration was generated and applied earlier in this task) |
| `git diff --check` (whitespace) | Passed |
| Live rehearsal (rebuilt `web`/`worker`, real `docker compose`) | `/health/ready` reported `"worker_status": "healthy"` from the actual standalone worker container's heartbeat (not a test). Created a disposable workspace and deleted it via the real HTTP flow (`curl` with a fresh cookie jar, `/workspace/delete/confirm`); the workspace row was **not** removed synchronously by the request — the standalone `worker` container's own logs show it independently claiming and purging: `WORKSPACE_CLEANUP: claimed 1, succeeded 1` followed by the structured JSON event line, `workspace_ref` hashed, raw UUID absent |

## Scope boundary

The deployment target's actual managed-PostgreSQL/object-storage provisioning, HTTPS/secrets configuration, and the measured capacity run are `OPS-T09`. Final cross-cutting acceptance (`OPS-A01`–`OPS-A16` together, one commit) is `OPS-T10`.
