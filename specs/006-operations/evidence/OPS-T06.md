# OPS-T06 Verification Evidence

- **Task:** Route import validation through claim-and-execute
- **Requirements:** `OPS-001`–`OPS-004`, `OPS-007`, `OPS-008`, `OPS-017`
- **Acceptance scenarios:** `OPS-A04`, `OPS-A09`, `OPS-A11`, `OPS-A12`, `OPS-A16`
- **Date:** 8 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence

## A structural gap found before implementing

`tasks.md`'s original wording ("`import_preview` creates its `IngestionAttempt`...") was wrong: `import_preview` is the read-only GET view that renders an already-computed attempt. The actual work — `PreviewService.preview()` — ran entirely inside `source_upload`'s POST handler, creating the finished (`READY`/`REJECTED`) `IngestionAttempt` in one call. Unlike a `ReconciliationRun`, there was no frozen row for a `WorkItem` to point at before parsing happened.

`IngestionAttempt.state`'s `RECEIVED` and `PARSING` choices already existed in the model — unused by the synchronous `preview()` path, which created attempts directly in their terminal state. That is a strong signal the schema was built for exactly this split. `PreviewService.preview()` is now `create_shell()` (creates the `RECEIVED` attempt — `physical_hash` is already known from the artifact, everything else waits) followed by `complete()` (parses, then transitions to `READY`/`REJECTED`). `preview()` itself survives as a synchronous convenience (`create_shell` + `complete` in one call) so every existing caller — including `tests/test_full_snapshot_activation.py`'s 32 call sites — needed no change.

## Implemented contracts

- `WorkspaceIngestionRepository.complete_attempt()`: a new repository method that updates an existing `RECEIVED` attempt in place (state, semantic hash, counts, validation) rather than `create_attempt`'s full-row creation.
- `ingestion.preview.execute_claimed_import(work_item, token)`: the `JobKind.IMPORT_VALIDATION` executor for `jobs.services.claim_and_execute`, mirroring `execute_claimed_run` exactly — it derives `workspace_id` only from `work_item.workspace_id`, so a forged/foreign target fails at `WorkspaceIngestionRepository.get_attempt()` before any artifact byte is read.
- Fencing: `PreviewService.complete(..., attempt_token=None)` gained the same token-comparison pattern as `publish_run`, but against `jobs.WorkItem.current_token` directly (locked via `select_for_update`) rather than a duplicated field on `IngestionAttempt` — imports have no equivalent of a run's expensive, resumable computation requiring its own frozen-row token; the `WorkItem` lock alone is sufficient. A mismatch raises `ImportStateConflict`, which `execute_claimed_import` translates to `TransientJobFailure` for `claim_and_execute`'s retry path — exactly mirroring `RunStateConflict`'s treatment in `OPS-T04`. This closes a real (if lower-probability, since re-parsing identical bytes is deterministic) risk: `RawRow` has a `(attempt, row_number)` unique constraint, so a fenced attempt completing late would previously have crashed with `IntegrityError` instead of being cleanly rejected.
- `source_upload` now: uploads bytes (unchanged) → `create_shell()` → `jobs.services.enqueue()` (reserves `active_jobs`) → `claim_and_execute(..., work_item_id=...)` with `execute_claimed_import` → redirects to the same `import-preview` URL as before. A `claim_and_execute` exception is logged and swallowed (matching `reconciliation_run_start`'s pattern) rather than surfaced as a 500 — the shell attempt persists in `RECEIVED` state either way, and `import_preview`'s existing render path handles a not-yet-completed attempt without special-casing (empty row list, `stale` comparison short-circuits false).
- New settings: `JOBS_IMPORT_MAX_ATTEMPTS` (3), `JOBS_IMPORT_LEASE_SECONDS` (60), `JOBS_IMPORT_BACKOFF_SECONDS` (5) — independent of the `JOBS_RUN_*` values, since import parsing and reconciliation computation have different expected durations.

## Verification results

| Check | Result |
|---|---|
| `tests/test_import_job_wiring.py` (new) | 4 passed: end-to-end claim-and-execute success + quota release; forged cross-workspace `WorkItem` rejected before reading artifact bytes; fenced attempt cannot complete after reclaim, the reclaiming attempt can; transient-failure retry-then-succeed |
| `tests/test_ingestion_preview.py` (one test's assertions updated: the shell attempt now correctly survives a downstream raw-row persistence failure instead of the whole thing vanishing — the new, intentional two-phase semantics, not a regression) | 15 passed |
| `tests/test_ingestion_workflow.py`, `tests/test_full_snapshot_activation.py`, `tests/test_ingestion_persistence.py`, `tests/test_ingestion_downloads.py`, `tests/test_artifact_intake.py` (unmodified) | 83 passed |
| Full repository regression | 524 passed in 18.93 seconds |
| `python manage.py makemigrations --check --dry-run` | No changes detected (no model changes this task) |
| `git diff --check` (whitespace) | Passed |
| Live browser rehearsal (rebuilt `web`/`worker`, real `docker compose`) | Uploaded a fresh CSV through the actual left-source upload form; preview page showed "left source · Ready", "3 source rows · 0 blocking errors" — identical evidence to the pre-refactor synchronous path; workspace usage panel read "0 / 10 Active jobs" both before and after |

## Scope boundary

Workspace cleanup (`OPS-T07`) is the third and final job kind; it does not yet exist. The standalone `worker` management command still only writes a heartbeat — `OPS-T08` wires its polling loop to call `claim_and_execute` for every registered kind.
