# UX-T04 verification

## Scope

Unpaired case evidence now exposes retained counterpart candidates. A reviewer can choose a candidate, provide a mandatory reason, and submit a CSRF-protected manual link. The command is checked against the current workspace/book generation and candidate set; conflicts return a recoverable error. The decision marks the scope dirty, keeps the earlier run immutable, and is included as a `MANUAL` pair on the next run.

## Verification

- Focused manual-link journey: `1 passed, 12 deselected`.
- Full regression suite: `465 passed`.
- Django system checks: passed.
- Migration drift check: passed (`No changes detected`).
- `git diff --check`: passed.

The browser test covers candidate selection, blank-reason rejection, durable decision submission, pending-rerun state, and publication of the manual pair in a new run.
