# UX-T01 Evidence — Scoped Workbench Application Projections

- **Task:** UX-T01
- **Result:** Pass
- **Date:** 7 September 2026
- **Task commit:** The commit containing this evidence

## Delivered

- `WorkbenchService.readiness` identifies the exact missing source sides and never treats an unactivated dataset as runnable.
- `ensure_run_context` establishes one workspace-owned default scope and one immutable initial policy only after both datasets have active revisions. Repeated calls reuse the same scope and policy.
- `snapshot` separates the selected historical run from the current-run pointer and current case projections. Selecting an old run never changes which cases are labelled current.
- Missing, malformed, cross-scope, and cross-workspace selected-run identifiers use the same `WorkbenchUnavailable` result.
- A dirty scope and mismatched applied decision generation remain explicit for pending-rerun presentation.

## Focused verification

| Scenario | Result |
|---|---|
| Neither source active | Not ready; LEFT and RIGHT reported |
| Only ledger active | Not ready; RIGHT reported |
| Both sources active | Ready |
| Context requested twice | One scope and one policy revision |
| Historical run selected | Historical run selected; current cases still reference latest run |
| Foreign, absent, malformed run | `WorkbenchUnavailable` |

## Release checks

| Check | Result |
|---|---|
| Focused readiness and snapshot tests | 2 passed |
| Full repository regression | 460 passed in 41.94 seconds |
| Django system check | Passed, 0 issues |
| Migration drift | Passed, no changes detected |
| Compilation | Passed |
| Diff hygiene | Passed |

## Scope boundary

This task provides application projections only. UX-T02 adds the public run and workbench routes and renders these values without JavaScript.
