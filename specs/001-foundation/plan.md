# 001 Foundation and Anonymous Workspace — Implementation Plan

- **Status:** In progress
- **Specification:** [spec.md](./spec.md)
- **Target branch:** `codex/001-foundation`
- **Last updated:** 5 September 2026

## Summary

Create the Django/PostgreSQL application shell, a framework-independent domain package, secure anonymous workspace resolution, a minimal reconciliation-book boundary, quota enforcement, revocation/expiry behavior, private structured logging, and a runnable web/worker/database development stack.

The smallest vertical slice is: open the site in two browsers, receive two independent expiring workspaces, create separate books, prove cross-session denial, revoke one workspace, and show that the other remains usable. Import and reconciliation behavior remain in later specs.

## Constitution check

| Principle | How the plan complies |
|---|---|
| Evidence is immutable | Foundation tables contain ownership and lifecycle metadata; no source evidence is introduced or overwritten. |
| Identity and agreement differ | The book boundary names the two sources without introducing pair/comparison logic. |
| Automatic matching may abstain | Matching is absent from this slice; later engine inputs remain independent of web state. |
| Results are explainable | Correlation and lifecycle events establish the audit foundation without logging financial payloads. |
| Reviewer authority is durable | Book/workspace ownership supports later append-only decisions; this plan creates no mutable decision shortcut. |
| Runs publish atomically | The worker is only made runnable; run/publication tables arrive under spec 006. |
| Decimal/time semantics are explicit | All lifecycle instants are timezone-aware UTC; expiry is calculated once from creation. |
| Anonymous access is isolated | All workspace-owned repositories require `WorkspaceId`; UUIDs never authorize requests. |
| Domain core is framework-independent | Domain value objects and policies import no Django, storage, network, request, or wall clock. |
| Specifications precede behavior | Every task maps to reviewed `FND` requirements and scenarios. |
| Claims require evidence | Startup, isolation, security headers/cookies, logging privacy, and request cost receive named verification. |
| Complexity earns its place | One application and PostgreSQL are retained; no external queue, SPA, identity provider, or cache is added. |

## Affected architecture

| Module/component | Change | Requirement IDs |
|---|---|---|
| `config` | Django settings, URLs, ASGI/WSGI entrypoints, environment validation | FND-008, FND-010 |
| `reconciliation.domain` | Immutable `WorkspaceId`, `BookId`, `ExpiryPolicy`, `QuotaPolicy`, lifecycle results and failures | FND-007, FND-011, FND-013 |
| `workspaces` | Workspace model, session binding, middleware/context, authorization, lifecycle service | FND-001-FND-005, FND-008, FND-011, FND-013 |
| `books` | Minimal workspace-owned book model and independent demo-book creation | FND-002, FND-006, FND-012 |
| `web` | Workspace shell, expiry/recovery/export disclosure, deletion and demo-book forms | FND-003, FND-008, FND-012 |
| `observability` | Correlation IDs, structured log filters, redaction tests | FND-009 |
| `worker` | Runnable worker command and heartbeat sufficient for local readiness | FND-004, FND-010 |
| Local infrastructure | Versioned dependency lock, Docker Compose web/worker/PostgreSQL, health checks | FND-010 |

## Domain contracts

- `WorkspaceId` and `BookId` are opaque UUID value objects. They identify; they never authorize.
- `ExpiryPolicy(created_at) -> expires_at` returns exactly `created_at + 7 days` in UTC. It receives time as input and reads no clock.
- `WorkspaceLifecycle.evaluate(state, expires_at, now)` returns active or revoked behavior without persistence.
- `QuotaPolicy` receives current retained bytes, book count, active-job count, configured limits, and the proposed reservation. It returns an allowed reservation or a typed limit failure without modifying state.
- `WorkspaceAccess` contains the authorized workspace ID and expiry, never the raw session secret.
- Typed failures distinguish unavailable workspace, stale/expired session, quota exceeded, and concurrency conflict internally. Browser responses do not reveal whether a foreign resource exists.

## Data model and migrations

### `workspace`

| Field/constraint | Plan |
|---|---|
| `id` | UUID primary key |
| `session_digest` | Unique digest of the current server-side session key; raw key is not copied here |
| `state` | `ACTIVE`, `REVOKED`, or `DELETED`; only `ACTIVE` grants access |
| `created_at`, `expires_at` | UTC instants; database check requires `expires_at = created_at + interval '7 days'` where supported by migration strategy, otherwise service plus migration test |
| `revoked_at`, `deleted_at` | Nullable UTC lifecycle evidence |
| quota counters | Nonnegative retained bytes, book count, and active-job count used under row lock |
| indexes | Unique session digest; `(state, expires_at)` for revocation/cleanup scans |

### `reconciliation_book`

| Field/constraint | Plan |
|---|---|
| `id` | UUID primary key |
| `workspace_id` | Required foreign key; indexed with public ID |
| `name`, `kind` | User-visible label and `USER`/`DEMO` origin |
| `sample_template_version` | Nullable; records which curated template created a demo book |
| `created_at` | UTC instant |
| uniqueness | A public ID is always resolved together with workspace ownership |

Quota reservations lock one workspace row and update counters in the same transaction that creates the bounded resource. Database checks prevent negative counters. Later specs may replace derived counters with a reservation ledger if measured contention or repair needs justify it; that change requires a plan update.

Migration recovery is forward-only for the initial empty database. The migration creates tables and constraints; its reverse removes only unused foundation tables. Once user data exists, destructive reversal is replaced by restoring the prior application image and applying a corrective forward migration.

## Web and application contracts

| Route/operation | Behavior |
|---|---|
| `GET /` | Resolve an active workspace or create one after rotating the session key; render exact expiry and limitations |
| `GET /workspace` | Render books and workspace disclosure through active `WorkspaceAccess` |
| `POST /books/demo` | Atomically reserve quota and create a new independent demo-book shell; never reset an existing book |
| `POST /workspace/delete` | Revoke synchronously, clear access, enqueue/idempotently signal later cleanup, and redirect to a fresh-entry state |
| `GET /health/ready` | Report web process and database readiness without workspace or secret detail |
| worker heartbeat | Persist or expose freshness for local readiness; spec 006 replaces this with leased work processing |

Every state-changing route uses Django CSRF validation. Production-like settings require HTTPS redirect/HSTS as selected by deployment plan and a Secure, HttpOnly, SameSite session cookie. Workspace IDs supplied by URL or form are ignored as authority; application services receive the session-derived `WorkspaceAccess` first.

Full pages remain usable without JavaScript. HTMX is optional in this slice and must use the same authorization and CSRF path as ordinary forms.

## Authorization contract suite

Define a reusable test contract for each workspace-owned resource repository and route:

1. The owner can read and perform every supported mutation while active.
2. A second workspace receives the same non-disclosing unavailable response for random, foreign, expired, revoked, and deleted IDs.
3. No foreign row, count, name, timestamp, filename, or side effect appears in response, logs, or events.
4. Worker and export adapters require an explicit owning workspace ID from trusted persisted context.
5. Later specs must register each new workspace-owned model and endpoint with this suite.

## Configuration decisions

Initial public-showcase defaults are 250 MiB retained content, 10 books, and 2 active jobs per workspace. They are environment-configurable and displayed when a request is refused. File-level limits remain in spec 002. Local development may use the same defaults so tests and documentation do not conceal deployment behavior.

Environment validation fails startup when production mode lacks an allowed host, CSRF trusted origin, secure cookie configuration, database URL, or secret key. Secret values never receive defaults in production.

## Observability

- Generate or validate a bounded correlation ID at the request boundary and return it in the response.
- Log event name, correlation ID, route name, status, duration, workspace public ID or irreversible log pseudonym, and typed failure category.
- Filter session/cookie headers, form bodies, uploaded values, secrets, and raw financial payloads.
- Record workspace creation, quota refusal, revocation, and cleanup signal as lifecycle events without pretending the anonymous actor is verified.

## Verification strategy

| Evidence | Requirements/scenarios |
|---|---|
| Pure domain import test and architecture boundary check | FND-007 / FND-A05 |
| Workspace lifecycle unit/property tests with injected instants | FND-005, FND-011 / FND-A03, FND-A06 |
| Two-client integration and route contract tests | FND-001, FND-002, FND-006 / FND-A01-FND-A03, FND-A12 |
| Delete/expiry plus late-worker publication probe | FND-004 / FND-A04 |
| CSRF and production-cookie settings checks | FND-008 / FND-A08 |
| Captured structured-log redaction test | FND-009 / FND-A09 |
| Clean local-stack smoke test | FND-010 / FND-A10 |
| Concurrent quota reservation tests | FND-013 / FND-A11 |
| Multiple demo-book integration test | FND-006, FND-012 / FND-A07, FND-A12 |

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Concurrent first requests create two workspaces | Rotate/create the server-side session first, enforce unique digest, and retry resolution after an integrity conflict. |
| Quota checks race | Lock the workspace row and reserve counters in the same transaction as creation. |
| Expiry differs across web and worker | Pass UTC `now` into one lifecycle policy and use persisted `expires_at`. |
| Cookie loss strands data | Display no-recovery behavior; fixed expiry reclaims it. |
| Generic ORM access bypasses scope | Keep unscoped managers out of application modules, require repository/context APIs, and run the reusable isolation contract. |
| Minimal worker becomes accidental final queue | Name it foundation-only and replace its temporary heartbeat interface in the spec 006 task map. |

## Rejected implementation approaches

- Browser local storage as authority: cannot protect server-side data or background work.
- Workspace UUID as a bearer token: leaks access through copied URLs, history, logs, and referrers.
- Signed self-contained workspace state: makes revocation, quotas, and cleanup coordination harder.
- Sliding inactivity expiry: conflicts with the reviewed fixed deadline and makes deletion timing unpredictable.
- Database row-level security in the first slice: valuable defense in depth, but it adds connection-context and migration complexity before the application boundary is proven. Reconsider only with a dedicated ADR and integration evidence.
- Redis/Celery for the foundation heartbeat: adds a service before background workload warrants it.

## Implementation order

1. Project/dependency/local-stack skeleton and pure domain boundary.
2. Workspace and book schema with lifecycle/quota constraints.
3. Session resolution, middleware, authorization repository, and two-client tests.
4. Workspace shell, disclosures, demo books, deletion, and expiry.
5. Correlation/log redaction and production-settings tests.
6. Worker heartbeat, clean-start smoke test, and completed verification record.
