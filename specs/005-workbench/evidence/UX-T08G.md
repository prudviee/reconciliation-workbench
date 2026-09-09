# UX-T08G changed-evidence reaffirmation

## Acceptance matrix

| Requirement | Evidence | Result |
|---|---|---|
| Reaffirmation is offered only for an active decision whose current evidence differs from its reviewed baseline | Decision-detail visibility assertions for `EVIDENCE_CHANGED`, plus the post-rerun absence of the action | Pass |
| Preview compares the prior reviewed observation baseline with every current authority endpoint | Rendered old/new observation assertions and live browser inspection of both current records | Pass |
| A non-empty reason is required before mutation | Blank-reason response and unchanged-history assertion | Pass |
| Commit is bound to the displayed decision revision, resolution generation, and complete current observation set | Hidden-baseline assertions and stale-evidence conflict response | Pass |
| Reaffirmation appends a new revision and moves active endpoint claims to current observations | Historical-link/current-reaffirm history assertions and active-claim checks | Pass |
| The prior reconciliation result remains visible while the book is marked pending | Post-commit workbench assertions and live browser inspection | Pass |
| Rerun evaluates the reaffirmed baseline and resets review health to unchanged | Post-rerun decision-health assertion and live browser result | Pass |
| CSRF and workspace route boundaries protect the mutation | CSRF rejection plus the shared decision-detail workspace isolation contract | Pass |

## Verification record

- Focused changed-evidence and browser reaffirmation workflows: `2 passed, 27 deselected`.
- Full PostgreSQL regression: `536 passed`.
- Django system check: no issues; migration drift check: no changes detected; Git whitespace check: clean.
- Live browser verification on an amount correction from `100 USD` to `101 USD`:
  - the decision page displayed `evidence_changed · comparison_changed`, the prior observation baseline, and both current authority endpoints;
  - submitting reason `Reviewed the corrected amount and confirmed the relationship remains authoritative.` appended revision 2 as `reaffirm` while retaining revision 1 as historical `link`;
  - the workbench retained the previous result and displayed the pending-rerun state;
  - rerunning produced the expected pair and classified the current decision as unchanged.
- Docker web, worker, and PostgreSQL services remained healthy during the browser journey.
