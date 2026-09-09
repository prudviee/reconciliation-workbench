# UX-T08E conflict-complete decision replacement

## Acceptance matrix

| Requirement | Evidence | Result |
|---|---|---|
| Replacement choices come only from the current run's retained left and right inputs | Query ownership, current-run filtering, and browser workflow assertions | Pass |
| The confirmation step shows the target authority, proposed identities, current reason, and every additional active decision that will be displaced | Conflict-complete preview workflow assertions | Pass |
| Replacement requires a non-empty new reason | Blank-reason response and unchanged-revision assertions | Pass |
| A forged or incomplete confirmation cannot mutate authority | Invalid-preview response and unchanged-revision assertions | Pass |
| Commit succeeds only for the previewed target revision, resolution generation, reviewed observations, and complete conflict set | Decision service concurrency contract and browser workflow assertions | Pass |
| Replacement appends history, transfers active claims, and supersedes every approved conflict | Revision, claim, and supersession assertions | Pass |
| Replacement marks reconciliation pending while the previously published run remains inspectable | Workbench workflow assertion | Pass |
| Workspace and book ownership remain enforced for record choices, preview, and mutation | Query and command ownership contracts | Pass |

## Verification record

- Focused browser workflow test: `1 passed, 17 deselected`.
- Related decision and browser regression: `42 passed`.
- Full PostgreSQL regression: `534 passed`.
- Django system check: no issues; migration drift check: no changes detected.
- Live browser verification on the saved `TX-1003 ↔ CP-9003` authority:
  - the decision page listed current records from each side and preselected the authority's existing endpoints;
  - the preview showed the target revision, original reason, exact record identities, and explicitly stated that no additional decisions would be displaced in this dataset;
  - submitting reason `Reconfirmed both source identities after reviewing the retained records.` created revision `2` as `REPLACE`;
  - revision `1` remained visible as historical evidence while revision `2` became the active authority;
  - the workbench displayed `Changes are waiting for a rerun` and kept the earlier completed run available for inspection.
- The automated browser workflow additionally creates two active unmatched authorities and verifies that replacement previews and supersedes the conflicting authority as one exact commit.
