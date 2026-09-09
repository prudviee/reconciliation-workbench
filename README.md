# Reconciliation Workbench

Reconciliation Workbench is an explainable transaction-reconciliation application for comparing records produced independently by an internal ledger and a counterparty. It preserves the original evidence, performs deterministic one-to-one matching, explains every result, and carries reasoned reviewer decisions safely across corrections and later runs.

The project was built for the Atlas Software Engineer take-home assignment and extended into a complete local showcase. It uses spec-driven development from product decisions through acceptance evidence.

## What it demonstrates

- Private, seven-day anonymous workspaces with no sign-in.
- Two-sided CSV preparation with built-in ledger and counterparty adapters.
- Configurable mappings for additional CSV formats.
- Raw, canonical, validation, and provenance previews before activation.
- Immutable full-snapshot and delta revisions with correction and replay handling.
- Trusted-reference matching followed by weighted candidate generation and global one-to-one assignment.
- Conservative abstention for ties, incomplete evidence, hard contradictions, and bounded computations.
- Field-level discrepancy explanations with explicit decimal, currency, and UTC-time semantics.
- Server-side search, filters, stable pagination, historical runs, and formula-safe CSV/JSON exports.
- Reasoned manual links, accept-unmatched decisions, candidate rejection, reaffirmation, revocation, and conflict-complete replacement.
- PostgreSQL-backed work claims, leases, retries, fencing, truthful progress, and atomic publication.
- Private local file storage with automatic workspace-expiry cleanup.

The complete browser workflow is server-rendered and requires no JavaScript.

## Quick start with Docker

### Prerequisites

- [Git](https://git-scm.com/downloads)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker Engine with Compose v2

Clone and start the application:

```powershell
git clone https://github.com/prudviee/reconciliation-workbench.git
cd reconciliation-workbench
docker compose up --build -d --wait
```

Open [http://localhost:8010](http://localhost:8010). The readiness endpoint is [http://localhost:8010/health/ready](http://localhost:8010/health/ready).

Docker starts three healthy services:

| Service | Purpose |
|---|---|
| `web` | Django application on port `8010` |
| `worker` | Durable import, reconciliation, and cleanup jobs |
| `db` | PostgreSQL on host port `55432` |

Useful commands:

```powershell
# Follow application output
docker compose logs -f web worker

# Stop the application while retaining data
docker compose down

# Remove the application and all local database/upload data
docker compose down --volumes
```

The final command is destructive. Ordinary rebuilds and `docker compose down` preserve the named database and private-artifact volumes.

If ports `8010` or `55432` are already in use, change their host-side values in `compose.yaml` before starting the stack.

## Five-minute assignment walkthrough

The repository includes safe synthetic inputs:

- `demo/atlas-ledger.csv`
- `demo/atlas-counterparty.csv`

1. Open the application and select **Create demo book**.
2. Open **Prepare sources**.
3. Upload `atlas-ledger.csv` to the left **Internal ledger** source.
4. Review its raw/canonical preview and activate it.
5. Upload `atlas-counterparty.csv` to the right **Counterparty** source, selecting the Counterparty adapter.
6. Review and activate the second source.
7. Open the workbench and start reconciliation.
8. Inspect `TX-1002` to see a field-level amount discrepancy.
9. Inspect the unmatched `TX-1003`, choose its retained candidate, enter a reason, and save the manual link.
10. Run reconciliation again and inspect the new manual pair alongside the immutable earlier run.

The detailed presenter script is in [demo/README.md](./demo/README.md), and the tested journey is recorded in [UX-T05 evidence](./specs/005-workbench/evidence/UX-T05.md).

## How matching works

The engine processes an immutable snapshot in explicit stages:

1. Exclude cancelled or ineligible observations.
2. Apply durable reviewer reservations and rejected relationships.
3. Pair unique trusted shared references.
4. Generate a bounded candidate graph using compatible instrument, side, currency, quantity, time, and amount evidence.
5. Calculate versioned feature scores with `Decimal`, quantized to integer basis points.
6. Solve each complete connected component as an optional-unmatched one-to-one assignment using SciPy's linear assignment solver.
7. Re-solve without each selected edge to measure its counterfactual global gap.
8. Confirm an automatic match only when score, evidence coverage, contradiction, completeness, and stability gates all pass.
9. Compare paired financial fields independently from the pairing decision.

This separates two questions that reconciliation systems often conflate: **Do these records describe the same transaction?** and **Do their financial values agree?** A manually or automatically paired transaction can still carry an amount or time discrepancy.

The complete algorithm, formulas, thresholds, and counterexamples are documented in [Reconciliation algorithm](./docs/04-reconciliation-algorithm.md).

## Key decisions and why

| Decision | Reason |
|---|---|
| Django modular monolith with PostgreSQL | Keeps transactions and deployment understandable while preserving strong module boundaries. |
| Full server-rendered pages | Meets the assignment with a keyboard-operable workflow and no frontend build or JavaScript dependency. |
| Anonymous session workspace | Lets reviewers try the full product immediately without adding account and recovery scope. |
| Immutable evidence and append-only decisions | Corrections and reviewer actions remain auditable instead of silently rewriting history. |
| Global one-to-one assignment | Avoids contradictory local greedy choices when candidates compete for the same record. |
| Conservative abstention | Uncertain, tied, or incomplete evidence becomes review work rather than an unsafe automatic pair. |
| PostgreSQL job leases and fencing | A late or retried worker cannot publish over a newer attempt. |
| Private Docker volume for uploads | Keeps the verified release free and self-contained without AWS or another storage account. |

Detailed HLD, LLD, alternatives, consequences, and threat boundaries are linked under [Design and evidence](#design-and-evidence).

## Data and operational boundaries

| Boundary | Verified value |
|---|---:|
| Encoding | UTF-8 or UTF-8 with BOM |
| Delimiters | Comma, semicolon, or tab |
| Maximum file size | 25 MiB |
| Maximum rows per file | 10,000 |
| Maximum columns | 100 |
| Maximum characters per field | 4,096 |
| Default workbench page size | 50 cases |
| Maximum workbench page size | 100 cases |
| Anonymous workspace lifetime | Seven days from creation |

Uploaded CSVs are stored in a private Docker volume shared only by the web and worker containers. Downloads pass through workspace authorization. Clearing browser data loses access to the anonymous workspace, although expiry cleanup still removes it later.

## Development and verification

For host-side development, start PostgreSQL first with `docker compose up -d db`, then create the environment and run the suite:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements\dev.lock
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python manage.py check
.\.venv\Scripts\python manage.py makemigrations --check --dry-run
```

On macOS or Linux, replace `.\.venv\Scripts\python` with `.venv/bin/python`.

The current release has **538 passing tests**. Coverage includes pure reconciliation rules, property and boundary cases, PostgreSQL constraints and concurrency, workspace isolation, immutable history, job fencing, exports, clean-start verification, and complete browser journeys. The consolidated workbench evidence is [UX-T08](./specs/005-workbench/evidence/UX-T08.md).

Maintainers can run the destructive clean-start verifier from a checkout whose current Compose volumes may be discarded:

```powershell
python scripts\verify_clean_start.py --evidence specs\001-foundation\evidence\FND-T09-runtime.json
```

It rebuilds from an ordinary temporary filesystem, removes this project's existing Compose volumes, waits for all services, checks readiness and migrations, and verifies that web and worker share the private artifact volume. Use it only when deleting the current local demo data is acceptable.

## Known limits and what was left out

- The verified release is a single-host Docker Compose application; there is no hosted public demo.
- Anonymous workspaces cannot be recovered on another browser or device.
- Storage is a local persistent Docker volume. A hosted deployment needs a new durable private-storage decision.
- Reconciliation is one-to-one between two sources; split settlements and one-to-many matching are outside this release.
- The engine does not perform foreign-exchange conversion.
- Files are CSV only; spreadsheets, PDFs, and direct provider integrations are outside this release.
- A measured 10,000-row reconciliation took `11.01 s`, missing the initial `10 s` target. The result is disclosed in [capacity evidence](./specs/006-operations/evidence/OPS-T09.md).
- The included worker processes durable work but does not initiate a calendar-based morning run automatically.

## What I would do next

1. Profile and optimize the 10,000-row candidate and assignment path against a fixed reference machine.
2. Add recoverable accounts only when cross-device access becomes a real requirement.
3. Select a free hosted target with durable private storage, then verify retention and recovery against that provider.
4. Add scheduled run creation and notification policies for operational use.
5. Extend reconciliation policies for one-to-many settlements, fees, and explicit FX conversion.

## Design and evidence

- [Design documentation index](./docs/README.md)
- [High-level design](./docs/02-hld.md)
- [Low-level design](./docs/03-lld.md)
- [Reconciliation algorithm](./docs/04-reconciliation-algorithm.md)
- [Architecture decisions](./docs/05-architecture-decisions.md)
- [Deployment](./docs/07-deployment.md)
- [Specification workflow](./specs/README.md)
- [Project constitution](./specs/constitution.md)
- [Feature roadmap](./specs/roadmap.md)
- [Critical design review](./specs/reviews/2026-09-05-critical-review.md)
- [Consolidated design](./DESIGN.md)

Every implemented feature follows:

```text
Problem → Spec → Acceptance scenarios → Plan → Tasks → Implementation → Verification → Evidence
```
