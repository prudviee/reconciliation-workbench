# FND-T09 Verification Evidence

- **Task:** Prove clean startup and architecture constraints
- **Requirements:** `FND-007`, `FND-010`
- **Acceptance scenarios:** `FND-A05`, `FND-A10`
- **Date:** 6 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence; see Git history for `FND-T09`
- **Machine-readable record:** `FND-T09-runtime.json`

## Implemented scope

- A repeatable clean-start gate removes only this Compose project's declared volumes, stages ordinary source files for OneDrive compatibility, builds the images, starts the stack with health waiting, and records successful evidence as JSON.
- The gate verifies the exact running service set, HTTP readiness payload, PostgreSQL connectivity, a fresh worker heartbeat, fully applied migrations, migration ownership, and component versions.
- The worker heartbeat now contains an inspectable timezone-aware timestamp. Container health requires the file to be both nonempty and fresh.
- Static architecture tests parse every domain source file and refuse framework, persistence-adapter, or web-layer imports.
- Python distribution discovery now includes every application package: books, config, foundation, observability, reconciliation, and workspaces.
- Local startup and clean verification commands are documented in the project README.

## Checks and results

| Check | Result | Evidence summary |
|---|---|---|
| Clean application state | Pass | The verifier removed the project's prior Compose volume and rebuilt from an empty PostgreSQL data volume. |
| Image build | Pass | Both application service images built from the staged current source tree. |
| Service health | Pass | The exact expected set—database, web, and worker—reported running and healthy. |
| HTTP readiness | Pass | The public readiness endpoint returned HTTP 200 with web and database ready. |
| PostgreSQL probe | Pass | PostgreSQL reported that it was accepting connections. |
| Migration ownership | Pass | Compose assigns migration application to one service; all migrations applied during web startup and `migrate --check` found none pending. |
| Worker heartbeat | Pass | The worker wrote a nonempty UTC timestamp and its freshness health check passed. |
| Architecture constraints | Pass | Static AST inspection found no forbidden domain imports; isolated runtime import also loaded no Django or Psycopg modules. |
| Package discovery | Pass | Every current application package is listed for distribution discovery. |
| Full regression suite | Pass | 87 tests passed against the running PostgreSQL 17.6 Compose service after the clean-stack run. |
| Migration consistency | Pass | `makemigrations --check --dry-run` reported no changes. |
| Django system check | Pass | `System check identified no issues (0 silenced).` |
| Diff hygiene | Pass | `git diff --check` found no whitespace errors. |

## Measured reference environment

| Item | Observed value |
|---|---|
| Clean startup duration | 18.375 seconds |
| Host | Windows 11 Home Single Language 10.0.26200, Intel Core i7-1260P, 15.6 GiB memory |
| Docker | Engine 29.7.2; Compose 5.5.0 |
| Application container | Python 3.12.14; Django 5.2.17 |
| Database container | PostgreSQL 17.6 |
| Installed browsers | Chrome 152.0.7977.76; Edge 152.0.4191.62 |

## Environment recovery note

Docker Desktop initially failed before project startup because abandoned internal Unix socket files could not be renamed. The stale runtime folders were preserved under timestamped backup names, Docker then started normally, and no factory reset was used. The clean gate intentionally recreated only the `reconciliation-workbench` Compose volume.

The Desktop checkout is inside OneDrive. Docker BuildKit rejects OneDrive Cloud Files reparse-point metadata even when files are pinned locally, so the verifier copies current source content into an ordinary temporary directory for the build. Containers use the resulting immutable image and do not depend on that temporary directory after startup.
