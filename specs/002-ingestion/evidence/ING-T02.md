# ING-T02 Evidence — Workspace-Owned Ingestion Persistence

- **Task:** ING-T02
- **Result:** Passed
- **Date:** 6 September 2026
- **Environment:** Python 3.12.14, Django 5.2.17, PostgreSQL 17.6

## Implemented boundary

The persistence slice adds workspace-owned records for source systems, book-side assignments, immutable mapping and contract revisions, datasets, artifact metadata, ingestion attempts, tagged raw rows, stable logical identities, immutable observations, dataset revisions, and materialized membership.

All public lookups enter through a repository constructed with a `WorkspaceId`. Relationship factories resolve every parent in that workspace before creating the child. Foreign identifiers and random identifiers therefore have the same public failure.

Evidence models refuse instance updates, instance deletion, queryset updates, and queryset deletion. Lifecycle state remains mutable only on ingestion attempts and the current dataset head. PostgreSQL constraints independently enforce valid roles, modes, reference semantics, attempt states, canonical sides/states, cancellation eligibility, row numbers, sizes, and the required uniqueness rules.

## Verification

| Check | Command scope | Result |
|---|---|---:|
| Persistence and isolation | `tests/test_ingestion_persistence.py` | 18 passed |
| Persistence plus architecture | persistence and architecture constraint modules | 21 passed |
| Full regression suite | all tests | 136 passed |
| Django system check | project configuration and registered models | 0 issues |
| Migration drift | generated models against committed migrations | no changes detected |

The tests construct the complete source-to-membership graph, resolve every resource as its owner, prove foreign/random lookup parity, reject cross-workspace parents, reject mismatched membership links, exercise every immutable model through instance and bulk entry points, provoke database constraints directly, and inspect the reconciliation candidate indexes.

## Remaining acceptance scope

This task establishes retained metadata and immutable database evidence. Artifact byte storage, bounded parsing, activation, correction/replay sequences, HTTP authorization, and private downloads are covered by later ingestion tasks and remain partial in the specification verification table.
