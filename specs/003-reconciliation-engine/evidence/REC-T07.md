# REC-T07 Verification Evidence

- **Task:** Compare paired fields with exact explicit semantics
- **Requirements:** `REC-004`, `REC-012`, `REC-015`
- **Acceptance scenarios:** `REC-A01`, `REC-A06`, `REC-A16`
- **Date:** 7 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence; see Git history for `REC-T07`

## Implemented scope

- Pairing remains independent from comparison: manual, authoritative-reference, and weighted-global pairs use the same field ledger and are never unpaired because values disagree.
- Canonically ordered comparisons for reference, instrument, side, quantity, timestamp, unit price, gross amount, currency, and versioned state compatibility.
- Exact `Decimal` signed differences and `max(absolute, relative × larger absolute value)` allowances with inclusive boundaries.
- Elapsed, timezone-aware timestamp comparison with exact instants, signed differences, and an inclusive configured tolerance.
- Currency equality is explicit; unlike or missing currencies make monetary values not comparable and prevent subtraction.
- Shared-reference and source-local/shared-alias contracts compare the correct reference namespace and state the pair origin.
- Missing values, exact values, tolerated differences, discrepancies, and not-comparable results retain source values and factual explanations.
- Comparison evidence rejects mismatched difference types, one-sided difference metadata, negative allowances, and calculated differences on missing or not-comparable fields.
- Corrected the versioned demo policy to its approved design values: quantity `0.00000001`, timestamp 60 seconds, unit price `0.01`, and gross amount `0.05`.

## Boundary fixtures

| Field | Exact inclusive boundary | Immediately beyond | Result |
|---|---:|---:|---|
| Quantity | `10` vs `10.00000001` | `10` vs `10.000000011` | Within tolerance; discrepant |
| Unit price | `100` vs `100.01` | `100` vs `100.0100001` | Within tolerance; discrepant |
| Gross amount | `1000` vs `1000.05` | `1000` vs `1000.050001` | Within tolerance; discrepant |
| Timestamp | 60 seconds | 60.000001 seconds | Within tolerance; discrepant |
| Timestamp instant | `12:00 UTC` vs `17:30 +05:30` | Not applicable | Exact |
| Relative quantity | `100` vs `101` at 1% | Not applicable | Allowed difference `1.01`; within tolerance |

## Explanation snapshots

| Scenario | Stored result | Factual explanation |
|---|---|---|
| Timestamp at boundary | `WITHIN_TOLERANCE` | `Timestamp differs by 60 seconds; the allowed elapsed difference is 60 seconds.` |
| Authoritative amount discrepancy | `DISCREPANT`, signed difference `170`, allowed `0.05` | `Gross amount differs by 170; the allowed difference is 0.05.` |
| Currency mismatch | Currency `DISCREPANT`; money `NOT_COMPARABLE` | `Gross amount is not comparable because currencies differ: left is USD and right is EUR.` |
| Shared authoritative reference | `EXACT` | `Shared reference is exactly equal at T-1011; the pair origin is authoritative reference.` |
| Compatible unequal states | `WITHIN_TOLERANCE` | The observed states and versioned policy compatibility are stated explicitly. |

## Checks and results

| Check | Result | Evidence summary |
|---|---|---|
| Focused comparison/contract/reference/scoring/architecture suite | Pass | 83 checks passed for comparison semantics, exact boundaries, immutable contracts, prior reference/scoring behavior, and framework isolation. |
| Full regression suite | Pass | 351 tests passed against the active local PostgreSQL stack in 69.28 seconds. |
| Authoritative discrepancy | Pass | Trusted reference `T-1011` remained paired while 34,000 versus 34,170 produced a gross-amount discrepancy with signed difference 170. |
| Decimal boundaries | Pass | Quantity, unit-price, and gross-amount values exactly on their configured boundaries passed; the smallest tested value beyond each boundary failed. |
| Timestamp boundaries | Pass | Exactly 60 seconds passed, 60.000001 seconds failed, and timezone-offset representations of the same instant were exact. |
| Currency safety | Pass | USD versus EUR produced a currency discrepancy and no unit-price or gross-amount subtraction. Missing currency also produced explicit not-comparable monetary evidence. |
| Reference contracts | Pass | Shared references and shared aliases used their declared namespaces; unequal source-local IDs did not override equal shared aliases. |
| State compatibility | Pass | Equal states were exact; unequal states followed the versioned directional compatibility matrix. |
| Explanation language | Pass | Snapshots state observed values, differences, limits, rules, and origin; unsupported fee, fraud, intent, or delay claims are absent. |
| Determinism | Pass | Repeated comparisons returned equal immutable evidence in canonical field order. |

## Scope boundary

This task compares fields only after identity pairing has been established. REC-T08 assembles manual, authoritative, and accepted weighted-global pairs with these comparisons into a complete deterministic engine result.
