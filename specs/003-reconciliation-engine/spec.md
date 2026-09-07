# 003 Reconciliation Engine — Specification

- **Status:** Verified
- **Prefix:** `REC`
- **Depends on:** 001, 002
- **Reviewed:** 7 September 2026

## Outcome

The pure deterministic engine identifies authoritative and globally justified one-to-one pairs, deliberately abstains on ambiguity, compares paired values, and explains every outcome.

## Requirements

- **REC-001** The pure engine MUST accept immutable snapshots, matching/comparison policies, and decision inputs without database, HTTP, file, clock, or network access.
- **REC-002** Cancelled records and reviewer-reserved identities MUST be removed from automatic matching with explicit outcomes.
- **REC-003** A unique trusted shared reference MUST establish a pair unless an active rejection or reservation prohibits it.
- **REC-004** Reference pairing MUST remain paired when other fields disagree and MUST expose those discrepancies.
- **REC-005** Candidate generation MUST union versioned blocking passes and distinguish search windows from scoring bands and comparison tolerances.
- **REC-006** Heuristic edges MUST store complete feature evidence, missingness, contradictions, and fixed-point score contributions.
- **REC-007** Missing features MUST contribute zero and MUST NOT cause remaining weights to renormalize.
- **REC-008** Eligible bounded components MUST use optional-unmatched global one-to-one assignment.
- **REC-009** A proposed heuristic edge MUST pass score, evidence, contradiction, complete-computation, and counterfactual global-gap gates before automatic confirmation.
- **REC-010** Equal optimal assignments and incomplete/over-limit components MUST abstain.
- **REC-011** Each eligible input MUST have exactly one terminal outcome: one pair or one explicit unpaired classification.
- **REC-012** Field comparison MUST use exact decimals, explicit currencies, timezone-aware timestamps, versioned compatibility, and inclusive tolerances.
- **REC-013** Identical inputs and versions MUST produce identical outcomes regardless of input row ordering.
- **REC-014** Matching scores MUST be described as rule scores, never probabilities, unless a separately calibrated model is introduced.
- **REC-015** Explanations MUST state evidence and MUST NOT infer fees, fraud, or business intent without structured support.
- **REC-016** Heuristic automatic matching MUST require instrument, side, currency, quantity, timestamp, and at least one monetary field to be present and valid.
- **REC-017** Scores MUST use the versioned demo weights and basis-point units defined in the algorithm design; thresholds MUST be applied on the same integer scale.
- **REC-018** After ambiguity gating, the engine MUST retain the accepted subset and MUST NOT repeatedly eliminate alternatives until weaker edges appear certain.
- **REC-019** Decision-health candidate diagnostics MUST be read-only and MUST NOT feed reserved identities into assignment.
- **REC-020** Under `SHARED_MUST_AGREE`, two present unequal references in the guaranteed shared namespace MUST prohibit heuristic automatic pairing; under `SOURCE_LOCAL_OR_ALIAS`, unequal local IDs MUST NOT be treated as a contradiction unless mapped shared aliases conflict.
- **REC-021** A non-unique trusted shared reference on either side MUST produce an ambiguity outcome and MUST NOT create an authoritative automatic pair.
- **REC-022** The initial policy MUST cap a solved component at 100 real nodes and 2,500 edges, a run at 250,000 candidate edges, and enumeration at 200 candidates per record; reaching a completeness-affecting cap MUST withhold heuristic automatic matches for the affected partition.

## Acceptance scenarios

- **REC-A01** A trusted `T-1011` reference with amount 34,000 versus 34,170 is paired and classified as an amount discrepancy.
- **REC-A02** Scores `[[94,92],[93,20]]` with floor 70 produce L1–R2 and L2–R1 rather than the greedy result.
- **REC-A03** Four equal eligible scores produce zero global gaps and an ambiguous result with no heuristic automatic pair.
- **REC-A04** All edges below assignment floor select unmatched options.
- **REC-A05** An edge exactly at automatic threshold and gap margin follows documented inclusive boundary behavior.
- **REC-A06** Different currencies produce a currency discrepancy and not-comparable monetary difference.
- **REC-A07** An over-limit or truncated partition reports a limitation and creates no automatic heuristic match.
- **REC-A08** Reordering either input leaves the canonical EngineResult unchanged.
- **REC-A09** Given a sparse candidate missing quantity or timestamp, even when its available fields agree, then it cannot become an automatic heuristic pair.
- **REC-A10** Given an accepted-unmatched identity with a new plausible record, then the diagnostic reports the candidate and any current allocation without changing assignment.
- **REC-A11** Given a selected component where one proposed edge fails its global gap, then removing that edge does not trigger a second weaker automatic-selection loop.
- **REC-A12** Given plain immutable values and an injected policy, when the engine runs in a process with Django, database, filesystem, clock, and network access unavailable, then it returns the same canonical result as the normal process.
- **REC-A13** Given cancelled, manually linked, accepted-unmatched, and actively rejected relationships including a trusted-reference pair, when automatic matching runs, then each is excluded, reserved, or prohibited with an explicit outcome and none enters a forbidden candidate or authoritative pair.
- **REC-A14** Given two versioned blocking passes where either pass discovers a valid edge, when candidates are generated, then the complete union is scored; changing a search window does not silently change the score band or comparison tolerance.
- **REC-A15** Given a weighted candidate with a missing monetary feature and a hard contradiction, when its explanation is rendered, then every feature's presence, contribution, and rule is recorded, the contradiction prevents automation, the score is labelled a rule score, and no unsupported fee, fraud, or intent claim appears.
- **REC-A16** Given decimals and timestamps exactly on and immediately beyond configured inclusive comparison tolerances, when paired fields are compared, then boundary values agree, beyond-boundary values disagree, and timezone-equivalent instants compare as equal.
- **REC-A17** Given otherwise identical records with unequal present references, when the contract is `SHARED_MUST_AGREE`, then heuristic automation is prohibited; when the same IDs are source-local under `SOURCE_LOCAL_OR_ALIAS` with no conflicting shared alias, then they remain eligible for weighted evidence.
- **REC-A18** Given one trusted reference repeated by two records on either side, when authoritative matching runs, then no pair is selected for that reference and the full conflicting member set is reported as ambiguous.

## Invariants and failure behavior

- Manual and accepted-unmatched reservations precede every automatic stage. (`REC-002`)
- Rejected relationships block authoritative and heuristic automatic links while active. (`REC-003`)
- Reference matches bypass heuristic compatibility gates only to expose discrepancies, never to suppress them. (`REC-004`)
- Candidate enumeration completeness is part of the evidence. A truncated graph cannot produce a global-certainty claim. (`REC-005`, `REC-009`, `REC-022`)
- Solver tie-breaking can affect internal proposal order but cannot affect confirmed output because zero-gap edges abstain. (`REC-010`, `REC-013`)
- Scores and global gaps describe stability under one versioned policy, not probability or financial truth. (`REC-014`, `REC-015`)

## Performance and capacity

The initial hard safeguards are defined by `REC-022`. The implementation plan must benchmark them on the documented 10,000-by-10,000 synthetic workload. (Constitution XI)

## Out of scope

One-to-many allocation, settlement netting, FX conversion, calibrated ML probability, and LLM-selected pairs.

## Resolved decisions

- The initial demo policy uses quantity 35, timestamp 25, unit price 15, and gross amount 25; floor 7000 basis points, automatic threshold 9000, and global gap 800. These are versioned hypotheses and must be evaluated rather than presented as standards.
- Automatic heuristic acceptance requires every hard-gate field, quantity, timestamp, and at least one valid monetary feature. Missing scored fields still contribute zero. A source-specific policy may require more evidence, never less than this first-release floor.

## Requirement-to-scenario matrix

| Requirement | Scenarios |
|---|---|
| REC-001 | REC-A12 |
| REC-002 | REC-A13 |
| REC-013 | REC-A08 |
| REC-019 | REC-A10 |
| REC-003 | REC-A01, REC-A13 |
| REC-004 | REC-A01 |
| REC-005 | REC-A07, REC-A14 |
| REC-006, REC-007, REC-014, REC-015 | REC-A09, REC-A15 |
| REC-008 | REC-A02, REC-A04 |
| REC-009 | REC-A02, REC-A03, REC-A05, REC-A07, REC-A09, REC-A15 |
| REC-010 | REC-A03, REC-A07 |
| REC-011 | REC-A02, REC-A03, REC-A04 |
| REC-012 | REC-A01, REC-A05, REC-A06, REC-A16 |
| REC-016 | REC-A09 |
| REC-017 | REC-A02, REC-A05 |
| REC-018 | REC-A11 |
| REC-020 | REC-A17 |
| REC-021 | REC-A18 |
| REC-022 | REC-A07 |

## Change history

| Date | Change | Reason |
|---|---|---|
| 5 September 2026 | Initial draft | Define advanced deterministic matcher |
| 5 September 2026 | Fixed evidence coverage, score policy, diagnostic isolation, non-iterative gating, limits, and traceability; marked Ready | Critical SDD review |
