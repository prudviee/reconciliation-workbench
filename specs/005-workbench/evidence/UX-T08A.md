# UX-T08A accept-unmatched browser acceptance

## Acceptance matrix

| Requirement | Evidence | Result |
|---|---|---|
| An eligible unpaired case previews the retained record and offers accept-unmatched | Rendered case-detail assertion | Pass |
| The action requires a non-empty reason | Empty-reason response assertion | Pass |
| The saved decision reserves one record and marks the workbench pending | Decision command and pending-workbench assertions | Pass |
| A rerun publishes the record as `ACCEPTED_UNMATCHED` | Persisted run-unpaired assertion | Pass |
| Cancelled, pending, or already-reviewed evidence does not offer a conflicting initial action | Template state assertions and optimistic-generation guard | Pass |
| The route remains protected by the active anonymous workspace and CSRF middleware | Existing guarded case lookup and Django POST middleware | Pass |

## Verification record

- Focused browser workflow tests: `2 passed, 15 deselected`.
- Related ingestion, run, and resolution regression: `61 passed`.
- Full PostgreSQL regression: `533 passed`.
- Django system check: no issues; migration drift check: no changes detected.
- Live browser verification:
  - the eligible `TX-1003` case offered the accept-unmatched action and required a reason;
  - saving the decision displayed the pending-publication message and hid both initial reviewer actions;
  - the workbench reported changes waiting for a rerun;
  - rerunning created immutable run `732d07d9-e3f0-4b81-bd6a-d596a56270b5`, removed the candidate, and showed `TX-1003` as `unchanged`;
  - the published case retained the original source evidence, recorded resolution generation `1`, and kept the earlier run in occurrence history.
- Diff hygiene: passed; only repository line-ending conversion notices were emitted.
