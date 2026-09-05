# FND-T02 Verification Evidence

- **Task:** Add workspace lifecycle and quota domain contracts
- **Requirements:** `FND-011`, `FND-013`
- **Acceptance scenarios:** `FND-A06`, `FND-A11`
- **Date:** 5 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence; see Git history for `FND-T02`

## Implemented scope

- Immutable opaque workspace and book identifiers.
- Timezone-aware fixed-expiry policy with no clock access.
- Explicit active, expired, revoked, and deleted lifecycle results.
- Immutable quota amounts for retained bytes, books, and active jobs.
- Pure quota reservation policy with typed, inspectable limit failures.
- Public domain exports without Django, Psycopg, storage, request, or network imports.

## Checks and results

| Check | Result | Evidence summary |
|---|---|---|
| Focused domain suite | Pass | 18 tests passed from the exact Desktop checkout. |
| Domain import boundary | Pass | Import with Django settings/database absent loaded no Django or Psycopg modules. |
| UTC expiry | Pass | Offset-aware creation normalized to UTC and produced exactly seven days of retention. |
| Inclusive boundary | Pass | Access allowed one microsecond before expiry and denied exactly at expiry. |
| Activity invariance | Pass | Evaluating activity throughout the week never changed the persisted expiry. |
| Durable non-active state | Pass | Revoked and deleted states never regained access before the old deadline. |
| Quota exact boundary | Pass | Reservations reaching each configured limit were accepted. |
| Quota refusal | Pass | One-unit overflow for bytes, books, and jobs produced the correct typed failure. |
| Generated quota combinations | Pass | All current/requested combinations from 0 through 8 agreed with `current + requested <= limit`. |
| Invalid quota values | Pass | Negative, Boolean, and non-integer values were rejected. |
| Python compilation | Pass | Domain and test trees compiled without error. |
| Django system check | Pass | `System check identified no issues (0 silenced).` |

## Remaining evidence

`FND-A11` is only partially closed at feature level. `FND-T05` must prove database row locking and concurrent quota reservations. `FND-T07` must persist and enforce the fixed expiry at every active boundary before `FND-011` is complete.
