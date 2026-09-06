# 002 Source Mapping and Ingestion — Verification

- **Status:** In progress
- **Specification:** [spec.md](./spec.md)
- **Plan:** [plan.md](./plan.md)
- **Verified commit:** Pending
- **Environment:** Foundation reference environment; Python 3.12.14, Django 5.2.17, PostgreSQL 17.6 container on Windows 11

Task evidence is recorded as implementation advances. `Pending` and `Partial` entries must not be represented as passed.

## Acceptance results

| Scenario | Result | Required evidence |
|---|---|---|
| ING-A01 | Pending | Assignment adapter golden previews and activation |
| ING-A02 | Partial | `ING-T01.md`: pure parser rejects ambiguous/nonexistent local instants and accepts an explicit fold; persistent preview remains. |
| ING-A03 | Pending | Original → correction → replay temporal sequence |
| ING-A04 | Pending | Snapshot omission versus delta omission membership sets |
| ING-A05 | Pending | Malformed snapshot atomic-refusal test |
| ING-A06 | Pending | Formatting/order semantic-hash equivalence properties |
| ING-A07 | Pending | UTF-8 BOM and three-delimiter previews |
| ING-A08 | Partial | `ING-T01.md`: exact decimal parser and canonical-row constructor reject non-finite and out-of-range values without rounding; persistence remains. |
| ING-A09 | Partial | `ING-T01.md`: tagged raw cells preserve multiplicity-relevant missing/null/empty/value distinctions; hashing and duplicate rows remain. |
| ING-A10 | Partial | `ING-T02.md`: artifact, raw-row, logical-identity, observation, revision, and membership records refuse instance and bulk mutation; retained bytes and correction history remain. |
| ING-A11 | Pending | Two predefined adapters plus configurable-mapping parity |
| ING-A12 | Partial | `ING-T01.md`: cancelled canonical rows remain immutable and report ineligible; persistence and engine-input exclusion remain. |
| ING-A13 | Partial | `ING-T01.md`: delta contracts must distinguish upsert, cancel, and retract and cannot treat omission as an operation; membership behavior remains. |
| ING-A14 | Pending | Byte/row/column/field limit boundary tests |
| ING-A15 | Partial | `ING-T02.md`: every source and ingestion repository returns the same unavailable result for foreign and random IDs and refuses cross-workspace relationships; HTTP/download boundaries remain. |
| ING-A16 | Partial | `ING-T01.md`: required-value, enum, decimal, and datetime failures preserve row, field, original value, and expected interpretation; adapter/duplicate cases remain. |
| ING-A17 | Pending | Physical/semantic/resolved-state hash separation fixture |

## Requirement traceability

| Requirement | Planned implementation | Planned tests/evidence | Result |
|---|---|---|---|
| ING-001 | Private artifact vault and immutable row evidence | ING-A10 | Partial: immutable artifact metadata and raw-row evidence passed; private byte storage remains |
| ING-002 | Mapping/source contract revisions | ING-A01, ING-A11 | Partial: immutable pure and persistent revisions passed; adapters remain |
| ING-003 | Persistent preview and UI | ING-A01 | Pending |
| ING-004 | Typed validation pipeline | ING-A02, ING-A05, ING-A08, ING-A09, ING-A16 | Partial: field interpretation primitives passed; row/preview aggregation remains |
| ING-005 | Atomic activation | ING-A05 | Pending |
| ING-006 | Snapshot/delta membership services | ING-A04 | Pending |
| ING-007 | Immutable observations/revisions | ING-A03, ING-A10 | Partial: append-only persistence boundaries passed; activation/correction history remains |
| ING-008 | Four distinct hash contracts | ING-A03, ING-A06, ING-A09, ING-A17 | Pending |
| ING-009 | Historical replay guard | ING-A03 | Pending |
| ING-010 | Explicit restore/provider ordering | ING-A03 | Pending |
| ING-011 | Adapter registry and mapping workflow | ING-A11 | Pending |
| ING-012 | Cancellation eligibility | ING-A12 | Partial: canonical eligibility passed; persisted/engine boundary remains |
| ING-013 | Strict UTF-8 and explicit delimiters | ING-A07 | Pending |
| ING-014 | Exact numeric limits | ING-A08 | Partial: pure parser/constructor passed; database and preview refusal remain |
| ING-015 | Tagged multiplicity-preserving semantics | ING-A09 | Partial: raw cell tags passed; semantic serialization remains |
| ING-016 | Explicit delta operations and preview base | ING-A13 | Partial: operation contract passed; base-bound activation remains |
| ING-017 | Bounded parser | ING-A14 | Pending |
| ING-018 | Workspace scope for all ingestion resources | ING-A15 | Partial: persistence repositories and relationship factories passed; HTTP/storage boundaries remain |

## Automated checks

| Check | Result | Evidence to record |
|---|---|---|
| Unit/property | Partial | Exact parsing, tagged values, source/delta contracts, provenance immutability, and cancellation eligibility passed; hashing and membership functions remain. |
| Integration | Partial | PostgreSQL models, constraints, indexes, immutable evidence, ownership, and repository isolation passed; storage, activation, correction, replay, stale base, and cleanup remain. |
| Browser/accessibility | Pending | Upload-map-preview-activate/history journey on desktop and mobile |
| Security/isolation | Partial | Foreign/random repository parity and cross-workspace relationship refusal passed; revoked HTTP access, private downloads, filenames, and logs remain. |
| Performance | Pending | 10,000-row parse and activation time/memory plus page query counts |
| Operations | Partial | Django system checks and migration drift check passed for the persistence slice; final clean Compose and storage-volume behavior remain. |

## Measurements

| Metric | Workload/environment | Target | Observed |
|---|---|---:|---:|
| Preview time | 10,000 rows on named reference host | Measure; no advance speed claim | Pending |
| Preview peak memory | Near-limit 25 MiB CSV | Measure; remain bounded | Pending |
| Full-snapshot activation | 10,000 valid rows | Measure; atomic completion | Pending |
| Delta activation | 1,000 operations over 10,000-member base | Measure; atomic completion | Pending |
| Preview page queries | One 100-row page | Fixed ceiling after implementation | Pending |

## Known design boundaries

- Parsing is synchronous and bounded in this specification. Durable leased background execution arrives in specification 006.
- UTF-8 with optional BOM and comma, semicolon, or tab delimiters are the only first-release CSV inputs.
- Configurable mappings use allowlisted transformations only; executable expressions are excluded.
- PDF/OCR, live provider APIs, inferred snapshot/delta semantics, FX conversion, and sources without stable identity are excluded.

## Verification decision

Pending. Change the ingestion spec to `Verified` only after all 17 scenarios and 18 requirements have linked passing evidence at one tested commit.
