# OPS-T10 Verification Evidence

> **Storage target superseded:** Specification 007 removes the external storage adapter. The jobs, fencing, cleanup, health, and capacity evidence below remains applicable.

- **Task:** Close jobs, operations, and deployment acceptance
- **Requirements:** `OPS-001`–`OPS-017`
- **Acceptance scenarios:** `OPS-A01`–`OPS-A16`
- **Date:** 8 September 2026
- **Result:** Pass, with `OPS-T09`'s already-disclosed reconciliation-capacity miss (~11.01s vs. 10s target) carried forward unresolved

## Acceptance matrix

| Scenario | Evidence | Result |
|---|---|---|
| OPS-A01 (expired lease cannot publish) | `tests/test_run_fencing.py::test_a_stale_token_cannot_publish_after_a_newer_attempt_reclaims_the_run` | Pass |
| OPS-A02 (correction during computation coalesces to current replacement) | `tests/test_reconciliation_runs.py::test_manifest_maps_active_authority_and_publishes_complete_immutable_facts`, `test_pair_case_reuses_logical_identity_across_corrected_observations` | Pass |
| OPS-A03 (publication failure marks nothing completed, pointer unchanged) | `tests/test_reconciliation_runs.py::test_publication_failure_rolls_back_every_fact_and_marks_failed`, `test_health_projection_rolls_back_with_failed_publication` | Pass |
| OPS-A04 (same manifest twice reuses one logical run; retries stay separate attempts) | `tests/test_reconciliation_runs.py::test_manifest_is_idempotent_and_foreign_workspace_cannot_discover_run`, `tests/test_run_job_wiring.py::test_repeated_manifest_freeze_reuses_the_work_item_without_double_reserving` | Pass |
| OPS-A05 (workspace expiry blocks old URLs and jobs) | `tests/test_artifact_intake.py::test_revoked_workspace_cannot_retain_staged_bytes`, `tests/test_workspace_cleanup.py::test_purge_refuses_a_workspace_that_is_still_active` | Pass |
| OPS-A06 (documented capacity fixture records durations even on a miss) | `specs/006-operations/evidence/OPS-T09.md`, `OPS-T09-reconciliation-capacity.json`, `OPS-T09-ingestion-capacity.json` | Pass (target itself missed, honestly recorded) |
| OPS-A07 (repeated cleanup delivery stays revoked, no premature deletion) | `tests/test_workspace_cleanup.py::test_redelivering_a_completed_cleanup_is_a_no_op`, `test_purge_leaves_other_workspaces_completely_untouched` | Pass |
| OPS-A08 (healthy web, stale worker heartbeat, distinguished) | `tests/test_foundation_health.py::test_readiness_distinguishes_a_stale_worker_from_a_healthy_web_and_database` | Pass |
| OPS-A09 (rollback/enqueue failure leaves no runnable orphan; retry resolves to exactly one run) | `create_run_manifest`'s single `transaction.atomic()` block (enqueue only after commit, `OPS-002`) plus `tests/test_run_job_wiring.py::test_repeated_manifest_freeze_reuses_the_work_item_without_double_reserving` | Pass |
| OPS-A10 (queued run outlives later policy/mapping/dataset changes; uses frozen manifest, publishes historical/stale once stale) | `tests/test_reconciliation_runs.py::test_manifest_maps_active_authority_and_publishes_complete_immutable_facts`, `test_ambiguity_case_uses_complete_logical_members_and_reuses_unchanged_membership` | Pass |
| OPS-A11 (transient retries to the limit, permanent failure, terminal state, last success stays available) | `tests/test_jobs_domain.py::test_permanent_failure_terminates_on_first_attempt`, `tests/test_jobs_persistence.py::test_mark_failed_terminal_outcome_leaves_the_item_failed`, `tests/test_run_job_wiring.py::test_claim_and_execute_retries_a_transient_executor_failure`, `tests/test_reconciliation_runs.py::test_workbench_keeps_current_result_during_running_and_failed_rerun` | Pass |
| OPS-A12 (only persisted stage names and measured counts reach the UI) | `tests/test_observability.py::test_job_execution_log_carries_stage_and_job_id_without_raw_workspace_id`, `tests/test_reconciliation_engine.py::test_global_assignment_stage_is_preserved_by_orchestration` | Pass |
| OPS-A13 (HTTPS, secure cookies, private artifacts, secrets, migrations, DB readiness, worker freshness independently verified) | `tests/test_workspace_sessions.py -k production` (2 tests), `tests/test_artifact_intake.py::test_configured_artifact_store_selects_s3_when_configured`, `docs/07-deployment.md` §3–4, live `/health/ready` on the clean-boot stack below | Pass |
| OPS-A14 (logs/traces/metrics keep correlation and stage metadata, drop raw rows and secrets) | `tests/test_observability.py` (all 6 tests) | Pass |
| OPS-A15 (live 7-day expiry disclosed separately from longer backup retention) | `docs/07-deployment.md` §6 (retention disclosure text) | Pass (documentation requirement, no runtime assertion) |
| OPS-A16 (forged cross-workspace manifest fails before reading financial data; owning workspaces unchanged) | `tests/test_run_job_wiring.py::test_a_work_item_pointed_at_another_workspaces_run_fails_before_any_financial_read`, `tests/test_import_job_wiring.py::test_a_work_item_pointed_at_another_workspaces_attempt_fails_before_reading_bytes`, `tests/test_workspace_cleanup.py::test_purge_leaves_other_workspaces_completely_untouched` | Pass |

## New in this task

`tests/test_worker_command.py::test_worker_once_drains_a_run_an_import_and_a_cleanup_together` — a capstone integration test proving all three `JobKind`s coexist correctly inside one `worker --once` poll cycle: a reconciliation run and an import validation both complete for two different workspaces while a third, unrelated workspace's cleanup purges concurrently in the same cycle, each claim only touching its own workspace's rows. This is new coverage — no prior task exercised more than one job kind per worker invocation.

## Full verification

| Check | Result |
|---|---|
| `tests/test_worker_command.py` (4 tests, incl. the new capstone) | 4 passed |
| Full repository regression | **540 passed** |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| `tests/test_domain_boundary.py`, `tests/test_architecture_constraints.py` | 4 passed |
| `git diff --check` (whitespace) | Passed |
| PostgreSQL concurrency probe | `tests/test_jobs_persistence.py::test_claim_batch_never_claims_the_same_row_twice_concurrently` — two real threads/connections racing `SELECT ... FOR UPDATE SKIP LOCKED`, exactly one claim wins |
| Adversarial cross-workspace/ownership matrix | `OPS-A16` row above — both forgeable kinds (run, import) plus cleanup's cross-workspace isolation test |
| Expiry/cleanup matrix | `OPS-A05`, `OPS-A07` rows above |
| Deployment rehearsal | `docs/07-deployment.md`; no live cloud account in this environment, so this is configuration/documentation, not an actual cloud deploy (already disclosed in `OPS-T09.md`) |
| Capacity measurement | `OPS-T09.md` — one target missed by ~10%, disclosed, not re-measured here |

## Clean Compose startup

Run as an isolated second Compose project (`-p recon-clean-check`, port-overridden via a temporary `compose.clean-check.yaml` using `!override`) rather than `docker compose down -v` on the stack already carrying this session's demo data — that would have destroyed a running demo unrelated to this check. `docker compose -p recon-clean-check -f compose.yaml -f compose.clean-check.yaml up --build -d` against brand-new, empty `postgres-data`/`artifact-data` volumes:

- `db`, `web`, `worker` all built and reached Compose `healthy` status (`web`'s healthcheck hits `/health/ready`; `worker`'s checks a fresh heartbeat file).
- `web`'s boot command (`migrate --noinput && runserver`) applied every migration cleanly against the empty database — no manual intervention.
- `GET /health/ready` on the fresh stack returned `{"status": "ready", "database": "ready", "worker_status": "healthy", "worker_heartbeat_age_seconds": 3.192}` — all three independent signals green from a cold start.
- Torn down with `docker compose -p recon-clean-check down -v` (only this isolated project's containers/volumes/network) and the override file deleted; the original `reconciliation-workbench` stack and its demo data were never stopped or touched, confirmed by `docker compose ps` before and after.

## Scope boundary

No live cloud account exists in this environment, so `OPS-A13`'s deployment-target checks and `OPS-A06`'s capacity numbers are the closest available verification (subprocess-level settings checks and this machine's own Compose PostgreSQL), not a rehearsal against the actual resolved managed-platform/S3-compatible target named in `docs/07-deployment.md`. The reconciliation capacity target miss recorded in `OPS-T09.md` remains open and is not resolved by this task — closing it is a profiling/tuning exercise, not an architectural change, and is out of scope for spec closure per this task's own evidence template.
