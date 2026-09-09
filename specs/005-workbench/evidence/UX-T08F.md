# UX-T08F reasoned candidate rejection

## Acceptance matrix

| Requirement | Evidence | Result |
|---|---|---|
| Rejection can start only from a candidate retained in the current run's allocation evidence | Current-occurrence candidate lookup and forged-observation assertions | Pass |
| Preview identifies both logical records, both exact observations, financial values, score, and blocking reasons | Rendered preview assertions and live browser inspection | Pass |
| Preview lists every active saved decision involving either record and states that none are displaced | Scoped decision query and explicit empty-state assertion | Pass |
| A non-empty reason is required before mutation | Blank-reason response and unchanged-decision assertion | Pass |
| Commit is bound to the displayed resolution generation and reviewed observations | Decision command concurrency contract and submitted hidden-baseline assertions | Pass |
| Rejection reserves neither endpoint, so both records remain available for other relationships | Zero-active-claim assertion and domain authority contract | Pass |
| Rerun removes only the rejected relationship and preserves both records as unmatched in the one-edge fixture | Post-rerun pair and unpaired assertions | Pass |
| CSRF and workspace boundaries protect preview and commit | CSRF rejection plus foreign GET/POST equality assertions | Pass |

## Verification record

- Focused weighted-evidence and rejection workflows: `2 passed, 26 deselected`.
- Related reconciliation, decision, persistence, and browser regression: `70 passed`.
- Full PostgreSQL regression: `535 passed`.
- Django system check: no issues; migration drift check: no changes detected.
- Live browser verification on a weighted-global candidate:
  - the allocation table exposed the `10,000 bp` rule score, all four feature contributions, global selection, `3,000 bp` counterfactual gap, gate result, and `Review rejection` action;
  - the confirmation showed both logical IDs, both observation IDs, timestamps, instruments, explicit USD amounts, score, and active-decision impact;
  - submitting reason `The operations team confirmed these are separate trades despite similar financial values.` saved an active `reject candidate` decision without endpoint claims;
  - the workbench retained the prior `1 pair / 1 candidate` result and displayed `Changes are waiting for a rerun`;
  - rerunning produced `0 pairs / 2 unmatched / 0 candidates`, and the new run classified the saved decision as unchanged.
- Docker web, worker, and PostgreSQL services remained healthy during the browser journey.
