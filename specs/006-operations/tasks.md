# 006 Jobs, Operations, and Deployment — Tasks

- **Status:** Draft
- **Specification:** [spec.md](./spec.md)
- **Plan:** [plan.md](./plan.md)

## Task conventions

- `[ ]` pending, `[~]` in progress, `[x]` verified, `[!]` blocked.
- Each task includes implementation, verification, and evidence in one commit.
- Task order establishes the pure claim/lease/retry mechanism before any caller depends on it, the highest-value fencing gap (reconciliation runs) before the second caller (imports) reuses the same mechanism, workspace cleanup after both callers exist so it has real cross-references to prove it does not delete prematurely, and operability/deployment last since nothing else depends on it.

## Phase 1: job domain and persistence contracts

- [x] **OPS-T01 — Define pure job domain contracts** (`OPS-003`, `OPS-007`, `OPS-017`)
  - Change: `reconciliation/domain/jobs.py` — `JobKind` (`IMPORT_VALIDATION`, `RECONCILIATION_RUN`, `WORKSPACE_CLEANUP`), `JobState` (`READY`, `LEASED`, `SUCCEEDED`, `FAILED`), `LeaseToken`, `RetryDecision` (pure function of attempt count, max attempts, and an explicit transient/permanent failure category), and `ClaimEligibility` (pure evaluation of a work item's claimability given state/available_at/lease_until and the current time).
  - Verify: every `RetryDecision` boundary (`attempt_count == max_attempts`, transient vs. permanent category), every `ClaimEligibility` boundary (lease exactly expired, exactly not yet available), and a blocked-import test proving the module performs no database, HTTP, file, clock, or network access.
  - Evidence: domain test results and the retry/eligibility boundary matrix.

- [x] **OPS-T02 — Persist `WorkItem`/`JobAttempt` and the claim query** (`OPS-001`, `OPS-002`, `OPS-003`, `OPS-017`; `OPS-A04`, `OPS-A09`)
  - Change: new `jobs` app; `WorkItem` (workspace, kind, state, one exact-shape target FK per kind, available_at, lease_until, current_token, attempt_count, max_attempts) and `JobAttempt` (work_item, token, leased_at, lease_until, completed_at, outcome, failure_category, immutable after creation); the `select_for_update(skip_locked=True)` claim query; `owned_by()` querysets matching every other table.
  - Verify: exact-shape check constraint rejects a row with zero or two target FKs set for its kind; two concurrent claim transactions against the same ready rows never claim the same row (`skip_locked` proof); a rollback of manifest-freeze-plus-enqueue leaves no work item, and a retry after a successful freeze reuses the same logical run rather than creating a second one.
  - Evidence: migration/constraint inventory and concurrent-claim test result.

## Phase 2: reconciliation-run fencing

- [x] **OPS-T03 — Add the run fencing token and verify it at publication** (`OPS-003`, `OPS-004`, `OPS-005`, `OPS-006`; `OPS-A01`, `OPS-A02`, `OPS-A03`, `OPS-A10`)
  - Change: `reconciliation_run.current_attempt_token` (nullable); `publish_run` compares it against the claiming attempt's token inside the existing `select_for_update` transaction and raises the existing `RunStateConflict` on mismatch without writing any fact.
  - Verify: an attempt whose lease expired and was reclaimed by a second attempt cannot publish once the second attempt completes; a forced failure between `compute_run` and `publish_run` leaves no partial `run_pair`/`run_unpaired`/case row and `scope.current_run` unchanged; a decision or dataset change between enqueue and worker start, or during computation, publishes as `STALE` and does not advance the current pointer, while a subsequent coalesced rerun does.
  - Evidence: PostgreSQL concurrency probe (reclaim-then-publish), forced-failure rollback snapshot, stale/current before-after snapshot.

- [ ] **OPS-T04 — Route reconciliation-run execution through claim-and-execute** (`OPS-001`, `OPS-002`, `OPS-007`, `OPS-008`, `OPS-017`; `OPS-A04`, `OPS-A09`, `OPS-A11`, `OPS-A12`, `OPS-A16`)
  - Change: `create_run_manifest` creates its `WorkItem` inside the same transaction that freezes the manifest; `execute_and_publish_run` is replaced by `jobs.services.claim_and_execute`, which validates every manifest resource ID against the manifest's own workspace before `compute_run` reads any financial row, then calls the unchanged `compute_run`/`publish_run` boundary; transient failures re-ready the item with backoff up to `max_attempts`, permanent failures fail on the first attempt; `active_jobs` quota is reserved on enqueue and released on the terminal state; `foundation.views.reconciliation_run_start` calls `claim_and_execute` inline for the local single-process Compose path.
  - Verify: a manifest containing another workspace's scope/dataset/decision ID fails before any `TransactionObservation` value is read and leaves the owning workspaces unchanged; a transient failure retries to the documented limit and then reports `FAILED` while the last successful run stays selectable throughout; a permanent validation failure reaches `FAILED` without retrying; the workbench receives only persisted `RunProgressStage` names and measured counts at every polled state, never an invented percentage.
  - Evidence: adversarial cross-workspace manifest test, retry-limit test log, browser evidence reused from specification 005 confirming no percentage appears.

## Phase 3: import validation and storage

- [ ] **OPS-T05 — Extract `StorageAdapter` and add the object-storage implementation** (`OPS-010`, `OPS-013`)
  - Change: a `StorageAdapter` protocol behind `ingestion.artifacts.PrivateArtifactStore` (kept as the local filesystem implementation); one S3-compatible object-storage implementation selected as the deployment target's adapter (see `plan.md`'s resolved deployment-target decision); settings-driven adapter selection.
  - Verify: specification 002's existing `PrivateArtifactStore` contract test suite (stage, publish, hash, quota-limit, byte/row/column/field-limit behavior) passes unmodified against both implementations.
  - Evidence: contract-test parity report across both adapters.

- [ ] **OPS-T06 — Route import validation through claim-and-execute** (`OPS-001`–`OPS-004`, `OPS-007`, `OPS-008`, `OPS-017`; `OPS-A04`, `OPS-A09`, `OPS-A11`, `OPS-A12`, `OPS-A16`)
  - Change: `import_preview` creates its `IngestionAttempt` and `IMPORT_VALIDATION` `WorkItem` in one transaction; `ArtifactIntakeService`'s parse/validate/preview step runs from a claimed attempt instead of inline in the request, reusing the identical claim/fence/retry/ownership-validation path proven in OPS-T03–OPS-T04.
  - Verify: the same claim-concurrency, fencing, retry-limit, cross-workspace-manifest, and truthful-progress tests as OPS-T03/OPS-T04, applied to import attempts; physical/semantic hash deduplication from specification 002 is unaffected by the claim indirection.
  - Evidence: parity test results against OPS-T04's evidence, confirming the shared mechanism behaves identically for both callers.

## Phase 4: workspace cleanup

- [ ] **OPS-T07 — Implement idempotent workspace cleanup** (`OPS-009`, `OPS-015`, `OPS-016`; `OPS-A05`, `OPS-A07`, `OPS-A15`)
  - Change: `WORKSPACE_CLEANUP` work items claim `WorkspaceCleanupRequest` rows; the cleanup service re-locks the workspace, re-verifies `REVOKED`/`DELETED` state and zero remaining live references, deletes owned database rows workspace-first, deletes artifact bytes only after the row-deleting transaction has committed, and sets `processed_at`; deployment documentation states both the seven-day live `Workspace.expires_at` window this job enforces and the storage/database providers' separate longer backup-retention window.
  - Verify: an expired/deleted workspace rejects new work-item creation and every existing URL immediately (before cleanup even runs); redelivering an already-processed cleanup request is a no-op that changes nothing; an artifact still referenced by a row created after the cleanup request but before the worker claims it survives the run; the deployment retention statement matches the measured deletion behavior for both the live store and the disclosed backup window.
  - Evidence: adversarial expiry-access matrix, re-delivery idempotency test, live-reference survival test, retention-statement verification against the deployed target.

## Phase 5: operability, deployment, and release

- [ ] **OPS-T08 — Extend health reporting and structured observability** (`OPS-011`, `OPS-014`; `OPS-A08`, `OPS-A13`, `OPS-A14`)
  - Change: `/health/ready` reports web readiness, database reachability, and worker liveness/freshness (computed from the most recent `job_attempt` heartbeat) as independent fields; `observability.logging.EVENT_FIELDS` gains book/scope/run/import/job identifiers and stage duration; a worker-side structured logger reuses the existing salted-HMAC workspace reference from `observability.middleware`.
  - Verify: a stopped worker degrades only the worker signal while web/database stay healthy; sampled job and request logs built from representative session and financial fixtures contain only allowlisted fields — no raw transaction row or session secret appears.
  - Evidence: health-endpoint independence matrix and a log-field audit against the fixture corpus.

- [ ] **OPS-T09 — Ship deployment configuration and measured capacity** (`OPS-010`, `OPS-012`, `OPS-013`, `OPS-016`; `OPS-A06`, `OPS-A13`, `OPS-A15`)
  - Change: deployment configuration for the resolved target (managed PostgreSQL, S3-compatible object storage, HTTPS ingress, environment-held secrets, migrations executed as a controlled release step, versioned web/worker images); one capacity measurement run on a named workload and environment, recorded honestly whether or not the planning target is met.
  - Verify: a deployment rehearsal against the managed target independently confirms HTTPS, secure/HttpOnly/SameSite cookies, private artifact access, environment-held secrets, controlled migration execution, database readiness, and worker freshness; the capacity report cites the actual workload/environment rather than an unmeasured claim; deployed retention text is verified against OPS-T07's measured behavior.
  - Evidence: deployment rehearsal record and capacity measurement report in `specs/006-operations/evidence/`.

- [ ] **OPS-T10 — Close jobs, operations, and deployment acceptance** (`OPS-001`–`OPS-017`; `OPS-A01`–`OPS-A16`)
  - Change: end-to-end corpus exercising all three job kinds together (a run and an import in flight while a cleanup drains), final traceability, README/roadmap status update, verification record, and any defect found by the complete review.
  - Verify: all sixteen acceptance scenarios, the PostgreSQL concurrency probes, the adversarial cross-workspace/ownership matrix, the expiry/cleanup matrix, the deployment rehearsal, the capacity measurement, the full regression suite, migration consistency, domain-boundary check, and clean Compose startup, all at one commit.
  - Evidence: acceptance matrix, concurrency/capacity measurements, deployment rehearsal record, clean-runtime record, limitations, and final verified commit.

## Final traceability

| Requirement | Task IDs | Acceptance/evidence | Complete |
|---|---|---|---|
| OPS-001 | OPS-T02, OPS-T04, OPS-T06, OPS-T10 | OPS-A10 | No |
| OPS-002 | OPS-T02, OPS-T04, OPS-T06, OPS-T10 | OPS-A09 | No |
| OPS-003 | OPS-T01, OPS-T02, OPS-T03, OPS-T10 | OPS-A01 | No |
| OPS-004 | OPS-T03, OPS-T10 | OPS-A01, OPS-A02, OPS-A04, OPS-A10 | No |
| OPS-005 | OPS-T03, OPS-T10 | OPS-A03 | No |
| OPS-006 | OPS-T03, OPS-T10 | OPS-A02, OPS-A04, OPS-A10 | No |
| OPS-007 | OPS-T01, OPS-T04, OPS-T06, OPS-T10 | OPS-A11 | No |
| OPS-008 | OPS-T04, OPS-T06, OPS-T10 | OPS-A12 | No |
| OPS-009 | OPS-T07, OPS-T10 | OPS-A05, OPS-A07 | No |
| OPS-010 | OPS-T05, OPS-T08, OPS-T09, OPS-T10 | OPS-A13 | No |
| OPS-011 | OPS-T08, OPS-T10 | OPS-A14 | No |
| OPS-012 | OPS-T09, OPS-T10 | OPS-A06 | No |
| OPS-013 | OPS-T05, OPS-T09, OPS-T10 | OPS-A13 | No |
| OPS-014 | OPS-T08, OPS-T10 | OPS-A08, OPS-A13 | No |
| OPS-015 | OPS-T07, OPS-T10 | OPS-A05, OPS-A07 | No |
| OPS-016 | OPS-T07, OPS-T09, OPS-T10 | OPS-A15 | No |
| OPS-017 | OPS-T01, OPS-T02, OPS-T04, OPS-T06, OPS-T10 | OPS-A16 | No |

## Deferred work

- Multi-region active-active operation, Kubernetes, Kafka, external workflow engines, and unlimited file or component sizes remain outside the first release, as stated by this specification's out-of-scope section.
- The specific object-storage bucket provider's account/credential provisioning is an implementation-time step under the resolved S3-compatible adapter decision (`plan.md`), not an open architectural question.
- This is the final specification in the roadmap; no further specification exists to receive work deliberately cut from this one. Anything not listed above and not implemented by OPS-T10 is a defect against this specification, not a deferral.
