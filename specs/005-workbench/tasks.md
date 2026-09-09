# 005 Workbench and Run History — Tasks

- **Status:** Complete
- **Specification:** [spec.md](./spec.md)
- **Plan:** [plan.md](./plan.md)

## Submission-critical tasks

- [x] **UX-T01 — Prepare scoped workbench application projections** (`UX-001`, `UX-002`, `UX-006`, `UX-007`, `UX-008`, `UX-018`; `UX-A05`, `UX-A06`, `UX-A10`, `UX-A14`)
  - Change: default-scope/policy readiness, workspace-owned run summaries, selected historical run projections, current case projections, and typed unavailable failures.
  - Verify: incomplete-source states, idempotent setup, latest-success preservation, historical/current separation, and foreign/absent matrix.
  - Evidence: readiness table, query bounds, and isolation results.

- [x] **UX-T02 — Deliver run controls and reconciliation workbench** (`UX-001`–`UX-003`, `UX-007`–`UX-009`, `UX-011`–`UX-013`, `UX-015`, `UX-018`; `UX-A01`, `UX-A05`, `UX-A08`–`UX-A10`, `UX-A12`, `UX-A14`–`UX-A16`)
  - Change: scoped run POST, latest/selected-run GET, outcome summary, current cases, run history, preparation recovery, pagination, and responsive accessible table.
  - Verify: no-JavaScript start-to-results flow, truthful counts/states, old-run selection, CSRF, stable pages, and route isolation.
  - Evidence: browser response fixtures and accessibility assertions.

- [x] **UX-T03 — Render complete case evidence and history** (`UX-002`, `UX-004`–`UX-006`, `UX-011`, `UX-012`, `UX-014`, `UX-015`, `UX-018`; `UX-A01`–`UX-A03`, `UX-A06`–`UX-A08`, `UX-A14`, `UX-A16`)
  - Change: side-by-side raw/canonical values, field differences/tolerances, pair reason/origin, candidate evidence, policy/input versions, current review, immutable occurrences, and lineage.
  - Verify: discrepancy, manual pair, unpaired, history, explicit currency/time labels, narrow layout, and foreign/absent cases.
  - Evidence: evidence-surface matrix and rendered-content assertions.

- [x] **UX-T04 — Complete reasoned manual linking and rerun persistence** (`UX-007`, `UX-010`, `UX-011`, `UX-018`; `UX-A02`, `UX-A04`, `UX-A10`–`UX-A12`, `UX-A14`)
  - Change: unmatched partner selection, complete preview, mandatory reason, expected-generation commit, conflict recovery, pending-rerun state, and rerun action.
  - Verify: reason rejection, both identities shown before commit, CSRF, cross-workspace denial, durable decision, manual pair after rerun, and unchanged prior run.
  - Evidence: end-to-end browser journey and mutation before/after snapshots.

- [x] **UX-T05 — Close the Atlas submission browser acceptance** (`UX-001`, `UX-002`, `UX-004`, `UX-006`–`UX-013`, `UX-015`, `UX-018`; `UX-A01`, `UX-A02`, `UX-A04`–`UX-A06`, `UX-A08`–`UX-A12`, `UX-A14`, `UX-A16`)
  - Change: curated CSV fixtures, final navigation/copy/polish, submission README, browser verification record, and defects found by the complete journey.
  - Verify: upload → activate → run → inspect discrepancy → manual link → rerun → history in under five minutes without developer tools; full regression and clean Compose.
  - Evidence: submission acceptance matrix, demo script, runtime record, and final verified commit.

## Post-submission showcase tasks

- [x] **UX-T06 — Add complete server-side discovery and safe exports** (`UX-003`, `UX-017`, `UX-018`; `UX-A13`–`UX-A15`)
  - Change: combined search/filter/sort, complete totals, and formula-safe historical/current CSV and JSON exports.
  - Evidence: [UX-T06 acceptance](./evidence/UX-T06.md) and [runtime record](./evidence/UX-T06-runtime.json).

- [x] **UX-T07 — Add enhanced allocation explanation and async states** (`UX-005`, `UX-008`, `UX-014`, `UX-016`, `UX-018`; `UX-A03`, `UX-A05`, `UX-A07`, `UX-A17`)
  - Change: complete candidate table, optional bounded graph, persisted progress stages/counts, and production failure/retry presentation.
  - Evidence: [UX-T07 acceptance](./evidence/UX-T07.md) and [runtime record](./evidence/UX-T07-runtime.json).

- [ ] **UX-T08 — Close the complete showcase specification** (`UX-001`–`UX-018`; `UX-A01`–`UX-A17`)
  - Change: complete remaining accessibility, responsive, performance, export, async, visual, and deployment-connected acceptance evidence.
  - [x] **UX-T08A — Expose accept-unmatched review in the browser** (`UX-004`, `UX-007`, `UX-010`, `UX-011`, `UX-018`; `UX-A04`, `UX-A10`, `UX-A11`)
    - Change: preview the retained unpaired record, require a reason, commit the reserved decision with optimistic concurrency, label the pending rerun, and hide the action for cancelled or already-reviewed evidence.
    - Evidence: [UX-T08A acceptance](./evidence/UX-T08A.md).
  - [x] **UX-T08B — Format typed comparison values for reviewers** (`UX-004`, `UX-015`; `UX-A01`, `UX-A08`)
    - Change: preserve typed evidence internally while presenting decimals, UTC timestamps, missing values, and time tolerances as readable comparison labels.
    - Evidence: [UX-T08B acceptance](./evidence/UX-T08B.md).
  - [x] **UX-T08C — Make selected historical occurrence evidence inspectable** (`UX-004`, `UX-006`; `UX-A06`)
    - Change: list the selected historical run's immutable cases separately from current review, link each result to its retained occurrence, identify historical evidence and current-review status independently, and disable reviewer actions on past evidence.
    - Evidence: [UX-T08C acceptance](./evidence/UX-T08C.md).
  - [x] **UX-T08D — Expose saved-decision review and reasoned revocation** (`UX-004`, `UX-007`, `UX-010`, `UX-011`, `UX-018`; `UX-A10`, `UX-A11`)
    - Change: show active reviewer authorities on relevant cases, open a complete identity/reason/history preview, require a new reason to revoke, release claims append-only, and mark the workbench pending until rerun.
    - Evidence: [UX-T08D acceptance](./evidence/UX-T08D.md).
  - [x] **UX-T08E — Expose conflict-complete decision replacement** (`UX-004`, `UX-007`, `UX-010`, `UX-011`, `UX-018`; `UX-A10`, `UX-A11`)
    - Change: choose current left/right evidence, preview the target and every displaced active decision, require a reason, commit only the exact generation/conflict set, retain superseded history, and mark reconciliation pending.
    - Evidence: [UX-T08E acceptance](./evidence/UX-T08E.md).
  - [x] **UX-T08F — Expose reasoned candidate rejection** (`UX-004`, `UX-007`, `UX-010`, `UX-011`, `UX-018`; `UX-A04`, `UX-A10`)
    - Change: open a rejection preview from retained allocation evidence, show both exact identities and every active decision involving them, require a reason, reject only the reviewed current-run relationship, preserve both records for other matches, and mark reconciliation pending.
    - Evidence: [UX-T08F acceptance](./evidence/UX-T08F.md).

## Scope decision

UX-T01 through UX-T05 are required for the Atlas submission. UX-T06 through UX-T08 remain important public-showcase work but are not required by the assignment brief.
