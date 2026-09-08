# UX-T07 allocation and run-state acceptance

## Acceptance matrix

| Requirement | Evidence | Result |
|---|---|---|
| Weighted cases show every candidate and all persisted feature contributions | `test_weighted_run_persists_candidates_components_and_comparisons` | Pass |
| The candidate table names source identities, rule score, global selection, counterfactual objective, global gap, and gates | Rendered weighted-case assertions | Pass |
| The table remains a complete explanation without a graph | Service and rendered-content assertions over every candidate in the retained component | Pass |
| Runs persist real stages and only measured counts | Run publication and failure assertions | Pass |
| No estimated percentage is stored or shown | Progress contract and workbench template inspection | Pass |
| A running rerun leaves the last successful result selected and usable | `test_workbench_keeps_current_result_during_running_and_failed_rerun` | Pass |
| A failed rerun preserves that result and presents failure code plus retry | Service, workbench rendering, and retry redirect assertions | Pass |
| Progress and evidence queries remain workspace-scoped | Existing run/case isolation suite plus guarded workbench route | Pass |

## Verification record

- Full PostgreSQL regression: `469 passed`.
- Django system checks: passed.
- Migration drift check: passed (`No changes detected`).
- Progress migration applied successfully in the running Compose stack.
- `git diff --check`: passed.
- Running stack readiness: `GET /health/ready` returned HTTP 200 with database ready.
- Browser inspection confirmed completed stage labels after backfilling existing runs.

The local request path remains synchronous for the submission build. These durable progress states are the UI and persistence contract that specification 006 will use for background execution.
