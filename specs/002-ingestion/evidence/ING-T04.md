# ING-T04 Evidence — Source Adapters and Persistent Preview

- **Task:** ING-T04
- **Result:** Passed
- **Date:** 6 September 2026
- **Environment:** Python 3.12.14, Django 5.2.17, PostgreSQL 17.6

## Implemented boundary

The adapter registry defines the assignment ledger format, the assignment counterparty format, and a configurable mapping composed only from typed column bindings, declared constants, exact datetime/decimal parsers, and explicit enum maps. Stored contracts round-trip through JSON without executable expressions and reject unregistered adapter keys, unknown canonical fields, missing required fields, and invalid enum targets.

The preview pipeline rereads private CSV bytes under the same structural limits, validates required and duplicate headers, tags every raw cell as missing/null/empty/value, aggregates independent field failures, and marks every row involved in a duplicate source identity. Valid fields and their provenance remain visible when another field fails. Cancelled rows remain visible and are marked ineligible.

Preview persistence is atomic. An attempt becomes READY only with zero blocking errors; otherwise it becomes REJECTED. Header issues live once on the attempt, while row issues retain row number, field, original value, code, and expectation. Raw rows are inserted in bounded batches, and an injected post-insert failure rolls back the attempt and every row.

## Verification

| Check | Command scope | Result |
|---|---|---:|
| Adapter contracts and serialization | `tests/test_source_adapters.py` | 8 passed |
| Interpretation and persistent preview | `tests/test_ingestion_preview.py` | 12 passed |
| Focused adapter/preview total | both modules | 20 passed |
| Full regression suite | all tests | 181 passed |
| Django system check | registered models/configuration | 0 issues |
| Migration drift | models against migrations including attempt validation | no changes detected |

The golden parity fixture maps the two assignment headers and a semicolon-delimited third-party format to the same reference, UTC instant, instrument, side, exact decimals, currency, state, and eligibility. Other cases cover four simultaneous typed field failures, missing/duplicate/extra columns, duplicate valid and invalid rows, raw-cell tags, partial canonical evidence, cancelled rows, header-level persistence, and atomic rollback.

## Remaining acceptance scope

The backend preview is complete for full snapshots. The server-rendered upload/mapping/preview interface is delivered in ING-T10. Semantic hashes arrive in ING-T05, dataset activation in ING-T06, and delta preview/activation in ING-T08.
