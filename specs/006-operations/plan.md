# 006 Jobs, Operations, and Deployment — Implementation Plan

- **Status:** Draft
- **Specification:** [spec.md](./spec.md)
- **Target branch:** `codex/006-operations`
- **Last updated:** 8 September 2026

## Summary

Specifications 002–005 execute CSV validation and reconciliation runs synchronously inside the HTTP request and defer leased background work to this specification by name (`002-ingestion/plan.md`, `004-review-and-cases/plan.md`, `005-workbench/plan.md`). The high-level design already commits to the shape of that work: PostgreSQL-backed work items instead of a separate queue product, claim by short row lock, one fencing token per attempt, renewable leases, bounded retries (`docs/02-hld.md` §9). This plan implements exactly that design and nothing broader.

Add one new `jobs` app owning `WorkItem` and `JobAttempt` — the claim/lease/fence/retry mechanism — as a reusable layer with no reconciliation-specific knowledge. Move the two existing synchronous boundaries behind it without changing their proven contracts: `reconciliation.services.ReconciliationRunService.compute_run`/`publish_run` gain a fencing check at the point they already lock the run row; `ingestion.services.ArtifactIntakeService`'s parse/validate step is invoked from a claimed `IMPORT_VALIDATION` work item instead of inline in `import_preview`. Add a third kind, `WORKSPACE_CLEANUP`, that drains the `WorkspaceCleanupRequest` rows specification 001 already writes on revocation but nothing yet processes.

Replace the heartbeat-only `foundation.management.commands.worker` with a claim loop, extend `/health/ready` to separately report web/database/worker signals, extend `observability.logging.EVENT_FIELDS` with job/run/import identifiers and stage durations, introduce a `StorageAdapter` boundary behind `ingestion.artifacts.PrivateArtifactStore` with one object-storage implementation, and document the managed-PostgreSQL/object-storage/HTTPS/secrets deployment target plus one measured capacity run.

The domain and web contracts proven by specifications 002–005 do not change. This specification changes what invokes them and adds the operational floor underneath.

## Constitution check

| Principle | How the plan complies |
|---|---|
| Evidence is immutable | `WorkItem` is the only mutable pointer (state, lease, token); `JobAttempt` rows are append-only, one per claim, and are never edited after creation. |
| Identity and agreement differ | Not applicable to this specification; no comparison or pairing behavior changes. |
| Automatic matching may abstain | Unchanged; the engine boundary (`compute_run`) is invoked with the same frozen manifest, only from a claimed attempt instead of inline. |
| Results are explainable | `RunProgressStage`/`progress_counts` already record truthful stages (specification 005); this plan adds the attempt token and job identifiers to the same evidence rather than replacing it. |
| Reviewer authority is durable | Unchanged; decisions are frozen into the manifest exactly as today before enqueueing. |
| Runs publish atomically | Closes the gap directly: `execute_and_publish_run` currently transitions `FROZEN/FAILED → RUNNING` with an `.update()` that is not conditioned on the read lifecycle, so two concurrent callers can both proceed. Publication gains a fencing-token recheck inside the same locked transaction that already writes run facts. |
| Decimal/time semantics are explicit | Unchanged; no numeric or time contract is touched. |
| Anonymous access is isolated | `WorkItem`/`JobAttempt` carry direct `workspace` ownership like every other table; a worker resolves the target only through the frozen manifest's workspace, never a caller-supplied ID (OPS-017). |
| Domain core is framework-independent | `reconciliation/domain/jobs.py` adds pure `JobKind`, `JobState`, `LeaseToken`, `RetryDecision`, and `ClaimEligibility` values with no database or clock access; the `jobs` app adapts them at the boundary, matching `workspaces.py`/`workspaces` today. |
| Specifications precede behavior | Every task below maps to an `OPS` requirement or acceptance scenario. |
| Claims require evidence | Capacity and reliability claims cite the measurement in `specs/006-operations/evidence/`, not narrative. |
| Complexity earns its place | Considered Celery/RQ/Dramatiq and rejected them (see below): no broker is already deployed, `requirements/runtime.lock` pins no message-queue client, and PostgreSQL row locking with `SKIP LOCKED` satisfies every stated requirement without new infrastructure. |

## Affected architecture

| Module/component | Change | Requirement IDs |
|---|---|---|
| `jobs` (new app) | `WorkItem`, `JobAttempt` models; claim/renew/complete/fail/retry service; domain value objects | OPS-001–OPS-004, OPS-007, OPS-017 |
| `reconciliation.services.ReconciliationRunService` | `execute_and_publish_run` becomes claim-driven; `publish_run` verifies the caller's fencing token under its existing row lock before writing facts | OPS-001–OPS-006 |
| `reconciliation.models.ReconciliationRun` | Add `current_attempt_token` (nullable) so publication can compare it against the claim | OPS-003, OPS-004 |
| `ingestion.services.ArtifactIntakeService` / `foundation.views.import_preview` | Parse/validate step runs from a claimed `IMPORT_VALIDATION` attempt instead of inline in the request | OPS-001–OPS-004, OPS-007, OPS-008 |
| `ingestion.artifacts` | Extract `StorageAdapter` protocol; keep `PrivateArtifactStore` as the local implementation; add one object-storage adapter | OPS-010, OPS-013 |
| `workspaces.lifecycle` / new `workspaces.cleanup` | Process `WorkspaceCleanupRequest` rows via a `WORKSPACE_CLEANUP` work item: verify no live reference, delete rows/artifact bytes, set `processed_at` idempotently | OPS-009, OPS-015, OPS-016 |
| `workspaces.quotas` | `active_jobs` reservation (already modeled, unused) is reserved on enqueue and released on terminal state | OPS-001, OPS-017 |
| `foundation.management.commands.worker` | Replace the heartbeat-only loop with a claim loop dispatching by `JobKind`; keep the existing heartbeat file contract | OPS-003, OPS-014 |
| `foundation.views.readiness` (or a new route) | Separate web readiness, database reachability, and worker liveness/freshness | OPS-014 |
| `observability.logging` / `observability.middleware` | Extend `EVENT_FIELDS` with book/scope/run/import/job identifiers and stage duration; add a worker-side structured logger reusing the same salted-HMAC workspace reference | OPS-011 |
| `compose.yaml`, deployment docs | Managed PostgreSQL, private object storage, HTTPS ingress, environment secrets, migrations as a release step | OPS-010, OPS-013 |
| `specs/006-operations/evidence/` | Capacity measurement on a named workload/environment | OPS-012 |

## Domain contracts

### Job identity and lifecycle

`reconciliation/domain/jobs.py` adds:

- `JobKind`: `IMPORT_VALIDATION`, `RECONCILIATION_RUN`, `WORKSPACE_CLEANUP`.
- `JobState`: `READY`, `LEASED`, `SUCCEEDED`, `FAILED` (matches `docs/03-lld.md` §9's state machine exactly).
- `LeaseToken`: an opaque, unique, generated value; equality is the only operation the domain needs.
- `RetryDecision`: a pure function of `(attempt_count, max_attempts, failure_category)` returning either a backoff `available_at` offset or a terminal `FAILED` outcome. `failure_category` distinguishes transient (network/timeout/lock-wait) from permanent (validation, programming error) failures per OPS-007; the category comes from an explicit, closed set the caller supplies — the domain never inspects exception types.
- `ClaimEligibility`: pure evaluation of whether a `WorkItem` row is claimable now, given `state`, `available_at`, and `lease_until` against the current time. The persistence layer supplies the equivalent `WHERE` clause; the domain function exists so the eligibility rule is unit-tested once and not duplicated between the query and any manual inspection code.

No job type touches money, time comparison policy, or matching logic; those contracts remain exactly as specifications 003–004 defined them.

### Ownership validation before financial reads

A claimed attempt's first step, before `compute_run` touches any `RunInput`/`TransactionObservation` row, is confirming every resource ID in the frozen manifest (`scope_id`, dataset revision IDs, decision revision IDs) resolves under the manifest's own `workspace_id` — the same `owned_by()` filter every repository already applies, just invoked once up front instead of relying on each downstream query to fail closed individually. A manifest with a foreign or forged ID fails this check and transitions the attempt to `FAILED` without a single financial value having been read, satisfying OPS-017/OPS-A16 by construction rather than by trusting that every later query happens to filter correctly.

### Fencing at publication

`ReconciliationRunService.publish_run` already opens one locked transaction that reads `ReconciliationRun` with `select_for_update`. This plan adds one comparison inside that same lock: the run's `current_attempt_token` must equal the token the caller was issued at claim time. A mismatch (an expired lease that a newer attempt has since reclaimed) raises the existing `RunStateConflict` and writes nothing — the same typed failure the view already handles, so `foundation.views.reconciliation_run_start` needs no new exception branch. This is the minimal change that satisfies OPS-004 without altering `_persist_result`, `_persist_decision_health`, or `materialize_run_cases`.

## Data model and migrations

| Entity | Essential fields and constraints |
|---|---|
| `work_item` | workspace, kind, state, target reference, available_at, lease_until, current_token, attempt_count, max_attempts, created_at, updated_at; check constraint requiring exactly the one target FK valid for `kind` (`import_attempt` for `IMPORT_VALIDATION`, `reconciliation_run` for `RECONCILIATION_RUN`, `cleanup_request` for `WORKSPACE_CLEANUP`) — the same exact-shape pattern `ReconciliationRun`/`RunPair` already use, not a generic content-type FK |
| `job_attempt` | work_item, token (unique), leased_at, lease_until, completed_at, outcome (`SUCCEEDED`/`FAILED`/`EXPIRED`), failure_category; immutable after creation like every `Run*` evidence table |

Explicit relational target columns are chosen over a generic `(content_type, object_id)` pair so that ownership joins stay direct and the workspace-isolation query pattern used everywhere else (`OwnedQuerySet.owned_by`) applies unchanged — a generic FK would need its own isolation proof per target type.

`reconciliation_run` gains `current_attempt_token` (nullable `CharField`, cleared on completion/failure). No other existing table changes shape; `WorkspaceCleanupRequest.processed_at` already exists and is simply written by the new cleanup path instead of staying permanently null.

Claim query: `WorkItem.objects.select_for_update(skip_locked=True).filter(Q(state=READY, available_at__lte=now) | Q(state=LEASED, lease_until__lt=now)).order_by("available_at")[:batch_size]`, executed inside one short transaction per batch. `skip_locked=True` is what makes two worker processes safe without an external coordinator — a second worker's claim query simply skips rows the first has already locked instead of blocking behind them.

Migrations are additive only: two new tables plus one nullable column with no backfill required (existing runs have no in-flight attempt to reconcile). Rollback drops the new tables and column; no existing table's meaning changes.

## Web and application contracts

No public route changes shape. `POST /books/{id}/runs` (`run-start`) and `POST /books/{id}/sources/{side}/upload` keep their existing redirect-after-post behavior for the local single-process Compose deployment: the request still calls `create_run_manifest`/enqueue, then waits on the same-process worker call synchronously so the demo and browser tests from specification 005 do not regress. What changes underneath is that the call now goes through `jobs.services.claim_and_execute(work_item_id)` instead of directly into `execute_and_publish_run`, so the identical code path runs whether the caller is the request thread (local Compose) or a separate `worker` process (deployed target). This keeps specification 005's required no-JavaScript, synchronous-feeling submission flow intact while making the underlying execution path the one that ships to production.

`GET /health/ready` gains `database` (existing) and two additional fields, `worker_heartbeat_age_seconds` and `worker_status`, computed from the most recent `job_attempt` heartbeat rather than the flat file the stub worker writes today — the file-based heartbeat becomes the local-only liveness signal `docker compose`'s healthcheck already polls; the database-backed one is what a deployed health check without shared-filesystem access can read (OPS-014).

## Background processing

This is the specification's primary subject.

- **Job identity:** one `WorkItem` per unit of work; `IMPORT_VALIDATION` and `RECONCILIATION_RUN` items are created inside the same transaction that already exists (`import_preview`'s attempt creation, `create_run_manifest`'s manifest freeze) — satisfies OPS-001/OPS-002 by construction rather than adding a second write path.
- **Idempotency:** `RECONCILIATION_RUN` reuses the existing unique `(scope, manifest_hash)` constraint — a duplicate enqueue for an unchanged manifest returns the existing run's `WorkItem`, matching OPS-A04. `IMPORT_VALIDATION` reuses the existing physical/semantic hash deduplication from specification 002.
- **Retry:** transient failures (`OperationalError`, lock timeout) re-ready the item with exponential backoff up to `max_attempts` (initial value 3, documented in evidence); permanent failures (validation errors, programming errors) go straight to `FAILED` and stay inspectable — `ReconciliationRun.failure_code` and `IngestionAttempt` state already carry this, unchanged.
- **Lease/fencing:** lease duration is set from the measured p95 run duration (specification 005/003 evidence) plus margin, documented in `specs/006-operations/evidence/`, not guessed.
- **Progress:** unchanged — `RunProgressStage`/`progress_counts` already report real stages; the worker writes to the same fields it does today, just from a claimed attempt instead of the request thread.
- **Publication:** unchanged transaction shape, plus the token recheck described above.
- **Cleanup job:** `WORKSPACE_CLEANUP` claims a `WorkspaceCleanupRequest`, re-verifies under lock that the workspace is still `REVOKED`/`DELETED` (a workspace cannot be reactivated, so this recheck is defensive, not a race), deletes owned rows workspace-first (children before the workspace row, respecting `on_delete` already declared), deletes artifact bytes only after the database transaction that removed their referencing rows has committed, and sets `processed_at`. Re-delivery of an already-processed request is a no-op (`processed_at` already set) — satisfies OPS-015's idempotency and OPS-A07's re-delivery scenario directly. Deleting the live-store row/bytes is the entire scope of this job: the chosen object-storage and PostgreSQL providers separately retain their own backup snapshots on their own schedule, which this job neither controls nor accelerates. Deployment documentation states both periods — the seven-day live `Workspace.expires_at` window this job enforces, and the provider's longer backup-retention window — rather than implying deletion here erases backups, satisfying OPS-016/OPS-A15.

Not applicable: no cross-service network calls, no external message broker, no multi-region coordination.

## UI behavior

No new page. The workbench's existing "waiting for a rerun" / "latest result is current" / failed-run states (specification 005) already express truthful progress and keep the last successful result selectable; this specification does not add a percentage bar or new loading state, per OPS-008's prohibition on fabricated percentages and specification 005's `UX-016`. The only visible addition is that a run started while the worker is briefly between polling cycles is still `QUEUED` for a bounded moment — the existing `RunProgressStage.QUEUED` label already covers this and needs no new template.

## Verification plan

| Requirement | Verification layer | Planned evidence |
|---|---|---|
| OPS-001, OPS-002, OPS-A09 | Integration | Manifest freeze and work-item creation occur in one transaction; a rollback of either leaves no runnable orphan and a retry resolves to exactly one logical run |
| OPS-003, OPS-004, OPS-A01 | PostgreSQL concurrency | Two processes claim concurrently; only one gets a live token; an expired-lease attempt cannot publish after reclaim |
| OPS-005, OPS-A03 | Integration | Forced failure between compute and publish leaves no partial `run_pair`/`run_unpaired`/case rows and `scope.current_run` unchanged |
| OPS-006, OPS-A02, OPS-A10 | Integration | Decision/data change mid-computation, or between enqueue and worker start, completes as `STALE` against the frozen manifest; a coalesced rerun becomes `CURRENT` |
| OPS-007, OPS-A11 | Unit + integration | Transient failure retries to the documented limit then reports `FAILED`; a permanent validation failure reaches `FAILED` on its first attempt without retrying; both remain separately inspectable and the last successful run stays selectable throughout |
| OPS-008, OPS-A12 | Browser (reuses specification 005 evidence) | Only persisted stage names and measured counts reach the UI at every polled state; no percentage is emitted without a measured denominator |
| OPS-009, OPS-015, OPS-A05, OPS-A07 | Integration + adversarial | Expired/deleted workspace rejects new work and existing URLs; repeated cleanup delivery is a no-op; referenced artifacts survive until their owning rows are gone |
| OPS-010, OPS-013, OPS-A13 | Deployment rehearsal | `docker compose`-equivalent against the managed target boots with HTTPS, secure/HttpOnly/SameSite cookies, private artifact access, environment secrets, and the object-storage adapter; migrations run as a separate release step; database readiness and worker freshness are independently verified |
| OPS-011, OPS-A14 | Log inspection | Sampled job/request logs against representative session and financial fixtures contain only `EVENT_FIELDS`-allowlisted values; no raw row or secret appears |
| OPS-012, OPS-A06 | Measurement | Documented workload/environment; durations recorded and reported honestly even if a target is missed |
| OPS-014, OPS-A08 | Integration | `/health/ready` reports web/database/worker signals independently; a stale worker heartbeat degrades only the worker signal while web/database stay healthy |
| OPS-A04 | Integration | Same manifest enqueued twice yields one logical run and two distinguishable attempts |
| OPS-016, OPS-A15 | Deployment rehearsal + documentation | Deployed retention text states both the seven-day live workspace expiry and the storage provider's longer backup retention window; access ends at live expiry without claiming immediate backup erasure |
| OPS-017, OPS-A16 | Adversarial integration | A manifest containing another workspace's resource IDs is rejected before any financial row is read and before publication; owning workspaces are unchanged |

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Claim query contention under `SKIP LOCKED` at low row counts | Wasted polling, not incorrectness | Bounded batch size and interval; documented, not tuned blindly |
| Synchronous in-request execution (kept for the local Compose demo) masks a broker-shaped bug that only appears with a separate worker process | Deployed behavior diverges from locally-verified behavior | Both paths call the identical `jobs.services.claim_and_execute`; only the caller (request thread vs. `worker` command) differs, so the concurrency tests exercise the real deployed path |
| Object-storage adapter introduced without exercising every ingestion edge case against it | Deployment-only failure specification 002's local tests would not catch | Reuse specification 002's `PrivateArtifactStore` contract tests against both adapters, not a second bespoke suite |
| Cleanup deletes an artifact still referenced by a row created after the cleanup request but before the worker claims it | Data loss for a resource the workspace still legitimately owns | Cleanup re-locks the workspace and re-verifies `REVOKED`/`DELETED` state and zero remaining live references immediately before each delete, inside the same transaction as the delete |
| Retry storm from a permanently misconfigured dependency (e.g., unreachable object storage) | Queue fills with doomed retries | Bounded `max_attempts` per item; failure category distinguishes transient from permanent so a misconfiguration fails fast instead of retrying |
| Adding Celery/Redis "to be safe" | New infrastructure, new failure modes, contradicts constitution XII and the already-stated HLD decision | Rejected explicitly below; PostgreSQL already satisfies every stated requirement |

## Rejected implementation approaches

| Approach | Why rejected |
|---|---|
| Celery/RQ/Dramatiq with Redis as broker | No broker is deployed today; `requirements/runtime.lock` pins none; PostgreSQL row locking already satisfies leasing, fencing, and retry without new infrastructure — constitution XII requires a stated problem the alternative solves that PostgreSQL does not, and none exists here. |
| Generic `(content_type, object_id)` polymorphic work-item target | Breaks the direct-ownership join pattern every other table uses and needs its own isolation proof; explicit per-kind FKs with an exact-shape constraint match the codebase's existing style. |
| `SELECT ... FOR UPDATE` without `SKIP LOCKED` | Serializes claim attempts across worker processes instead of letting them skip locked rows, defeating the purpose of multiple workers. |
| Advisory locks instead of row locks for claiming | Advisory locks are session-scoped and invisible to `EXPLAIN`/introspection; row locks on a real table keep the claim visible in ordinary queries and match every other concurrency-sensitive path in this codebase (`select_for_update` on `ReconciliationBook`, `Workspace`). |
| Cron-only cleanup with no work-item row | Would need its own state machine for idempotency and retries, duplicating what `WorkItem` already provides; reusing one mechanism for all three job kinds keeps the claim/lease/retry code paths single. |
| Percentage progress bar computed from elapsed time | Explicitly prohibited by OPS-008 and `UX-016`; elapsed time is not proof of remaining work. |
| Storing the fencing token only on `JobAttempt`, not also on `ReconciliationRun` | Publication already locks and updates `ReconciliationRun` in one transaction; checking the token there costs one column and one comparison, versus a second cross-table lock if the token lived only on the attempt. |

## Delivery and rollback

Additive migrations (two tables, one nullable column) ship first and are inert until the `jobs` app is wired into `import_preview` and `reconciliation_run_start`. Each of the three job kinds is wired in its own commit: `RECONCILIATION_RUN` first (highest-value fencing gap, most existing test coverage to reuse), then `IMPORT_VALIDATION`, then `WORKSPACE_CLEANUP`. The synchronous call sites remain functionally reachable as a fallback path (same-process claim-and-execute) until the deployed worker rehearsal passes, so a revert of any single commit restores the prior synchronous behavior without a data migration.

Deployment configuration (managed PostgreSQL, object storage, HTTPS, secrets, migrations-as-release-step) ships last, after every job kind is verified against local Compose, since it has no code dependency on the others and rehearsing it early would only add risk while the job mechanism is still changing.

**Deployment target (resolved, per spec.md's "Provider selection is a plan-level decision"):** a managed container platform running the versioned web and worker images against managed PostgreSQL (matching ADR-001's process split with no new orchestration layer — rejecting Kubernetes stays consistent with the spec's stated out-of-scope), paired with an S3-compatible object-storage bucket for `StorageAdapter`'s production implementation. S3-compatible was chosen over a vendor-specific SDK so the adapter speaks one protocol regardless of which bucket provider ends up hosting it, and over self-hosted MinIO because this deployment has no existing compute to host it on and the spec's target is a small, bounded artifact volume (25 MiB/file, quota-limited per workspace) that does not justify operating storage infrastructure. The exact bucket provider is an environment-variable-configured endpoint/credential pair, not a code dependency, so naming it here fixes the architecture without blocking on account provisioning.

Every implementation task produces one commit containing code, focused tests, and an evidence record, matching specifications 001–005. The feature is not verified until the full suite, the PostgreSQL concurrency probes (OPS-A01, OPS-A03, OPS-A04, OPS-A09, OPS-A10), the adversarial isolation matrix (OPS-017, OPS-A16), the expiry/cleanup matrix (OPS-A05, OPS-A07, OPS-A15), the deployment rehearsal (OPS-A08, OPS-A13, OPS-A14), and the capacity measurement (OPS-A06) all pass at one commit, per the release gate in `docs/06-verification-and-delivery.md` §11.

## Open decisions

- **Lease duration and retry limit values.** The plan fixes the mechanism; the numbers (initial lease duration, backoff schedule, `max_attempts`) are measured from specification 003/005 evidence during task 1 and recorded in `specs/006-operations/evidence/`, not guessed here. Tasks that depend on the exact value (retry backoff tests) cannot start until it is recorded.

This is an implementation-time parameter, not an architectural question — the deployment provider is already named above per spec.md's resolved-decision requirement — so this plan is ready for task breakdown.
