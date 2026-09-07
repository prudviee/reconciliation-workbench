# REV-T10 Evidence — Bounded Scoped Review Queries

## Outcome

Implemented the read contracts required by specification 005 without adding public routes. Every query establishes an active workspace, then the owning book and reconciliation scope, before resolving child identifiers. Foreign, absent, and malformed resource identifiers raise the same `ReviewQueryUnavailable` result.

## Delivered

- Framework-independent opaque keyset cursor and bounded page contracts in `reconciliation/querying.py`.
- `DecisionQueryService` with stable decision pagination, current authority and health projection, immutable decision history labels, and the existing complete replacement preview mapped to the common unavailable contract.
- `CaseQueryService` with stable current-case pagination, occurrence history, occurrence detail, current-review detail, and bidirectional lineage projections.
- Page sizes are restricted to 1–100, defaulting to 50.
- Ordering uses `(created_at, UUID)` keysets, so equal timestamps remain deterministic and pages contain no duplicate or omitted rows.

## Query measurements

Measured with `django_assert_num_queries` on PostgreSQL. Counts do not grow with page contents or history length.

| Projection | Database queries |
|---|---:|
| Decision page | 4 |
| Decision history | 5 |
| Case page | 4 |
| Case history | 5 |
| Case occurrence | 4 |
| Current case review | 5 |
| Case lineage | 5 |

The context cost is three fixed queries: active workspace, owned book, and owned scope. Each projection then uses one bounded/select-related query, plus one owned-envelope query where a case or decision identity must first be established.

## Pagination evidence

- Five decisions at page size two were traversed across all cursors in exact `(created_at, id)` order with five unique identities.
- Two current cases at page size one were traversed across both cursors with no duplicate or omitted identity.
- A malformed cursor is rejected.
- Page sizes `0`, `101`, and boolean values are rejected before query execution.
- Current and historical revision/occurrence labels are derived from persisted current pointers, independent of tie-break ordering.

## Isolation matrix

| Boundary | Foreign | Absent/malformed | Result |
|---|---:|---:|---|
| Book context | Verified | Verified | `ReviewQueryUnavailable` |
| Scope context | Verified | Verified | `ReviewQueryUnavailable` |
| Decision history | Verified | Verified | `ReviewQueryUnavailable` |
| Replacement preview | Verified | Verified | `ReviewQueryUnavailable` |
| Case history | Verified | Verified | `ReviewQueryUnavailable` |
| Case occurrence | Verified | Verified | `ReviewQueryUnavailable` |
| Current case review | Verified | Verified | `ReviewQueryUnavailable` |
| Case lineage | Verified | Verified | `ReviewQueryUnavailable` |

No probe returned foreign values, counts, identifiers, or an existence distinction.

## Focused verification

- `python -m pytest tests/test_resolution_commands.py tests/test_reconciliation_runs.py -q -k query`
- Result: 11 passed.

## Release-gate verification

- `python -m pytest -q`
- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `python -m compileall -q ...`
- `git diff --check`

Final full-suite result: **455 passed in 34.41 seconds**. Django system checks, migration drift, compilation, architecture constraints, and diff hygiene also passed.
