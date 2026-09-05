# Reconciliation Workbench

An explainable transaction-reconciliation system that preserves source evidence, performs constrained one-to-one matching, exposes field-level discrepancies, and carries reviewer decisions safely across corrected files and later runs.

This project uses spec-driven development end to end.

## Start here

- [Specification workflow](./specs/README.md)
- [Project constitution](./specs/constitution.md)
- [Feature roadmap](./specs/roadmap.md)
- [Critical design review](./specs/reviews/2026-09-05-critical-review.md)
- [Design documentation](./docs/README.md)
- [Consolidated design](./DESIGN.md)

## Development rule

Every feature follows this path:

```text
Problem → Spec → Acceptance scenarios → Plan → Tasks → Implementation → Verification → Evidence
```

No feature implementation starts while its specification contains unresolved decisions or lacks testable acceptance scenarios. When behavior changes, the specification changes in the same commit or before the implementation.
