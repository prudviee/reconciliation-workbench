# 005 Workbench and Run History — Specification

Status: Draft
Prefix: `UX`
Depends on: 001–004

## Outcome

A visitor can complete the entire reconciliation workflow through a polished, accessible interface and understand how every result was produced.

## Requirements

- **UX-001** The product MUST provide workspace, import/prepare, workbench, case evidence, and runs/activity surfaces.
- **UX-002** The workbench MUST display pairing, financial comparison, and current review as separate dimensions.
- **UX-003** Search, filters, sorting, and pagination MUST operate over the complete server-side result set.
- **UX-004** Case evidence MUST show raw/canonical values, field differences, tolerance, pair origin, policy/input versions, decisions, and history.
- **UX-005** Weighted matches MUST expose candidate reasons, feature contributions, assignment outcome, and counterfactual global gap.
- **UX-006** Historical views MUST clearly distinguish evidence effective in that run from current saved decisions/evidence.
- **UX-007** Pending changes MUST be labelled and provide a clear rerun action.
- **UX-008** A running or failed new run MUST leave the last successful result available.
- **UX-009** Import failures MUST identify source row, field, original value, and expected interpretation.
- **UX-010** Reviewer actions MUST preview affected identities/decisions and require a reason.
- **UX-011** The core workflow MUST be operable by keyboard, use visible focus, labelled controls, announced errors, and non-color state text.
- **UX-012** Desktop MUST support the complete table/evidence workflow; smaller screens MUST provide a usable dedicated case view.
- **UX-013** The curated demo MUST complete in five minutes without developer tools.

## Acceptance scenarios

- **UX-A01** A user filters to amount discrepancies, opens a case, and sees both values, difference, tolerance, and pair reason.
- **UX-A02** A manually linked case with unequal amounts displays both “manually paired” and “amount mismatch.”
- **UX-A03** A global allocation example displays why the globally selected edge differs from the local highest score.
- **UX-A04** A keyboard-only user completes search, case inspection, manual link, accept unmatched, rerun, and historical inspection.
- **UX-A05** A failed rerun leaves the earlier result visible with an intelligible failure/retry state.
- **UX-A06** Opening an old run displays its immutable values and a separately labelled current-review panel.

## Out of scope

Native mobile applications, free-form dashboard builders, real-time multi-user collaboration, and a general-purpose chatbot.

## Open questions

- Final visual identity/name and design tokens.
- Whether the candidate graph uses a small accessible SVG enhancement or a table only in the first release.
