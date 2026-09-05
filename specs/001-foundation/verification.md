# 001 Foundation and Anonymous Workspace — Verification

- **Status:** Pending
- **Specification:** [spec.md](./spec.md)
- **Plan:** [plan.md](./plan.md)
- **Verified commit:** Pending
- **Environment:** Pending; record Python, Django, PostgreSQL, browser, OS/container, CPU, and memory

No implementation exists yet. `Pending` entries are deliberate and must not be represented as passed.

## Acceptance results

| Scenario | Result | Required evidence |
|---|---|---|
| FND-A01 | Partial | `FND-T04.md`: a new browser receives one workspace; disclosure page assertions remain for FND-T06. |
| FND-A02 | Pass for current build | `FND-T03.md` and `FND-T04.md`: scoped persistence plus HTTP reads/mutations return identical unavailable responses for foreign and random book IDs. |
| FND-A03 | Pass | `FND-T04.md`: same-client refresh retained the session-bound workspace with no duplicate creation. |
| FND-A04 | Pending | Revocation across current page/mutation/worker boundaries plus reusable contract registration for later resource types |
| FND-A05 | Pass | `FND-T01.md`: isolated subprocess imported the domain package without Django settings/database and loaded no Django/Psycopg modules |
| FND-A06 | Pass for domain policy | `FND-T02.md`: exact seven-day UTC expiry, inclusive boundary, activity invariance, and irreversible non-active states |
| FND-A07 | Pending | Multiple-book and cross-session sample integration |
| FND-A08 | Pass | `FND-T04.md`: missing CSRF proof was rejected; session cookie and fail-closed production settings were inspected. |
| FND-A09 | Pending | Structured-log capture/redaction assertion |
| FND-A10 | Pass for T01 scope | `FND-T01.md`: clean image build; PostgreSQL, web, and worker healthy; readiness and homepage returned 200 |
| FND-A11 | Partial | `FND-T02.md`: immutable quota policy and typed limit failures pass; database concurrency remains for FND-T05 |
| FND-A12 | Pending | Two-session sample ownership and mutation isolation |

## Requirement traceability

| Requirement | Planned implementation | Planned tests/evidence | Result |
|---|---|---|---|
| FND-001 | Workspace session service | FND-A01 | Partial: secure session creation/resolution passed; disclosure page remains |
| FND-002 | Workspace context and scoped repositories | FND-A02 | Pass for every resource and route in the current build; later specs must register new types |
| FND-003 | Workspace disclosure view | FND-A01 plus content review | Pending |
| FND-004 | Revocation service and boundary guards | FND-A04 | Pending |
| FND-005 | Session resolution | FND-A03 | Pass |
| FND-006 | Workspace-owned book/sample creation | FND-A12 | Partial: atomic workspace-owned user/demo book persistence passed; two-session route flow remains |
| FND-007 | Pure domain package | FND-A05 and architecture check | Pass for current package |
| FND-008 | CSRF/session production settings | FND-A08 | Pass |
| FND-009 | Correlation and log redaction | FND-A09 | Pending |
| FND-010 | Compose stack and health commands | FND-A10 | Pass; repeat at final release gate |
| FND-011 | Fixed expiry policy | FND-A06 | Pass for pure policy; persistence remains |
| FND-012 | Independent demo-book creation | FND-A07 | Pending |
| FND-013 | Atomic quota reservation | FND-A11 | Partial: pure policy passed; atomic persistence remains |

## Automated checks

| Check | Result | Evidence to record |
|---|---|---|
| Unit | Pass for current scope | Domain import, opaque IDs, lifecycle, expiry, quota boundaries, and generated quota combinations passed |
| Integration | Partial | T01 stack, T03 persistence, and T04 session/HTTP ownership flows passed; visitor UI and revocation remain |
| Property | Partial | Expiry/activity invariance and generated quota sum/boundary combinations passed; persistent concurrency remains |
| Browser | Pending | Disclosure, refresh, demo-book, delete flow without JavaScript |
| Security/isolation | Partial | Persistence and HTTP foreign/random parity, CSRF rejection, secure cookie attributes, and production fail-closed settings passed; log coverage remains |
| Performance | Pending | Workspace query count and clean startup duration |

## Manual review

Pending review of expiry/no-recovery wording, quota errors, keyboard behavior, visible focus, announced form errors, non-color state labels, and narrow-screen workspace page.

## Measurements

| Metric | Workload/environment | Target | Observed |
|---|---|---:|---:|
| Workspace-resolution database lookups | One same-session home-page refresh after middleware | At most 1 additional indexed lookup | 1 workspace-table lookup |
| Clean local startup | Named reference environment from empty application volumes | Record honestly; no advance claim | Pending |
| Concurrent book quota | Requests at configured limit | Never exceed configured count | Pending |

## Known limitations

- Verified actor identity, account recovery, cross-device access, and multi-user collaboration are intentionally absent.
- Clearing the session cookie loses access; retained data becomes reachable only through cleanup after fixed expiry.
- The foundation worker proves process/readiness wiring only; leased work execution and publication arrive in spec 006.
- Import, reconciliation, decision, and result resource types join the workspace isolation contract in their own specs.

## Verification decision

Pending. Change the feature spec to `Verified` only after every acceptance scenario passes at one recorded commit and the evidence above is complete.
