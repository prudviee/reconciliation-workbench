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
| FND-A01 | Pending | New-session integration plus expiry page assertion |
| FND-A02 | Pending | Reusable cross-workspace read/mutation contract |
| FND-A03 | Pending | Same-client refresh integration |
| FND-A04 | Pending | Revocation across current page/mutation/worker boundaries plus reusable contract registration for later resource types |
| FND-A05 | Pass | `FND-T01.md`: isolated subprocess imported the domain package without Django settings/database and loaded no Django/Psycopg modules |
| FND-A06 | Pending | Injected-clock seven-day boundary test with activity |
| FND-A07 | Pending | Multiple-book and cross-session sample integration |
| FND-A08 | Pending | CSRF rejection and production-like cookie/header inspection |
| FND-A09 | Pending | Structured-log capture/redaction assertion |
| FND-A10 | Pass for T01 scope | `FND-T01.md`: clean image build; PostgreSQL, web, and worker healthy; readiness and homepage returned 200 |
| FND-A11 | Pending | Storage/book/job quota boundary and concurrency tests |
| FND-A12 | Pending | Two-session sample ownership and mutation isolation |

## Requirement traceability

| Requirement | Planned implementation | Planned tests/evidence | Result |
|---|---|---|---|
| FND-001 | Workspace session service | FND-A01 | Pending |
| FND-002 | Workspace context and scoped repositories | FND-A02 | Pending |
| FND-003 | Workspace disclosure view | FND-A01 plus content review | Pending |
| FND-004 | Revocation service and boundary guards | FND-A04 | Pending |
| FND-005 | Session resolution | FND-A03 | Pending |
| FND-006 | Workspace-owned book/sample creation | FND-A12 | Pending |
| FND-007 | Pure domain package | FND-A05 and architecture check | Pass for current package |
| FND-008 | CSRF/session production settings | FND-A08 | Pending |
| FND-009 | Correlation and log redaction | FND-A09 | Pending |
| FND-010 | Compose stack and health commands | FND-A10 | Pass; repeat at final release gate |
| FND-011 | Fixed expiry policy | FND-A06 | Pending |
| FND-012 | Independent demo-book creation | FND-A07 | Pending |
| FND-013 | Atomic quota reservation | FND-A11 | Pending |

## Automated checks

| Check | Result | Evidence to record |
|---|---|---|
| Unit | Partial | Domain import boundary passed; lifecycle, expiry, quota, and ID value objects remain |
| Integration | Partial | T01 PostgreSQL/web/worker startup passed; session, ownership, books, revocation, and constraints remain |
| Property | Pending | Expiry/activity invariance and nonnegative quota reservations |
| Browser | Pending | Disclosure, refresh, demo-book, delete flow without JavaScript |
| Security/isolation | Pending | CSRF, cookie flags, foreign/random ID parity, log redaction |
| Performance | Pending | Workspace query count and clean startup duration |

## Manual review

Pending review of expiry/no-recovery wording, quota errors, keyboard behavior, visible focus, announced form errors, non-color state labels, and narrow-screen workspace page.

## Measurements

| Metric | Workload/environment | Target | Observed |
|---|---|---:|---:|
| Workspace-resolution database lookups | One normal authenticated-by-session page request after middleware | At most 1 additional indexed lookup | Pending |
| Clean local startup | Named reference environment from empty application volumes | Record honestly; no advance claim | Pending |
| Concurrent book quota | Requests at configured limit | Never exceed configured count | Pending |

## Known limitations

- Verified actor identity, account recovery, cross-device access, and multi-user collaboration are intentionally absent.
- Clearing the session cookie loses access; retained data becomes reachable only through cleanup after fixed expiry.
- The foundation worker proves process/readiness wiring only; leased work execution and publication arrive in spec 006.
- Import, reconciliation, decision, and result resource types join the workspace isolation contract in their own specs.

## Verification decision

Pending. Change the feature spec to `Verified` only after every acceptance scenario passes at one recorded commit and the evidence above is complete.
