# REV-T01 Verification Evidence

- **Task:** Define immutable review and stable-case contracts
- **Requirements:** `REV-001`, `REV-002`, `REV-005`, `REV-009`, `REV-012`, `REV-013`
- **Acceptance scenarios:** `REV-A10`, `REV-A11`, `REV-A13`
- **Date:** 7 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence

## Implemented contracts

- Six exact actions: LINK, ACCEPT_UNMATCHED, REJECT_CANDIDATE, REAFFIRM, REVOKE, and REPLACE.
- Three active authority shapes with explicit endpoint behavior. LINK reserves two endpoints, accepted-unmatched reserves one, and rejection reserves none.
- Mandatory nonblank reason and actor, nonnegative expected resolution generation, expected target revision, explicit replacement-conflict revisions, and reviewed observation baselines.
- Strict action compatibility: initial actions require their matching authority, reaffirm/revoke require an existing target, and replacement requires a target plus new authority.
- Replacement previews retain every conflicting decision, current revision, and claimed endpoint and expose the canonical expected conflict set needed for commit.
- Exact health vocabulary separated from attention reasons and authority: UNCHANGED, EVIDENCE_CHANGED, PARTNER_UNAVAILABLE, and NEW_CANDIDATE.
- Versioned length-prefixed SHA-256 keys for pair, unpaired, and ambiguity cases.
- Immutable occurrence and many-to-many lineage plan values with matching case/result kinds, no self-edges, no duplicates, and deterministic ordering.

## Action and baseline matrix

| Action | Authority supplied | Existing target | Reviewed observations | Endpoint reservation |
|---|---|---|---:|---|
| LINK | Left/right pair | No | 2 | Both |
| ACCEPT_UNMATCHED | One identity and side | No | 1 | One |
| REJECT_CANDIDATE | Left/right relation | No | 2 | None |
| REAFFIRM | Inherited from target | Yes | 1–2 fresh observations | Unchanged |
| REVOKE | None | Yes | 0 | Released by later service |
| REPLACE | New authority | Yes | Matches new authority endpoints | Defined by new authority |

Every row rejects a missing reason. Initial actions reject targets or conflict approvals. Reaffirm rejects a missing fresh baseline. Revoke rejects authority/baseline/conflict payloads. Replacement canonicalizes multiple conflict revisions and rejects duplicate or target-repeating approvals.

## Stable digest vectors

The vectors lock the key encoding across processes and later persistence adapters.

| Kind | Inputs | Stable key |
|---|---|---|
| Pair | book B1, left L1, right R1 | `pair:3b240f5dcff6118f57187c5fb1d7c6e9fbbe3d88e42864db072d18ee1518888d` |
| Unpaired | book B1, LEFT, L1 | `unpaired:447604f540f372bbe760079086117d8780249f99435df2bd4049f140383d4c24` |
| Ambiguity | book B1, scope S1, policy `11…11`, left L1/L2, right R1/R2 | `ambiguity:67765459c8ca0f0510e045688096cb62f45d7ee34a9c8397fa4c1cb21647bfa8` |

Pair order is semantic and is not sorted. Ambiguity members are sorted within their declared sides. Changing book, scope, policy digest, side, or complete member set changes the key.

## Verification results

| Check | Result |
|---|---|
| Focused review contracts plus framework boundary | 25 passed in 1.13 seconds |
| Review and existing engine contract regression | 60 passed in 4.16 seconds |
| Full repository regression | 395 passed in 20.72 seconds |
| Domain import without Django/settings/database | Passed |
| Diff whitespace check | Passed |

## Scope boundary

This task defines pure immutable values only. Database ownership, endpoint-role checks, PostgreSQL claim concurrency, mutations, health computation, and case transition discovery begin in REV-T02 through REV-T09. Browser presentation remains in specification 005.
