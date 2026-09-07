# 003 Reconciliation Engine — Tasks

- **Status:** In Progress
- **Specification:** [spec.md](./spec.md)
- **Plan:** [plan.md](./plan.md)

## Task conventions

- `[ ]` pending, `[~]` in progress, `[x]` verified, `[!]` blocked.
- Each task includes implementation, verification, and evidence in one commit.
- Task order follows the engine pipeline; a later task cannot weaken an earlier reservation, completeness, or abstention invariant.

## Phase 1: immutable decision contracts

- [x] **REC-T01 — Define immutable engine inputs, policies, and outcomes** (`REC-001`, `REC-011`–`REC-017`, `REC-020`, `REC-022`; `REC-A05`, `REC-A08`, `REC-A12`)
  - Change: frozen record/snapshot, decision, policy, feature, pair, unpaired, component, diagnostic, and result value objects with strict validation and canonical ordering.
  - Verify: framework-free imports, invalid decimal/time/identity/policy boundaries, initial 3,500/2,500/1,500/2,500 weights and 7,000/9,000/800 thresholds, and terminal-coverage validator.
  - Evidence: focused unit results and public-contract inventory.

- [x] **REC-T02 — Apply exclusions, reviewer reservations, and trusted references** (`REC-002`–`REC-004`, `REC-020`, `REC-021`; `REC-A01`, `REC-A13`, `REC-A17`, `REC-A18`)
  - Change: deterministic preprocessing for cancellation, manual links, accepted-unmatched/reserved identities, active rejection prohibitions, reference semantics, unique reference pairs, and duplicate-reference ambiguity.
  - Verify: precedence matrix including rejected trusted reference, invalid manual endpoint, discrepancies retained on authoritative/manual pairs, local-ID mismatch, alias conflict, and full duplicate member sets.
  - Evidence: golden preprocessing table and focused tests.

## Phase 2: candidate evidence

- [x] **REC-T03 — Generate a complete bounded union of blocking passes** (`REC-005`, `REC-013`, `REC-022`; `REC-A07`, `REC-A08`, `REC-A14`)
  - Change: versioned pass definitions, deterministic union/deduplication, per-edge inclusion reasons, 200-per-record and 250,000-per-run enforcement, partition completeness evidence.
  - Verify: either-pass discovery, order invariance, exact limit boundaries, truncation, and separation of search windows from scoring/comparison settings.
  - Evidence: generated blocking fixtures and completeness matrix.

- [x] **REC-T04 — Score candidates with complete fixed-point evidence** (`REC-006`, `REC-007`, `REC-009`, `REC-014`–`REC-017`, `REC-020`; `REC-A05`, `REC-A09`, `REC-A15`, `REC-A17`)
  - Change: Decimal quantity/time/price/amount features, basis-point contributions, missingness, coverage gate, hard contradictions, reference rule, and rule-score explanations.
  - Verify: every band boundary, half-even quantization, missing feature zero/no renormalization, sparse automation refusal, contradictory shared reference, local reference eligibility, exact threshold inclusivity, and forbidden vocabulary.
  - Evidence: feature ledger fixtures and boundary table.

## Phase 3: global selection and abstention

- [x] **REC-T05 — Solve bounded optional-unmatched one-to-one assignment** (`REC-008`, `REC-010`, `REC-013`, `REC-017`, `REC-022`; `REC-A02`, `REC-A04`, `REC-A07`, `REC-A08`)
  - Change: candidate connected components, replaceable solver protocol, SciPy rectangular adapter, dummy unmatched choices, forbidden sentinels, objectives, and component limits of 100 real nodes/2,500 edges.
  - Verify: greedy counterexample, unequal sides, all below-floor, forbidden edges, disconnected components, limit boundaries, and exhaustive oracle parity on generated small graphs.
  - Evidence: solver golden fixtures, oracle results, and component evidence.

- [x] **REC-T06 — Gate proposals by counterfactual global stability once** (`REC-009`, `REC-010`, `REC-018`; `REC-A03`, `REC-A05`, `REC-A07`, `REC-A09`, `REC-A11`)
  - Change: forbid-one-edge counterfactual objectives/gaps, equal-optimum abstention, inclusive threshold/gap gates, completeness/coverage/contradiction gates, and single-pass accepted-subset retention.
  - Verify: four-edge tie, exact threshold/margin, failed edge without weaker re-solve, over-limit abstention, and generated brute-force gap parity.
  - Evidence: counterfactual decision table and oracle comparison.

## Phase 4: comparison and orchestration

- [x] **REC-T07 — Compare paired fields with exact explicit semantics** (`REC-004`, `REC-012`, `REC-015`; `REC-A01`, `REC-A06`, `REC-A16`)
  - Change: exact/tolerated/discrepant/not-comparable results for reference, instrument, side, quantity, timestamp, unit price, gross amount, and currency; factual explanations only.
  - Verify: exact and immediately beyond inclusive decimal/time tolerances, timezone-equivalent instants, unlike-currency monetary refusal, and authoritative discrepancy preservation.
  - Evidence: boundary fixtures and explanation snapshots.

- [x] **REC-T08 — Orchestrate deterministic complete engine results** (`REC-001`, `REC-011`, `REC-013`; `REC-A02`–`REC-A04`, `REC-A08`, `REC-A12`)
  - Change: pure stage orchestration, canonical graph/result digests, exactly-one terminal outcome validation, stable reason ordering, and public `reconcile` entry point.
  - Verify: end-to-end golden scenarios, hundreds of input permutations, duplicate/missing terminal-outcome mutation tests, and subprocess execution with framework/I/O access blocked.
  - Evidence: canonical result fixtures and isolated-process output digest.

- [x] **REC-T09 — Add read-only accepted-unmatched decision-health diagnostics** (`REC-019`, `REC-022`; `REC-A10`)
  - Change: separate bounded diagnostic search over accepted-unmatched records, plausible candidates, current allocation facts, and explicit limited state without assignment mutation.
  - Verify: newly plausible free/allocated counterpart, unchanged selected pairs and unpaired outcomes, incomplete diagnostic warning, and deterministic ordering.
  - Evidence: before/after result identity and diagnostic fixture.

## Phase 5: release evidence

- [ ] **REC-T10 — Measure and close reconciliation acceptance** (`REC-001`–`REC-022`; `REC-A01`–`REC-A18`)
  - Change: labelled synthetic corpus, exact/reference baseline comparison, advanced matcher evaluation, 10,000-by-10,000 bounded workload, README scope update, and final traceability.
  - Verify: automatic precision/recall and candidate recall use documented denominators; every scenario/requirement has linked evidence; full suite and clean Compose gate pass at one commit.
  - Evidence: labelled synthetic metrics, component/runtime/memory measurements, limitations, completed verification record, and final tested commit.

## Final traceability

| Requirement | Task IDs | Acceptance/evidence | Complete |
|---|---|---|---|
| REC-001 | REC-T01, REC-T08, REC-T10 | REC-A12 | Partial: T01, T08 |
| REC-002 | REC-T02, REC-T10 | REC-A13 | Partial: T02 |
| REC-003 | REC-T02, REC-T10 | REC-A01, REC-A13 | Partial: T02 |
| REC-004 | REC-T02, REC-T07, REC-T10 | REC-A01 | Partial: T02, T07 |
| REC-005 | REC-T03, REC-T10 | REC-A07, REC-A14 | Partial: T03 |
| REC-006, REC-007 | REC-T04, REC-T10 | REC-A09, REC-A15 | Partial: T04 |
| REC-008 | REC-T05, REC-T10 | REC-A02, REC-A04 | Partial: T05 |
| REC-009, REC-010 | REC-T04–REC-T06, REC-T10 | REC-A02, REC-A03, REC-A05, REC-A07, REC-A09, REC-A15 | Partial: T04–T06 |
| REC-011 | REC-T01, REC-T08, REC-T10 | REC-A02–REC-A04 | Partial: T01, T08 |
| REC-012 | REC-T07, REC-T10 | REC-A01, REC-A05, REC-A06, REC-A16 | Partial: T07 |
| REC-013 | REC-T01, REC-T03, REC-T05, REC-T08, REC-T10 | REC-A08 | Partial: T01, T03, T05, T08 |
| REC-014, REC-015 | REC-T01, REC-T04, REC-T07, REC-T10 | REC-A15 | Partial: T01, T04, T07 |
| REC-016, REC-017 | REC-T01, REC-T04, REC-T05, REC-T10 | REC-A05, REC-A09 | Partial: T01, T04–T05 |
| REC-018 | REC-T06, REC-T10 | REC-A11 | Partial: T06 |
| REC-019 | REC-T09, REC-T10 | REC-A10 | Partial: T09 |
| REC-020 | REC-T01, REC-T02, REC-T04, REC-T10 | REC-A17 | Partial: T01–T02, T04 |
| REC-021 | REC-T02, REC-T10 | REC-A18 | Partial: T02 |
| REC-022 | REC-T01, REC-T03, REC-T05, REC-T09, REC-T10 | REC-A07 | Partial: T01, T03, T05, T09 |

## Deferred work

- Run persistence, worker lifecycle, atomic publication, cases, and durable reviewer actions remain in [004-review-and-cases](../004-review-and-cases/spec.md).
- Evidence drawers, assignment visualization, workbench actions, exports, and responsive browser behavior remain in [005-workbench](../005-workbench/spec.md).
- Scheduled runs, production storage, deployment, retention execution, and operational alerting remain in [006-operations](../006-operations/spec.md).
