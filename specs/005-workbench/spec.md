# 005 Workbench and Run History — Specification

- **Status:** Verified
- **Prefix:** `UX`
- **Depends on:** 001–004
- **Reviewed:** 5 September 2026

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
- **UX-014** The candidate table MUST be the complete accessible explanation; any graph MUST be a progressive enhancement and MUST NOT contain unique required information.
- **UX-015** Amounts MUST use tabular numerals, right alignment, and explicit currencies; status MUST remain understandable without color.
- **UX-016** Async progress MUST show real stages and available counts without invented percentages or blocking access to the latest successful result.
- **UX-017** CSV/JSON exports MUST identify whether they contain historical run facts or current review state, preserve decimal strings and timezone labels, and neutralize spreadsheet-formula execution from untrusted cells.
- **UX-018** Every page, HTMX fragment, search, action preview, download, and export MUST authorize the requested resource through the active workspace before rendering content or counts.

## Acceptance scenarios

- **UX-A01** A user filters to amount discrepancies, opens a case, and sees both values, difference, tolerance, and pair reason.
- **UX-A02** A manually linked case with unequal amounts displays both “manually paired” and “amount mismatch.”
- **UX-A03** A global allocation example displays why the globally selected edge differs from the local highest score.
- **UX-A04** A keyboard-only user completes search, case inspection, manual link, accept unmatched, rerun, and historical inspection.
- **UX-A05** A failed rerun leaves the earlier result visible with an intelligible failure/retry state.
- **UX-A06** Opening an old run displays its immutable values and a separately labelled current-review panel.
- **UX-A07** With scripts or the optional graph unavailable, the candidate table still exposes every reason, score contribution, selected allocation, and global gap needed to understand the outcome.
- **UX-A08** Given two currencies and multiple statuses in the case table, then values retain explicit units and every status has text/icon meaning independent of color.
- **UX-A09** Given invalid source values across multiple rows, when import preview fails, then each error exposes source row, field, original value, and expected interpretation without hiding the prior valid dataset.
- **UX-A10** Given a decision or evidence change after the latest successful run, when the workbench opens, then pending changes are labelled, their scope is explained, and the rerun action is available while historical facts remain unchanged.
- **UX-A11** Given a manual-link, replacement, revocation, or accept-unmatched action, when its confirmation opens, then every affected identity and active decision is shown and a non-empty reason is required before commit.
- **UX-A12** Given a representative curated workspace, when a new visitor follows the visible product flow without developer tools, then workspace creation, preparation, reconciliation, evidence review, one decision, rerun, and history inspection complete within five minutes.
- **UX-A13** Given values beginning with spreadsheet formula characters plus precise decimals and labelled timezones, when historical and current-review exports are downloaded, then each export names its view, preserves numeric/time semantics, and opens without evaluating an untrusted cell as a formula.
- **UX-A14** Given IDs and crafted filter/action requests from another workspace, when every full-page, fragment, search, preview, download, and export route is exercised, then no foreign values, counts, filenames, or existence distinction is returned and no mutation occurs.
- **UX-A15** Given results spanning multiple pages, when the user combines search, filters, sorting, and pagination, then rows and totals reflect the complete server-side result in stable order rather than only the previously visible page.
- **UX-A16** Given desktop, tablet, and narrow mobile viewports, when the same case is inspected, then desktop retains the complete table/evidence workflow and smaller screens provide a readable dedicated case view with the required evidence and basic decisions.
- **UX-A17** Given a running reconciliation with known completed-stage counts and a previous successful result, when progress refreshes, then actual stages/counts update, no invented percentage appears, and the previous result remains usable.

## Invariants and failure behavior

- The selected historical run controls run-fact values and pairings; current review is never blended into those facts. (`UX-006`)
- Manual link, replacement, revocation, and acceptance previews show every affected identity and active decision before commit. (`UX-010`)
- Search/filter counts represent the complete server-side query, not the visible page only. (`UX-003`)
- Failed partial HTMX requests preserve the current page and provide a recoverable error message. (`UX-008`, `UX-011`)
- Drawer focus is trapped while open and returns to the initiating row when closed. (`UX-011`)
- The latest successful result remains accessible throughout a new run and after failure. (`UX-008`, `UX-016`)

## Performance and capacity

Planning target: typical paginated workbench requests remain below 500 ms p95 on the documented reference environment. Page size defaults to 50 cases and is capped at 100. Evidence loads on demand; result summary and filters do not load the complete candidate graph into the browser. (`UX-003`, `UX-004`, Constitution XI)

## Out of scope

Native mobile applications, free-form dashboard builders, real-time multi-user collaboration, and a general-purpose chatbot.

## Resolved decisions

- The product name remains Reconciliation Workbench. Initial tokens use a neutral background, dark navy text, one blue primary accent, restrained semantic colors, and tabular numeric typography; exact values belong to the UI plan and visual review.
- A complete candidate table is required. A small SVG graph is permitted as progressive enhancement for bounded components, but it cannot be the sole source of information.

## Requirement-to-scenario matrix

| Requirement | Scenarios |
|---|---|
| UX-001 | UX-A04, UX-A12 |
| UX-013 | UX-A12 |
| UX-002, UX-015 | UX-A02, UX-A08 |
| UX-003 | UX-A01, UX-A15 |
| UX-004 | UX-A01 |
| UX-009 | UX-A09 |
| UX-005, UX-014 | UX-A03, UX-A07 |
| UX-006 | UX-A06 |
| UX-007 | UX-A10 |
| UX-010 | UX-A11 |
| UX-008 | UX-A05, UX-A17 |
| UX-011 | UX-A04 |
| UX-012 | UX-A16 |
| UX-016 | UX-A05, UX-A17 |
| UX-017 | UX-A13 |
| UX-018 | UX-A14 |

## Change history

| Date | Change | Reason |
|---|---|---|
| 5 September 2026 | Initial draft | Define showcase workflow |
| 5 September 2026 | Fixed accessible evidence, visual baseline, pagination/progress behavior, and traceability; marked Ready | Critical SDD review |
| 7 September 2026 | Planned submission-critical implementation separately from post-submission showcase enhancements | User-directed submission prioritization |
| 8 September 2026 | Added an explicit browser accept-unmatched closure task | UI-only assignment verification found the required domain action was not reachable from an unmatched case |
