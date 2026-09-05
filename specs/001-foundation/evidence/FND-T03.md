# FND-T03 Verification Evidence

- **Task:** Migrate workspace and reconciliation-book ownership
- **Requirements:** `FND-001`, `FND-002`, `FND-006`
- **Acceptance scenarios:** `FND-A01`, `FND-A02`
- **Date:** 5 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence; see Git history for `FND-T03`

## Implemented scope

- PostgreSQL-backed workspace and reconciliation-book tables with UUID identifiers and required ownership.
- Unique server-side session digest storage, fixed seven-day expiry, lifecycle scan index, and nonnegative quota counters.
- User/demo book shape constraints, workspace/public-ID lookup index, and workspace/creation-time list index.
- Workspace repository that normalizes lifecycle instants to UTC and derives expiry through the pure domain policy.
- Book repository bound to one `WorkspaceId` for list, count, get, create, rename, and delete operations.
- One generic `BookUnavailable` result for foreign, random, and missing identifiers.

## Checks and results

| Check | Result | Evidence summary |
|---|---|---|
| Complete current suite | Pass | 39 tests passed against an isolated PostgreSQL test database. |
| Migration consistency | Pass | `makemigrations --check --dry-run` reported `No changes detected`. |
| Django system check | Pass | `System check identified no issues (0 silenced).` |
| Fresh schema creation | Pass | Pytest created the test database and applied all migrations before the persistence suite. |
| Workspace constraints | Pass | Unique session digest, exact seven-day expiry, valid state, and nonnegative counters are database-enforced. |
| UTC persistence | Pass | An offset-aware creation instant was normalized and returned in UTC with the same absolute time. |
| Ownership constraint | Pass | PostgreSQL rejected a book whose workspace did not exist. |
| Book shape constraints | Pass | Empty names and inconsistent user/demo template metadata were rejected. |
| Owner operations | Pass | Owner-scoped create, get, rename, delete, list, and count operations succeeded. |
| Foreign/random parity | Pass | Get, rename, and delete returned the same typed unavailable failure for foreign and random IDs without side effects. |
| Collection isolation | Pass | Workspace-scoped lists and counts excluded another workspace's books. |
| Query/index inspection | Pass | The lookup SQL included workspace and book IDs; schema introspection found the composite ownership, list, cleanup, uniqueness, check, and foreign-key structures. |

## Remaining evidence

The persistence portion of `FND-A02` is closed. `FND-T04` must prove the same isolation at the HTTP/session boundary, and later resource types must register with the reusable contract. `FND-A01` still needs session creation and the workspace page. `FND-A12` still needs a two-session demo-book flow.
