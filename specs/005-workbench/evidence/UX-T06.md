# UX-T06 discovery and export acceptance

## Acceptance matrix

| Requirement | Evidence | Result |
|---|---|---|
| Search, outcome filter, review filter, sorting, and pagination operate on one complete server-side query | `test_case_query_pages_are_stable_complete_and_bounded` | Pass |
| Filtered totals represent the complete result rather than the visible page | Query-service assertions and `test_workbench_combines_search_filters_sort_and_complete_totals` | Pass |
| A cursor cannot be replayed under different filters | Filter-bound cursor assertion | Pass |
| Current-review CSV and JSON identify their view and follow active filters | `test_case_exports_are_explicit_precise_formula_safe_and_isolated` | Pass |
| Selected-run CSV and JSON contain immutable run facts without current-review state | Historical export assertions | Pass |
| Decimal values remain strings and timestamps carry an explicit UTC offset | CSV and JSON semantic assertions | Pass |
| CSV neutralizes formula-leading source identities | Formula-cell assertion using the synthetic identity `=2+2` | Pass |
| Foreign workspace routes reveal no book, run, filename, values, or counts | Export isolation assertion | Pass |

## Verification record

- Full PostgreSQL regression: `468 passed`.
- Django system checks: passed.
- Migration drift check: passed (`No changes detected`).
- `git diff --check`: passed.
- Running Compose stack: web and database healthy; `GET /health/ready` returned HTTP 200.
- Live browser acceptance: combined reference search, outcome filtering, and newest-first sorting returned `1 of 1`; the current-review download links retained those filters and the selected-run links remained explicitly complete.

The only warnings are pytest cache write warnings from the protected `.pytest_cache` directory in the Desktop checkout. They do not affect application behavior or verification.
