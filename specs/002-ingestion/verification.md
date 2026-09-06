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
| ING-A01 | Partial | `ING-T04.md`: ledger and counterparty assignment formats persist equivalent canonical previews with raw values and provenance; activation/UI remain. |
| ING-A02 | Partial | `ING-T01.md`, `ING-T04.md`: ambiguous/nonexistent time primitives and invalid-date preview rejection passed; browser-assisted selection remains. |
| ING-A03 | Passed | `ING-T07.md`: original → correction → original replay retains the correction; an explicit reason restores the original as a third immutable revision. |
| ING-A04 | Partial | `ING-T06.md`: a later full snapshot materializes only present identities and preserves omitted historical evidence; delta omission remains. |
| ING-A05 | Passed | `ING-T04.md`, `ING-T06.md`: rejected/tampered previews cannot activate, injected preview/activation failures roll back every write, and the earlier head remains unchanged. |
| ING-A06 | Passed | `ING-T05.md`: physical bytes differ while valid decimal/time formatting, column order, and row order normalize to the same persisted semantic-input digest. |
| ING-A07 | Partial | `ING-T03.md`, `ING-T04.md`: strict UTF-8/BOM scanning and persisted mapped delimiter previews passed; browser display remains. |
| ING-A08 | Partial | `ING-T01.md`, `ING-T04.md`: exact decimals reject non-finite/over-precision values and persist original values without canonical observations; activation remains. |
| ING-A09 | Passed | `ING-T01.md`, `ING-T04.md`, `ING-T05.md`: tagged raw values remain distinct, duplicate multiplicity changes semantic identity, and every duplicate row is identified. |
| ING-A10 | Partial | `ING-T02.md`–`ING-T07.md`: private bytes, raw rows, observations, revisions, and memberships remain append-only through correction, replay, no-change, and restore; final integrated inspection remains. |
| ING-A11 | Partial | `ING-T04.md`: two predefined adapters and one allowlisted configurable contract produce canonical parity; browser mapping workflow remains. |
| ING-A12 | Partial | `ING-T01.md`, `ING-T04.md`, `ING-T06.md`: cancelled rows persist, activate, and remain ineligible with provenance; engine-input exclusion remains. |
| ING-A13 | Partial | `ING-T01.md`: delta contracts must distinguish upsert, cancel, and retract and cannot treat omission as an operation; membership behavior remains. |
| ING-A14 | Partial | `ING-T03.md`, `ING-T04.md`: exact/one-over structural limits and bounded preview re-read passed; browser reporting remains. |
| ING-A15 | Partial | `ING-T02.md`, `ING-T03.md`: repositories hide foreign/random IDs, factories reject cross-workspace relationships, storage keys cannot escape the private root, and revoked workspaces retain no upload; HTTP/download boundaries remain. |
| ING-A16 | Partial | `ING-T01.md`, `ING-T04.md`: required-value, enum, decimal, datetime, header, extra-column, and duplicate failures preserve structured context and partial valid provenance; browser display remains. |
| ING-A17 | Partial | `ING-T05.md`: versioned physical, semantic-input, observation, and resolved-state functions are distinct and state hashes change with membership; two-base delta application remains. |

## Requirement traceability

| Requirement | Planned implementation | Planned tests/evidence | Result |
|---|---|---|---|
| ING-001 | Private artifact vault and immutable row evidence | ING-A10 | Partial: exact bytes, safe metadata, private storage, and immutable row schema passed; row parsing/correction retention remains |
| ING-002 | Mapping/source contract revisions | ING-A01, ING-A11 | Partial: immutable revisions plus two predefined and configurable typed contracts passed; release closure remains |
| ING-003 | Persistent preview and UI | ING-A01 | Partial: complete READY/REJECTED raw/canonical/provenance persistence passed; UI remains |
| ING-004 | Typed validation pipeline | ING-A02, ING-A05, ING-A08, ING-A09, ING-A16 | Partial: field and header aggregation, partial preview, duplicates, and atomic persistence passed; UI/activation gates remain |
| ING-005 | Atomic activation | ING-A05 | Partial: row-locked full-snapshot publication, final head write, stale conflict, and rollback passed; release closure remains |
| ING-006 | Snapshot/delta membership services | ING-A04 | Partial: exact full-snapshot replacement passed; delta remains |
| ING-007 | Immutable observations/revisions | ING-A03, ING-A10 | Partial: correction, omission, replay, no-change, and explicit restore history passed; release inspection remains |
| ING-008 | Four distinct hash contracts | ING-A03, ING-A06, ING-A09, ING-A17 | Partial: hashes drive no-change/replay and activated state passed; delta use remains |
| ING-009 | Historical replay guard | ING-A03 | Partial: prior state detection records REPLAYED without head movement; release closure remains |
| ING-010 | Explicit restore/provider ordering | ING-A03 | Partial: nonblank reason creates an audited restore revision; optional provider ordering is excluded until a trusted provider contract declares it |
| ING-011 | Adapter registry and mapping workflow | ING-A11 | Partial: allowlisted registry/contracts and canonical parity passed; mapping UI remains |
| ING-012 | Cancellation eligibility | ING-A12 | Partial: canonical and persisted-preview eligibility passed; engine boundary remains |
| ING-013 | Strict UTF-8 and explicit delimiters | ING-A07 | Partial: bounded scanner and mapped persistence passed all three delimiters/BOM; UI remains |
| ING-014 | Exact numeric limits | ING-A08 | Partial: pure and persisted preview refusal passed; activation remains |
| ING-015 | Tagged multiplicity-preserving semantics | ING-A09 | Partial: tagged serialization, order independence, and multiplicity passed; release closure remains |
| ING-016 | Explicit delta operations and preview base | ING-A13 | Partial: operation contract passed; base-bound activation remains |
| ING-017 | Bounded parser | ING-A14 | Partial: enforcement, typed failures, and bounded persisted preview passed; UI reporting remains |
| ING-018 | Workspace scope for all ingestion resources | ING-A15 | Partial: persistence repositories, relationship factories, private paths, quota transaction, and revoked intake passed; HTTP/download boundaries remain |

## Automated checks

| Check | Result | Evidence to record |
|---|---|---|
| Unit/property | Partial | Parsing, tagged values, adapters, validation/provenance, four versioned digest contracts, order/format normalization, multiplicity, and cancellation eligibility passed; membership transition functions remain. |
| Integration | Partial | Persistence, artifacts, previews, hashes, atomic activation, concurrency, no-change, replay, and explicit restore passed; delta and cleanup remain. |
| Browser/accessibility | Pending | Upload-map-preview-activate/history journey on desktop and mobile |
| Security/isolation | Partial | Repository parity, cross-workspace refusal, generated contained keys, metadata sanitization, and pre-stage revoked-workspace refusal passed; HTTP downloads and logs remain. |
| Performance | Pending | 10,000-row parse and activation time/memory plus page query counts |
| Operations | Partial | Django/migration checks passed and Compose declares one shared private artifact volume for web/worker; final clean-stack volume behavior remains. |

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
