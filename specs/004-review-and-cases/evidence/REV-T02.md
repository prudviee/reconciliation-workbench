# REV-T02 Verification Evidence

- **Task:** Add book generations, scopes, and immutable policy revisions
- **Requirements:** `REV-010`, `REV-011`, `REV-012`, `REV-016`
- **Acceptance scenarios:** `REV-A06`, `REV-A12`
- **Date:** 7 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence

## Implemented persistence

- `reconciliation_book.generation` tracks effective dataset and policy changes; `resolution_generation` is a separate nonnegative counter reserved for reviewer authority changes beginning in REV-T04.
- `reconciliation_scope` owns one workspace/book/coverage, one left dataset, one right dataset, a local generation, and a dirty flag. Database constraints enforce unique book coverage, nonblank coverage, distinct datasets, and nonnegative generation.
- `policy_revision` stores exact matching and comparison policy objects, a versioned canonical SHA-256 digest, a book-local revision number, workspace ownership, and creation time.
- Policy revisions reject instance updates, bulk updates, and ordinary deletes. A changed policy appends a revision; an identical canonical payload returns the existing revision without changing generations.
- Workspace-scoped repositories resolve the owning book before accepting datasets or child identifiers and require the left/right dataset roles to match the book.

## Generation transition evidence

| Event | Book data generation | Book resolution generation | Consuming scope generation/dirty | Other scope |
|---|---:|---:|---|---|
| New dataset revision activated | +1 | unchanged | +1 / dirty | unchanged |
| Format-equivalent no-change activation | unchanged | unchanged | unchanged | unchanged |
| Historical replay refused | unchanged | unchanged | unchanged | unchanged |
| New policy revision | +1 | unchanged | +1 / dirty | all scopes in owning book dirty |
| Canonically identical policy submitted | unchanged | unchanged | unchanged | unchanged |
| Stale expected policy generation | unchanged | unchanged | unchanged | unchanged |

The activation transaction now locks workspace, attempt, owning book, and dataset before publication. It advances the dataset pointer first, then increments the already locked book and only scopes whose left or right dataset is the activated dataset. A failed outer transaction rolls back the pointer, generation, and dirty flags together.

## Isolation and constraints

- A scope rejects reversed roles, datasets from a different book, mixed-workspace datasets, and foreign books.
- Foreign and absent scope IDs both raise `ScopeUnavailable`; foreign and absent policy IDs both raise `PolicyUnavailable`.
- The migration depends on the latest ingestion migration before adding protected dataset foreign keys, avoiding a migration cycle with ingestion's existing dependency on `books.0001`.
- `manage.py check` found no issues and `makemigrations --check --dry-run` reported no model drift.

## Verification results

| Check | Result |
|---|---|
| Scope/policy plus full activation tests | 21 passed in 10.13 seconds |
| Exact no-change and replay generation assertions | Passed in the full suite |
| Django system check | Passed, zero issues |
| Migration drift check | Passed, no changes detected |
| Full repository regression | 400 passed in 17.50 seconds |
| Diff whitespace check | Passed |

## Scope boundary

This task establishes data/policy generations and scope ownership. It does not yet change `resolution_generation`; atomic decision commits own that behavior in REV-T04. Current run pointers are added with immutable run persistence in REV-T06, and current case projections begin in REV-T08.
