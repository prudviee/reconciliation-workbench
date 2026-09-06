# 001 Foundation and Anonymous Workspace — Specification

- **Status:** Verified
- **Prefix:** `FND`
- **Depends on:** Constitution
- **Reviewed:** 5 September 2026

## Outcome

A visitor can open the application and receive an isolated, expiring workspace without creating an account. The project has a runnable Django/PostgreSQL foundation and a framework-independent domain package.

## Requirements

- **FND-001** The system MUST create or resolve one server-side workspace from an opaque secure browser session.
- **FND-002** Every workspace resource lookup and mutation MUST be scoped through the active session; knowledge of another UUID MUST grant no access.
- **FND-003** The interface MUST show the workspace's exact expiry time, lack of recovery, export path, and delete action.
- **FND-004** Deleting or expiring a workspace MUST revoke access before asynchronous data/file cleanup.
- **FND-005** The same browser session MUST retain access across refreshes until expiry or deletion.
- **FND-006** A different browser session MUST receive an independent workspace; demo reconciliation book shells created in either session MUST remain independent.
- **FND-007** The domain package MUST import no Django model, request, storage, job, or wall-clock dependency.
- **FND-008** State-changing browser requests MUST use CSRF protection; cookies MUST use deployment-appropriate Secure, HttpOnly, and SameSite settings.
- **FND-009** Logs MUST use correlation IDs and MUST exclude session secrets and raw financial payloads.
- **FND-010** Local setup MUST start the web process, worker, and PostgreSQL from documented commands.
- **FND-011** Workspace expiry MUST be fixed at seven days from creation and MUST NOT extend through activity.
- **FND-012** The same browser MUST support multiple isolated demo books without one sample load replacing another.
- **FND-013** Anonymous workspaces MUST enforce configurable limits for retained storage, book count, and concurrent active jobs; refusal MUST explain the exceeded limit without deleting existing work.

## Acceptance scenarios

- **FND-A01** Given a new browser, when the home page opens, then a workspace is created and the exact expiry, lack of recovery, available-result export path, and delete action are displayed.
- **FND-A02** Given two independent sessions and a workspace-owned resource available in the current build, when one session retrieves or mutates the other's resource ID through any supported path, then no resource data is returned; every later resource type must join the same isolation contract suite.
- **FND-A03** Given an existing session, when the browser refreshes, then the same workspace and books remain.
- **FND-A04** Given deletion or expiry, when any route or worker boundary available in the current build uses the old workspace, then access and new work are denied; every later route and worker type must join the same revoked-workspace contract suite.
- **FND-A05** Given a domain test, when importing the domain package, then Django settings and database initialization are unnecessary.
- **FND-A06** Given continued activity throughout the week, when the original seven-day expiry arrives, then access still expires at the previously displayed time.
- **FND-A07** Given an existing user book shell, when a demo book shell is created, then the demo receives a separate identity and the existing book remains unchanged.
- **FND-A08** Given a production-like HTTPS configuration, when a state-changing form and session response are inspected, then missing CSRF proof is rejected and the session cookie is Secure, HttpOnly, and SameSite.
- **FND-A09** Given representative successful and failed requests containing transaction values, when structured logs are captured, then each has a correlation ID and none contains the session secret or raw financial payload.
- **FND-A10** Given a clean supported machine, when the documented local-start procedure is followed, then the web readiness check, worker heartbeat, and PostgreSQL connectivity all succeed.
- **FND-A11** Given a workspace at each configured storage, book, or active-job limit, when one more resource is requested, then the request is refused with a clear limit message and existing books, results, and jobs remain unchanged.
- **FND-A12** Given two independent sessions that load the same sample template, when either session adds or changes a book, then the other session's sample books and counts remain unchanged.

## Invariants and failure behavior

- A URL identifier never grants workspace access by itself. (`FND-002`, Constitution VIII)
- Workspace authorization is resolved before loading child objects. (`FND-002`)
- Expiry is checked for web requests, worker publication, downloads, exports, and scheduled work. (`FND-004`, `FND-011`)
- A missing, invalid, expired, or deleted session produces no distinction that exposes another workspace's existence. (`FND-002`)
- Cleanup may retry, but revoked workspace access cannot become active again. (`FND-004`)
- The deployment plan selects provider-specific cookie, HTTPS, database, and storage settings while preserving these requirements. (`FND-008`, Constitution VIII)

## Performance and capacity

Planning target: workspace resolution adds no more than one indexed database lookup to a normal request after session middleware. The deployed value is measured rather than claimed in advance. (`FND-001`, Constitution XI)

## Out of scope

Accounts, password recovery, cross-device access, verified reviewer identity, and team membership.

## Resolved decisions

- Retention is seven days from workspace creation. A fixed deadline is predictable for visitors and cleanup; activity does not extend it.
- Deployment-provider selection belongs to the implementation plan. It may change concrete settings, but it cannot weaken secure cookie, private storage, isolation, or retention behavior.

## Requirement-to-scenario matrix

| Requirement | Scenarios |
|---|---|
| FND-001, FND-003 | FND-A01 |
| FND-002 | FND-A02 |
| FND-005 | FND-A03 |
| FND-004 | FND-A04 |
| FND-007 | FND-A05 |
| FND-011 | FND-A06 |
| FND-012 | FND-A07 |
| FND-008 | FND-A08 |
| FND-009 | FND-A09 |
| FND-010 | FND-A10 |
| FND-013 | FND-A11 |
| FND-006 | FND-A12 |

## Change history

| Date | Change | Reason |
|---|---|---|
| 5 September 2026 | Initial draft | Establish anonymous foundation behavior |
| 5 September 2026 | Fixed retention, added isolation/failure invariants and traceability; marked Ready | Critical SDD review |
| 5 September 2026 | Began implementation after `FND-T01` verification | Versioned project, domain boundary, and local web/worker/PostgreSQL stack passed their task gate |
| 6 September 2026 | Clarified that foundation demos are book shells; real source rows remain in specification 002 | Keep the public interface and acceptance evidence aligned with implemented behavior |
| 6 September 2026 | Marked Verified after `FND-T01`–`FND-T10` | All 12 acceptance scenarios and 13 requirements have recorded evidence on the tested foundation branch |
