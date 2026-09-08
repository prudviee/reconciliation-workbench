# OPS-T07 Verification Evidence

- **Task:** Implement idempotent workspace cleanup
- **Requirements:** `OPS-009`, `OPS-015`, `OPS-016`
- **Acceptance scenarios:** `OPS-A05`, `OPS-A07`, `OPS-A15`
- **Date:** 8 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence

## Design: cascade the whole workspace, not a hand-maintained deletion order

Every workspace-owned table across every app (`books`, `sources`, `ingestion`, `reconciliation`, `resolutions`, `cases`, `jobs` — 36 FKs checked) carries a direct `workspace = ForeignKey(Workspace, on_delete=CASCADE)`. `workspaces.cleanup.purge_workspace` therefore does not hand-order deletions across apps or worry about `PROTECT` relationships between sibling tables (e.g. `ReconciliationRun.left_revision → DatasetRevision`) — Django's own cascade collector already resolves the complete dependency graph correctly, because every table it would need to delete is *also* directly reachable from `Workspace` via its own `CASCADE` edge, so nothing scheduled for deletion is left referencing something outside the deletion set. One `workspace.delete()` inside a lock purges books, sources, datasets, observations, decisions, runs, cases, and the job-queue bookkeeping in one transaction. Artifact bytes are handled separately (see below) since they live outside the database.

**Rejected alternative:** a permanent tombstone row (keep `Workspace`/`WorkspaceCleanupRequest` after clearing everything else, matching their existing `state`/`deleted_at` fields). Rejected because achieving it would require overriding the CASCADE relationship for two tables while preserving it for everything else, adding real complexity for an audit trail nothing in this specification reads back. The absence of the `Workspace` row is itself sufficient proof of "already purged" for `OPS-A07`'s idempotency check.

## A same-transaction ordering bug found and fixed while implementing

Wiring `WorkspaceLifecycleService._revoke()` to enqueue the `WORKSPACE_CLEANUP` `WorkItem` through `jobs.services.enqueue()` (the same helper `OPS-T04`/`OPS-T06` use) looked right but wasn't: `enqueue()` reserves `active_jobs` quota via `WorkspaceQuotaService().reserve()`, which itself calls `lifecycle_service.require_active()` — and by the time `_revoke()` reaches the enqueue call, it has *already* saved the workspace's new `REVOKED`/`DELETED` state a few lines above, in the same transaction. `require_active()` on an already-revoked workspace always raises `WorkspaceUnavailable`, which would have made `_revoke()` — called incidentally from ordinary `require_active()` checks whenever any request finds a workspace has just expired — always fail. A forked review agent confirmed this by tracing the actual call chain and fixed it: `WORKSPACE_CLEANUP` items are now created directly (`WorkItem.objects.get_or_create(cleanup_request=cleanup, ...)`, bypassing `enqueue()`'s quota reservation entirely) — reasonable on its own terms too, since cleanup is system-triggered teardown, not user-initiated work competing for the same anti-abuse budget as uploads/runs.

## A second self-referential bug found and fixed while testing

A *successful* cleanup deletes the workspace, which cascades away the very `WorkItem`/`JobAttempt` rows `jobs.services.claim_and_execute`'s own post-execution bookkeeping (`mark_succeeded`) tries to update immediately afterward — `mark_succeeded` raised `WorkItemUnavailable` even though the executor had just succeeded. Fixed by having `claim_and_execute` treat `WorkItemUnavailable` from `mark_succeeded` (only reachable after the executor itself raised nothing) as confirmation of success rather than a failure — documented inline as a `WORKSPACE_CLEANUP`-specific consequence, not a silent catch-all.

## Implemented contracts

- `workspaces.cleanup.purge_workspace(workspace_id, *, attempt_token=None) -> bool`: returns `False` immediately (no-op) if the workspace row is already gone (`OPS-A07`). Otherwise snapshots every `FileArtifact.storage_key` the workspace owns *before* the transaction (safe: a revoked workspace can accept no new uploads, so the snapshot cannot go stale), locks the workspace, re-verifies `REVOKED`/`DELETED` state (`CleanupStateConflict` otherwise), verifies the claiming attempt's fencing token against the locked `WorkItem` when supplied, deletes the workspace (cascading everything), then deletes each snapshotted artifact's bytes via `StorageAdapter.delete_published` — added to the protocol and both `PrivateArtifactStore` and `S3ArtifactStore` this task.
- `workspaces.cleanup.execute_claimed_cleanup(work_item, token)`: the `JobKind.WORKSPACE_CLEANUP` executor for `claim_and_execute`, translating `CleanupStateConflict` into `TransientJobFailure` exactly like the run/import executors translate their own conflict types.
- `WorkspaceLifecycleService._revoke()` now creates the `WORKSPACE_CLEANUP` `WorkItem` alongside the existing `WorkspaceCleanupRequest` it already wrote, inside the same lock/transaction — `expire()` and `delete()` both flow through it, so both paths get cleanup work enqueued.

## Verification results

| Check | Result |
|---|---|
| `tests/test_workspace_cleanup.py` (new) | 7 passed: exactly-once enqueue across repeated `delete()` calls; full purge removes every owned row and the artifact bytes; a second, untouched workspace and its artifact survive completely intact; redelivering a completed cleanup is a no-op; an active (not yet revoked) workspace refuses cleanup; the real `claim_and_execute` path purges end-to-end; a fenced cleanup attempt cannot purge after reclaim, the reclaiming attempt can |
| `tests/test_workspace_lifecycle.py`, `tests/test_workspace_quotas.py`, `tests/test_workspace_persistence.py` (pre-existing, re-verified by the fixing agent) | 39 passed |
| Full repository regression | 531 passed in 19.21 seconds |
| `python manage.py makemigrations --check --dry-run` | No changes detected (no model changes this task) |
| `git diff --check` (whitespace) | Passed |

## OPS-016 / OPS-A15 disclosure (documentation, not code, closes this)

This job's scope is exactly the live store: the database rows and artifact bytes a revoked/deleted workspace owns. It has no visibility into, and does not touch, whatever backup retention the managed PostgreSQL and object-storage providers apply on their own schedule once `OPS-T09` selects them. Deployment documentation must state both periods explicitly — the seven-day live `Workspace.expires_at` window this job enforces, and the provider's separate, likely-longer backup-retention window — so a user is not told data is gone when a backup snapshot might still contain it. That disclosure is `OPS-T09`'s deliverable; this task only guarantees the live-store half is true.

## Scope boundary

Nothing yet calls `claim_and_execute(JobKind.WORKSPACE_CLEANUP, ...)` automatically — the standalone `worker` management command still only writes a heartbeat. `OPS-T08` wires its polling loop to call `claim_and_execute` for every registered `JobKind`, which is what makes cleanup (and reclaimed/retried runs and imports) actually happen without a request in flight.
