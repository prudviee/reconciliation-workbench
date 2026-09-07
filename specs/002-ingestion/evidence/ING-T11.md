# ING-T11 Evidence — Ingestion Release Closure

- **Task:** ING-T11
- **Result:** Passed
- **Date:** 7 September 2026
- **Release suite:** 230 tests passed

## Capacity result

The reproducible benchmark accepted and previewed 10,000 rows at 24,610,077 bytes, then published a separate 10,000-member full snapshot and a 1,000-operation delta over that base. The resolved delta contained 9,900 members after 100 explicit retractions; all 100 cancellations remained members and were ineligible.

Activation was changed from per-row identity/observation writes to bounded bulk publication. The measured full activation used 79 queries and the delta activation used 44. Complete timing and peak-memory results are recorded in [`ING-T11-capacity.json`](./ING-T11-capacity.json) and summarized in `verification.md`.

## Clean-stack result

The verifier removed only the volumes declared by this Compose project, staged an ordinary-filesystem build context, rebuilt all images, applied migrations through the web service, and waited for all services. PostgreSQL, web and worker reported healthy; readiness returned the exact expected payload; the worker heartbeat was current; no migration was pending; and a private artifact-volume probe written by web was read by worker and removed.

The machine-readable result is [`ING-T11-runtime.json`](./ING-T11-runtime.json). The verified stack remains running on `http://localhost:8010` for inspection.

## Release gates

| Gate | Result |
|---|---:|
| All ING-A01–ING-A17 scenarios | passed |
| All ING-001–ING-018 requirements | passed |
| Full automated regression | 230 passed |
| Django system check | 0 issues |
| Migration drift | no changes detected |
| Near-limit 10,000-row preview | passed |
| 10,000-member atomic activation | passed |
| 1,000-operation delta activation | passed |
| Empty-volume Compose rebuild | passed |
| Shared private artifact volume | passed |

## Decision

Specification 002 is Verified. Its measured synchronous latency is documented without making a speed guarantee; durable background execution remains assigned to specification 006.
