# REV-T06 Verification Evidence

- **Task:** Freeze authorized manifests and persist complete run facts atomically
- **Requirements:** `REV-005`–`REV-008`, `REV-010`, `REV-011`, `REV-015`, `REV-016`
- **Acceptance scenarios:** `REV-A01`–`REV-A03`, `REV-A06`, `REV-A09`, `REV-A12`
- **Date:** 7 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence

## Three-phase boundary

| Phase | Transaction behavior | Durable effect |
|---|---|---|
| Freeze | Short transaction; locks the active workspace, scope, and book | Appends one canonical manifest plus immutable observation and decision-revision inputs |
| Compute | No database transaction | Reconstructs domain records, policy values, and reviewer authority only from frozen rows; runs the deterministic engine with the declared solver version |
| Publish | Short transaction; locks the workspace, book, scope, and run | Validates exact inputs/versions, appends the complete evidence graph, marks the run completed, then advances the current pointer only if every dependency is unchanged |

Freeze and publish use the shared workspace → book → scope → run lock order. This matches decision and activation mutations and avoids an inverted book/scope lock under concurrent work.

The manifest includes the workspace, book, scope and coverage identity; exact left/right dataset revision IDs; ordered logical transaction, observation and fingerprint triples; policy revision and digest; active unsuperseded decision revision IDs; book data and resolution generations; scope generation; and engine/solver versions. Canonical JSON with sorted keys produces the SHA-256 manifest identity. Recreating an unchanged manifest returns the existing frozen run.

## Authority mapping

| Active authority | Frozen endpoints available | Engine input and observed result |
|---|---|---|
| LINK | Both | `ManualLink`; pair origin is `MANUAL` and the owning revision is stored on the pair |
| LINK | One | `ReservedIdentity`; the available endpoint cannot be assigned automatically |
| ACCEPT_UNMATCHED | Record available | `AcceptedUnmatched`; terminal outcome is `ACCEPTED_UNMATCHED` |
| REJECT_CANDIDATE | Both | `RejectedRelationship`; the edge is prohibited before authoritative-reference and weighted assignment stages |
| Any authority | No applicable endpoint | Authority revision remains in the manifest; no invalid engine endpoint is fabricated |

The decision revision list is immutable historical input. Later decisions cannot affect computation or queries for an earlier run.

## Publication inventory and invariants

The normalized result contains run pairs, field comparisons, unpaired outcomes, complete candidate evidence, assignment components with proposal/counterfactual evidence, and accepted-unmatched diagnostics. Direct workspace ownership is carried on every evidence table. Database constraints enforce run-local input uniqueness, candidate-edge uniqueness, one pair per left/right observation, one unpaired row per observation, enum values, pair score shape, component limit shape, and valid run lifecycle/result shape.

The domain `EngineResult` enforces the terminal partition before publication: every frozen left and right observation appears exactly once as paired or unpaired. Publication additionally checks the exact frozen revision IDs, ordered inputs, engine version, and solver version.

All run-input and result query sets reject update/delete operations. The mutable run envelope permits lifecycle publication fields but rejects changes to the frozen manifest, dependencies, versions, and creation time.

## Atomicity and freshness proofs

- A publication probe injected after every result row was written and before finalization raised an exception. PostgreSQL rolled back pairs, comparisons, candidates, components, unpaired rows, diagnostics, and the scope pointer together. The outer execution boundary then recorded only `FAILED` plus the stable failure code.
- A scope-generation change after freeze produced a complete `STALE` run with all historical facts retained. It did not advance `scope.current_run` and left the scope dirty.
- An unchanged dependency set produced `CURRENT`, advanced `scope.current_run`, and cleared the dirty flag in the same transaction as result publication.
- Foreign-workspace manifest and run identifiers produced the same `RunUnavailable` outcome as absent identifiers.

## Verification results

| Check | Result |
|---|---|
| Focused manifest/authority/publication suite | 7 passed in 6.79 seconds |
| Full repository regression | 425 passed in 24.74 seconds |
| Django system check | Passed, 0 issues |
| Migration drift check | Passed, no changes detected |
| Python compile check | Passed |
| Diff whitespace check | Passed |

## Scope boundary

This task persists authority and complete engine evidence without calculating review health or stable cases. REV-T07 derives decision health from immutable run facts while leaving authority unchanged. REV-T08 then materializes stable cases and occurrences from completed runs.
