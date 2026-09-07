# REV-T03 Verification Evidence

- **Task:** Persist append-only decisions, revisions, supersessions, and claims
- **Requirements:** `REV-001`, `REV-002`, `REV-003`, `REV-004`, `REV-009`, `REV-016`
- **Acceptance scenarios:** `REV-A05`, `REV-A10`, `REV-A11`, `REV-A12`
- **Date:** 7 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence

## Implemented schema

| Table | Durable role | Key database protections |
|---|---|---|
| `decision` | Workspace/book-owned envelope with mutable current-revision pointer | Workspace/book index; protected revision pointer |
| `decision_revision` | Append-only action, authority shape, endpoints, reason, actor, reviewed baseline, and predecessor | Unique revision number; one successor per predecessor; positive revision; nonblank reason/actor; distinct pair endpoints; valid action/authority/endpoint shape |
| `decision_supersession` | Append-only edge from one replacement revision to every displaced authority revision | Unique edge; no self-edge; protected superseded evidence |
| `active_decision_claim` | Current endpoint reservation for a reserving authority | Unique `(book, logical_transaction)` and `(decision_revision, logical_transaction)` |

`resolutions` is a registered Django/distribution package. Its immutable models reject instance updates/deletes and its querysets reject bulk update/delete. Mutable decision envelopes and active claims are intentionally separate from revision and supersession evidence.

## History and replacement evidence

- A decision's predecessor chain records its own ordered revisions and cannot branch.
- A replacement can record multiple supersession edges, including its prior revision and an authority from another decision. This preserves every affected decision rather than collapsing conflicts into one predecessor.
- Original and replacement reasons remain readable in revision order after the current pointer moves.
- Rejection revisions have relationship endpoints but no automatic claim rows; claim mutation is owned by REV-T04.

## Claim and shape evidence

- Competing claim rows for one logical identity in the same book fail the named PostgreSQL unique constraint.
- LINK and REJECT_CANDIDATE rows require two distinct pair endpoints and no single endpoint.
- ACCEPT_UNMATCHED rows require one logical identity plus LEFT/RIGHT side and no pair endpoints.
- REVOKE rows require no active authority fields.
- Initial action names must match their authority kinds; REAFFIRM and REPLACE may carry any supported active authority kind.
- Cross-row workspace, book, and source-side checks cannot be expressed safely as SQL `CHECK` constraints. They are explicitly assigned to the locked command service in REV-T04; the database-local shape is already enforced here.

## Isolation evidence

`WorkspaceDecisionRepository` resolves the owned book before decision, revision, history, or claim reads. A real ID supplied with the wrong book or workspace produces the same `DecisionUnavailable` outcome as an absent resource and returns no partial history or claims.

## Verification results

| Check | Result |
|---|---|
| Focused persistence/constraint/immutability/isolation suite | 7 passed in 3.38 seconds |
| Persistence plus generation/domain boundary regression | 12 passed in 4.15 seconds |
| Django system check | Passed, 0 issues |
| Migration drift check | Passed, no changes detected |
| Full repository regression | 407 passed in 23.66 seconds |
| Diff whitespace check | Passed |

## Scope boundary

This task establishes tables, database-local constraints, append-only guards, and scoped reads. It does not expose a partial write API. REV-T04 owns locked endpoint resolution, side/workspace/book validation, initial revision creation, claims, generation advancement, scope dirtying, conflict translation, and rollback behavior.
