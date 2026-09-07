# Specification Roadmap

This roadmap orders feature specifications by dependency. It does not reduce the advanced first-release scope.

| Order | Specification | Prefix | Depends on | Current status | Outcome |
|---:|---|---|---|---|---|
| 001 | Foundation and anonymous workspace | FND | Constitution | Verified | Runnable project, workspace isolation, shared domain vocabulary |
| 002 | Source mapping and ingestion | ING | 001 | Verified | Immutable evidence, validation preview, dataset revisions |
| 003 | Reconciliation engine | REC | 001, 002 | Verified | Exact, weighted-global, ambiguity, comparison, pure engine |
| 004 | Decisions and stable cases | REV | 001–003 | Ready | Durable review authority, case history, concurrency safety |
| 005 | Workbench and run history | UX | 001–004 | Ready | Polished complete user workflow and accessible evidence |
| 006 | Jobs, operations, and deployment | OPS | 001–005 | Ready | Reliable background execution, observability, retention, deployment |

## Milestone 1: executable foundation

Specifications 001 and the minimum cross-cutting contracts establish Django/PostgreSQL project structure, anonymous workspace authorization, domain value conventions, and continuous verification.

Exit evidence:

- Workspace isolation integration tests.
- Health checks and local development instructions.
- Domain package imports no Django model or web types.

## Milestone 2: trustworthy evidence

Specification 002 implements upload, adapter contracts, mapping preview, validation, physical/semantic/state hashes, full-snapshot/delta semantics, observations, and membership.

Exit evidence:

- Original → correction → original replay does not roll back current state.
- Malformed snapshot cannot replace a valid head.
- Two predefined adapters and one configurable mapping pass contract tests.

## Milestone 3: advanced reconciliation

Specification 003 delivers trusted references, candidate blocking, weighted evidence, optional global assignment, sensitivity gating, field comparison, and deterministic result partitioning.

Exit evidence:

- Greedy counterexample and tied ambiguity behave as specified.
- Solver objective agrees with exhaustive tiny-graph solutions.
- Held-out synthetic evaluation records precision, recall, candidate recall, review rate, and runtime.

## Milestone 4: durable human review

Specification 004 implements manual links, accepted unmatched records, rejected candidates, reaffirmation, revocation, health alerts, stable cases, and atomic claims.

Exit evidence:

- Decisions survive correction and rerun as specified.
- Conflicting endpoint claims cannot both succeed.
- Historical decisions and reversals remain visible.

## Milestone 5: polished showcase workflow

Specification 005 builds import/setup, workbench, case evidence, candidate graph explanation, filters, history, comparison between runs, and exports.

Exit evidence:

- Complete keyboard-operable browser journey.
- Paired, comparison, and review dimensions remain separate.
- Curated demo completes in under five minutes without developer tools.

## Milestone 6: release reliability

Specification 006 provides job leasing/fencing, retries, conditional publication, expiry cleanup, security checks, observability, capacity measurements, and deployment.

Exit evidence:

- Late workers and stale runs cannot replace current results.
- Deployed workspace retention matches the interface.
- Release gate in `docs/06-verification-and-delivery.md` passes.

## Cross-specification rules

- A feature may depend on a stable interface from an earlier spec before the earlier UI is complete.
- Temporary stubs must be named in the plan and removed by a mapped task.
- Cross-spec changes update every affected spec and plan in the same branch.
- Specifications are verified in order of dependency, while design and test work may overlap.
- A milestone is complete only when its verification evidence is committed.

`Ready` means the behavioral specification is ready for implementation planning. It does not mean the dependency has been implemented or the feature has been verified.
