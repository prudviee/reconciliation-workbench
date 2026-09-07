# Reconciliation Workbench

Reconciliation Workbench is being built as an explainable transaction-reconciliation system that preserves source evidence, performs constrained one-to-one matching, exposes field-level discrepancies, and carries reviewer decisions safely across corrected files and later runs.

This project uses spec-driven development end to end.

## Current verified scope

Specifications 001–003 are complete. Visitors receive isolated seven-day anonymous workspaces and can create independent reconciliation books. Each book has a two-sided source-preparation workflow with private CSV upload, the two Atlas assignment adapters, an allowlisted configurable mapping, raw/canonical/provenance preview, structured validation, immutable full-snapshot and delta activation, correction/replay protection, history, and authorized original-file downloads.

The supported CSV boundary is UTF-8 or UTF-8 with BOM, comma/semicolon/tab delimiters, 25 MiB, 10,000 rows, 100 columns, and 4,096 characters per field. The verified pure reconciliation engine applies reviewer reservations and trusted references, generates bounded candidates, records fixed-point rule evidence, solves optional-unmatched global assignments, abstains on incomplete or unstable results, compares paired fields exactly, and emits read-only accepted-unmatched diagnostics. Persistence for runs and decisions, the browser workbench, and production operations follow in specifications 004–006.

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

From an ordinary local checkout, start the web, worker, and database processes:

```powershell
docker compose up --build
```

When the services are healthy, open `http://localhost:8010` and inspect readiness at `http://localhost:8010/health/ready`. For a checkout stored under OneDrive, use the clean-start gate below because Docker BuildKit cannot consume Cloud Files reparse-point metadata directly.

Create a demo book, choose **Prepare sources**, and upload the assignment ledger and counterparty CSVs. Each side can instead use **Define mapping** for a third format. Review the retained evidence before selecting **Confirm and activate**.

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
