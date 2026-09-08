# UX-T05 submission acceptance

## Acceptance matrix

| Journey step | Evidence | Result |
|---|---|---|
| Create isolated book and upload both assignment sources | `test_no_javascript_workbench_starts_run_and_shows_results` | Pass |
| Activate both sources after reviewing retained evidence | Existing ingestion workflow suite | Pass |
| Start a synchronous run without JavaScript | UX-T02 focused journey | Pass |
| Inspect selected-run counts and current review queue | UX-T02 focused journey | Pass |
| Open a case and inspect raw/canonical values, comparisons, policy metadata, history, and lineage | `test_case_detail_exposes_side_by_side_evidence_and_history` | Pass |
| Select a retained counterpart and require a reason | `test_case_detail_manual_link_requires_reason_and_marks_rerun_pending` | Pass |
| Preserve the earlier run while marking current review pending | Manual-link journey and run-history assertions | Pass |
| Rerun and publish the manual pair | Manual-link journey asserts a `MANUAL` pair in the new run | Pass |
| View historical and current runs from the workbench | Manual-link journey asserts the historical-run label | Pass |
| Enforce CSRF and workspace isolation | UX-T02 route and CSRF tests plus existing isolation suite | Pass |

## Verification record

- Full PostgreSQL regression: `465 passed`.
- Django system checks: passed.
- Migration drift check: passed (`No changes detected`).
- `git diff --check`: passed.
- Running stack readiness: `GET /health/ready` returned HTTP 200 with database ready.
- The required journey is server-rendered and does not require sign-in, JavaScript, or developer tools.

The only test warnings are pytest cache write warnings caused by a protected `.pytest_cache` directory in the Desktop checkout; they do not affect application verification.
