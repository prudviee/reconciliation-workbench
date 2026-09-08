# UX-T08C selected historical occurrence evidence

## Acceptance matrix

| Requirement | Evidence | Result |
|---|---|---|
| Selecting a historical run lists that run's cases separately from current review | Historical workbench workflow assertion | Pass |
| Every historical result links to its exact retained occurrence | Run-qualified case URL assertion | Pass |
| A case removed from current review remains inspectable in its original run | Manual-link transition workflow assertion | Pass |
| Historical evidence and current review status cannot be mistaken for one another | Historical notice and `not in current review` assertions | Pass |
| Reviewer mutations are unavailable on historical evidence | Manual-link and accept-unmatched absence assertions | Pass |
| A run that does not contain the case cannot be used to access it | Case/run membership 404 assertion | Pass |
| Large historical runs use bounded, cursor-based pages | Selected-run query projection and pagination link | Pass |

## Verification record

- Focused historical browser and projection tests: `2 passed`.
- Related workbench, run, and browser regression: `44 passed`.
- Full PostgreSQL regression: `533 passed`.
- Django system check: no issues; migration drift check: no changes detected.
- Live browser verification with runs `215f4674-bfaf-48c1-bf3e-a45a741b6cbf` and `732d07d9-e3f0-4b81-bd6a-d596a56270b5`:
  - selecting the earlier run rendered a distinct four-case immutable-results table and the separate four-case current-review table;
  - the selected summary read `historical · completed`;
  - opening historical `TX-1003` retained run `215f4674`, resolution generation `0`, the original observation and raw values;
  - the page labelled its timeline `historical` and its current review `unchanged`;
  - neither reviewer action was present;
  - the occurrence history linked both the historical and current facts;
  - the Workbench breadcrumb returned to the same selected historical run.
- Diff hygiene: passed; only repository line-ending conversion notices were emitted.
