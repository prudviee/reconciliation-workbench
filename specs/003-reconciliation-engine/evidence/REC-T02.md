# REC-T02 Verification Evidence

- **Task:** Apply exclusions, reviewer reservations, and trusted references
- **Requirements:** `REC-002`–`REC-004`, `REC-020`, `REC-021`
- **Acceptance scenarios:** `REC-A01`, `REC-A13`, `REC-A17`, `REC-A18`
- **Date:** 7 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence; see Git history for `REC-T02`

## Implemented scope

- Deterministic preprocessing partition that keeps each snapshot input in exactly one manual/authoritative pair, explicit terminal outcome, or remaining automatic-matching set.
- Cancellation exclusion, accepted-unmatched reservation, generic reviewer reservation, and stale manual-link attention before every automatic stage.
- Manual pair precedence without compatibility filtering; field comparison remains a later independent stage.
- Active rejection relationships retained as explicit prohibitions for authoritative and later heuristic stages.
- Unique trusted shared-reference matching and source-local-or-explicit-alias behavior.
- Duplicate trusted references on either side withheld from automation with the complete conflicting left/right member set.
- Wrong-side relationship decisions rejected at the domain boundary; absent historical endpoints do not fabricate inputs or outcomes.

## Checks and results

| Check | Result | Evidence summary |
|---|---|---|
| Focused reference/contract/architecture suite | Pass | 42 checks passed for precedence, partition integrity, trusted references, reservations, active rejections, reference semantics, ordering, and framework independence. |
| Full regression suite | Pass | 271 tests passed against the active local PostgreSQL stack in 15.56 seconds. |
| Compilation and diff integrity | Pass | Domain modules and focused tests compiled without error; Git whitespace validation passed. |
| Authoritative reference | Pass | A unique trusted `T-1011` pair was selected despite a gross-amount discrepancy and despite complete non-reference field disagreement. |
| Manual precedence | Pass | Valid manual links reserved both endpoints without compatibility filtering; absent or cancelled partners produced explicit attention for the eligible endpoint. |
| Reservation precedence | Pass | Cancelled, accepted-unmatched, and reviewer-reserved records never entered authoritative matching; cancellation remained the stronger outcome. |
| Active rejection | Pass | A rejected unique trusted-reference relationship produced no automatic pair, preserved the prohibition revision, and left the identities available only for permitted later relationships. |
| Duplicate reference | Pass | Duplicates on the left, right, and one side alone produced no pair and reported every conflicting member; reservations were applied before uniqueness assessment. |
| Reference semantics | Pass | Source-local IDs did not pair; equal explicit shared aliases did pair; unequal aliases remained for later evidence and contradiction evaluation. |
| Determinism and validation | Pass | Reordered records/decisions produced equal results, and relationship endpoints placed on the wrong side were rejected. |

## Scope boundary

This task selects only manual and authoritative-reference pairs. Remaining records and prohibited relationships feed REC-T03 candidate generation. Comparison evidence is added by REC-T07.
