# Verification and Delivery Plan

## 1. Verification strategy

The project must demonstrate that its difficult behavior is correct, deterministic, and visible. Verification therefore covers five layers:

1. Pure domain examples and property tests.
2. Persistence and concurrency integration tests.
3. Labelled synthetic algorithm evaluation.
4. Browser-level workflow and accessibility tests.
5. Deployment and performance checks on a documented reference environment.

Passing a few sample rows is insufficient. The tests target the invariants that make corrections and human review safe.

## 2. Unit and contract tests

### Source adapters

- Correctly identify each supported format.
- Produce expected canonical records from representative fixtures.
- Normalize `BUY/B`, dates, decimals, instruments, currencies, and statuses.
- Preserve raw values and row provenance.
- Decode UTF-8 and optional BOM deterministically for comma, semicolon, and tab delimiters.
- Reject ambiguous dates and unknown required enums.
- Reject NaN, infinity, overflow, and unsupported precision.
- Enforce byte, row, column, and field-length limits without partial activation.
- Produce deterministic output under equivalent formatting.
- Pass one shared adapter contract suite.

### Comparison

- Exact values.
- Difference exactly equal to inclusive tolerance.
- Difference just inside and outside the boundary.
- Absolute-only and combined absolute/relative rules.
- Negative signed difference and zero denominator.
- Timezone and cross-midnight timestamps.
- Currency mismatch produces not-comparable amount.
- Missing values do not become zero.

### Scoring

- Each feature at zero, midpoint, and band boundary.
- Zero band equality and inequality.
- Missing evidence contributes zero without renormalization.
- Required-evidence coverage blocks automatic acceptance.
- Minimum automatic evidence includes instrument, side, currency, quantity, timestamp, and at least one monetary field.
- Decimal-to-basis-point rounding follows the configured mode.
- Weight sum and score range validation.
- Reference contradiction behavior follows the contract revision.
- Correlated price/amount fixtures do not create hidden double certainty.

### Assignment

- Greedy counterexample selects the documented global result.
- Equal optimum has zero global gap and abstains.
- Near-margin values behave correctly at the inclusive boundary.
- Empty, one-sided, and rectangular components.
- Weak real edges choose dummy unmatched options.
- Forbidden/rejected edges are never selected.
- Duplicate trusted references produce ambiguity rather than an arbitrary authoritative pair.
- Tiny graph objective agrees with exhaustive enumeration.
- Disconnected components equal a whole-graph reference solution.
- Stable input reordering does not change domain outcomes.
- Incomplete or oversized components never produce automatic heuristic pairs.

## 3. Persistence and integration tests

### Import and temporal history

- Identical byte upload returns the existing attempt.
- Formatting-equivalent data resolves through semantic deduplication.
- Original upload → correction → original replay keeps the correction current.
- Intentional restore creates a new correction revision.
- Full-snapshot omission removes current membership only.
- Delta omission preserves current membership.
- Delta upsert, cancellation, and retraction affect only their explicit identities and activation rejects a stale preview base.
- A malformed full snapshot never replaces the valid head.
- Historical membership retains its original observations after correction.
- Reprocessing the same bytes under a new mapping requires explicit preview.
- Physical, semantic-input, and resolved-state hashes remain distinct; multiplicity and missing/null/empty representations affect semantic identity.

### Decisions

- Manual link reserves exactly two endpoints.
- Two concurrent links cannot claim one endpoint.
- Accepted-unmatched prevents automatic matching.
- New candidate diagnostic alerts without undoing acceptance.
- Rejection blocks both reference and heuristic automatic stages.
- Corrected rejected evidence creates attention without silent reuse.
- Corrected amount/time preserves manual link and updates comparison.
- Cancellation preserves decision history and flags the remaining endpoint.
- Reaffirmation advances the reviewed observation baseline.
- Revoke and replace append history and update claims atomically.

### Runs and jobs

- Same manifest returns the same logical run.
- Decision or data change during execution makes the result stale.
- A stale completed run cannot advance the current pointer.
- A later-finishing older run cannot replace a newer run.
- Expired lease permits retry with a new attempt token.
- Fenced worker cannot publish.
- Rows from different attempts never mix.
- Publication failure leaves no partial completed result.
- Every eligible input appears exactly once in pair/unpaired partition.
- Two dated scopes update their own case projections independently.

### Isolation and security

- Substituting another workspace's book, import, case, run, artifact, job, or export ID returns no data.
- Full-page, fragment, filter, action-preview, history, download, and export routes return no foreign values, counts, filenames, or existence distinction.
- A worker rejects a manifest whose persisted resources cross workspace ownership.
- State-changing requests require valid CSRF protection.
- Production-like session cookies are Secure, HttpOnly, and SameSite.
- Downloads require the active workspace session.
- Filenames cannot escape storage paths.
- Displayed CSV strings are HTML-escaped.
- Spreadsheet-formula cells are safely exported.
- Expired/deleted workspace cannot start new work.
- Storage, book, and active-job quotas refuse only the new request under concurrent load.
- Logs, traces, metrics, and errors retain correlation/stage data while excluding raw rows, cookies, and secrets.
- Live expiry and any longer backup-retention statement match measured deployment behavior.

## 4. Property and metamorphic tests

Use generated examples to verify:

- Reordering source rows does not change results.
- Running identical inputs twice produces identical domain output.
- No observation appears in two selected pairs.
- Every eligible observation has one terminal outcome.
- Adding an unrelated disconnected transaction does not modify existing components.
- Equivalent decimal text normalizes identically.
- Formatting-only corrections do not alter decision fingerprints.
- Increasing a tolerance cannot turn a passing field comparison into failure.
- Removing candidate edges cannot improve the unconstrained optimal objective.
- A reported global gap equals the objective difference from the explicit forbidden-edge solve.

## 5. Synthetic evaluation design

Create a deterministic generator that emits two source formats and a hidden truth map. Scenario families include:

- Clean shared references.
- Identifier loss or source-local identifiers.
- Small amount, price, quantity, and timestamp drift.
- Material discrepancies.
- Repeated identical trades.
- Unmatched records on both sides.
- Cancellations and corrections.
- Greedy traps and tied components.
- Missing optional fields.
- Dense candidate groups and component-limit cases.

Development and held-out seeds are separate. Threshold tuning uses only development data.

Compare:

1. Exact-reference baseline.
2. Greedy weighted baseline.
3. Weighted global assignment with abstention.

Report:

| Metric | Definition |
|---|---|
| Automatic precision | Correct automatic pairs / all automatic pairs |
| Automatic recall | Correct automatic pairs / true pairs eligible for automation |
| Candidate recall | Eligible true heuristic pairs appearing in candidate graph / all eligible true heuristic pairs |
| Review rate | Eligible records requiring human review / eligible records |
| False automatic matches | Count, with fixture and evidence details |
| Workflow coverage | Records handled through automatic or explicit human outcomes |
| Runtime | Stage and total duration on declared hardware |
| Component distribution | Node/edge sizes, over-limit counts, sensitivity solves |

Manual pairs do not inflate automatic precision. Manually reserved endpoints are excluded from automatic-recall eligibility. If there are no automatic predictions, precision is reported as not applicable. All results are labelled synthetic; zero errors in a small sample is not a real-world accuracy claim.

## 6. Browser verification

The primary Playwright journey is:

1. Create an anonymous workspace.
2. Load the curated sample book.
3. Inspect source mappings and preview.
4. Activate both sources.
5. Run reconciliation and wait through truthful stages.
6. Filter to discrepancies and open evidence.
7. Inspect weighted/global allocation details.
8. Reject one candidate.
9. Manually link a pair and retain its amount mismatch.
10. Accept one unmatched record with a reason.
11. Activate a correction and rerun.
12. Verify decisions persist and cases change as expected.
13. Open the prior run and verify its original evidence.
14. Export results.

Accessibility checks cover keyboard-only operation, focus return after drawers, visible focus, labelled controls, status without color, announced errors, meaningful table headers, and reduced-motion behavior where relevant.

## 7. Performance and capacity targets

Initial targets to measure:

- 10,000 rows per source.
- 25 MiB maximum file.
- Complete reconciliation under 10 seconds on a documented two-vCPU/four-GiB environment, subject to component caps.
- Typical paginated workbench responses below 500 ms p95 on that environment.
- Immediate acknowledgement for asynchronous imports and runs.
- 100 real nodes and 2,500 edges per solved component initially.
- 250,000 candidate edges per run initially.
- 200 enumerated candidates per record initially; reaching the cap withholds affected heuristic automation.

Tests report measurements rather than converting targets into claims. A missed target triggers profiling of parsing, candidate enumeration, solver sensitivity, persistence, or queries before changing architecture.

## 8. Observability checks

Structured logs include workspace, book, scope, run, import, and job identifiers plus stage durations. They exclude raw transaction payloads and session secrets.

Metrics include:

- Upload size and validation duration.
- Row validation failures by code.
- Duplicate and replay counts.
- Candidate count and candidate recall in evaluation.
- Component size and overflow.
- Automatic, ambiguous, unmatched, and review rates.
- Manual override/rejection rate.
- Correction and reopened-case counts.
- Run duration, retries, stale completions, and fenced attempts.

## 9. Implementation sequence

The full advanced behavior is the selected first-release target. These checkpoints are dependency order, not separate simplified and advanced releases.

| Checkpoint | Exit evidence |
|---|---|
| 1. Domain vocabulary | Canonical value objects, source contracts, comparison tests, labelled fixtures |
| 2. Advanced matcher | Candidate graph, weighted evidence, assignment, sensitivity, exhaustive tiny-graph verification |
| 3. Temporal persistence | Imports, hashes, memberships, corrections, decisions, run manifests, publication tests |
| 4. Vertical workflow | Upload → activate → run → inspect → decide → rerun → history |
| 5. Product completeness | Mapping workflow, cases, filters, exports, failures, workspace expiry |
| 6. Polish | Visual consistency, keyboard access, responsive case view, loading/error states |
| 7. Release verification | Held-out evaluation, capacity measurement, deployment, demo rehearsal |

An executable vertical flow should exist early, but every checkpoint preserves the final architecture. Commit history should communicate these coherent milestones.

## 10. Demonstration script

| Time | Demonstration |
|---|---|
| 0:00–0:30 | Open the anonymous workspace and state the problem |
| 0:30–1:05 | Inspect source mappings and activate prepared inputs |
| 1:05–1:40 | Show exact, tolerated, discrepant, unmatched, ambiguous, and excluded results |
| 1:40–2:25 | Explain the global-assignment counterexample and edge evidence |
| 2:25–3:15 | Reject a candidate, manually link the correct pair, retain amount mismatch |
| 3:15–3:45 | Accept an unmatched record and activate a correction |
| 3:45–4:30 | Rerun, show persistent decisions and changed cases, inspect previous immutable run |

The recording should emphasize user-visible behavior, then open the algorithm explanation only where it proves why a result is trustworthy.

## 11. Release gate

The release is ready when:

- Required unit, integration, property, and browser tests pass.
- The held-out synthetic report is generated and honestly labelled.
- Global allocation and ambiguity fixtures match documented outcomes.
- No known defect contradicts a core invariant.
- Historical evidence survives the complete correction workflow.
- Cross-workspace isolation is verified.
- The deployed quotas, live expiry, cleanup, and backup-retention behavior match the documentation.
- The demo completes reliably within five minutes.
- README setup, assumptions, algorithm, measurements, known limits, and demo steps are complete.

The future public repository and video are delivery artifacts. This design package does not publish or send either one.
