# 004 Decisions and Stable Cases — Implementation Plan

- **Status:** Complete
- **Specification:** [spec.md](./spec.md)
- **Target branch:** `codex/004-review-and-cases`
- **Last updated:** 7 September 2026

## Summary

Persist the pure reconciliation engine behind three explicit boundaries: a short transaction that freezes a run manifest, deterministic computation outside a transaction, and a short atomic publication transaction that writes immutable run facts and advances current projections only when dependencies still agree. Add durable reviewer authority as append-only decision revisions with atomic endpoint claims, then derive decision health and stable cases from completed-run evidence without rewriting either historical results or earlier review actions.

The first coherent slice is framework-independent decision and case identity contracts. Persistence then establishes book generations, dated scopes, versioned policies, decisions, and claims before any mutation service exists. The implementation next publishes complete synchronous runs, projects decision health, creates stable case occurrences and lineage, and closes with workspace-scoped queries and all thirteen acceptance scenarios. Browser forms and pages remain in specification 005; leases, retries, and worker fencing remain in specification 006.

## Constitution check

| Principle | How the plan complies |
|---|---|
| Evidence is immutable | Decision revisions, run inputs, completed results, case occurrences, and lineage edges are append-only. Mutable rows contain only current pointers, generations, lifecycle, or derived projections. |
| Identity and agreement differ | LINK authority reserves stable logical identities; fresh observations only change comparisons and health. A discrepant manual pair remains paired. |
| Automatic matching may abstain | Publication preserves every unpaired classification, candidate limit, component limit, and diagnostic uncertainty returned by the engine. |
| Results are explainable | Run facts retain candidate features, assignment evidence, field comparisons, origins, classifications, and exact policy/input version identities. |
| Reviewer authority is durable | Claims and relationship prohibitions are book-wide and survive scope/rerun changes until an explicit append-only action changes authority. |
| Runs publish atomically | A completed result and its cases publish in one transaction after partition and dependency checks; partial facts never become visible. |
| Decimal/time semantics are explicit | Persisted decimals remain exact numeric/string values from validated engine contracts; timestamps are aware UTC; immutable policy revisions carry every tolerance. |
| Anonymous access is isolated | Repositories require `WorkspaceId`, resolve book ownership before child IDs, and return the same unavailable result for foreign and absent resources. |
| Domain core is framework-independent | Decision commands, key builders, health classification, and lineage planning are pure values/functions; ORM services adapt them at the boundary. |
| Specifications precede behavior | Every task maps to `REV` requirements and acceptance scenarios and records verification evidence before the next task begins. |
| Claims require evidence | Concurrency, corrections, rejections, history, lineage, immutability, isolation, and bounded pagination each have named tests and evidence records. |
| Complexity earns its place | Database uniqueness protects endpoint claims, explicit lineage preserves merges/splits, and separate per-scope projections prevent completion-order corruption. |

## Affected architecture

| Module/component | Change | Requirement IDs |
|---|---|---|
| `reconciliation.domain.review` | Immutable actions, targets, expected-version commands, conflicts, health, case keys, occurrence descriptors, and lineage plans | REV-001–REV-005, REV-009, REV-012–REV-015 |
| `books` | Add data/policy and resolution generations; persist reconciliation scopes and immutable policy revisions | REV-003, REV-010–REV-012, REV-016 |
| `resolutions` | Persist decision envelopes/revisions/supersessions/claims; validate and commit review commands atomically | REV-001–REV-009, REV-012, REV-015, REV-016 |
| `reconciliation` persistence/application | Freeze manifests, map current observations/decisions into engine values, run synchronously, and publish immutable facts | REV-005–REV-008, REV-010, REV-011, REV-015, REV-016 |
| `cases` | Persist stable case keys, immutable occurrences, explicit many-to-many lineage, and scope-specific current projections | REV-005, REV-010, REV-011, REV-013, REV-014, REV-016 |
| `ingestion.activation` | Increment the book data generation and mark affected scopes dirty when a dataset head changes | REV-006, REV-011, REV-012 |
| `tests/` and spec evidence | Domain, migration, transaction, concurrency, correction/rerun, lineage, isolation, pagination, and release verification | REV-001–REV-016 |

## Domain contracts

### Reviewer commands and authority

`DecisionAction` contains `LINK`, `ACCEPT_UNMATCHED`, `REJECT_CANDIDATE`, `REAFFIRM`, `REVOKE`, and `REPLACE`. `DecisionAuthority` contains the three active authority shapes: a left/right link, a single left or right accepted-unmatched identity, or a left/right rejected relationship. Every command contains a nonblank reason, an anonymous-workspace actor descriptor, expected book resolution generation, and expected current revision IDs for every authority it intends to change.

Pure validation enforces target shape and side compatibility. LINK and REPLACE require one left and one right logical identity. ACCEPT_UNMATCHED requires one identity with its book side. REJECT_CANDIDATE requires a cross-side relationship and creates no endpoint reservation. REAFFIRM keeps the same authority and advances its reviewed observation baseline. REVOKE removes authority without deleting its history. REPLACE provides the proposed new authority plus the complete explicitly approved set of conflicting current revisions.

`ReplacementPreview` returns the proposed authority, all endpoint-claim conflicts, all directly affected active decisions, their current revision IDs, and the current resolution generation. Commit must repeat conflict discovery under the book lock and compare it with the submitted preview. An omitted, added, or changed conflict yields a typed stale/conflict failure and changes nothing.

### Health

`DecisionHealth` is exactly `UNCHANGED`, `EVIDENCE_CHANGED`, `PARTNER_UNAVAILABLE`, or `NEW_CANDIDATE`; attention reasons are separate factual codes. Health never activates, deactivates, or rewrites authority.

- LINK is `PARTNER_UNAVAILABLE` when either logical identity is absent from the selected scope. When both exist, a changed reviewed observation or changed relevant comparison is `EVIDENCE_CHANGED`; otherwise it is `UNCHANGED`.
- REJECT_CANDIDATE remains active across all corrections. A relevant observation change is `EVIDENCE_CHANGED`; a newly authoritative-reference relationship adds an evidence-conflict attention reason.
- ACCEPT_UNMATCHED is `PARTNER_UNAVAILABLE` when its identity is absent. A complete bounded diagnostic that finds a plausible counterpart is `NEW_CANDIDATE`; an incomplete/failed diagnostic cannot assert absence and records a limitation. Other matching-relevant evidence changes are `EVIDENCE_CHANGED`; otherwise it is `UNCHANGED`.
- REAFFIRM stores the currently reviewed observation IDs and evidence baseline, allowing later unchanged runs to return `UNCHANGED`.

### Stable case identity

Canonical key material is version-tagged, length-prefixed, UTF-8 encoded, and SHA-256 digested. Public stable keys include a case-kind prefix and the digest; raw concatenation is never used.

- Pair key: book ID plus ordered left and right logical transaction IDs.
- Unpaired key: book ID, source side, and logical transaction ID.
- Ambiguity key: book ID, reconciliation scope ID, matching-policy digest, and the complete sorted left/right member identities. Candidate truncation or an incomplete component cannot be presented as a complete ambiguity membership.

`CaseOccurrenceDescriptor` points to exactly one immutable run result: pair, unpaired, or assignment component. `CaseTransitionPlan` compares all current cases in one scope with newly published occurrences and emits explicit `PREDECESSOR_OF` edges for every merge and split. Pair formation from two unpaired identities therefore links both prior cases. An ambiguity membership change creates a new key and a lineage edge rather than editing the earlier case.

## Data model and migrations

All public entities use UUIDs. Evidence tables use immutable model guards; application services are the only supported mutation path for mutable envelopes and pointers. Every table carries direct workspace ownership where it prevents unsafe joins and makes deletion/isolation explicit.

### Books, scopes, and policies

| Entity | Essential fields and constraints |
|---|---|
| `reconciliation_book` changes | `generation` and `resolution_generation`, nonnegative and default zero; both change only under a locked book transaction |
| `reconciliation_scope` | workspace, book, coverage key, left/right datasets, current run pointer, dirty flag/generation; unique `(book, coverage_key)` and distinct left/right datasets |
| `policy_revision` | workspace, book, monotonically increasing revision, immutable matching/comparison JSON, digest, created time; unique `(book, revision)` and `(book, digest)` |

An activated dataset head increments `book.generation` and marks only scopes containing that dataset dirty. A new effective policy does the same. A decision mutation increments only `resolution_generation` and marks relevant book scopes dirty. Generation updates use `F()` expressions while holding the book lock; callers never calculate the next value from an unlocked object.

### Decisions

| Entity | Essential fields and constraints |
|---|---|
| `decision` | workspace, book, immutable public identity, current revision pointer, created time |
| `decision_revision` | decision, predecessor within that decision, revision number, action, authority kind, left/right or single logical endpoints, reason, actor kind, reviewed observation IDs/digest, created time; unique `(decision, revision)`; immutable |
| `decision_supersession` | replacement revision and each explicitly superseded revision; unique pair; immutable |
| `active_decision_claim` | workspace, book, logical transaction, owning active revision; unique `(book, logical_transaction)` |

Shape check constraints require exactly the endpoints valid for the authority kind. Cross-table ownership and left/right roles are revalidated under lock. Active rejections are derived from unsuperseded, non-revoked current revisions and have no claim rows. Current revision pointers and claim rows may change; revisions and supersession edges may only be appended.

PostgreSQL's unique claim constraint is the final arbiter for concurrent writers. The service locks the book, validates expected generation/revisions, appends revisions, replaces the bounded claim set, increments `resolution_generation`, and marks scopes dirty in one `transaction.atomic()` block. `IntegrityError` is translated to a stable conflict without leaking foreign IDs.

### Immutable runs

| Entity | Essential fields and constraints |
|---|---|
| `reconciliation_run` | workspace, scope, manifest hash, frozen data/resolution generations, policy revision, engine/solver versions, lifecycle, freshness, timestamps, result digest/counts; unique successful manifest |
| `run_input` | run, side, logical transaction, observation; unique `(run, logical transaction)` |
| `run_decision_input` | run, decision revision; unique pair |
| `candidate_evidence` | run, left/right observations, component reference, blocking/features/flags JSON, score; unique edge per run |
| `assignment_component` | run, graph digest, member IDs, objective, proposal/counterfactual/limit evidence; unique digest per run |
| `run_pair` | run, left/right observations and logical identities, origin, decision/reference IDs, score/global gap, explanation; unique left and right observations per run |
| `field_comparison` | pair, field, serialized source values/difference/tolerance/status/explanation; unique `(pair, field)` |
| `run_unpaired` | run, observation/logical identity, classification, explanation; unique `(run, observation)` |
| `run_diagnostic` | run, owning decision revision, kind, completeness, candidate/allocation evidence |

Run creation locks the scope/book, resolves exact current dataset revisions, policy, active decisions, observations, and generations, canonicalizes the manifest, and appends run/input rows. Computation uses only those frozen references and occurs outside a database transaction. Publication revalidates the `EngineResult` terminal partition and frozen references, writes every fact plus cases in one transaction, and marks the run completed. If dependencies changed, facts remain historical with `STALE` freshness and do not advance `scope.current_run`; otherwise the run becomes `CURRENT`, advances the pointer, and clears the scope dirty flag. Worker tokens and retries are deliberately absent until specification 006.

### Stable cases

| Entity | Essential fields and constraints |
|---|---|
| `investigation_case` | workspace, book, kind, stable key/digest, ordered logical endpoint metadata or ambiguity members/policy scope; unique `(book, stable_key)` |
| `case_occurrence` | workspace, case, run, result kind and exactly one result reference, state snapshot; unique `(case, run, result identity)`; immutable |
| `case_lineage` | workspace, predecessor case, successor case, transition kind, caused-by run; unique edge/run; immutable; no self-edge |
| `case_scope_projection` | workspace, case, scope, current occurrence, current review health/attention, applied run and resolution generations; unique `(case, scope)` |

Current projections are replaceable derived state and update only for the publishing scope. Historical occurrences, lineages, run counts, and run facts never change when a later decision is made. A decision mutation may mark affected projections pending/dirty, but it cannot rewrite their occurrence or historical state.

## Web and application contracts

No HTML pages or public routes are added. Specification 004 exposes workspace-scoped application services for later views:

- `preview_decision(workspace_id, book_id, command) -> ReplacementPreview`
- `commit_decision(workspace_id, book_id, command) -> DecisionRevisionView`
- `list_decisions(..., cursor, page_size <= 100)` and `get_decision_history(...)`
- `create_run_manifest(workspace_id, scope_id) -> FrozenRun`
- `execute_and_publish_run(workspace_id, run_id) -> PublishedRun`
- `list_cases(..., cursor, page_size <= 100)`, `get_case_history(...)`, and `get_case_lineage(...)`

All child identifiers are resolved only after the owning workspace and book/scope have been established. Foreign and absent IDs produce the same typed unavailable result. Command validation errors are separate from optimistic concurrency conflicts so specification 005 can map them to `400` and `409` without parsing text.

## Background processing

Not applicable. The runner is an application service with freeze, compute, and publish phases and is invoked synchronously in tests and local workflows. Specification 006 will enqueue the same frozen run ID, add leases/fencing/retries, and call the unchanged compute/publication boundaries.

## UI behavior

No interface is added. Query and preview contracts provide all data needed by specification 005: active authority, independent health and attention reasons, complete affected-decision previews, immutable history, historical-run labels, case occurrences, lineage, stable pagination cursors, and pending-change generations.

## Verification plan

| Requirement | Verification layer | Planned evidence |
|---|---|---|
| REV-001, REV-002, REV-004 | Domain, model, service | Complete action/target matrix, mandatory reasons, claim shapes, append-only history, actor and predecessor/supersession evidence |
| REV-003, REV-009, REV-012 | PostgreSQL transaction/concurrency | Competing endpoint writers, stale generation/revision, exact replacement preview, rollback, and database uniqueness tests |
| REV-005–REV-008, REV-015 | Domain and correction/rerun integration | Manual discrepancy persistence, accepted-unmatched diagnostic, rejection prohibition/reference conflict, four exact health fixtures |
| REV-010, REV-013, REV-014 | Domain, persistence, integration | Canonical key vectors, occurrence preservation, two-to-one merge, ambiguity successor, one-to-many split and complete lineage |
| REV-011 | Immutability and historical integration | Before/after snapshots prove later decisions and projections do not alter completed run values/counts |
| REV-016 | Adversarial integration | Foreign workspace and same-workspace foreign-book list/detail/preview/commit/history/lineage probes reveal nothing and mutate nothing |
| Capacity constraint | Database measurement | Cursor pagination at the documented fixture size; decision transaction query/touch set remains bounded and excludes engine computation |

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Application-only claim checks race | One endpoint gains two authorities | PostgreSQL unique `(book, logical_transaction)` claim plus book lock and translated `IntegrityError` |
| Replacement records only one conflict | Silent loss of another authority/history | Explicit many-to-many supersession edges and exact conflict-set comparison between preview and commit |
| Health accidentally controls authority | A correction silently drops a manual decision or rejection | Separate enums/tables/functions; engine inputs derive from authority only; health is written only to projections/diagnostics |
| Current decisions contaminate old runs | Historical counts and explanations change | Freeze decision revision IDs in the manifest; immutable run tables; separate current review queries |
| Case key changes with observation correction | Duplicate cases and broken history | Keys use logical identities, not observations or values; ambiguity keys alone change with complete membership |
| Scope completions overwrite each other | Wrong current case state for another period | Unique per-case/per-scope projections updated only by that scope's publication |
| Partial publication becomes visible | Counts disagree and cases point to incomplete evidence | Validate first, write all facts/cases in one atomic transaction, advance pointers last |
| Generic JSON hides invalid evidence shapes | Unqueryable or contradictory facts | Relational identity/score/status columns and model constraints for invariants; JSON only for bounded nested engine ledgers validated before persistence |
| Synchronous execution is mistaken for production reliability | Long request or duplicate work risk | Keep three-phase service boundary, label it local/synchronous, and defer transport/leases/fencing to specification 006 |

## Rejected implementation approaches

| Approach | Why rejected |
|---|---|
| Store decisions on a run result row | Authority would disappear across future scopes and corrections. |
| Update one mutable decision record in place | Earlier reasons, baselines, and reversals would be unrecoverable. |
| Let a REPLACE command silently steal claims | It would conceal affected decisions and violate explicit supersession. |
| Use only a predecessor pointer for replacement conflicts | One replacement can conflict with multiple decisions; a chain cannot represent the complete affected set. |
| Make rejections endpoint claims | It would block valid relationships with other counterparts instead of prohibiting only one edge. |
| Expire rejections when evidence changes | Corrections would silently weaken reviewer authority. |
| Put health into the decision lifecycle state | Evidence freshness and reviewer authority answer different questions and must change independently. |
| Key cases by observation ID or run-result ID | Corrections and reruns would create unrelated cases for the same stable transaction identity. |
| Mutate an ambiguity case when membership changes | Historical membership would be lost and split/merge navigation would be impossible. |
| Keep one book-wide current case pointer | Independently current scopes could overwrite one another in completion order. |
| Persist only summary counts | Reviewers could not reproduce, explain, compare, or audit individual outcomes. |
| Add job leasing in this specification | It couples review semantics to operations before synchronous publication correctness is proven. |

## Delivery and rollback

Changes are additive except for book generation columns and the ingestion activation hook. Migrations add nonnegative generation defaults before services rely on them. New apps remain unreachable from public routes until specification 005, so each task can be reverted with its migration while no external workflow depends on it. Once decision/run data exists, rollback is code rollback with tables retained; destructive reverse migration is not part of operational recovery.

Every implementation task produces one commit containing code, focused tests, and an evidence record. The feature is not verified until the full suite, migration checks, concurrent PostgreSQL probes, correction/rerun scenarios, cross-workspace adversarial matrix, and clean Compose gate pass at one commit.

## Open decisions

None. The specification and this plan fix authority lifetime, replacement conflict representation, generation boundaries, run publication semantics, health precedence, stable keys, lineage, isolation, and deferral boundaries needed to implement without behavioral guesswork.
