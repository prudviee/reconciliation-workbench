# 004 Decisions and Stable Cases — Specification

Status: Draft
Prefix: `REV`
Depends on: 001–003

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

## Acceptance scenarios

- **REV-A01** Given a manual pair, when one amount is corrected, then the pair remains, its comparison changes, and health requires attention.
- **REV-A02** Given an accepted-unmatched record, when a plausible counterpart appears, then acceptance remains active and a new-candidate alert appears.
- **REV-A03** Given a rejected pair that later gains equal shared references, then it remains automatically prohibited and receives an evidence-conflict alert.
- **REV-A04** Given two concurrent attempts to link the same endpoint differently, then at most one succeeds.
- **REV-A05** Given a revoked decision, then its original revision and reason remain visible in history.
- **REV-A06** Given historical run 1 and a later decision, then run 1 facts remain unchanged while current review is separately labelled.

## Out of scope

Multi-user attribution, approval chains, role-based permissions, comments, and external case-management integrations.

## Open questions

- Final stable case key and explicit merge/split lineage rules.
- Whether reject-candidate health expires after specific identity-field changes or always requires explicit review.
