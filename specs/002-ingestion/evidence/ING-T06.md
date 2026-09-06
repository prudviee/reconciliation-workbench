# ING-T06 Evidence — Atomic Full-Snapshot Activation

- **Task:** ING-T06
- **Result:** Passed
- **Date:** 6 September 2026
- **Environment:** Python 3.12.14, Django 5.2.17, PostgreSQL 17.6

## Implemented boundary

A READY full-snapshot preview activates inside one database transaction. The service preflights active workspace access, then locks the workspace, attempt, and target dataset. It rechecks that the dataset head still equals the previewed base before creating anything.

Every canonical preview is reconstructed through the domain validators. Stable logical identities are reused by source key, while observations, revisions, and memberships are appended. The resolved-state hash covers the complete new membership. The attempt becomes ACTIVATED and the dataset head advances only after all observations, the revision, and all batched memberships exist.

A rejected, already activated, stale, incomplete, inconsistent, duplicate, or tampered preview cannot publish. Any exception rolls back logical identities, observations, revision, memberships, attempt state, and head movement together.

## Verification

| Check | Command scope | Result |
|---|---|---:|
| Full-snapshot activation | `tests/test_full_snapshot_activation.py` | 8 passed |
| Full regression suite | all tests | 206 passed |
| Django system check | project configuration | 0 issues |
| Migration drift | models against migrations | no changes detected |

The focused suite proves first activation, exact materialized membership and state hash, omission in a replacement snapshot, correction as a new observation, retained earlier membership, cancelled/ineligible activation, refusal to activate one attempt twice, rejected-preview refusal, tampered canonical evidence refusal, rollback after memberships were inserted, and a two-thread same-base race.

In the concurrency case, both previews bind to the same null base. PostgreSQL locking allows exactly one head advance; the other attempt remains READY and receives `StalePreview`. Only one revision exists afterward.

## Remaining acceptance scope

ING-T07 adds semantic no-change, historical replay, and explicit restore policy. ING-T08 adds delta membership operations. Final performance and clean-stack activation measurements remain in ING-T11.
