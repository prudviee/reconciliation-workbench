# FND-T01 Verification Evidence

- **Task:** Create the versioned Python/Django project and local stack
- **Requirements:** `FND-007`, `FND-010`
- **Acceptance scenarios:** `FND-A05`, `FND-A10`
- **Date:** 5 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence; see Git history for `FND-T01`

## Implemented scope

- Python 3.12 project metadata with exact runtime and development lock files.
- Django 5.2.17 project and PostgreSQL connection configuration.
- Framework-independent `reconciliation.domain` package.
- Database-backed readiness endpoint.
- Temporary database-backed worker heartbeat command.
- Dockerfile and Compose services for PostgreSQL, web, and worker.
- Host and container startup instructions.

## Dependency evidence

| Component | Verified version |
|---|---|
| Host Python | 3.12.14 |
| Container Python | 3.12.14 slim Bookworm image |
| Django | 5.2.17 |
| Psycopg / binary | 3.3.5 |
| pytest | 9.1.1 |
| pytest-django | 4.14.0 |
| Host PostgreSQL fallback test | 16.11 |
| Compose PostgreSQL | 17.6 Alpine image |
| Docker Desktop / Engine | 4.89.0 / 29.7.2 |

## Checks and results

| Check | Result | Evidence summary |
|---|---|---|
| Django system check | Pass | `System check identified no issues (0 silenced).` |
| Python compilation | Pass | `config`, `foundation`, `reconciliation`, and `tests` compiled without error. |
| Domain isolation | Pass | Subprocess imported `reconciliation.domain` with `DJANGO_SETTINGS_MODULE` absent and no Django/Psycopg modules loaded. |
| Host PostgreSQL integration | Pass | Fresh isolated cluster initialized, migrations applied, and all 3 tests passed in 0.71 seconds. The exact Desktop checkout then passed all 3 tests against the Compose database in 0.58 seconds. |
| Host web readiness | Pass | Readiness returned `status=ready`, `database=ready`. |
| Host worker boundary | Pass | Worker created its fresh heartbeat and returned `worker heartbeat ready`. |
| Compose validation | Pass | `docker compose config -q` returned success. |
| Clean image build | Pass | Python base resolved by digest and the exact Desktop checkout built with a 32.12 kB runtime-only context after excluding documentation and temporary data. |
| Compose service health | Pass | `db`, `web`, and `worker` all reported healthy. |
| Container Django check | Pass | `System check identified no issues (0 silenced).` |
| HTTP smoke | Pass | `/health/ready` returned ready/database-ready and `/` returned HTTP 200 with `Reconciliation Workbench`. |
| Cleanup | Pass | Project containers and network stopped; the named PostgreSQL volume was retained. |

## Environment note

Docker Desktop 4.73.1 initially failed before the engine started because Windows left malformed AF_UNIX runtime sockets. The settings and socket directories were backed up, Docker Desktop was updated to 4.89.0, and the documented targeted workaround disabled the unused Docker AI subsystem. No Docker images, containers, or volumes were reset. The project stack then built and passed normally. This was a host-tool repair, not an application workaround.

## Remaining foundation work

This task proves only the executable boundaries. Workspace lifecycle, ownership, sessions, quota reservations, visitor UI, revocation, and structured-log behavior remain pending in `FND-T02` through `FND-T10`.
