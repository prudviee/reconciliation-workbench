# ING-T01 Verification Evidence

- **Task:** Define immutable source and canonical value contracts
- **Requirements:** `ING-002`, `ING-004`, `ING-012`, `ING-014`–`ING-016`
- **Acceptance scenarios:** `ING-A02`, `ING-A08`, `ING-A09`, `ING-A12`, `ING-A13`, `ING-A16`
- **Date:** 6 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence; see Git history for `ING-T01`

## Implemented scope

- Framework-independent, immutable dataset mode, operation, reference, side, state, raw-cell, validation, binding, enum, source-contract, provenance, and canonical-row values.
- Explicit distinction between missing, declared null, empty, and exact source text.
- Structured field failures containing row number, canonical field, failure code, original display value, and expected interpretation.
- Base-10 `Decimal` parsing without binary floating point, silent rounding, or acceptance beyond `NUMERIC(38,12)`.
- Exact timestamp-format parsing, UTC normalization, required timezone for naive input, and detection of ambiguous and nonexistent local instants.
- Explicit three-operation delta contract: upsert, cancel, and retract. Full snapshots cannot carry a delta operation map.
- Cancelled observations remain immutable canonical evidence but report ineligible for matching; retractions cannot create observations.
- Read-only field-provenance projection and uniqueness checks for contract bindings, enum values, operation tokens, null tokens, and provenance fields.

## Checks and results

| Check | Result | Evidence summary |
|---|---|---|
| Focused domain/architecture suite | Pass | 33 ingestion, domain-import, and static architecture checks passed. |
| Full regression suite | Pass | 118 tests passed against PostgreSQL 17.6. |
| Raw value distinctions | Pass | Missing, declared null, empty, and value cells retained distinct kind/value pairs. |
| Required fields | Pass | Missing, null, empty, and whitespace-after-trim failures retained row, field, original value, and expectation. |
| Decimal capacity | Pass | 26 integer plus 12 fractional digits, a 12-place subunit, negative values, and exponent notation within capacity passed. |
| Decimal refusal | Pass | Invalid text, NaN, infinity, 13 fractional places, 27 integer digits with scale 12, and exponent overflow returned typed failures without rounding. |
| Timestamp semantics | Pass | Offset input normalized to UTC; naive input required a timezone; DST overlap rejected by default and accepted only with explicit earlier/later fold; DST gap was rejected. |
| Enum semantics | Pass | Only declared source tokens mapped; an unknown token remained available on the structured issue. |
| Delta contract | Pass | Delta mode required nonblank operation field and mappings covering upsert, cancel, and retract; snapshots rejected operation mappings. |
| Cancellation | Pass | Settled rows were eligible, cancelled rows were ineligible, cancellation required cancelled state, and retraction could not create an observation. |
| Immutability | Pass | Frozen source/canonical objects rejected mutation and provenance mapping rejected writes/duplicate fields. |
| Domain boundary | Pass | Runtime import and static AST checks found no Django, Psycopg, web, storage, or adapter dependency. |
| Migration/Django checks | Pass | No migration drift; Django reported no system-check issues. |

## Scope boundary

This task defines interpretation values and field-level behavior only. Persistent source-contract revisions, adapter row aggregation, duplicate-key reporting, hashes, artifacts, previews, observations, and dataset activation are assigned to `ING-T02`–`ING-T08`.
