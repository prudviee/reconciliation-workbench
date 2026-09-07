# 003 Reconciliation Engine — Implementation Plan

- **Status:** Approved
- **Specification:** [spec.md](./spec.md)
- **Target branch:** `codex/003-reconciliation-engine`
- **Last updated:** 7 September 2026

## Summary

Build the reconciliation decision core as an immutable, framework-independent Python package. The engine first applies durable reviewer reservations and exclusions, then establishes unique trusted-reference pairs, generates a complete bounded candidate graph, records fixed-point feature evidence, solves optional-unmatched one-to-one assignments, and confirms only edges that pass every automation and counterfactual-stability gate. Pair comparison remains separate from identity selection so authoritative and manual pairs can expose discrepancies.

The smallest coherent slice is the immutable input, policy, evidence, and output contract. Later tasks add one decision stage at a time behind pure functions. Persistence, background execution, review cases, and browser presentation belong to specifications 004 and 005; this specification returns all evidence those layers need without importing them.

## Constitution check

| Principle | How the plan complies |
|---|---|
| Evidence is immutable | Frozen value objects retain input revisions, feature evidence, solver facts, comparisons, and terminal outcomes. |
| Identity and agreement differ | Pair selection and field comparison are separate pure stages; disagreement never dissolves an authoritative or manual pair. |
| Automatic matching may abstain | Incomplete graphs, ties, contradictions, weak scores, insufficient evidence, and exceeded limits produce explicit unpaired outcomes. |
| Results are explainable | Every heuristic edge records values, presence, bands, feature basis points, weighted contributions, contradictions, proposal status, objective, and global gap. |
| Reviewer authority is durable | Manual links and accepted-unmatched reservations are consumed before automatic stages; active rejections prohibit both reference and heuristic links. |
| Runs publish atomically | The pure engine returns one validated result object. Database publication is deferred to specification 004 and can persist that object atomically. |
| Decimal/time semantics are explicit | Policies use `Decimal`, aware `datetime`, explicit currency compatibility, inclusive boundaries, and integer basis-point solver values. |
| Anonymous access is isolated | The engine accepts one already-authorized immutable snapshot and performs no lookup by public identifier. Workspace enforcement stays at the adapter boundary. |
| Domain core is framework-independent | Domain modules import only the Python standard library and a narrow solver protocol; the SciPy adapter has no Django dependency. |
| Specifications precede behavior | Every task maps to REC requirements and acceptance scenarios, and each completion records evidence. |
| Claims require evidence | Golden, exhaustive-oracle, permutation, boundary, isolation, and capacity checks close the specification. |
| Complexity earns its place | Global assignment addresses the documented greedy failure; counterfactual gaps address unstable optima; hard caps bound both costs. |

## Affected architecture

| Module/component | Change | Requirement IDs |
|---|---|---|
| `reconciliation.domain.reconciliation` | Frozen snapshot, decision, policy, pair, unpaired, diagnostic, and result contracts with invariant validation | REC-001, REC-002, REC-011–REC-017 |
| `reconciliation.domain.references` | Reservation/exclusion preprocessing and unique trusted shared-reference pairing | REC-002–REC-004, REC-020, REC-021 |
| `reconciliation.domain.candidates` | Versioned blocking-pass union, deterministic enumeration, completeness and limit evidence | REC-005, REC-013, REC-022 |
| `reconciliation.domain.scoring` | Decimal feature functions, hard compatibility rules, complete evidence, basis-point scoring | REC-006, REC-007, REC-014–REC-017, REC-020 |
| `reconciliation.domain.assignment` | Connected components, optional-unmatched assignment, objective/gap analysis, non-iterative acceptance | REC-008–REC-010, REC-013, REC-018, REC-022 |
| `reconciliation.domain.comparison` | Exact/tolerated/discrepant/not-comparable field comparison and bounded explanations | REC-004, REC-012, REC-015 |
| `reconciliation.domain.engine` | Deterministic orchestration, result validation, terminal outcome coverage, decision-health diagnostics | REC-001, REC-011, REC-013, REC-019 |
| `reconciliation.solvers.scipy_assignment` | Replaceable adapter for rectangular linear assignment using integer costs | REC-008, REC-010, REC-013 |
| `tests/` and spec evidence | Golden, boundary, exhaustive, permutation, framework-isolation, and capacity verification | REC-001–REC-022 |

## Domain contracts

### Immutable input

`EngineSnapshot` contains two ordered-independent tuples of `MatchRecord`, exact dataset revision identities, and a reference contract. A record carries a stable observation identity, source identity, eligibility/state, shared reference or local reference, optional resolved alias, instrument, side, currency, quantity, unit price, gross amount, and aware execution time. Values are already normalized by specification 002; the engine still rejects invalid types, non-finite decimals, naive times, duplicate identities, or cross-side identity collisions.

`DecisionInputs` contains immutable manual links, accepted-unmatched reservations, active rejected relationships, and reviewer-reserved identities. Validation rejects conflicting active reservations before matching rather than resolving them by tuple order.

### Versioned policy

`MatchingPolicy` contains explicit version strings, blocking passes, feature bands, basis-point weights, assignment floor, automatic threshold, minimum global gap, reference semantics, and hard capacity limits. The initial policy has weights quantity 3500, timestamp 2500, unit price 1500, and gross amount 2500; floor 7000, automatic threshold 9000, and global gap 800. Weight totals and every threshold are validated on the same 0–10,000 integer scale.

`ComparisonPolicy` contains exact decimal tolerances, aware time tolerance, compatible currency rules, boundary inclusivity, and its version. Search windows, scoring bands, and comparison tolerances are distinct fields and types so changing one cannot silently change another.

### Evidence and outcomes

`CandidateEvidence` records why every blocking pass included the edge; each feature's input values, missingness, difference, band, feature basis points, weight, and weighted contribution; hard contradictions; completeness; and total rule score. Missing features produce a zero contribution without weight redistribution.

`AssignmentComponentEvidence` records stable member IDs, graph digest, candidate count, solver version, optimal utility, selected proposed edges, counterfactual objective and global gap for each proposal, tie/limit/completeness state, and accepted subset. Counterfactuals forbid exactly one proposed edge against the same complete component. Acceptance is evaluated once and the solver is not rerun after failed gates.

Each eligible record appears exactly once in `PairOutcome` or `UnpairedOutcome`. Unpaired classifications distinguish accepted-unmatched, cancelled/excluded, manual-attention, no-candidate, below-floor, ambiguous, prohibited, and computation-limited. `EngineResult` canonicalization sorts all public tuples by stable identity so input row order cannot alter equality or serialization.

### Pure entry point

```python
reconcile(
    snapshot: EngineSnapshot,
    matching_policy: MatchingPolicy,
    comparison_policy: ComparisonPolicy,
    decisions: DecisionInputs,
    solver: AssignmentSolver,
) -> EngineResult
```

No default clock, environment read, random source, filesystem, HTTP client, ORM, or process-global configuration is permitted. Version identities are explicit inputs. The pure domain entry point can execute with Django and external I/O imports blocked.

## Data model and migrations

Not applicable. Specification 003 defines pure values and computations only. Specification 004 will map validated `EngineResult` evidence into immutable run tables and publish a completed run in one transaction.

## Web and application contracts

Not applicable. A later adapter translates authorized, frozen dataset memberships and active decision revisions into `EngineSnapshot` and `DecisionInputs`. The web layer never sends raw browser-selected IDs directly into the engine without workspace-scoped resolution.

## Background processing

Not applicable in this specification. Solver execution is synchronous and pure from the caller's perspective. Specification 004 owns job identity, retries, cancellation checks, fencing, stale-result rejection, and publication.

## UI behavior

No UI is added here. Result contracts deliberately include readable reason codes, rule-score labels, feature evidence, discrepancies, alternatives, and limitations for specification 005. Explanations use supported facts only and never infer fees, fraud, probability, or intent.

## Assignment approach

Candidate edges at or below the assignment floor remain evidence but do not enter the solver. Each complete eligible graph is split into connected components. For `n` left and `m` right records, the adapter receives an `n × (m+n)` matrix: a real allowed edge has cost `-(score_bp - floor_bp)`, a forbidden real edge has a sentinel greater than any feasible objective, and each left row has zero-cost dummy columns. This allows either side to remain unmatched and never forces a weak edge.

The implementation uses SciPy's rectangular linear assignment routine behind `AssignmentSolver`; tests do not rely on SciPy tie ordering. Small components are cross-checked against an exhaustive enumerator. Public output is deterministically ordered, and equal optimums abstain because their counterfactual global gap is zero.

## Verification plan

| Requirement | Verification layer | Planned evidence |
|---|---|---|
| REC-001 | Unit, architecture, subprocess isolation | Frozen contract tests and blocked-framework/I/O execution for REC-A12 |
| REC-002–REC-004, REC-020, REC-021 | Unit and golden scenarios | Reservation, rejection, authoritative discrepancy, semantics, and duplicate-reference matrices |
| REC-005, REC-022 | Unit, property, performance | Blocking union, deterministic enumeration, truncation propagation, 200/2,500/250,000 limits |
| REC-006, REC-007, REC-014–REC-017 | Unit and boundary | Complete feature ledger, missingness, contradiction, fixed-point and inclusive threshold fixtures |
| REC-008–REC-010, REC-018 | Golden and exhaustive oracle | Greedy counterexample, all-weak, equal optima, counterfactual gaps, and non-iterative accepted subset |
| REC-011, REC-013 | Invariant and permutation property | Exact terminal coverage and canonical result equality across input permutations |
| REC-012, REC-015 | Boundary and snapshot | Decimal/time/currency comparisons and explanation vocabulary checks |
| REC-019 | Unit | Read-only accepted-unmatched candidate diagnostics, including allocated counterpart evidence |

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Solver matrix encodes forbidden or unmatched choices incorrectly | Forced or missing pairs | Golden rectangular fixtures plus exhaustive comparison for generated small graphs |
| Tie behavior leaks solver ordering | Nondeterministic automatic links | Counterfactual gap gate, canonical ordering, and permutation tests |
| Candidate truncation is mistaken for absence | False certainty | Completeness is a required partition fact; any completeness-affecting cap withholds affected heuristic matches |
| Correlated amount and unit-price evidence inflates confidence | Unjustified automation | Preserve independent contributions, label weights as hypotheses, and report synthetic precision/recall by scenario family |
| Decimal conversion enters through float | Boundary instability | Accept `Decimal` only, reject non-finite values, and quantize score basis points with `ROUND_HALF_EVEN` |
| Counterfactual solving multiplies runtime | Capacity target missed | Hard component limits, measured workload, reusable matrices, and explicit limited outcomes |
| Conflicting reviewer inputs are silently ordered | Authority violation | Validate reservation consistency before any matching stage and return a typed input error |

## Rejected implementation approaches

| Approach | Why rejected |
|---|---|
| Greedy best-edge selection | Fails REC-A02 by consuming a counterpart needed for the greater global objective. |
| Exact-reference-only matching | Cannot demonstrate weighted evidence, one-to-one allocation, or principled ambiguity. |
| Pairwise mutual-best gating | Rejects some globally beneficial assignments and duplicates the global solver's role. |
| Iteratively delete failed proposals and resolve | Can manufacture certainty for weaker edges, violating REC-018. |
| Treat rule score as probability | No labelled calibration evidence exists and REC-014 prohibits the claim. |
| Renormalize around missing features | Makes sparse records look stronger and violates REC-007. |
| Use floats in scoring or comparison | Creates avoidable decimal and threshold ambiguity. |
| Custom production assignment algorithm | Adds correctness and performance risk without benefit over a replaceable, tested linear-assignment adapter. |
| Send candidate selection to an LLM | Nondeterministic, unsupported by evidence, and outside the explicit deterministic baseline. |

## Delivery and rollback

All changes are additive domain modules and tests on `codex/003-reconciliation-engine`. No migration or stored data changes occur. Each task produces one commit with its evidence record. Reverting a task commit removes that bounded capability. The full feature is not marked complete until the clean full suite, pure-process check, exhaustive solver comparison, and documented 10,000-by-10,000 synthetic capacity measurement pass at one commit.

## Open decisions

None. The specification and algorithm design resolve the behavior needed for implementation. Version strings and policy values are explicit, so future tuning can add a new policy without rewriting prior results.
