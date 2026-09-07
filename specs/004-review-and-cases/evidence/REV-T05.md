# REV-T05 Verification Evidence

- **Task:** Implement previewed reaffirmation, revocation, and replacement
- **Requirements:** `REV-001`, `REV-004`, `REV-009`, `REV-012`, `REV-015`, `REV-016`
- **Acceptance scenarios:** `REV-A05`, `REV-A09`, `REV-A10`, `REV-A11`, `REV-A12`
- **Date:** 7 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence

## Lifecycle behavior

| Action | Appended revision | Authority effect | Claim effect |
|---|---|---|---|
| REAFFIRM | Same authority, fresh reviewed observation IDs/digest, predecessor, reason, actor | Remains active | Existing claims move to the new revision |
| REVOKE | No authority payload, predecessor, reason, actor | Becomes inactive | All authority claims are released |
| REPLACE | New authority/baseline, predecessor, reason, actor, explicit supersession edges | New authority becomes active; target and approved conflicts are superseded | Every superseded authority releases its full claim set; new authority claims are created |

Each successful command increments `resolution_generation` exactly once and dirties book scopes. Earlier revisions, reasons, reviewed baselines, and supersession edges remain append-only.

## Preview and explicit supersession

`preview_replacement` resolves the active target and proposed authority inside the workspace/book boundary. It returns:

- the exact resolution generation;
- the target decision and current revision;
- every conflicting decision/current revision;
- the full endpoint claim set of each conflicting authority, including claims that do not overlap the proposed authority.

The strongest fixture begins with two active links, `L1–R1` and `L2–R2`, then proposes `L1–R2`. Preview reports the complete `L2–R2` authority. Commit explicitly approves that revision, appends one replacement, records supersession edges to the target and conflicting revisions, removes all four old claim rows, and creates only `L1` and `R2` claims for the replacement.

A command that omits the reported conflict fails with `CONFLICT_SET_CHANGED`. The database remains at two revisions, zero supersession edges, the original claims, and the original generation. A stale target, revoked target, or already superseded target fails with `STALE_REVISION`.

## History and isolation evidence

- Revocation leaves the original revision and original reason visible and appends a separate reversal reason.
- Reaffirmation creates a new baseline without changing endpoint authority and moves claims from the predecessor revision.
- A superseded external decision retains its current historical revision pointer, while the explicit incoming supersession edge makes it inactive and prevents reaffirmation.
- Foreign-workspace preview and commit calls return the same unavailable outcome and leave the owner's generation, revision history, and claims unchanged.
- All lifecycle work runs under the workspace and book locks; reconciliation computation is outside this transaction.

## PostgreSQL locking correction

The first focused run exposed that PostgreSQL does not allow `FOR UPDATE` across the nullable outer join from a decision to its current revision. The final implementation locks the decision row alone and loads the immutable current revision separately. The book remains the serialization boundary, and no unsupported joined-row lock is issued.

## Verification results

| Check | Result |
|---|---|
| Focused lifecycle/preview/replacement suite | 11 passed in 4.49 seconds |
| Review domain, persistence, generation, and lifecycle regression | 46 passed in 4.78 seconds |
| Django system check | Passed, 0 issues |
| Migration drift check | Passed, no changes detected |
| Full repository regression | 418 passed in 21.89 seconds |
| Diff whitespace check | Passed |

## Scope boundary

This task completes reviewer-authority mutation semantics. Corrections do not automatically revoke or replace any authority. REV-T06 will freeze active, unsuperseded decision revisions into engine manifests and persist immutable run facts; REV-T07 will compute health separately from that authority.
