# 004 Decisions and Stable Cases — Specification

- **Status:** Ready
- **Prefix:** `REV`
- **Depends on:** 001–003
- **Reviewed:** 5 September 2026

## Outcome

Reviewers can make durable, explainable decisions that survive reruns while later corrections remain visible through decision health and stable case history.

## Requirements

- **REV-001** The system MUST support LINK, ACCEPT_UNMATCHED, REJECT_CANDIDATE, REAFFIRM, REVOKE, and REPLACE actions with a reason.
- **REV-002** LINK MUST reserve both stable identities; ACCEPT_UNMATCHED MUST reserve one; REJECT_CANDIDATE MUST prohibit only the relationship.
- **REV-003** One identity MUST NOT participate in two active reserving decisions in the same book.
- **REV-004** Decisions MUST use append-only revisions and MUST preserve their earlier actions and reasons.
- **REV-005** Active decision authority MUST remain separate from UNCHANGED, EVIDENCE_CHANGED, PARTNER_UNAVAILABLE, and NEW_CANDIDATE health.
- **REV-006** Amount/time corrections to a manual link MUST preserve the pair and refresh comparisons with an attention flag.
- **REV-007** A rejected relationship MUST be excluded from every automatic matching stage while active.
- **REV-008** Accepted-unmatched identities MUST remain reserved; a read-only diagnostic search MAY create a new-candidate alert but MUST NOT alter assignment.
- **REV-009** Conflicting replacements MUST show their affected decisions and require explicit supersession.
- **REV-010** Stable cases MUST preserve lineage and per-scope occurrences across runs.
- **REV-011** Current review projections MUST NOT change immutable facts or counts stored for a completed run.
- **REV-012** Concurrent decision changes MUST use expected revisions/generations and fail safely on conflict.
- **REV-013** Pair cases MUST use the two logical identities as their stable key; unpaired cases MUST use one identity; ambiguity cases MUST use a digest of their complete sorted member identities and policy scope.
- **REV-014** Case transitions that merge or split prior cases MUST preserve explicit lineage to every predecessor and successor.
- **REV-015** A rejected relationship MUST remain active across corrections until explicitly reaffirmed, revoked, or superseded; changed evidence MUST update health.
- **REV-016** Decision, claim, case, occurrence, lineage, and current-review reads or mutations MUST be constrained to the active workspace and owning book.

## Acceptance scenarios

- **REV-A01** Given a manual pair, when one amount is corrected, then the pair remains, its comparison changes, and health requires attention.
- **REV-A02** Given an accepted-unmatched record, when a plausible counterpart appears, then acceptance remains active and a new-candidate alert appears.
- **REV-A03** Given a rejected pair that later gains equal shared references, then it remains automatically prohibited and receives an evidence-conflict alert.
- **REV-A04** Given two concurrent attempts to link the same endpoint differently, then at most one succeeds.
- **REV-A05** Given a revoked decision, then its original revision and reason remain visible in history.
- **REV-A06** Given historical run 1 and a later decision, then run 1 facts remain unchanged while current review is separately labelled.
- **REV-A07** Given two prior unpaired cases that become one pair, then the pair case links both predecessors and the prior occurrences remain navigable.
- **REV-A08** Given an ambiguity component whose complete member set changes, then a new ambiguity case key is created and lineage links it to the earlier case.
- **REV-A09** Given corrected evidence for a rejected pair, then the rejection remains effective until an explicit later decision changes it.
- **REV-A10** Given each supported action, when it is submitted without a reason or against an incompatible target, then it is rejected; when valid, its append-only revision records action, scope, actor, reason, and superseded revision where applicable.
- **REV-A11** Given an active link and a proposed replacement that claims one endpoint for another partner, when the preview and commit execute, then every conflicting decision is shown and no claim changes unless the request explicitly supersedes the current authority at its expected revision.
- **REV-A12** Given decision and case IDs from another workspace or book, when they are used in list, detail, preview, commit, history, or lineage requests, then no data is exposed and no local or foreign decision state changes.
- **REV-A13** Given an unchanged decision, changed matching evidence, an unavailable partner, and a newly plausible candidate in separate fixtures, when health is projected, then each receives exactly `UNCHANGED`, `EVIDENCE_CHANGED`, `PARTNER_UNAVAILABLE`, or `NEW_CANDIDATE` without changing the active authority.

## Invariants and failure behavior

- Decision revisions and case occurrences are append-only. (`REV-004`, `REV-010`)
- Active endpoint claims are changed atomically under the book's concurrency boundary. (`REV-003`, `REV-012`)
- Rejections prohibit a relationship but do not reserve either endpoint from other relationships. (`REV-002`, `REV-007`)
- Historical run facts never inherit decisions made after that run. (`REV-011`, Constitution VI)
- Current review projections are scoped by case and reconciliation scope; independently current periods cannot overwrite each other. (`REV-010`, `REV-011`)
- A diagnostic failure or limit cannot be interpreted as evidence that no new candidate exists. (`REV-008`)

## Performance and capacity

Planning constraint: case lists use server-side pagination. Decision changes touch a bounded set of claims, case projections, and dirty scopes inside a short transaction; they never wait for reconciliation computation. (`REV-003`, `REV-012`)

## Out of scope

Multi-user attribution, approval chains, role-based permissions, comments, and external case-management integrations.

## Resolved decisions

- Pair keys contain book and ordered left/right logical identities. Unpaired keys contain book, side, and logical identity. Ambiguity keys contain book, run scope/policy identity, and a digest of all sorted member identities. Changed membership creates a successor ambiguity case rather than rewriting the old key.
- Rejection authority does not expire automatically. Any matching-relevant correction marks `EVIDENCE_CHANGED`; an authoritative-reference conflict also requires attention. The reviewer must reaffirm, revoke, or supersede it.

## Requirement-to-scenario matrix

| Requirement | Scenarios |
|---|---|
| REV-001, REV-004 | REV-A05, REV-A10 |
| REV-002 | REV-A01, REV-A02, REV-A03 |
| REV-003, REV-012 | REV-A04 |
| REV-009 | REV-A11 |
| REV-005 | REV-A01, REV-A02, REV-A13 |
| REV-006 | REV-A01 |
| REV-007, REV-015 | REV-A03, REV-A09 |
| REV-008 | REV-A02 |
| REV-010, REV-013, REV-014 | REV-A07, REV-A08 |
| REV-011 | REV-A06 |
| REV-016 | REV-A12 |

## Change history

| Date | Change | Reason |
|---|---|---|
| 5 September 2026 | Initial draft | Define durable decisions and cases |
| 5 September 2026 | Fixed case keys/lineage and rejection lifetime; added concurrency/failure invariants and traceability; marked Ready | Critical SDD review |
