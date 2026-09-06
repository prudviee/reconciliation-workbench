# 002 Source Mapping and Ingestion — Verification

- **Status:** Pending
- **Specification:** [spec.md](./spec.md)
- **Plan:** [plan.md](./plan.md)
- **Verified commit:** Pending
- **Environment:** Pending; inherit the verified foundation environment and record changes

No ingestion implementation exists yet. `Pending` entries are deliberate and must not be represented as passed.

## Acceptance results

| Scenario | Result | Required evidence |
|---|---|---|
| ING-A01 | Pending | Assignment adapter golden previews and activation |
| ING-A02 | Pending | Ambiguous datetime refusal and corrected-contract preview |
| ING-A03 | Pending | Original → correction → replay temporal sequence |
| ING-A04 | Pending | Snapshot omission versus delta omission membership sets |
| ING-A05 | Pending | Malformed snapshot atomic-refusal test |
| ING-A06 | Pending | Formatting/order semantic-hash equivalence properties |
| ING-A07 | Pending | UTF-8 BOM and three-delimiter previews |
| ING-A08 | Pending | Decimal precision/range rejection without observation |
| ING-A09 | Pending | Multiplicity hash and duplicate row-number evidence |
| ING-A10 | Pending | Retained immutable artifact/raw/observation provenance after corrections |
| ING-A11 | Pending | Two predefined adapters plus configurable-mapping parity |
| ING-A12 | Pending | Cancelled evidence retained and excluded from eligible inputs |
| ING-A13 | Pending | Delta upsert/cancel/retract/omit plus stale-base conflict |
| ING-A14 | Pending | Byte/row/column/field limit boundary tests |
| ING-A15 | Pending | Cross-workspace repository, route, mutation, and download contract |
| ING-A16 | Pending | Complete row-error category fixture with original values and expectations |
| ING-A17 | Pending | Physical/semantic/resolved-state hash separation fixture |

## Requirement traceability

| Requirement | Planned implementation | Planned tests/evidence | Result |
|---|---|---|---|
| ING-001 | Private artifact vault and immutable row evidence | ING-A10 | Pending |
| ING-002 | Mapping/source contract revisions | ING-A01, ING-A11 | Pending |
| ING-003 | Persistent preview and UI | ING-A01 | Pending |
| ING-004 | Typed validation pipeline | ING-A02, ING-A05, ING-A08, ING-A09, ING-A16 | Pending |
| ING-005 | Atomic activation | ING-A05 | Pending |
| ING-006 | Snapshot/delta membership services | ING-A04 | Pending |
| ING-007 | Immutable observations/revisions | ING-A03, ING-A10 | Pending |
| ING-008 | Four distinct hash contracts | ING-A03, ING-A06, ING-A09, ING-A17 | Pending |
| ING-009 | Historical replay guard | ING-A03 | Pending |
| ING-010 | Explicit restore/provider ordering | ING-A03 | Pending |
| ING-011 | Adapter registry and mapping workflow | ING-A11 | Pending |
| ING-012 | Cancellation eligibility | ING-A12 | Pending |
| ING-013 | Strict UTF-8 and explicit delimiters | ING-A07 | Pending |
| ING-014 | Exact numeric limits | ING-A08 | Pending |
| ING-015 | Tagged multiplicity-preserving semantics | ING-A09 | Pending |
| ING-016 | Explicit delta operations and preview base | ING-A13 | Pending |
| ING-017 | Bounded parser | ING-A14 | Pending |
| ING-018 | Workspace scope for all ingestion resources | ING-A15 | Pending |

## Automated checks

| Check | Result | Evidence to record |
|---|---|---|
| Unit/property | Pending | Exact parsing, tagged values, contracts, hashing, snapshot/delta functions |
| Integration | Pending | Storage, persistence, activation, correction, replay, stale base, cleanup |
| Browser/accessibility | Pending | Upload-map-preview-activate/history journey on desktop and mobile |
| Security/isolation | Pending | Foreign/random/revoked parity, private downloads, safe filenames/logs |
| Performance | Pending | 10,000-row parse and activation time/memory plus page query counts |
| Operations | Pending | Migrations, checks, clean Compose stack and storage volume behavior |

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
