# UX-T02 verification

## Scope

The submission workbench now provides a server-rendered, no-JavaScript run flow:

- a preparation state explains when both source sides are available;
- a CSRF-protected POST creates and executes a scoped reconciliation run;
- the results page shows selected-run state, pair/unpaired/candidate counts, current review cases, and run history;
- a completed run can be opened directly from the redirect and the workbench offers a run-again action;
- foreign and absent books resolve identically, preserving workspace isolation;
- the source page links into the workbench.

## Verification

- Focused UX-T02 tests: `4 passed, 7 deselected`.
- Full regression suite: `463 passed`.
- Django system checks: passed.
- Migration drift check: passed (`No changes detected`).
- `git diff --check`: passed.

The bytecode compilation check was attempted but could not overwrite an existing protected `tests/__pycache__` file; the full test suite and Django checks passed.

## Acceptance evidence

The tests cover the no-JavaScript start-to-results flow, truthful run summary labels, route isolation, and rejection of a run-start request without a CSRF token. The implementation keeps historical run selection separate from current review state so an old run can be inspected without changing current cases.
