# 002 Source Mapping and Ingestion — Implementation Plan

- **Status:** In progress
- **Specification:** [spec.md](./spec.md)
- **Target branch:** `codex/002-ingestion`
- **Last updated:** 6 September 2026

## Summary

Build a bounded, deterministic CSV ingestion pipeline that preserves original evidence, translates the assignment's two formats and one configurable format into a shared canonical model, previews every interpretation, and atomically activates immutable dataset revisions. The implementation extends the verified anonymous-workspace, quota, revocation, and privacy boundaries from specification 001.

The first vertical slice uploads one ledger CSV and one counterparty CSV into a reconciliation book, previews raw and canonical rows with validation, activates two full-snapshot dataset revisions, and proves that earlier artifacts and observations remain unchanged after a correction.

## Assignment formats

The predefined adapters come from the assignment evidence; the assignment is a problem source and does not override the public-showcase decisions.

| Canonical field | Ledger adapter | Counterparty adapter | Interpretation |
|---|---|---|---|
| source record key | `trade_id` | `reference` | Required stable identity |
| business reference | `trade_id` | `reference` | Trusted shared reference in these predefined contracts |
| executed time | `traded_at` | `executed_at` | ISO-8601 with offset vs `%Y-%m-%d %H:%M:%S` in declared UTC |
| instrument | `instrument` | `symbol` | Trimmed canonical text |
| side | `side` | `direction` | `BUY`/`SELL` vs `B`/`S` |
| quantity | `quantity` | `qty` | Exact decimal, maximum `NUMERIC(38,12)` |
| unit price | `price` | `unit_price` | Exact decimal, maximum `NUMERIC(38,12)` |
| gross amount | `gross_amount` | `total` | Exact decimal, maximum `NUMERIC(38,12)` |
| currency | constant `USD` | constant `USD` | Explicit contract constant for the assignment's `*-USD` instruments |
| state | `state` | `status` | `SETTLED`/`CANCELLED`; cancelled remains evidence but is ineligible |

Both predefined contracts are `FULL_SNAPSHOT`. A configurable contract must explicitly choose mappings, constants, date format, timezone, enum mappings, stable identity, reference semantics, currency semantics, and snapshot/delta mode.

## Constitution check

| Principle | Plan compliance |
|---|---|
| Evidence is immutable | Original bytes, raw rows, observations, and dataset revisions are append-only through application services. |
| Identity and agreement differ | Stable source identity and business reference are mapped separately from amounts, timestamps, and state. |
| Automatic matching may abstain | Ingestion marks invalid/cancelled rows and never makes pairing decisions. |
| Results are explainable | Every canonical value keeps artifact, row, source column, original value, mapping revision, parser version, and validation provenance. |
| Reviewer authority is durable | Ingestion creates immutable evidence for later decisions and never edits decision state. |
| Runs publish atomically | Dataset activation uses one locked transaction and changes the head only after all membership rows exist. |
| Decimal/time semantics are explicit | Decimal limits reject rather than round; every timestamp parser has an explicit format and timezone. |
| Anonymous access is isolated | Every repository and route begins with session-derived `WorkspaceAccess`; IDs never authorize access. |
| Domain core is framework-independent | CSV syntax adapters and normalization policies use immutable Python values and import no Django/storage/request types. |
| Specifications precede behavior | Every task below maps to reviewed `ING` requirements and scenarios. |
| Claims require evidence | Parsing, limits, hashing, immutability, atomicity, isolation, and UI claims have named tests and records. |
| Complexity earns its place | Parsing is synchronous and bounded in this spec; specification 006 moves it behind leased jobs without changing domain contracts. |

## Module boundaries

| Module | Responsibility | Requirement IDs |
|---|---|---|
| `reconciliation.domain.ingestion` | Typed source contracts, raw-cell semantics, canonical rows, validation errors, snapshot/delta operations, deterministic serialization and hashes | ING-002–ING-004, ING-006, ING-008, ING-012–ING-017 |
| `sources` | Source systems, book-side assignments, immutable mapping revisions, immutable contract revisions, adapter registry | ING-002, ING-011, ING-018 |
| `ingestion` | Private artifact vault, attempts, raw rows, previews, logical transactions, observations, revisions, memberships, activation service | ING-001, ING-003–ING-010, ING-012, ING-016–ING-018 |
| `books` | Book source roles and dataset-head ownership | ING-005, ING-006, ING-018 |
| `foundation` | Server-rendered upload, mapping, preview, activation, evidence and private-download routes | ING-003, ING-011, ING-013, ING-017, ING-018 |
| `workspaces` | Retained-byte quota reservation/release and active-workspace enforcement | ING-001, ING-017, ING-018 |
| `observability` | Correlated, fixed-schema operational events without filenames, row values, or artifact bytes | ING-001, ING-018 |

Dependency direction remains inward: source/ingestion adapters may call the pure domain package; the domain package never imports Django, ORM models, file storage, HTTP, or the wall clock.

## Domain contracts

### Source contract

`SourceContractRevision` is immutable and contains:

- adapter key and parser version;
- explicit column-to-canonical mapping and allowlisted constants;
- stable source-key field and identity namespace;
- business-reference field and `TRUSTED_SHARED`, `SECONDARY`, or `NONE` semantics;
- exact timestamp format plus IANA timezone when the source value has no offset;
- side/state enum maps;
- explicit currency field or constant;
- `FULL_SNAPSHOT` or `DELTA` mode and, for delta, an explicit operation map;
- canonical serialization version and digest.

No mapping expression executes user code. Transformations are selected from a small allowlist: trim text, exact enum mapping, exact decimal parsing, declared datetime parsing, and a declared constant.

### Raw cell states

Before validation, each expected field is represented as one of:

- `MISSING`: the source column is absent from the row;
- `NULL`: the contract's explicit null token matched;
- `EMPTY`: the column exists with an empty string;
- `VALUE`: the exact decoded string.

These tags are included in semantic serialization so missing, null, and empty remain distinct. Duplicate rows remain duplicate serialized entries.

### Canonical observation

The immutable canonical row contains source key, business reference, UTC execution instant, instrument, side, quantity, unit price, gross amount, currency, state, eligibility, operation, and field-level provenance. Decimal values enter from strings and are never constructed through binary floating point.

The numeric validator rejects non-finite values, more than 38 total digits, or more than 12 fractional digits. It does not silently quantize. Timestamp parsing rejects a missing format, a missing timezone for naive values, nonexistent local instants, and ambiguous local instants unless the contract explicitly chooses a fold policy.

### Failure types

Typed failures distinguish encoding, delimiter, byte limit, row limit, column limit, field-length limit, missing column, missing/null/empty required value, unknown enum, ambiguous/nonexistent date, invalid/non-finite/over-precision decimal, duplicate source key, stale base, historical replay, unavailable resource, and activation conflict.

Browser errors show row number, field, original display value, and expected interpretation where safe. Operational logs contain only failure categories, counts, correlation IDs, and irreversible workspace references.

## Persistence model

All IDs are UUIDs. Every entity is owned by a workspace directly or through a constrained parent. Application repositories require `WorkspaceId` before accepting any public ID.

| Entity | Essential fields and constraints |
|---|---|
| `source_system` | workspace, name, adapter key; index by workspace/name |
| `book_source` | workspace, book, source system, LEFT/RIGHT role, identity namespace; unique `(book, role)` and same-workspace validation |
| `mapping_revision` | source, revision number, immutable mapping JSON, parser version, digest; unique `(source, revision)` and digest |
| `source_contract_revision` | source, mapping revision, mode, timezone, identity/reference/currency semantics, contract JSON, digest; immutable and versioned |
| `dataset` | workspace, book source, coverage key, current revision; unique `(book_source, coverage_key)` |
| `file_artifact` | workspace, generated storage key, physical SHA-256, original filename metadata, content type, byte size, created time; unique storage key |
| `ingestion_attempt` | workspace, artifact, dataset, contract revision, expected base revision, state, physical/semantic hash, delimiter, counts, timestamps |
| `raw_row` | workspace, attempt, row number, ordered raw-cell JSON, canonical-preview JSON, validation JSON; unique `(attempt, row_number)` |
| `logical_transaction` | workspace, book source, source key; unique `(book_source, source_key)` |
| `transaction_observation` | workspace, logical transaction, raw row, canonical columns, provenance JSON, fingerprint, eligibility; immutable |
| `dataset_revision` | workspace, dataset, parent revision, attempt, state hash, created time; one revision per successful attempt |
| `dataset_membership` | workspace, revision, logical transaction, observation; unique `(revision, logical_transaction)` and observation-owner validation |

Database check constraints cover modes, sides, attempt states, nonnegative sizes/counts, row numbers, decimal scale/precision through column types, and cancellation eligibility. Cross-table ownership is enforced in services under row locks and covered by adversarial tests; composite database constraints are added where Django migrations can express them without duplicating keys.

## Private artifact storage

- Accept only UTF-8 CSV with an optional UTF-8 BOM.
- Stream the request into a generated quarantine file while hashing and enforcing the 25 MiB limit; never derive a path from the submitted filename.
- Reserve workspace retained bytes before publishing the artifact record and final private storage key.
- Keep the artifact directory outside static/media public serving. Downloads stream only through an authorized Django view with a safe `Content-Disposition` filename.
- If file publication succeeds but the database transaction fails, record or sweep the generated orphan; never attach it to another workspace.
- Workspace deletion makes downloads unavailable immediately. Physical cleanup uses the durable cleanup request established by specification 001.

Local development uses a private filesystem volume. The storage interface remains replaceable by private object storage under specification 006.

## Bounded CSV pipeline

1. Reject the upload as soon as streamed bytes exceed 25 MiB.
2. Decode `utf-8-sig` strictly; invalid byte sequences fail the attempt.
3. Require an explicitly selected comma, semicolon, or tab delimiter and display it in preview.
4. Parse incrementally with hard defaults of 10,000 data rows, 100 columns, and 4,096 decoded characters per field.
5. Preserve header cells, row ordering, row numbers, and tagged raw values.
6. Validate required columns before interpreting data rows.
7. Apply the immutable contract field by field and preserve provenance.
8. Detect duplicate source keys across all rows and attach an error to every involved row number.
9. Compute physical and semantic hashes even for a rejected preview when sufficient bounded input was read safely.
10. Persist the complete preview and mark it `READY` only when every activation-blocking error is absent.

Limit failures stop further parsing, retain safe aggregate evidence, and create no dataset revision.

## Hash contracts

All hashes use SHA-256 over version-tagged byte encodings.

- **Physical hash:** exact artifact bytes.
- **Semantic input hash:** contract digest plus a sorted list of length-prefixed canonical raw-operation encodings. Sorting makes row order irrelevant; keeping a list preserves multiplicity. Tagged missing/null/empty states remain distinct.
- **Observation fingerprint:** canonical field/value/provenance meaning for one logical identity under the parser and contract versions.
- **Resolved state hash:** sorted pairs of stable logical identity and selected observation fingerprint for the complete materialized membership.

JSON used in hashing has sorted keys, compact separators, UTF-8, explicit type tags, and decimal/timestamp strings. Hash inputs never depend on Python object hashes, locale, database row order, or filename.

## Preview and activation

Preview is immutable and bound to:

- artifact;
- contract and mapping revisions;
- target dataset;
- expected base revision, including explicit `null` for the first revision;
- physical and semantic hashes;
- row validation and proposed membership changes.

Activation locks the dataset and owning workspace, rechecks active access and quota invariants, and verifies that the current head equals the previewed base. In one transaction it creates/reuses logical identities, appends observations, creates a dataset revision and all memberships, computes the resolved state hash, and finally advances the dataset head. Any error rolls back the whole activation.

### Full snapshot

The new membership contains exactly the valid source identities in the preview. Omitted prior identities remain historically inspectable but are absent from the new revision.

### Delta

The new membership starts as a copy of the previewed base and applies only explicit operations:

- `UPSERT`: add the identity or select a new immutable observation;
- `CANCEL`: select a new cancelled, ineligible observation;
- `RETRACT`: remove the identity from membership while preserving its evidence;
- omission: no effect.

If the base head changed after preview, activation returns a conflict and creates nothing.

## Replay and correction rules

- A physical duplicate may reuse stored bytes, but each interpretation attempt remains explicit.
- A semantic duplicate against the current effective state becomes an idempotent no-change attempt.
- Replaying an artifact/semantic input previously applied to an ancestor revision records the attempt but does not move the head backward.
- Changed canonical values create a new observation and revision; earlier observations and memberships remain immutable.
- Restoring historical values requires an explicit restore action with a reason or a provider revision that the source contract defines as monotonically newer.
- The implementation does not infer recency from arrival time alone.

## Web workflow

Server-rendered routes remain usable without JavaScript:

| Route | Behavior |
|---|---|
| `GET /books/{book}/sources` | Show two book sides, dataset heads, and preparation state |
| `GET/POST /books/{book}/sources/{side}/upload` | Select adapter/contract/delimiter and stream a CSV artifact |
| `GET/POST /books/{book}/sources/{side}/mapping` | Choose allowlisted mappings/constants for a third format and create immutable revisions |
| `GET /imports/{attempt}/preview` | Show raw/canonical values, provenance, errors, limits, hash identities, and proposed changes |
| `POST /imports/{attempt}/activate` | Activate only a ready preview against its expected base |
| `GET /imports/{attempt}` | Inspect accepted or rejected retained evidence |
| `GET /artifacts/{artifact}/download` | Stream original bytes after workspace authorization |

The preview defaults to a compact sample plus totals but supports server-side pagination over all retained row evidence. Values are HTML-escaped by templates. No raw CSV value enters a URL, log, or exception message.

## Transaction and concurrency boundaries

- Artifact quota reservation and artifact record creation share one database transaction; generated-file publication has explicit compensation.
- Mapping and contract revisions allocate their revision number while locking the source row.
- Preview persistence creates all raw rows before moving the attempt from `PARSING` to `READY` or `REJECTED`.
- Activation locks the dataset, checks expected head, and publishes revision/membership/head atomically.
- Concurrent activations from the same base allow one head advance; the loser receives `STALE_BASE` and retains its preview.
- Immutable evidence models have no general update repository. State transitions are limited to attempt lifecycle fields and dataset current-head pointers.

## Verification strategy

| Evidence | Requirements/scenarios |
|---|---|
| Pure contract/decimal/time/parser property tests | ING-002, ING-004, ING-013–ING-017 / ING-A02, ING-A07–ING-A09, ING-A14, ING-A16 |
| Assignment adapter golden fixtures plus configurable-mapping contract tests | ING-002, ING-003, ING-011 / ING-A01, ING-A11 |
| Artifact/raw-row immutability and private-download integration tests | ING-001, ING-018 / ING-A10, ING-A15 |
| Physical/semantic/state hash fixtures and ordering/multiplicity properties | ING-008, ING-015 / ING-A06, ING-A09, ING-A17 |
| Full-snapshot/delta activation and stale-base concurrency tests | ING-005, ING-006, ING-016 / ING-A04, ING-A05, ING-A13 |
| Correction/replay/restore temporal tests | ING-007, ING-009, ING-010 / ING-A03, ING-A10 |
| Cancellation eligibility contract | ING-012 / ING-A12 |
| Adversarial two-workspace repository/HTTP/download suite | ING-018 / ING-A15 |
| Browser upload-map-preview-activate review | ING-003, ING-011, ING-013, ING-017 / ING-A01, ING-A07, ING-A11, ING-A14 |

## Performance measurements

- Record parse/preview time and peak process memory for 10,000 rows near the 25 MiB limit on the named reference environment.
- Record activation time for a 10,000-row full snapshot and a 1,000-operation delta over a 10,000-row base.
- Assert a fixed query ceiling for paginated preview and evidence pages; do not load all raw rows into a template.
- Targets remain observations until measurement. Limit enforcement and atomicity are release blockers; an unmeasured speed claim is not.

## Recovery and migrations

- Additive forward migrations create source/ingestion tables and indexes without modifying verified foundation evidence.
- Before public data exists, the branch may rebuild its local application volume. After deployment, rollback uses the prior application image plus corrective forward migrations.
- Artifact cleanup is reference-aware: a physical object is deleted only when no retained artifact record refers to it.
- A failed activation requires no data repair because dataset-head publication is transactional.

## Rejected implementation approaches

- Store uploaded bytes in a public media directory: public URLs bypass workspace authorization.
- Use filenames as storage keys or duplicate identity: filenames are untrusted and unstable.
- Infer date formats, timezones, currency, or full/delta mode from values: plausible guesses can silently change financial meaning.
- Parse decimals through `float` or quantize excess precision: both can conceal source differences.
- Update one transaction row in place: destroys correction history and historical-run reproducibility.
- Use one hash for bytes, semantic input, and materialized state: those identities answer different questions.
- Treat duplicate replay as a new current correction: can roll a dataset head backward.
- Activate valid rows from a malformed snapshot: omission would be misread as authoritative removal.
- Execute user-provided expressions for configurable mappings: creates an unnecessary code-execution boundary.
- Introduce Celery/Redis for preview in this spec: bounded synchronous parsing is sufficient; reliable leased work belongs to specification 006.

## Implementation order

1. Pure ingestion values, source contracts, tagged raw values, validation failures, and exact numeric/time parsing.
2. Workspace-owned source, mapping, contract, dataset, artifact, attempt, raw-row, observation, revision, and membership persistence.
3. Private bounded artifact intake and retained-byte quota integration.
4. Predefined adapters, configurable mapping, preview persistence, and row-level validation.
5. Deterministic physical, semantic, observation, and state hashing.
6. Atomic full-snapshot activation and immutable evidence history.
7. Correction, replay, no-change, and explicit restore behavior.
8. Delta operations and stale-base concurrency control.
9. Cancellation eligibility plus workspace-scoped private downloads and isolation contracts.
10. Polished server-rendered preparation workflow and browser evidence.
11. Capacity measurements, clean-stack verification, traceability closure, and documentation.
