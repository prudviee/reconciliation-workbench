# 001 Foundation and Anonymous Workspace — Tasks

- **Status:** In progress
- **Specification:** [spec.md](./spec.md)
- **Plan:** [plan.md](./plan.md)

## Task conventions

- `[ ]` pending, `[~]` in progress, `[x]` verified, `[!]` blocked.
- Every task cites requirement and acceptance IDs.
- A task includes its verification and expected evidence.
- These tasks authorize no implementation by themselves; task status changes only when work and evidence exist.

## Phase 1: executable boundaries

- [x] **FND-T01 — Create the versioned Python/Django project and local stack** (`FND-007`, `FND-010`; `FND-A05`, `FND-A10`)
  - Change: dependency lock, Django project, pure domain package, PostgreSQL service, web command, temporary worker command, readiness checks.
  - Verify: clean-machine/container startup plus domain import with Django settings and database unavailable.
  - Evidence: exact startup/check commands, versions, health outputs, import-boundary result.

- [ ] **FND-T02 — Add workspace lifecycle and quota domain contracts** (`FND-011`, `FND-013`; `FND-A06`, `FND-A11`)
  - Change: immutable IDs, fixed-expiry policy, lifecycle results, quota reservations, typed failures.
  - Verify: boundary and property tests for UTC instants, fixed seven-day expiry, nonnegative counts, and refusal without mutation.
  - Evidence: named test results and representative boundary cases.

## Phase 2: persistence and authorization

- [ ] **FND-T03 — Migrate workspace and reconciliation-book ownership** (`FND-001`, `FND-002`, `FND-006`; `FND-A01`, `FND-A02`)
  - Change: tables, constraints, indexes, scoped repositories, and atomic book ownership.
  - Verify: migration checks, owner access, cross-workspace read/mutation denial, and query inspection.
  - Evidence: schema/migration result and isolation-contract result.

- [ ] **FND-T04 — Resolve workspaces through secure server-side sessions** (`FND-001`, `FND-002`, `FND-005`, `FND-008`; `FND-A01`, `FND-A02`, `FND-A03`, `FND-A08`)
  - Change: session rotation/binding, workspace middleware/context, CSRF path, production-cookie configuration.
  - Verify: two independent clients, refresh persistence, foreign/random ID parity, CSRF rejection, cookie flags.
  - Evidence: integration results and sanitized response-header inspection.

- [ ] **FND-T05 — Make quota reservations concurrency-safe** (`FND-013`; `FND-A11`)
  - Change: row-locked atomic reservations for retained bytes, books, and active jobs with clear failures.
  - Verify: concurrent at-limit attempts admit no more than configured capacity and preserve prior resources.
  - Evidence: concurrency test with final counters and invariant checks.

## Phase 3: visitor workflow

- [ ] **FND-T06 — Render workspace disclosures and independent demo books** (`FND-003`, `FND-006`, `FND-012`; `FND-A01`, `FND-A07`, `FND-A12`)
  - Change: workspace page, exact expiry/no-recovery/export/delete text, book list, demo-book creation form.
  - Verify: ordinary form flow without JavaScript; existing book remains after multiple demo creations; second session remains independent.
  - Evidence: browser test and reviewed page capture.

- [ ] **FND-T07 — Revoke on deletion and expiry before cleanup** (`FND-004`, `FND-011`; `FND-A04`, `FND-A06`)
  - Change: idempotent revocation service, delete route, expiry check at web/worker boundaries, cleanup signal.
  - Verify: current routes, mutations, worker signal/publication guard, and the reusable revoked-workspace contract fail after revocation; activity never moves expiry. Later specs register their jobs, downloads, exports, and publication paths.
  - Evidence: lifecycle integration and late-worker results.

## Phase 4: privacy and release evidence

- [ ] **FND-T08 — Add correlation and privacy-safe structured logs** (`FND-009`; `FND-A09`)
  - Change: correlation middleware, structured event schema, redaction/filtering.
  - Verify: capture successful and failed requests containing sentinel secrets/financial strings and assert absence with correlation present.
  - Evidence: redaction test summary without echoing the sentinels.

- [ ] **FND-T09 — Prove clean startup and architecture constraints** (`FND-007`, `FND-010`; `FND-A05`, `FND-A10`)
  - Change: documented local commands and automated smoke/architecture checks.
  - Verify: rebuild from clean volumes, apply migrations once, observe web/database readiness and fresh worker heartbeat.
  - Evidence: environment/version record, summarized command results, measured startup time.

- [ ] **FND-T10 — Complete foundation acceptance and documentation** (`FND-001`-`FND-013`; `FND-A01`-`FND-A12`)
  - Change: close traceability, document current commands and limitations, update status/history only after evidence passes.
  - Verify: every acceptance row and requirement row in `verification.md` has evidence; no target is reported as achieved without measurement.
  - Evidence: completed verification record at the tested commit.

## Final traceability

| Requirement | Task IDs | Acceptance/evidence | Complete |
|---|---|---|---|
| FND-001 | FND-T03, FND-T04, FND-T10 | FND-A01 | No |
| FND-002 | FND-T03, FND-T04, FND-T10 | FND-A02 | No |
| FND-003 | FND-T06, FND-T10 | FND-A01 | No |
| FND-004 | FND-T07, FND-T10 | FND-A04 | No |
| FND-005 | FND-T04, FND-T10 | FND-A03 | No |
| FND-006 | FND-T03, FND-T06, FND-T10 | FND-A12 | No |
| FND-007 | FND-T01, FND-T09, FND-T10 | FND-A05 | Partial: T01 passed |
| FND-008 | FND-T04, FND-T10 | FND-A08 | No |
| FND-009 | FND-T08, FND-T10 | FND-A09 | No |
| FND-010 | FND-T01, FND-T09, FND-T10 | FND-A10 | Partial: T01 passed |
| FND-011 | FND-T02, FND-T07, FND-T10 | FND-A06 | No |
| FND-012 | FND-T06, FND-T10 | FND-A07 | No |
| FND-013 | FND-T02, FND-T05, FND-T10 | FND-A11 | No |
