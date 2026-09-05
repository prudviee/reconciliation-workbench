# Product Design

## 1. Product statement

I am building a transaction-reconciliation workbench for comparing records produced independently by two financial systems. It translates incompatible source formats into a canonical model, links records that describe the same transaction, identifies material differences, and lets a reviewer resolve uncertainty without losing history.

The product should answer one question each morning:

> What still needs attention, and what evidence supports the next decision?

The difficult part is not CSV upload. The difficult part is preserving evidence, distinguishing identity from equality, resolving one-to-one conflicts, handling corrections, and carrying human decisions safely into later runs.

## 2. Users and access model

The primary user is a finance-operations reviewer investigating discrepancies between an internal ledger and a counterparty statement.

The public showcase does not require sign-in. Opening the application creates an isolated server-side workspace associated with a secure browser session. The same browser can return to that workspace until it expires. A different browser cannot recover it.

The interface must state:

- The exact expiry time.
- That clearing browser data loses access.
- That uploaded files are private to the workspace.
- How to export results.
- How to delete the workspace immediately.

The first-release live workspace expiry is seven days from creation and does not extend with activity. Deployment verification must confirm the displayed deadline and disclose any longer backup-retention period separately.

Configurable storage, book-count, and active-job quotas keep the public anonymous showcase usable. A limit refusal explains the reason and leaves existing work untouched.

## 3. Core concepts shown to the user

The UI keeps three dimensions separate:

| Dimension | Examples |
|---|---|
| Pairing | Automatically paired, manually paired, unmatched, ambiguous |
| Financial comparison | Exact, within tolerance, amount mismatch, time mismatch, not comparable |
| Current review | Needs review, accepted unmatched, pending rerun, requires attention, closed |

A row can therefore say **Manually paired · Amount mismatch**. Manual pairing establishes that two records describe the same transaction; it does not approve their values.

An accepted-unmatched transaction remains visibly unmatched. The reviewer has accepted that fact; the system has not invented a counterpart.

## 4. First-release capabilities

### Import and source preparation

- Upload CSV files for the two sides of a reconciliation.
- Use two predefined adapters and create a reusable mapping for a third format.
- Map source columns, date format, timezone, enums, currency, and source identity.
- Preview raw and normalized values before activation.
- Reject ambiguous dates, unknown states, invalid decimals, and conflicting source identifiers.
- Recognize exact and semantically equivalent duplicate uploads.
- Support declared full-snapshot and delta file contracts.
- Show additions, corrections, cancellations, and snapshot removals before activation.

### Reconciliation

- Reapply durable reviewer decisions.
- Pair unique trusted shared references.
- Generate plausible candidates through bounded search rules.
- Score candidate evidence using versioned weights.
- Solve complete connected components as optional one-to-one assignments.
- Withhold uncertain, tied, or incomplete results for review.
- Compare paired fields using explicit decimal and time tolerances.
- Explain why each record paired, remained unmatched, or became ambiguous.

### Review and history

- Inspect source records side by side.
- Manually link two records.
- Accept a record as genuinely unmatched.
- Reject an incorrect candidate so it is not repeatedly suggested.
- Reaffirm or revoke an earlier decision with a reason.
- Upload corrections without overwriting original evidence.
- Rerun with current inputs and decisions.
- Open earlier immutable runs and compare case changes.
- Export results with run, policy, and source-revision metadata.

## 5. Main workflow

```mermaid
flowchart LR
    A[Create anonymous workspace] --> B[Load demo or create reconciliation]
    B --> C[Upload and map both sources]
    C --> D[Preview and activate datasets]
    D --> E[Run reconciliation]
    E --> F[Review discrepancies and ambiguity]
    F --> G[Save decisions or upload correction]
    G --> H[Rerun]
    H --> I[Compare current and historical evidence]
```

## 6. Product surfaces

### Workspace

Shows named reconciliation books, latest successful runs, unresolved counts, pending changes, and workspace expiry. Primary actions are **Use demo dataset** and **New reconciliation**.

### Import and prepare

A guided upload → map → preview → validate → activate flow. It displays raw and interpreted dates, decimal values, status mappings, exclusions, duplicate status, and proposed dataset changes.

### Reconciliation workbench

The central interface contains:

- Selected run and exact source revisions.
- A compact outcome summary.
- A banner when saved changes require a rerun.
- Server-side search, filters, stable sorting, and pagination.
- A dense case table.
- A side-by-side evidence drawer.

The default view is **Needs review**. Additional views cover all cases, unmatched, ambiguous, discrepancies, accepted-unmatched, and excluded records.

### Case evidence

Each case has a stable URL. On desktop it opens in a drawer; smaller screens use a dedicated page. It shows:

- Raw and canonical values from both sources.
- Field differences and applied tolerances.
- Pair origin and decision effective in the selected run.
- Candidate-generation reasons.
- Score contributions and missing evidence.
- Selected global assignment and relevant alternatives.
- Current decisions, corrections, and case history.

### Runs and activity

Lists immutable runs with source revisions, rules, outcomes, lifecycle, and freshness. Consecutive-run comparison identifies newly linked, newly unmatched, changed discrepancies, applied decisions, and reopened cases.

## 7. Essential interactions

### Manual link

The reviewer searches the opposite source and sees differences before confirming. The preview includes any existing endpoint reservations that must be replaced. Confirmation requires a reason and saves an append-only decision.

### Accept unmatched

The action explicitly states that the transaction remains unmatched. It requires a reason and reserves the record from automatic linking. A newly arrived candidate creates an alert without silently removing the acceptance.

### Reject candidate

The relationship is excluded from every automatic matching stage while the decision applies. Both records can still match other records. New conflicting evidence creates an attention alert.

### Correction

A correction arrives through a source file, declared delta, or explicit restore-as-new-correction action. The application shows old and new observations and never edits uploaded bytes.

### Historical inspection

An old run opens with a clear historical banner. Values and pairings used in that run remain unchanged. Current review information is shown in a separately labelled panel.

## 8. Failure and empty states

| Situation | User experience |
|---|---|
| Missing required columns | Block preview and identify missing fields |
| Invalid rows | Show row, column, original value, and expected interpretation |
| Duplicate upload | Link to the existing import; do not reactivate old state |
| Stale activation preview | Recalculate changes against the new dataset head |
| Ambiguous candidates | Present the alternatives and withhold automatic pairing |
| Component too large | Explain the configured limit and require review or narrower scope |
| Worker failure | Keep the last successful result and offer safe retry |
| New inputs during a run | Retain the result as historical/stale and schedule the current inputs |
| Expired workspace | Explain loss of access and offer a new workspace |

## 9. Visual direction and accessibility

Use a restrained financial-operations style: light neutral background, dark navy text, one primary accent, tabular numerals, right-aligned amounts, explicit currencies, fixed table columns, and generous spacing in evidence views.

Every state has text as well as color. Forms have visible labels and announced errors. Users can search, open a row, navigate tabs, perform a decision, close the drawer, and return focus by keyboard. Progress shows real stages and counts rather than invented percentages.

Desktop supports the complete table-and-drawer workflow. Tablet uses a full-width evidence panel. Mobile supports summary, search, evidence, and basic decisions on dedicated pages; it does not compress the desktop table into unreadable cards.

## 10. Success criteria

- A visitor can complete the curated workflow in under five minutes without developer tools.
- Every automatic pair exposes its method, rules, evidence, input revisions, and ambiguity assessment.
- Manual linking never suppresses a discrepancy.
- Decisions survive refresh and rerun; reversals remain visible.
- Corrections do not change historical run evidence.
- Duplicate replay cannot roll current data backward.
- The global-allocation and tied-ambiguity examples produce the documented outcomes.
- Search and filters apply to the complete result, not only the displayed page.
- The full core workflow is keyboard operable and understandable without color.

## 11. Explicitly excluded from this release

- User accounts, passwords, recovery, and multi-user collaboration.
- One-to-many settlement allocation and netting.
- Foreign-exchange conversion.
- Live banking integrations.
- Posting journal entries or moving money.
- LLM decisions or uncalibrated probability claims.
- Microservices, Kafka, Kubernetes, and streaming ingestion.

These exclusions keep the domain honest. Each omitted feature requires rules beyond the assignment's one-to-one reconciliation problem.
