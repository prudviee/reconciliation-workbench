# ING-T09 Evidence — Ingestion Isolation and Cancellation Boundary

- **Task:** ING-T09
- **Result:** Passed
- **Date:** 6 September 2026
- **Environment:** Python 3.12.14, Django 5.2.17, PostgreSQL test database

## Implemented boundary

The ingestion repository now exposes a single candidate-input boundary that first resolves the requested dataset revision through workspace scope and then returns only settled observations explicitly marked eligible. Cancelled observations and their provenance remain retained and inspectable but cannot enter later candidate generation through this adapter.

Original artifact bytes are served only by a session-protected, workspace-scoped download route. Storage paths remain generated and private. Missing records, foreign identifiers, random identifiers, corrupt storage keys, and missing physical objects all produce the same not-found response. Expired and deleted sessions are rejected by the common workspace middleware before byte access.

Downloads use Django's safe attachment header generation, the sanitized retained filename, `private, no-store` caching, and `nosniff`. Request telemetry records the named route and opaque workspace reference without artifact IDs, filenames, source values, cookies, or bytes.

## Verification matrix

| Boundary | Owner | Foreign/random | Expired/deleted | Result |
|---|---:|---:|---:|---|
| Every source/ingestion repository getter | resolves | uniform unavailable | service/middleware guard | passed |
| Relationship mutations | succeeds for consistent graph | uniform unavailable | active-service guard | passed |
| Candidate-input revision | eligible settled only | uniform unavailable | active run boundary required | passed |
| Private artifact download | exact retained bytes | identical 404 response | common unavailable redirect | passed |
| Download headers and request logs | safe attachment | no metadata disclosure | no byte access | passed |

## Verification results

| Check | Result |
|---|---:|
| Focused downloads, persistence, and activation suite | 41 passed |
| Full regression suite | 221 passed |
| Django system check | 0 issues |
| Migration drift | no changes detected |

## Remaining acceptance scope

ING-T10 adds the remaining protected upload, mapping, preview, activation, and history routes and exercises them as one browser workflow. ING-T11 performs the clean-stack and final traceability gate.
