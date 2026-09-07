# REC-T04 Verification Evidence

- **Task:** Score candidates with complete fixed-point evidence
- **Requirements:** `REC-006`, `REC-007`, `REC-009`, `REC-014`–`REC-017`, `REC-020`
- **Acceptance scenarios:** `REC-A05`, `REC-A09`, `REC-A15`, `REC-A17`
- **Date:** 7 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence; see Git history for `REC-T04`

## Implemented scope

- Exact `Decimal` linear similarity for quantity, unit price, and gross amount using the larger of absolute and relative bands.
- Exact elapsed-time similarity without binary floating-point conversion.
- `ROUND_HALF_EVEN` integer basis-point feature similarities and weighted contributions on the documented 0–10,000 scale.
- Complete four-feature evidence for every candidate, including values, absolute difference, effective band, presence, similarity, fixed weight, contribution, and factual rule.
- Missing features contribute zero without weight redistribution; structured coverage failures enforce instrument, side, currency, quantity, timestamp, and at least one paired monetary feature.
- Structured hard contradictions for instrument, side, currency, guaranteed shared-reference, and mapped shared-alias disagreement.
- Candidate completeness inherited from bounded candidate partitions, canonical evidence ordering, and explicit `Rule score` labelling.

## Checks and results

| Check | Result | Evidence summary |
|---|---|---|
| Focused scoring/candidate/reference/contract/architecture suite | Pass | 72 checks passed for exact features, bands, missingness, coverage, contradictions, fixed-point boundaries, completeness, language, ordering, and framework independence. |
| Full regression suite | Pass | 301 tests passed against the active local PostgreSQL stack in 20.44 seconds. |
| Compilation and diff integrity | Pass | Reconciliation modules and focused scoring/candidate tests compiled without error; Git whitespace validation passed. |
| Complete feature ledger | Pass | Every candidate recorded quantity, timestamp, unit-price, and gross-amount values, differences, effective bands, presence, similarity, fixed weight, contribution, and factual rule. |
| Exact feature arithmetic | Pass | Controlled 80%-50%-75%-75% similarities produced contributions 2,800/1,250/1,125/1,875 and a 7,050 rule score. Relative bands used the larger magnitude and similarity stopped at zero. |
| Fixed-point boundaries | Pass | Zero bands handled equality explicitly, exact 90% evidence produced 9,000 basis points, and `.5` contributions followed `ROUND_HALF_EVEN` in both even directions. |
| Decimal-context isolation | Pass | Changing the caller's Decimal precision to 3 and rounding to `ROUND_DOWN` did not change evidence or score. |
| Missingness and coverage | Pass | Missing features contributed zero with original weights intact; all required-field failures were explicit; one complete monetary feature satisfied the monetary coverage floor. |
| Sparse candidate | Pass | An explicit alias pass without a time window surfaced a record pair with missing timestamps, retained it as evidence, gave timestamp zero contribution, and failed automatic coverage. |
| Hard contradictions | Pass | Present instrument, side, currency, guaranteed shared-reference, and mapped shared-alias disagreements were recorded independently from the score. Missing references were not contradictions. |
| Reference semantics | Pass | Unequal source-local IDs remained eligible evidence under `SOURCE_LOCAL_OR_ALIAS`; conflicting mapped aliases were prohibited by a structured contradiction. |
| Computation completeness | Pass | A candidate touching a truncated partition carried `complete_computation=False`. |
| Explanation language | Pass | Evidence was labelled `Rule score` and contained no unsupported fee, fraud, intent, or probability claim. |
| Determinism and validation | Pass | Reordered candidate inputs produced equal evidence; edges outside the remaining preprocessed records were rejected. |

## Scope boundary

This task calculates evidence but does not select pairs. REC-T05 performs optional-unmatched global assignment; REC-T06 applies score, coverage, contradiction, completeness, and counterfactual-gap gates.
