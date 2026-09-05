# FND-T05 Verification Evidence

- **Task:** Make quota reservations concurrency-safe
- **Requirement:** `FND-013`
- **Acceptance scenario:** `FND-A11`
- **Date:** 5 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence; see Git history for `FND-T05`

## Implemented scope

- One configured quota policy for retained bytes, reconciliation books, and active jobs.
- PostgreSQL row locking around every persisted reservation and release.
- Typed `QuotaExceeded` failures carrying resource, current usage, request, and limit.
- Book creation reserves one slot in the same outer transaction as the insert.
- Book deletion authorizes and locks the scoped book before releasing its slot and deleting it in one transaction.
- Failed inserts, missing deletes, foreign deletes, and quota refusals roll back without changing counters or existing resources.

## Checks and results

| Check | Result | Evidence summary |
|---|---|---|
| Focused quota suite | Pass | 11 tests passed against PostgreSQL. |
| Full regression suite | Pass | 60 tests passed after the scoped-delete ordering correction. |
| Configured limits | Pass | Settings values produced the exact three-resource policy limits. |
| Counter persistence | Pass | One combined reservation updated all three database counters exactly. |
| Boundary refusal | Pass | At-limit requests for bytes, books, and jobs returned typed, human-readable failures with unchanged counters. |
| Atomic book creation | Pass | At capacity, a second book was refused while the first book and counter remained intact. |
| Atomic book deletion | Pass | Deletion removed the book and released one slot together. |
| Rollback on insert failure | Pass | A database-rejected book insert left the book counter and table unchanged. |
| Missing-delete safety | Pass | A random book deletion left the existing book and count unchanged. |
| Cross-workspace delete regression | Pass | The full earlier isolation contract confirmed foreign and random deletes return `BookUnavailable` without quota changes. |
| Retained-byte concurrency | Pass | Six simultaneous reservations at capacity 2 admitted exactly 2 and refused 4; final usage was 2. |
| Book concurrency | Pass | Six simultaneous reservations at capacity 2 admitted exactly 2 and refused 4; final count was 2. |
| Active-job concurrency | Pass | Six simultaneous reservations at capacity 2 admitted exactly 2 and refused 4; final usage was 2. |
| Migration and Django checks | Pass | No migration drift; Django reported no system-check issues. |

## Defect found before commit

The first full regression run found that deletion released quota before confirming scoped ownership. A foreign or random delete against an empty caller workspace therefore raised an internal release conflict instead of the generic unavailable result. The transaction now locks the workspace, authorizes and locks the scoped book, releases the counter, and deletes the book in that order. The focused quota suite and full isolation suite then passed.

## Remaining evidence

Retained-file and active-job resource creation arrive in later specifications. Those operations must call this shared row-locking service in their own creation/publication transactions and join the same quota contract.
