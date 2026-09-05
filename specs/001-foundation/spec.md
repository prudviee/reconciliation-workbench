# 001 Foundation and Anonymous Workspace — Specification

Status: Draft
Prefix: `FND`
Depends on: Constitution

## Outcome

A visitor can open the application and receive an isolated, expiring workspace without creating an account. The project has a runnable Django/PostgreSQL foundation and a framework-independent domain package.

## Requirements

- **FND-001** The system MUST create or resolve one server-side workspace from an opaque secure browser session.
- **FND-002** Every workspace resource lookup and mutation MUST be scoped through the active session; knowledge of another UUID MUST grant no access.
- **FND-003** The interface MUST show the workspace's exact expiry time, lack of recovery, export path, and delete action.
- **FND-004** Deleting or expiring a workspace MUST revoke access before asynchronous data/file cleanup.
- **FND-005** The same browser session MUST retain access across refreshes until expiry or deletion.
- **FND-006** A different browser session MUST receive an independent workspace and sample dataset.
- **FND-007** The domain package MUST import no Django model, request, storage, job, or wall-clock dependency.
- **FND-008** State-changing browser requests MUST use CSRF protection; cookies MUST use deployment-appropriate Secure, HttpOnly, and SameSite settings.
- **FND-009** Logs MUST use correlation IDs and MUST exclude session secrets and raw financial payloads.
- **FND-010** Local setup MUST start the web process, worker, and PostgreSQL from documented commands.

## Acceptance scenarios

- **FND-A01** Given a new browser, when the home page opens, then a workspace is created and expiry is displayed.
- **FND-A02** Given two independent sessions, when one requests the other's book, run, import, case, artifact, job, or export ID, then no resource data is returned.
- **FND-A03** Given an existing session, when the browser refreshes, then the same workspace and books remain.
- **FND-A04** Given deletion or expiry, when any old URL is requested, then access is denied and no new job can be created.
- **FND-A05** Given a domain test, when importing the domain package, then Django settings and database initialization are unnecessary.

## Out of scope

Accounts, password recovery, cross-device access, verified reviewer identity, and team membership.

## Open questions

- Confirm whether retention is seven days from creation or seven days of inactivity with a maximum lifetime.
- Select the initial deployment provider before finalizing cookie and storage settings.
