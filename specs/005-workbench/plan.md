# 005 Workbench and Run History — Implementation Plan

- **Status:** Complete
- **Specification:** [spec.md](./spec.md)
- **Target branch:** `codex/005-submission-workbench`
- **Last updated:** 8 September 2026

## Summary

Expose the verified ingestion, reconciliation, decision, and case services through a server-rendered Django workflow. The submission slice must let a visitor prepare both sources, start a run, understand every outcome, inspect field-level evidence, manually link two unmatched records with a reason, rerun, and see that the decision and earlier run remain preserved.

The implementation stays synchronous for the local submission. It uses progressive enhancement boundaries but requires no JavaScript. Every route resolves the active anonymous workspace before book, scope, run, case, occurrence, or transaction identifiers.

## Required submission sequence

1. Establish one default reconciliation scope and initial policy only after both source datasets have active revisions.
2. Render the latest successful run, summary counts, current cases, and prior runs without blending historical facts with current review state.
3. Render pair/unpaired evidence, raw and canonical values, field comparisons, policy/input versions, case occurrences, and lineage.
4. Preview and commit a manual link with both affected records and a mandatory reason; mark the result pending until rerun.
5. Execute the rerun synchronously, prove the manual link persists, and close the browser acceptance journey and README.

## Route contracts

| Method and route | Responsibility |
|---|---|
| `GET /books/{book}/workbench` | Readiness, latest/selected run, summary, paginated current cases, run history |
| `POST /books/{book}/runs` | Freeze, execute, and publish one scoped run; redirect to workbench |
| `GET /books/{book}/cases/{case}` | Current/historical evidence, comparisons, raw/canonical rows, decisions, occurrences, lineage |
| `POST /books/{book}/cases/{case}/link` | Validate the retained candidate, commit the exact reviewed link with reason and expected generation, and redirect to pending case evidence |

The manual-link page is the preview surface: it shows both the retained source record and candidate metadata before the reviewer submits the reasoned action. A dedicated JavaScript preview endpoint is deliberately deferred because the submission flow is server-rendered and no-JavaScript complete.

## Security and failure behavior

- Every full page and action uses the session workspace and returns the same 404 for foreign and absent resources.
- POST routes require CSRF and redirect after success.
- Invalid decisions return a labelled form error; stale generation/conflict returns 409 with a refresh path.
- A run failure leaves the previous successful run selectable and displays the failure without inventing progress.
- Manual decisions change current review state and dirty the scope; they never rewrite selected historical run facts.

## Verification

- Django client journey from two uploads through run, evidence, manual link, rerun, and history.
- Foreign/absent route matrix and CSRF checks.
- Assertions for field differences, pair origin, explicit currencies, reason requirement, pending labels, historical/current labels, and decision persistence.
- Keyboard structure, visible focus, narrow case layout, and no-JavaScript completion.
- Full PostgreSQL regression, migration drift, compilation, clean Compose, and diff hygiene.

## Deferred showcase work

Asynchronous job dispatch and optional SVG allocation visualization remain planned after the required submission journey. The complete candidate table, persisted truthful stages/counts, and failure/retry presentation are now delivered; durable background execution remains governed by specification 006.

## Completed showcase extension: UX-T06

The workbench now applies combined reference search, outcome and review filters, oldest/newest ordering, complete filtered totals, and cursor pagination in the authorized database query. Cursor namespaces bind the active filter set so a cursor cannot be replayed under different discovery criteria.

`GET /books/{book}/exports/cases.{csv|json}` provides two explicit views: filtered current-review state and complete selected-run facts. Both authorize the book, scope, and run through the active workspace. CSV output neutralizes formula-leading cells; JSON retains original text. Both formats preserve canonical decimals as strings and timestamps as labelled UTC offsets.

## Completed showcase extension: UX-T07

Weighted cases now resolve their retained assignment component and render every candidate edge, source identity, rule score, feature value/difference/similarity/weight/contribution, selection outcome, counterfactual objective, global gap, acceptance gate, contradiction, and coverage failure in an accessible table. This table remains the complete explanation without a graph.

Runs now persist `QUEUED`, `LOADING_INPUTS`, `MATCHING`, `PUBLISHING`, `COMPLETED`, or `FAILED` with only measured counts available at that stage. The workbench presents running and failed attempts separately while keeping the last successful result selected and usable. Failed runs include a retry action. The local submission request still executes synchronously; specification 006 will move the same persisted states behind durable background dispatch.
