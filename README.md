# Reconciliation Workbench

An explainable transaction-reconciliation system that preserves source evidence, performs constrained one-to-one matching, exposes field-level discrepancies, and carries reviewer decisions safely across corrected files and later runs.

This project uses spec-driven development end to end.

## Start here

- [Specification workflow](./specs/README.md)
- [Project constitution](./specs/constitution.md)
- [Feature roadmap](./specs/roadmap.md)
- [Critical design review](./specs/reviews/2026-09-05-critical-review.md)
- [Design documentation](./docs/README.md)
- [Consolidated design](./DESIGN.md)

## Development rule

Every feature follows this path:

```text
Problem → Spec → Acceptance scenarios → Plan → Tasks → Implementation → Verification → Evidence
```

No feature implementation starts while its specification contains unresolved decisions or lacks testable acceptance scenarios. When behavior changes, the specification changes in the same commit or before the implementation.

## Development foundation

The implementation targets Python 3.12, Django 5.2 LTS, and PostgreSQL. Exact resolved dependencies are recorded under `requirements/`.

Start the local web, worker, and database processes:

```powershell
docker compose up --build
```

When the services are healthy, open `http://localhost:8010` and inspect readiness at `http://localhost:8010/health/ready`.

To prove the complete stack from an empty project database, run the clean-start gate. This intentionally removes only the Compose volumes declared by this project, rebuilds the images, waits for PostgreSQL, web, and worker health, verifies that no migration remains unapplied, and writes a machine-readable evidence record:

```powershell
python scripts\verify_clean_start.py --evidence specs\001-foundation\evidence\FND-T09-runtime.json
```

The verifier stages a temporary ordinary-filesystem build context, so it also works when the checkout lives in a OneDrive folder whose Cloud Files metadata Docker BuildKit cannot read. It leaves the healthy stack running for inspection. Stop it later with `docker compose down`; add `--remove-volumes-after` only when the verified database should also be discarded.

For a host-side development environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements\dev.lock
.\.venv\Scripts\python -m pytest
```

The current worker command is a deliberately temporary database-backed heartbeat used to prove the process boundary. Specification 006 replaces it with leased work claims and fenced publication.
