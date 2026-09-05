# [NNN] Feature Name — Implementation Plan

- **Status:** Draft
- **Specification:** [link]
- **Target branch:** `codex/NNN-short-name`
- **Last updated:** [date]

## Summary

Explain the technical approach and the smallest coherent vertical slice.

## Constitution check

| Principle | How the plan complies |
|---|---|
| Evidence is immutable | ... |
| Identity and agreement differ | ... |
| Automatic matching may abstain | ... |
| Results are explainable | ... |
| Reviewer authority is durable | ... |
| Runs publish atomically | ... |
| Decimal/time semantics are explicit | ... |
| Anonymous access is isolated | ... |
| Domain core is framework-independent | ... |
| Specifications precede behavior | ... |
| Claims require evidence | ... |
| Complexity earns its place | ... |

## Affected architecture

| Module/component | Change | Requirement IDs |
|---|---|---|
| [module] | [change] | PREFIX-... |

## Domain contracts

List new or changed value objects, pure functions, invariants, and failure types.

## Data model and migrations

Describe tables, columns, constraints, indexes, backfill, rollback/recovery, and compatibility.

## Web and application contracts

Describe routes, forms, status codes, HTMX fragments, authorization, and transaction boundaries.

## Background processing

Describe job identity, idempotency, retry categories, lease/fencing, progress, and publication. State “not applicable” when absent.

## UI behavior

Describe full-page and partial states, loading, errors, keyboard/focus, and responsive layout.

## Verification plan

| Requirement | Verification layer | Planned evidence |
|---|---|---|
| PREFIX-001 | Unit/integration/browser/property/performance | [test or measurement] |

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| [risk] | [impact] | [mitigation] |

## Rejected implementation approaches

Record meaningful alternatives and link an ADR when the decision changes system architecture.

## Delivery and rollback

Describe deployment order, compatibility, feature exposure, rollback/recovery, and data implications.

## Open decisions

The plan cannot become approved while an item can materially change tasks or verification.
