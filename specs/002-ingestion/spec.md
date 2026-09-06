# 002 Source Mapping and Ingestion — Specification

- **Status:** In progress
- **Prefix:** `ING`
- **Depends on:** 001
- **Reviewed:** 5 September 2026

## Outcome

A reviewer can safely interpret different CSV formats, inspect validation and change previews, and activate immutable dataset revisions without losing earlier evidence.

## Requirements

- **ING-001** The system MUST preserve original artifact bytes, filename metadata, raw rows, and row numbers for the retention period.
- **ING-002** A versioned source contract MUST declare mapping, stable source identity, timezone, enums, currency semantics, reference semantics, and FULL_SNAPSHOT or DELTA mode.
- **ING-003** The system MUST preview raw and canonical values before activation.
- **ING-004** Ambiguous dates, unknown required enums, duplicate source keys, non-finite decimals, missing fields, and unsupported precision MUST block activation with row-level errors.
- **ING-005** A failed or malformed import MUST activate no partial dataset and MUST leave the earlier dataset head unchanged.
- **ING-006** A full snapshot MUST materialize exactly its valid identities; a delta MUST preserve omitted base identities.
- **ING-007** Corrections MUST create immutable observations and a new membership revision rather than update old observations.
- **ING-008** Physical artifact, semantic input, and resolved dataset-state hashes MUST remain distinct and versioned.
- **ING-009** Replaying an applied historical payload MUST NOT move the current dataset head backward.
- **ING-010** Restoring historical values MUST be an explicit new correction with a reason or a trustworthy newer provider revision.
- **ING-011** The first release MUST provide two predefined adapters and a configurable mapping workflow for a third format.
- **ING-012** Cancelled source rows MUST remain inspectable and be canonically marked ineligible for matching.
- **ING-013** The first release MUST accept UTF-8 CSV, including an optional UTF-8 BOM, with an explicitly previewed comma, semicolon, or tab delimiter.
- **ING-014** Canonical numeric fields MUST support at most 38 total digits and 12 fractional digits; larger or more precise values MUST fail validation rather than round silently.
- **ING-015** Semantic hashing MUST preserve row multiplicity and distinguish missing, null, and empty values until validation determines their meaning.
- **ING-016** A DELTA contract MUST distinguish explicit upsert, cancellation, and retraction operations; omission MUST have no effect, and activation MUST use the previewed base revision.
- **ING-017** Parsing MUST enforce configured byte, row, column, and field-length limits before activation and MUST report which limit was exceeded.
- **ING-018** Artifacts, source contracts, previews, imports, datasets, observations, and private downloads MUST be resolved through the active workspace and MUST reveal no cross-workspace metadata.

## Acceptance scenarios

- **ING-A01** Given the assignment's two formats, when mapped and previewed, then raw and canonical values plus provenance are visible; when activated, equivalent fields produce the expected canonical observations.
- **ING-A02** Given an ambiguous date, when preview runs, then activation is blocked until a format/timezone is selected.
- **ING-A03** Given original amount 100, correction 110, then replay of original bytes, when processed normally, then 110 remains current.
- **ING-A04** Given a missing identity in a full snapshot, then it leaves new membership; given the same omission in a delta, then it remains.
- **ING-A05** Given a malformed required row in a full snapshot, when activation is attempted, then no membership or head changes.
- **ING-A06** Given differently ordered and formatted equivalent rows, when normalized under the same contract, then their semantic input hashes match.
- **ING-A07** Given UTF-8 data with a BOM and a selected supported delimiter, when preview runs, then values are decoded deterministically and the selected delimiter is displayed.
- **ING-A08** Given a value outside NUMERIC(38,12), when validation runs, then the row fails with its original value and no rounded observation is created.
- **ING-A09** Given two identical duplicate rows versus one row, when semantic hashes are computed before validation, then the hashes differ and duplicate-key validation identifies both row numbers.
- **ING-A10** Given an accepted or rejected import, when its retained evidence is inspected after later corrections, then the original bytes, filename metadata, every retained raw row, row number, validation result, canonical observation where valid, and provenance remain available and unchanged.
- **ING-A11** Given each predefined assignment format and a third CSV with user-selected columns, when the same canonical fixture is previewed, then all three workflows produce the same canonical values and expose their source contracts.
- **ING-A12** Given a cancelled row in an otherwise valid dataset, when it is activated and reconciled, then the row remains inspectable with provenance and receives an excluded outcome without entering candidate generation.
- **ING-A13** Given the same base membership, when a delta upserts one identity, cancels another, explicitly retracts a third, and omits a fourth, then the resulting membership reflects only those explicit operations and retains the omitted identity; activation against a changed base is rejected as stale.
- **ING-A14** Given CSV input that exceeds each byte, row, column, or field-length limit, when preview runs, then it stops safely, names the exceeded limit, and activates no dataset revision.
- **ING-A15** Given two workspaces, when one submits the other's artifact, contract, preview, import, dataset, observation, or download ID to every supported read/mutation path, then no metadata, content, existence distinction, or state change crosses the workspace boundary.
- **ING-A16** Given rows containing an ambiguous date, unknown required enum, duplicate source key, non-finite decimal, missing required field, and unsupported precision, when preview runs, then each row is rejected with its row number, field, original value, and expected interpretation and activation is blocked.
- **ING-A17** Given formatting-equivalent files and the same delta applied to two different base memberships, when hashes are calculated, then physical hashes may differ while semantic hashes agree for equivalent inputs, and resolved state hashes differ for the different resulting memberships.

## Invariants and failure behavior

- Artifact storage may be reused, but interpretation remains scoped by dataset, contract, and mapping revision. (`ING-001`, `ING-002`, `ING-008`)
- A preview is bound to its expected base dataset revision; stale activation returns a conflict and requires a regenerated preview. (`ING-003`, `ING-016`)
- Full-snapshot activation is all-or-nothing. Invalid required rows cannot be interpreted as intentional removals. (`ING-004`, `ING-005`, `ING-006`)
- A delta's semantic input hash describes its operations; its state hash describes the resulting full membership. (`ING-008`, `ING-016`)
- A mapping change never silently reinterprets historical runs. (`ING-002`, `ING-007`, `ING-010`)
- Filenames cannot influence storage paths, and displayed source text is escaped. (`ING-001`, Constitution VIII)

## Performance and capacity

The initial supported limit is 25 MiB and 10,000 rows per file. Preview reports a clear limit error before dataset activation. Parsing and hashing are streamed where practical; activation remains atomic. (`ING-005`, `ING-017`)

## Out of scope

PDF/OCR ingestion, live provider APIs, executable user transformations, inferred snapshot/delta mode, and providers without any stable source identity guarantee.

## Resolved decisions

- Canonical quantity, unit price, and gross amount use NUMERIC(38,12). Inputs outside that range are rejected without rounding.
- The first release supports UTF-8 and UTF-8 BOM. The mapping preview supports comma, semicolon, and tab delimiters. Other encodings/delimiters require a later specification.

## Requirement-to-scenario matrix

| Requirement | Scenarios |
|---|---|
| ING-001 | ING-A10 |
| ING-002, ING-003 | ING-A01, ING-A11 |
| ING-004 | ING-A02, ING-A05, ING-A08, ING-A09, ING-A16 |
| ING-005 | ING-A05 |
| ING-006 | ING-A04 |
| ING-007, ING-009, ING-010 | ING-A03 |
| ING-008 | ING-A03, ING-A06, ING-A09, ING-A17 |
| ING-011 | ING-A11 |
| ING-012 | ING-A12 |
| ING-013 | ING-A07 |
| ING-014 | ING-A08 |
| ING-015 | ING-A09 |
| ING-016 | ING-A13 |
| ING-017 | ING-A14 |
| ING-018 | ING-A15 |

## Change history

| Date | Change | Reason |
|---|---|---|
| 5 September 2026 | Initial draft | Define source mapping and temporal ingestion |
| 5 September 2026 | Fixed precision/CSV contracts, added hash and failure invariants and traceability; marked Ready | Critical SDD review |
| 6 September 2026 | Began implementation after `ING-T01` verification | Pure source contracts, tagged raw values, exact decimal/time interpretation, and cancellation eligibility passed their task gate |
