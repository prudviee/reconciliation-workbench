# FND-T07 Verification Evidence

- **Task:** Revoke on deletion and expiry before cleanup
- **Requirements:** `FND-004`, `FND-011`
- **Acceptance scenarios:** `FND-A04`, `FND-A06`
- **Date:** 6 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence; see Git history for `FND-T07`

## Implemented scope

- Row-locked, idempotent expiry and deletion transitions.
- Database-enforced relationship between active/revoked/deleted states and lifecycle timestamps.
- One durable cleanup request per workspace with a valid reason and a partial pending-work index.
- Expiry enforcement during session resolution and quota-backed resource creation.
- Reusable worker/service boundary guard for active workspace authorization.
- CSRF-protected deletion confirmation, immediate session invalidation, deletion result, and unavailable-workspace page.
- New workspace creation after deletion without restoring access to the old workspace.

## Checks and results

| Check | Result | Evidence summary |
|---|---|---|
| Focused lifecycle suite | Pass | 9 deletion, expiry, schema, session, quota, and worker tests passed. |
| Full regression suite | Pass | 76 tests passed against isolated PostgreSQL 16.11. |
| Migration consistency | Pass | `makemigrations --check --dry-run` reported no changes. |
| Deletion order | Pass | Workspace state and revocation timestamps committed with the cleanup signal while books remained available only to cleanup. |
| CSRF | Pass | A delete without CSRF proof returned 403 and created no lifecycle or cleanup change. |
| Stale browser boundary | Pass | Independent stale-cookie requests could not read, rename, or create workspace-owned books and returned the same unavailable redirect. |
| Direct creation boundary | Pass | Quota-backed book creation rejected a deleted workspace even outside an HTTP view. |
| Fixed persisted expiry | Pass | Five normal page requests left the original expiry unchanged; an expired deadline revoked on the next protected request. |
| Idempotence | Pass | Repeated expiry created one cleanup request and preserved the first revocation time; later deletion upgraded the same signal. |
| Database lifecycle constraint | Pass | PostgreSQL rejected a deleted state without revocation/deletion timestamps. |
| Cleanup schema | Pass | Introspection found the pending-work index and valid-reason check constraint. |
| Worker/publication guard | Pass | The temporary worker accepted an active workspace and refused the same UUID after revocation. |
| Replacement workspace | Pass | After deletion, the browser could create a distinct active workspace; the old workspace stayed deleted. |
| Browser confirmation review | Pass | The real page exposed an explicit, readable consequence summary, exact prior expiry, irreversible warning, destructive confirmation, and safe cancel action. |
| Django system check | Pass | `System check identified no issues (0 silenced).` |

## Environment note

Docker Desktop was installed but its engine was stopped. Startup hit its recurring stale `sailor-ingest.sock` defect. A requested repair of Docker runtime directories was rejected by automatic approval review, so verification used the already-created isolated PostgreSQL 16.11 cluster on local port 55434. Docker volumes were not reset or changed.

## Remaining evidence

The cleanup request is durable and access revocation is complete. Physical file/data cleanup processing is intentionally deferred until retained file resources exist. Every later job, download, export, publication, and scheduled path must call the same boundary guard and register with the reusable revoked-workspace contract.
