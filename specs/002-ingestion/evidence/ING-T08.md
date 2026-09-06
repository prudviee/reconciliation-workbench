# ING-T08 Evidence — Explicit Delta Activation

- **Task:** ING-T08
- **Result:** Passed
- **Date:** 6 September 2026
- **Environment:** Python 3.12.14, Django 5.2.17, PostgreSQL test database

## Implemented boundary

Delta previews now interpret an explicit operation column through the immutable source contract. `UPSERT` and `CANCEL` require a complete canonical observation, while `RETRACT` requires only the stable source identity and retains its raw operation evidence without creating an observation.

Activation locks and verifies the previewed dataset base, copies that base membership, applies only the explicit operations, and hashes the fully resolved membership. A stale base raises `StalePreview` before any evidence is published. Revision creation, new observations, memberships, attempt transition, and head movement remain one transaction.

## Membership transition

| Identity | Base | Delta operation | Result |
|---|---|---|---|
| `T-1` | settled amount 100 | `UPSERT` amount 125 | new immutable observation selected |
| `T-2` | settled | `CANCEL` | cancelled observation selected and ineligible |
| `T-3` | settled | `RETRACT` | absent from new membership; earlier evidence retained |
| `T-4` | settled | omitted | base observation remains selected |

## Verification

| Check | Result |
|---|---:|
| Focused preview and activation modules | 31 passed |
| Four-operation membership fixture | passed |
| Same semantic delta over divergent bases | semantic hashes equal; state hashes different |
| Changed-base activation | stale attempt retained as READY; winning head unchanged |
| Injected membership-publication failure | observations, revision, attempt, and head rolled back |
| Full regression suite | 214 passed |
| Django system check | 0 issues |
| Migration drift | no changes detected |

## Remaining acceptance scope

Private downloads, full route/repository isolation, cancellation candidate filtering, and privacy-safe response/log behavior are assigned to ING-T09. The browser workflow and capacity/clean-stack gates remain in ING-T10 and ING-T11.
