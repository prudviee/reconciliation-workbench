# ING-T05 Evidence — Versioned Hash Contracts

- **Task:** ING-T05
- **Result:** Passed
- **Date:** 6 September 2026
- **Environment:** Python 3.12.14, Django 5.2.17, PostgreSQL 17.6
- **Hash scheme:** `reconciliation-sha256-v1`

## Implemented boundary

Four identities now use explicit domain functions and distinct type-prefixed inputs:

| Identity | Meaning |
|---|---|
| Physical artifact | SHA-256 over exact byte chunks, independent of chunk boundaries |
| Semantic input | Contract digest plus sorted, length-prefixed semantic rows and normalized headers |
| Observation fingerprint | Canonical field values plus contract and provenance meaning for one observation |
| Resolved state | Sorted stable-identity/observation-fingerprint membership pairs |

Mapping and source-contract revisions also use the same versioned canonical JSON serializer. Preview refuses stored contract or mapping payloads whose recorded digest no longer matches their content.

Valid decimals normalize without rounding, equivalent aware timestamps normalize to fixed UTC text, and row/header order does not affect semantic identity. Invalid values retain explicit raw tags. Missing, null, empty, and ordinary raw values cannot collide. Sorted records preserve duplicates, so one row and two identical rows have different semantic digests.

## Verification

| Check | Command scope | Result |
|---|---|---:|
| Pure hashing contracts and golden values | `tests/test_ingestion_hashing.py` | 14 passed |
| Persistent preview/hash integration | `tests/test_ingestion_preview.py` | 15 passed |
| Combined hashing/preview checks | both modules | 29 passed |
| Full regression suite | all tests | 198 passed |
| Django system check | project configuration | 0 issues |
| Migration drift | models against migrations | no changes detected |

Golden SHA-256 values pin the serialization scheme. Property-oriented cases prove byte chunk invariance, JSON key-order invariance, decimal/time normalization, row/header order independence, duplicate multiplicity, raw-tag separation, observation change sensitivity, resolved-state order independence, and membership sensitivity. The integrated preview test persists equal semantic hashes for byte-different, column-reordered, row-reordered, decimal-reformatted, and timezone-equivalent CSV files.

## Remaining acceptance scope

The digest primitives and preview integration are complete. ING-T06 applies observation and resolved-state hashes during snapshot activation; ING-T07 uses them for correction/replay behavior; ING-T08 proves equal delta semantic input can resolve to different state hashes against different bases.
