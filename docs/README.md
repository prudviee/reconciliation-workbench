# Reconciliation Workbench — Design Documentation

This directory is the canonical design package for the transaction-reconciliation showcase. It describes the product and system before implementation.

## Reading order

1. [Product design](./01-product-design.md) — problem, users, scope, workflow, UX, and success criteria.
2. [High-level design](./02-hld.md) — architecture, trust boundaries, data flow, deployment, and operational model.
3. [Low-level design](./03-lld.md) — domain model, database entities, module contracts, state machines, and web endpoints.
4. [Reconciliation algorithm](./04-reconciliation-algorithm.md) — normalization, candidate generation, weighted scoring, global assignment, ambiguity, and comparison.
5. [Architecture decisions](./05-architecture-decisions.md) — selected choices, why they were selected, rejected alternatives, and consequences.
6. [Verification and delivery](./06-verification-and-delivery.md) — test strategy, synthetic evaluation, performance targets, demo, and implementation sequence.

The root [DESIGN.md](../DESIGN.md) is the earlier consolidated design. These focused documents are easier to review and should be updated first if a decision changes.

## Design principles

- Preserve source evidence and history.
- Separate transaction identity from financial agreement.
- Automate only when evidence is strong and the global solution is stable.
- Make every automatic result explainable.
- Retain manual decisions across runs without hiding later changes.
- Publish complete, reproducible results atomically.
- Keep the system deployable and understandable as a modular monolith.

## Current decisions

| Area | Decision |
|---|---|
| Release | Advanced, polished showcase in the first release |
| Access | Anonymous, isolated browser workspace; no sign-in |
| Application | Django, PostgreSQL, server-rendered templates, HTMX |
| Architecture | One repository and database; separate web and worker processes |
| Matching | Trusted references plus weighted global one-to-one assignment and ambiguity gating |
| History | Immutable files, observations, dataset revisions, and run snapshots |
| Human review | Manual link, accept unmatched, reject candidate, reaffirm, revoke |
| Scope | One-to-one reconciliation between two sources in a book |

## Document status

Status: design approved as the implementation baseline. Numeric thresholds and performance limits are initial hypotheses that must be benchmarked. No application implementation is included in this documentation set.
