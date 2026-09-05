# 003 Reconciliation Engine — Specification

Status: Draft
Prefix: `REC`
Depends on: 001, 002

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

## Acceptance scenarios

- **REC-A01** A trusted `T-1011` reference with amount 34,000 versus 34,170 is paired and classified as an amount discrepancy.
- **REC-A02** Scores `[[94,92],[93,20]]` with floor 70 produce L1–R2 and L2–R1 rather than the greedy result.
- **REC-A03** Four equal eligible scores produce zero global gaps and an ambiguous result with no heuristic automatic pair.
- **REC-A04** All edges below assignment floor select unmatched options.
- **REC-A05** An edge exactly at automatic threshold and gap margin follows documented inclusive boundary behavior.
- **REC-A06** Different currencies produce a currency discrepancy and not-comparable monetary difference.
- **REC-A07** An over-limit or truncated partition reports a limitation and creates no automatic heuristic match.
- **REC-A08** Reordering either input leaves the canonical EngineResult unchanged.

## Out of scope

One-to-many allocation, settlement netting, FX conversion, calibrated ML probability, and LLM-selected pairs.

## Open questions

- Validate initial feature weights and component limits against development fixtures.
- Decide required-evidence coverage rules per source contract before status becomes Ready.
