# 002 Source Mapping and Ingestion — Verification

- **Status:** Verified
- **Specification:** [spec.md](./spec.md)
- **Plan:** [plan.md](./plan.md)
- **Verified commit:** The commit containing this record
- **Environment:** Windows 11 host; Python 3.12.2 measurement environment; Python 3.12.14 clean container; Django 5.2.17; PostgreSQL 17.6

All 17 acceptance scenarios and 18 requirements have linked passing evidence. Task records live in [`evidence/`](./evidence/); machine-readable capacity and runtime results are `ING-T11-capacity.json` and `ING-T11-runtime.json`.

## Acceptance results

| Scenario | Result | Evidence |
|---|---|---|
| ING-A01 | Passed | T04 adapter parity; T10 raw/canonical/provenance browser journey and activation |
| ING-A02 | Passed | T01 ambiguous-time policy; T04 structured rejection; T10 accessible correction workflow |
| ING-A03 | Passed | T07 original → correction → replay guard and explicit restoration |
| ING-A04 | Passed | T06 exact snapshot membership; T08 delta omission preservation |
| ING-A05 | Passed | T04, T06 and T08 malformed/tampered/injected rollback evidence |
| ING-A06 | Passed | T05 semantic ordering and formatting equivalence fixtures |
| ING-A07 | Passed | T03 UTF-8/BOM and delimiter boundaries; T10 displayed delimiter |
| ING-A08 | Passed | T01/T04 exact precision refusal; T06 activation requires valid complete evidence |
| ING-A09 | Passed | T01/T04/T05 tagged missing/null/empty and multiplicity evidence |
| ING-A10 | Passed | T02–T07 immutable bytes, rows, observations, revisions and correction history; T10 inspection page |
| ING-A11 | Passed | T04 canonical parity; T10 configurable mapping and third-format upload |
| ING-A12 | Passed | T01/T04/T06 retained cancellation; T09 candidate-input exclusion |
| ING-A13 | Passed | T08 upsert/cancel/retract/omission transition and stale-base refusal |
| ING-A14 | Passed | T03 every exact/one-over limit; T10 visible blocked preview |
| ING-A15 | Passed | T02/T03/T09 repository, mutation, route, download and log isolation; T10 import-route parity |
| ING-A16 | Passed | T01/T04 complete structured error matrix; T10 rendered row evidence |
| ING-A17 | Passed | T05 distinct hash contracts; T08 identical semantic delta over divergent bases |

## Requirement traceability

| Requirement | Implementation | Tests/evidence | Result |
|---|---|---|---|
| ING-001 | Private artifact vault and immutable row evidence | A10; T02, T03, T10, T11 | Passed |
| ING-002 | Immutable mapping and source-contract revisions | A01, A11; T01, T02, T04 | Passed |
| ING-003 | Persistent raw/canonical preview and UI | A01; T04, T10 | Passed |
| ING-004 | Typed validation and activation gate | A02, A05, A08, A09, A16; T01, T04, T06, T10 | Passed |
| ING-005 | Atomic dataset-head publication | A05; T06, T08 | Passed |
| ING-006 | Exact snapshot and delta membership | A04; T06, T08 | Passed |
| ING-007 | Immutable corrections and history | A03, A10; T02, T06, T07, T10 | Passed |
| ING-008 | Distinct versioned hash identities | A03, A06, A09, A17; T05–T08 | Passed |
| ING-009 | Historical replay guard | A03; T07 | Passed |
| ING-010 | Explicit restore reason | A03; T07 | Passed |
| ING-011 | Two predefined plus configurable adapter | A11; T04, T10 | Passed |
| ING-012 | Cancellation remains ineligible | A12; T01, T06, T09 | Passed |
| ING-013 | UTF-8/BOM and explicit supported delimiter | A07; T03, T04, T10 | Passed |
| ING-014 | NUMERIC(38,12) refusal without rounding | A08; T01, T04 | Passed |
| ING-015 | Multiplicity and raw-cell semantic tags | A09; T01, T05 | Passed |
| ING-016 | Explicit base-bound delta operations | A13; T01, T08 | Passed |
| ING-017 | Byte/row/column/field limits | A14; T03, T10, T11 | Passed |
| ING-018 | Workspace scope on every ingestion boundary | A15; T02, T03, T09, T10 | Passed |

## Verification gates

| Gate | Result |
|---|---|
| Full automated suite | 230 passed at release closure |
| Django system check | 0 issues |
| Migration drift | no changes detected |
| Browser/accessibility | upload → preview → activation/history passed without JavaScript at default and 375 px viewports; no console errors or page overflow |
| Security/isolation | repository and HTTP parity, safe download headers, cancellation exclusion, sanitized logging passed |
| Clean Compose | db/web/worker healthy from empty project volumes; web readiness, worker heartbeat, migration ownership and shared private artifact volume passed |

## Capacity measurements

Measurements are reproducible with `python scripts/measure_ingestion.py --output specs/002-ingestion/evidence/ING-T11-capacity.json`. The script uses temporary private storage and rolls its database transaction back after checking the published membership counts.

| Metric | Workload | Observed time | Peak Python memory | Queries |
|---|---|---:|---:|---:|
| Near-limit preview | 10,000 rows, 24,610,077 bytes | 31.492 s | 154.65 MiB | 35 |
| Standard preview | 10,000 rows, 600,069 bytes | 30.736 s | 102.16 MiB | 35 |
| Full activation | 10,000 valid members | 38.641 s | 238.83 MiB | 79 |
| Delta activation | 1,000 operations over 10,000 members | 16.052 s | 176.51 MiB | 44 |
| Preview page | 50 retained rows from a 61-row fixture | test gate | bounded by 12 | ≤12 queries |

The capacity run produced 10,000 full-snapshot memberships and 9,900 delta memberships after 800 upserts, 100 cancellations and 100 retractions. Activation now batches identities, observations and memberships; query counts are bounded by batch count instead of one query per row.

These values are measurements, not latency promises. The 10,000-row boundary is safe and atomic but synchronous processing can take about one minute across preview and activation on the reference host. Specification 006 moves long work behind durable leased jobs.

## Supported boundary and limitations

- UTF-8 and UTF-8 BOM CSV; comma, semicolon or tab delimiter.
- Maximum 25 MiB, 10,000 data rows, 100 columns and 4,096 characters per field.
- PDF/OCR, live provider APIs, executable transforms, inferred date/currency/mode semantics, and providers without a stable identity are excluded.
- Provider-revision ordering remains optional; restoration is currently authorized through the verified explicit-reason path.
- PostgreSQL is required. SQLite is intentionally outside the verified environment.

## Verification decision

Verified. Source ingestion now satisfies the specification with immutable evidence, deterministic interpretation, full and delta activation, replay protection, workspace isolation, an accessible preparation workflow, measured capacity, and a clean reproducible stack.
