# [NNN] Feature Name — Specification

- **Status:** Draft
- **Owner:** [name]
- **Created:** [date]
- **Last updated:** [date]
- **Depends on:** [spec IDs or none]

## Problem

Describe the user or system problem without prescribing implementation.

## Outcome

Describe the observable result and why it matters.

## Users and scenarios

### [PREFIX-A01] Scenario name

- **Given** concrete starting state
- **When** the user or system performs an action
- **Then** observable outcome
- **And** additional observable outcome

## Requirements

Use MUST for normative behavior, SHOULD for a justified default, and MAY for optional behavior.

- **[PREFIX-001]** The system MUST ...
- **[PREFIX-002]** The system MUST ...

## Invariants

- State what must remain true across every path, retry, and concurrent action.
- End each invariant with the requirement IDs or constitutional principle it refines. Add a requirement when the invariant introduces independently testable behavior.

## Error, empty, retry, and concurrency behavior

| Condition | Required behavior | Requirement |
|---|---|---|
| [condition] | [observable behavior] | PREFIX-... |

## Data and history behavior

Describe creation, correction, retention, deletion, historical views, and idempotency.

## Security and privacy

Describe workspace authorization, untrusted inputs, sensitive output, and retention effects.

## Accessibility

Describe keyboard, focus, labels, announcements, non-color status, and responsive behavior.

## Performance and capacity

State measurable targets and the reference workload/environment. Mark hypotheses as targets.

## Out of scope

- Explicitly list plausible behavior this feature will not provide.

## Dependencies

- Design sections, ADRs, other specs, external contracts.

## Open questions

- A spec cannot become Ready while a question changes its public behavior or data model.

## Requirement-to-scenario matrix

| Requirement | Acceptance scenarios |
|---|---|
| PREFIX-001 | PREFIX-A01 |

## Change history

| Date | Change | Reason |
|---|---|---|
| [date] | Initial draft | [reason] |
