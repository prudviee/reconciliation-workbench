# 002 Source Mapping and Ingestion — Tasks

- **Status:** In progress
- **Specification:** [spec.md](./spec.md)
- **Plan:** [plan.md](./plan.md)

## Task conventions

- `[ ]` pending, `[~]` in progress, `[x]` verified, `[!]` blocked.
- Each task includes implementation, verification, and evidence in one commit.
- Task order follows dependency order; a later task does not weaken an earlier invariant.

## Phase 1: pure interpretation contracts

- [x] **ING-T01 — Define immutable source and canonical value contracts** (`ING-002`, `ING-004`, `ING-012`, `ING-014`–`ING-016`; `ING-A02`, `ING-A08`, `ING-A09`, `ING-A12`, `ING-A13`, `ING-A16`)
  - Change: typed contracts, modes/operations/reference semantics, tagged raw cells, canonical row/provenance, structured row errors, exact decimal and datetime parsers.
  - Verify: framework-free imports; decimal precision/non-finite boundaries; aware/naive/ambiguous datetime cases; enum and required-value failures; cancelled eligibility.
  - Evidence: focused unit/property results and representative boundary table.

- [x] **ING-T02 — Add workspace-owned ingestion persistence** (`ING-001`, `ING-002`, `ING-007`, `ING-018`; `ING-A10`, `ING-A15`)
  - Change: source, book-side, mapping/contract revision, dataset, artifact, attempt, raw-row, logical identity, observation, revision, and membership models with constraints/indexes.
  - Verify: migrations, immutability entry points, same-workspace relationships, owner access, and foreign/random identifier parity.
  - Evidence: schema/constraint inspection and reusable isolation-contract results.

## Phase 2: safe preview

- [x] **ING-T03 — Stream private artifacts under hard limits** (`ING-001`, `ING-013`, `ING-017`, `ING-018`; `ING-A07`, `ING-A10`, `ING-A14`, `ING-A15`)
  - Change: generated private storage keys, UTF-8/BOM decoding, explicit delimiters, streamed physical hashing, byte/row/column/field limits, retained-byte quota transaction and compensation.
  - Verify: every limit boundary, invalid encoding, unsafe filename, quota refusal, file/record rollback, and revoked/foreign access.
  - Evidence: bounded-input tests, storage inspection, and quota invariants.

- [x] **ING-T04 — Build predefined adapters and configurable mapping previews** (`ING-002`–`ING-004`, `ING-011`, `ING-013`, `ING-017`; `ING-A01`, `ING-A02`, `ING-A07`, `ING-A11`, `ING-A14`, `ING-A16`)
  - Change: ledger/counterparty adapters, allowlisted configurable mapping, header validation, canonical preview, field provenance, duplicate detection, persistent ready/rejected attempts.
  - Verify: assignment golden fixtures, adapter parity, all row-error categories, duplicate row-number attribution, previewed delimiter, and no partial ready state.
  - Evidence: adapter contract matrix and retained preview examples.

- [x] **ING-T05 — Separate physical, semantic-input, observation, and state hashes** (`ING-008`, `ING-015`; `ING-A06`, `ING-A09`, `ING-A17`)
  - Change: versioned canonical serialization and deterministic digest functions.
  - Verify: byte differences vs semantic equivalence, order independence, multiplicity, missing/null/empty distinction, and different-base state divergence.
  - Evidence: golden digests and generated permutation/multiplicity tests.

## Phase 3: immutable activation

- [x] **ING-T06 — Activate full snapshots atomically** (`ING-005`–`ING-008`; `ING-A04`, `ING-A05`, `ING-A10`)
  - Change: row-locked activation, logical identities, immutable observations, dataset revisions/memberships, state hash, final head publication.
  - Verify: first activation, omission removal, malformed refusal, injected mid-activation rollback, historical evidence retention, and concurrent same-base conflict.
  - Evidence: transaction/failure results and before/after membership sets.

- [x] **ING-T07 — Preserve corrections and prevent historical replay rollback** (`ING-007`, `ING-009`, `ING-010`; `ING-A03`, `ING-A10`)
  - Change: correction classification, no-change detection, historical replay refusal, explicit restore-with-reason, optional trustworthy provider revision ordering.
  - Verify: original → correction → original replay; formatting-equivalent retry; restore as a new observation/revision; unchanged old bytes/rows/observations.
  - Evidence: temporal sequence with fixed IDs/hashes and immutable-history assertions.

- [x] **ING-T08 — Apply explicit deltas against the previewed base** (`ING-006`, `ING-008`, `ING-016`; `ING-A04`, `ING-A13`, `ING-A17`)
  - Change: copy-base membership, upsert/cancel/retract operations, omission semantics, expected-base conflict and resolved-state hashing.
  - Verify: four-operation fixture, two-base state divergence, stale concurrent activation, and rollback without head movement.
  - Evidence: membership transition table and race result.

## Phase 4: secure showcase workflow

- [x] **ING-T09 — Enforce cancellation and ingestion isolation at every boundary** (`ING-012`, `ING-018`; `ING-A12`, `ING-A15`)
  - Change: ineligible cancelled observations, scoped repositories/routes, authorized private byte downloads, revoked-workspace guards, safe content disposition and logs.
  - Verify: owner/foreign/random/expired/deleted cases for every ingestion resource and mutation; cancelled rows never enter the eligible-input adapter.
  - Evidence: contract-suite matrix and sanitized download headers/log capture.

- [ ] **ING-T10 — Deliver the upload, map, preview, and activate interface** (`ING-003`, `ING-004`, `ING-011`, `ING-013`, `ING-017`; `ING-A01`, `ING-A02`, `ING-A07`, `ING-A11`, `ING-A14`, `ING-A16`)
  - Change: server-rendered preparation pages, predefined/configurable contract forms, raw/canonical/provenance table, row errors, proposed changes, activation confirmation, and evidence history.
  - Verify: keyboard/no-JavaScript journey for both assignment formats and a third mapping; accessible errors; paginated large preview; stale activation recovery; desktop/mobile review.
  - Evidence: browser captures, accessibility inspection, query counts, and complete user journey.

## Phase 5: release evidence

- [ ] **ING-T11 — Measure and close ingestion acceptance** (`ING-001`–`ING-018`; `ING-A01`–`ING-A17`)
  - Change: 10,000-row fixtures, capacity measurements, clean-stack commands, README current-scope update, final traceability and limitations.
  - Verify: every acceptance/requirement row has linked evidence; bounded parse/activation measurements are recorded; full suite and clean Compose gate pass at one commit.
  - Evidence: completed verification record, environment, timings/memory, and final tested commit.

## Final traceability

| Requirement | Task IDs | Acceptance/evidence | Complete |
|---|---|---|---|
| ING-001 | ING-T02, ING-T03, ING-T11 | ING-A10 | Partial: T02–T03 passed |
| ING-002 | ING-T01, ING-T02, ING-T04, ING-T11 | ING-A01, ING-A11 | Partial: T01–T02, T04 passed |
| ING-003 | ING-T04, ING-T10, ING-T11 | ING-A01 | Partial: T04 passed |
| ING-004 | ING-T01, ING-T04, ING-T10, ING-T11 | ING-A02, ING-A05, ING-A08, ING-A09, ING-A16 | Partial: T01, T04 passed |
| ING-005 | ING-T06, ING-T11 | ING-A05 | Partial: T06 passed |
| ING-006 | ING-T06, ING-T08, ING-T11 | ING-A04 | Partial: T06, T08 passed |
| ING-007 | ING-T02, ING-T06, ING-T07, ING-T11 | ING-A03, ING-A10 | Partial: T02, T06–T07 passed |
| ING-008 | ING-T05–ING-T08, ING-T11 | ING-A03, ING-A06, ING-A09, ING-A17 | Partial: T05–T08 passed |
| ING-009 | ING-T07, ING-T11 | ING-A03 | Partial: T07 passed |
| ING-010 | ING-T07, ING-T11 | ING-A03 | Partial: T07 passed |
| ING-011 | ING-T04, ING-T10, ING-T11 | ING-A11 | Partial: T04 passed |
| ING-012 | ING-T01, ING-T09, ING-T11 | ING-A12 | Partial: T01, T09 passed |
| ING-013 | ING-T03, ING-T04, ING-T10, ING-T11 | ING-A07 | Partial: T03–T04 passed |
| ING-014 | ING-T01, ING-T11 | ING-A08 | Partial: T01 passed |
| ING-015 | ING-T01, ING-T05, ING-T11 | ING-A09 | Partial: T01, T05 passed |
| ING-016 | ING-T01, ING-T08, ING-T11 | ING-A13 | Partial: T01, T08 passed |
| ING-017 | ING-T03, ING-T04, ING-T10, ING-T11 | ING-A14 | Partial: T03–T04 passed |
| ING-018 | ING-T02, ING-T03, ING-T09–ING-T11 | ING-A15 | Partial: T02–T03, T09 passed |
