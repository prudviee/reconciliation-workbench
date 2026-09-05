# Project Constitution

- **Version:** 1.0.0
- **Ratified:** 5 September 2026

These principles constrain every specification, plan, task, implementation, and review.

## I. Evidence is immutable

Original uploaded bytes, raw rows, normalized observations, completed run facts, and decision revisions remain immutable during their retention period. Corrections create new evidence and membership; they never rewrite history.

Why: reconciliation must explain what each source said and what the system knew at any earlier run.

## II. Identity and agreement are different

Pairing determines whether two records describe the same transaction. Comparison independently determines whether their fields agree. Manual and authoritative pairs may contain material discrepancies.

Why: requiring equality before pairing hides the exact mismatches the product exists to investigate.

## III. Automatic matching may abstain

The engine automatically links only complete, policy-compliant, sufficiently stable evidence. Ties, incomplete candidate graphs, hard contradictions, and exceeded component limits become review cases.

Why: in financial reconciliation, a visible uncertainty is safer and more honest than a false certain-looking pair.

## IV. Every automatic result is explainable

Every automatic pair records its input revisions, policy and engine versions, candidate reasons, feature contributions, assignment objective, and ambiguity evidence. A rule score is never presented as a calibrated probability.

Why: reviewers and maintainers must be able to reproduce and challenge the result.

## V. Reviewer authority is durable and auditable

Manual link, accept-unmatched, reject-candidate, reaffirm, revoke, and replace actions are append-only decisions with reasons. Later evidence changes decision health without silently erasing or overriding authority.

Why: human work must survive future runs while corrections remain visible.

## VI. Runs are reproducible and atomically published

A run freezes exact data, policy, decision, engine, and solver versions. Every eligible input receives one terminal outcome. Partial results never become completed results, and stale computation never replaces a newer current result.

Why: a dashboard must not combine evidence from different moments or worker attempts.

## VII. Exact decimal and time semantics are explicit

Money and quantity use decimal arithmetic from source strings. Timezones, tolerances, inclusivity, currency compatibility, rounding, and missing-value behavior are versioned policy. Invalid values never become zero.

Why: implicit numeric and time assumptions create silent boundary defects.

## VIII. Anonymous access remains isolated

Every query, mutation, job, download, and export is scoped to the server-side workspace authorized by the browser session. IDs do not grant access. The interface states expiry, lack of recovery, and deletion behavior.

Why: removing sign-in should improve the demo experience without making visitor data shared.

## IX. The domain core remains framework-independent

Normalization contracts, scoring, assignment, comparison, and result validation use immutable value objects and perform no database, HTTP, file, clock, or network access.

Why: the logic that matters most must be fast to test, reproducible, and portable.

## X. Specifications precede behavior

Public behavior begins as a requirement and acceptance scenario. Plans map requirements to architecture. Tasks map to requirements and tests. Evidence closes the loop. Behavior changes update the specification before or with implementation.

Why: the project is intended to demonstrate disciplined learning and engineering, not only final code.

## XI. Claims require evidence

Performance, accuracy, security, accessibility, and reliability claims must cite an actual test, measurement, or review artifact. Synthetic evaluation is labelled synthetic. An unmet target is reported honestly.

Why: trustworthy engineering includes the limits of what has been proven.

## XII. Complexity must earn its place

Advanced matching is included because it addresses one-to-one allocation and ambiguity. New infrastructure or algorithms require a stated problem, considered alternatives, measurable benefit, and operational cost.

Why: sophistication should demonstrate judgment rather than accumulate technology.

## Governance

- The constitution overrides feature specs and plans.
- Changing a principle requires a dedicated ADR, impact analysis, document updates, and a version change.
- Removing or weakening a principle increments the major version.
- Adding a compatible principle increments the minor version.
- Clarifying wording without behavioral change increments the patch version.
- Every feature-plan review includes a constitution check.
