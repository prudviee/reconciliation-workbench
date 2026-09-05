# 002 Source Mapping and Ingestion — Specification

Status: Draft
Prefix: `ING`
Depends on: 001

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

## Acceptance scenarios

- **ING-A01** Given the assignment's two formats, when mapped and activated, then equivalent fields produce expected canonical observations with provenance.
- **ING-A02** Given an ambiguous date, when preview runs, then activation is blocked until a format/timezone is selected.
- **ING-A03** Given original amount 100, correction 110, then replay of original bytes, when processed normally, then 110 remains current.
- **ING-A04** Given a missing identity in a full snapshot, then it leaves new membership; given the same omission in a delta, then it remains.
- **ING-A05** Given a malformed required row in a full snapshot, when activation is attempted, then no membership or head changes.
- **ING-A06** Given differently ordered and formatted equivalent rows, when normalized under the same contract, then their semantic input hashes match.

## Out of scope

PDF/OCR ingestion, live provider APIs, executable user transformations, inferred snapshot/delta mode, and providers without any stable source identity guarantee.

## Open questions

- Final canonical precision per financial field and maximum supported source precision.
- Whether third-format mapping supports CSV delimiters/encodings beyond the curated fixtures in the first release.
