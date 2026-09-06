# ING-T07 Evidence — Correction, Replay, and Restore Policy

- **Task:** ING-T07
- **Result:** Passed
- **Date:** 6 September 2026
- **Environment:** Python 3.12.14, Django 5.2.17, PostgreSQL 17.6

## Implemented boundary

Full-snapshot activation now calculates the complete proposed state hash before creating logical identities or observations. If that state equals the current head, the attempt becomes NO_CHANGE and publishes nothing. If it equals an earlier state, the attempt becomes REPLAYED and the current head does not move backward.

Restoring a historical state is an explicit action. A nonblank reason of at most 1,000 characters is trimmed, stored on the attempt, and permits a new observation, membership, and revision whose parent is the current correction. A blank reason cannot bypass the replay guard. Trustworthy provider-revision ordering remains optional and is unavailable until a source contract explicitly declares such a monotonic provider field.

Formatting-only differences do not create corrections because observation fingerprints use normalized canonical values and provenance meaning rather than the original decimal spelling. Original artifacts and raw rows remain retained regardless of NO_CHANGE or REPLAYED disposition.

## Verification

| Check | Command scope | Result |
|---|---|---:|
| Activation, replay, and restore module | `tests/test_full_snapshot_activation.py` | 12 passed |
| T07 temporal/policy scenarios | no-change, replay, restore, invalid reason | 4 passed |
| Full regression suite | all tests | 210 passed |
| Django system check | project configuration | 0 issues |
| Migration drift | includes immutable attempt evidence plus activation reason | no changes detected |

The temporal fixture activates amount 100, then correction 110, then submits 100 again. The ordinary replay produces no revision and leaves 110 current. A fresh 100 preview with a reviewer reason creates a third revision, retains the 110 parent, records the reason, and selects a new immutable observation. The restored state hash equals the original state hash without reusing or mutating the original revision.

## Remaining acceptance scope

Delta operations and their base-sensitive state behavior arrive in ING-T08. The final integrated evidence-history page and clean-stack acceptance run remain in ING-T10 and ING-T11.
