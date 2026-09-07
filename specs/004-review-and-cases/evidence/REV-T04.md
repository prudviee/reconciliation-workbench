# REV-T04 Verification Evidence

- **Task:** Commit initial authority with atomic concurrency checks
- **Requirements:** `REV-001`, `REV-002`, `REV-003`, `REV-007`, `REV-008`, `REV-012`, `REV-016`
- **Acceptance scenarios:** `REV-A02`, `REV-A03`, `REV-A04`, `REV-A10`, `REV-A12`
- **Date:** 7 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence

## Atomic command boundary

`DecisionCommandService.commit_initial` accepts only LINK, ACCEPT_UNMATCHED, and REJECT_CANDIDATE. In one short database transaction it:

1. Locks and revalidates the active workspace.
2. Resolves and locks the workspace-owned book.
3. Compares the expected resolution generation.
4. Resolves every logical endpoint through workspace and book ownership and verifies LEFT/RIGHT roles.
5. Resolves every reviewed observation and proves exact correspondence with the authority endpoints.
6. Finds existing endpoint claims and returns the affected decision/revision set.
7. Appends one decision envelope and immutable first revision with canonical reviewed-evidence digest.
8. Creates two, one, or zero claims according to LINK, ACCEPT_UNMATCHED, or REJECT_CANDIDATE.
9. Increments `resolution_generation` exactly once and dirties the owning book's scopes.

An exception rolls back the envelope, revision, claims, generation, and scope changes together. The named unique claim constraint remains the database's final protection if a writer bypasses or races the application precheck.

## Authority outcomes

| Action | Revision evidence | Claim rows | Resolution generation |
|---|---|---:|---:|
| LINK | Pair endpoints, two reviewed observations, reason, actor, digest | 2 | +1 |
| ACCEPT_UNMATCHED | One endpoint/side, one reviewed observation, reason, actor, digest | 1 | +1 |
| REJECT_CANDIDATE | Relationship endpoints, two reviewed observations, reason, actor, digest | 0 | +1 |

The rejection row is durable active relationship authority and is ready for the frozen engine-input adapter in REV-T06. No assignment is run inside the decision transaction.

## Conflict and isolation evidence

- A stale expected generation returns `STALE_GENERATION` before any decision row is created.
- An already reserved endpoint returns `ENDPOINT_CLAIMED` with the owning decision and revision, instructing the caller to use replacement preview rather than stealing the claim.
- Reversed left/right endpoints, mixed-book logical IDs, foreign-workspace logical IDs, and foreign reviewed-observation IDs all produce the same unavailable outcome and no mutation.
- A revoked/expired workspace cannot create authority.
- Lifecycle actions are rejected by this initial-action boundary and remain assigned to REV-T05.

## Concurrent PostgreSQL evidence

Two independent connections attempted LINK commands at the same expected generation for the same left endpoint and different right endpoints. Exactly one committed. The persisted result contained:

- one decision;
- one revision;
- two claims;
- one resolution-generation increment.

The losing writer observed the book after the winning commit and failed safely. This proves the service-level book lock and expected generation satisfy `REV-A04`; the database unique constraint from REV-T03 remains defense in depth.

## Verification results

| Check | Result |
|---|---|
| Focused mutation/rollback/isolation/concurrency suite | 6 passed in 3.87 seconds |
| Authority, persistence, generation, and domain regression | 18 passed in 4.54 seconds |
| Django system check | Passed, 0 issues |
| Migration drift check | Passed, no changes detected |
| Full repository regression | 413 passed in 25.19 seconds |
| Diff whitespace check | Passed |

## Scope boundary

This task creates initial authority only. REAFFIRM, REVOKE, replacement preview, exact supersession, and claim swapping begin in REV-T05. Frozen engine input and proof that an active rejection excludes every automatic stage begin in REV-T06.
