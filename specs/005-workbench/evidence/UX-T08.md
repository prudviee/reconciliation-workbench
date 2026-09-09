# UX-T08 consolidated showcase acceptance

## Result

The complete workbench specification is verified through the submission journey, showcase extensions, reviewer-action closures, operations evidence, and this final documentation audit.

## Acceptance matrix

| Area | Evidence | Result |
|---|---|---|
| Complete no-JavaScript workflow | UX-T02 through UX-T05 browser journeys | Pass |
| Side-by-side evidence, history, and lineage | UX-T03 and UX-T08C | Pass |
| Manual link and accept unmatched | UX-T04 and UX-T08A | Pass |
| Reject, revoke, replace, and reaffirm | UX-T08D through UX-T08G | Pass |
| Server-side discovery and safe exports | UX-T06 | Pass |
| Allocation explanation and truthful run states | UX-T07 | Pass |
| Keyboard structure and non-color status | Semantic-template assertions in UX-T02/UX-T03 plus visible-focus and reduced-motion CSS tests | Pass |
| Responsive evidence and tables | Narrow-screen CSS assertions and live dedicated-page inspection | Pass |
| Workspace isolation and CSRF | Route/mutation matrices across UX-T02, UX-T04, UX-T06, and UX-T08A–UX-T08G | Pass |
| Durable background execution and health | OPS-T03, OPS-T04, OPS-T06, OPS-T08, and OPS-T10 | Pass |
| Local-only deployment and retained uploads | STO-T01 and `docs/07-deployment.md` | Pass |
| Typical workbench response target | 60 warm-cache requests against the curated three-case workbench: `55.657 ms` p95 | Pass for demonstrated workload |
| Large reconciliation target | OPS-T09: `11.01 s` against a `10 s` target | Disclosed miss |

## Final verification record

- Full PostgreSQL regression: `538 passed`.
- Django system check: no issues.
- Migration drift: no changes detected.
- Local Markdown links: all resolve.
- Current documentation scan: no HTMX, drawer, AWS, or external-storage implementation claims; historical/rejected alternatives remain clearly labelled.
- Docker Compose: PostgreSQL, web, and worker healthy after a clean rebuild of the final source.
- Public repository quick-start commands and destructive-volume behavior are documented in the root README.

## Performance measurement scope

The workbench latency sample used Django's production-mode request path from the host against the running Docker PostgreSQL database. Five warm-up requests preceded 60 measured requests for a current three-case curated book. Results were `43.994 ms` median, `55.657 ms` p95, and `250.498 ms` maximum. The sample verifies the ordinary showcase page only; it is not presented as a hosted or large-queue benchmark.

## Known limits

The verified showcase is single-host and local-only, has no recoverable account, supports CSV and one-to-one two-source reconciliation, performs no FX conversion, and does not schedule morning runs by calendar. These limits and proposed next steps are stated in the root README.
