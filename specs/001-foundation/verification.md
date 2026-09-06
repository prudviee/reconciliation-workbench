# 001 Foundation and Anonymous Workspace — Verification

- **Status:** Verified
- **Specification:** [spec.md](./spec.md)
- **Plan:** [plan.md](./plan.md)
- **Verified commit:** The `FND-T10` task commit containing this record
- **Environment:** Windows 11 10.0.26200; Intel Core i7-1260P; 15.6 GiB memory; Docker Engine 29.7.2; Compose 5.5.0; Python 3.12.14 and Django 5.2.17 containers; PostgreSQL 17.6; Chrome 152.0.7977.76; Edge 152.0.4191.62

Implementation evidence is recorded per task and linked below.

## Acceptance results

| Scenario | Result | Required evidence |
|---|---|---|
| FND-A01 | Pass | `FND-T04.md` and `FND-T06.md`: a new browser receives one workspace and sees exact expiry, privacy/no-recovery, export, and deletion disclosures. |
| FND-A02 | Pass for current build | `FND-T03.md` and `FND-T04.md`: scoped persistence plus HTTP reads/mutations return identical unavailable responses for foreign and random book IDs. |
| FND-A03 | Pass | `FND-T04.md`: same-client refresh retained the session-bound workspace with no duplicate creation. |
| FND-A04 | Pass for current build | `FND-T07.md`: delete/expiry revoke before cleanup signalling; stale reads, mutations, creation, quota service, and worker guard deny access. Later resource types must register. |
| FND-A05 | Pass | `FND-T01.md`: isolated subprocess imported the domain package without Django settings/database and loaded no Django/Psycopg modules |
| FND-A06 | Pass | `FND-T02.md` and `FND-T07.md`: exact seven-day UTC policy, unchanged persisted deadline across activity, boundary revocation, and durable cleanup signal passed. |
| FND-A07 | Pass | `FND-T06.md`: two demo book shells received separate identities and preserved an existing user book shell. |
| FND-A08 | Pass | `FND-T04.md`: missing CSRF proof was rejected; session cookie and fail-closed production settings were inspected. |
| FND-A09 | Pass | `FND-T08.md`: successful and failed request events carried bounded correlation IDs while request bodies, query values, cookies, and session secrets were excluded. |
| FND-A10 | Pass | `FND-T01.md`, `FND-T09.md`, and `FND-T09-runtime.json`: clean images and empty application volume; PostgreSQL, web, and worker healthy; readiness returned 200; migrations fully applied. |
| FND-A11 | Pass for current build | `FND-T02.md` and `FND-T05.md`: typed policy, row-locked persistence, atomic book creation/deletion, rollback, and concurrent capacity checks passed. Later bounded resource types must use the same service. |
| FND-A12 | Pass | `FND-T06.md`: two independent sessions created demo books with isolated lists and counts. |

## Requirement traceability

| Requirement | Planned implementation | Planned tests/evidence | Result |
|---|---|---|---|
| FND-001 | Workspace session service | FND-A01 | Pass: secure session creation/resolution and disclosure page verified |
| FND-002 | Workspace context and scoped repositories | FND-A02 | Pass for every resource and route in the current build; later specs must register new types |
| FND-003 | Workspace disclosure view | FND-A01 plus content review | Pass |
| FND-004 | Revocation service and boundary guards | FND-A04 | Pass for every resource and worker path in the current build; later types must register |
| FND-005 | Session resolution | FND-A03 | Pass |
| FND-006 | Workspace-owned book/sample creation | FND-A12 | Pass |
| FND-007 | Pure domain package | FND-A05 and architecture check | Pass; runtime import and static source boundaries both verified |
| FND-008 | CSRF/session production settings | FND-A08 | Pass |
| FND-009 | Correlation and log redaction | FND-A09 | Pass for request-boundary telemetry; later domain-event producers must use the same fixed-schema formatter |
| FND-010 | Compose stack and health commands | FND-A10 | Pass from empty project volumes with measured evidence |
| FND-011 | Fixed expiry policy | FND-A06 | Pass |
| FND-012 | Independent demo-book creation | FND-A07 | Pass |
| FND-013 | Atomic quota reservation | FND-A11 | Pass for foundation resources; later bounded resource types must integrate the shared service |

## Automated checks

| Check | Result | Evidence to record |
|---|---|---|
| Unit | Pass for current scope | Domain import, static architecture constraints, opaque IDs, lifecycle, expiry, quota boundaries, generated quota combinations, and timestamp heartbeat passed |
| Integration | Pass for current feature scope | Stack, persistence, session/HTTP ownership, demo books, deletion, expiry, cleanup signal, worker boundary, and request telemetry passed |
| Property | Pass for current scope | Expiry/activity invariance, generated quota combinations, and six-way concurrent reservations for every quota counter passed |
| Browser | Pass for current feature scope | Desktop/mobile disclosure, refresh, keyboard skip, demo creation, and deletion confirmation passed without JavaScript; deletion POST passed through the server integration client |
| Security/isolation | Pass for current feature scope | Persistence and HTTP foreign/random parity, CSRF rejection, secure cookie attributes, production fail-closed settings, and request-log redaction passed |
| Performance | Pass for foundation scope | Workspace query count and clean startup duration measured on the named reference environment |

## Manual review

Pass for the current workspace surface: expiry/no-recovery wording, quota errors, truthful demo-book labeling, keyboard skip behavior, visible focus, announced status/errors, non-color state labels, and a 390-pixel narrow-screen layout were reviewed. Deletion confirmation was browser-reviewed, and deletion behavior passed the server integration suite.

## Measurements

| Metric | Workload/environment | Target | Observed |
|---|---|---:|---:|
| Workspace-resolution database lookups | One same-session home-page refresh after middleware | At most 1 additional indexed lookup | 1 workspace-table lookup |
| Clean local startup | Named reference environment from empty application volumes | Record honestly; no advance claim | 18.344 seconds |
| Concurrent book quota | Six simultaneous one-book reservations with capacity 2 | Never exceed configured count | 2 admitted, 4 refused, final count 2 |

## Known limitations

- Verified actor identity, account recovery, cross-device access, and multi-user collaboration are intentionally absent.
- Clearing the session cookie loses access; retained data becomes reachable only through cleanup after fixed expiry.
- The foundation worker proves process/readiness wiring only; leased work execution and publication arrive in spec 006.
- Demo creation currently creates an independent reconciliation book shell. CSV parsing, source evidence, and populated demo transactions arrive in spec 002.
- Import, reconciliation, decision, and result resource types join the workspace isolation contract in their own specs.

## Verification decision

Verified. All 12 acceptance scenarios and 13 requirements have linked evidence; the full 89-test suite, clean Compose startup, migrations, browser review, security/isolation checks, and recorded measurements passed for the foundation scope.
