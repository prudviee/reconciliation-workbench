# 004 Decisions and Stable Cases — Tasks

- **Status:** In Progress
- **Specification:** [spec.md](./spec.md)
- **Plan:** [plan.md](./plan.md)

## Task conventions

- `[ ]` pending, `[~]` in progress, `[x]` verified, `[!]` blocked.
- Each task includes implementation, verification, and evidence in one commit.
- Task order establishes pure contracts before persistence, persistence before mutation, immutable runs before projections, and projections before release claims.

## Phase 1: authority and identity contracts

- [x] **REV-T01 — Define immutable review and stable-case contracts** (`REV-001`, `REV-002`, `REV-005`, `REV-009`, `REV-012`, `REV-013`; `REV-A10`, `REV-A11`, `REV-A13`)
  - Change: action/authority enums, validated commands, expected-version/conflict results, exact health values, canonical pair/unpaired/ambiguity key builders, occurrence descriptors, and lineage plans in the framework-independent domain.
  - Verify: every valid/invalid action-target shape, nonblank reason, canonical order and key vectors, ambiguity member/policy sensitivity, health vocabulary, and blocked Django/ORM imports.
  - Evidence: action matrix, stable digest vectors, and focused domain test results.

- [x] **REV-T02 — Add book generations, scopes, and immutable policy revisions** (`REV-010`–`REV-012`, `REV-016`; `REV-A06`, `REV-A12`)
  - Change: book data/resolution generation columns, workspace-owned reconciliation scopes, immutable policy revisions, locked generation services, and ingestion activation dirtying for affected scopes.
  - Verify: migration constraints, unique scope/policy identities, exact activation/policy data-generation changes with resolution generation untouched, unaffected scopes, immutable policy rows, and foreign-book rejection. Decision-driven resolution increments begin in REV-T04.
  - Evidence: migration/schema inspection and generation transition table.

## Phase 2: durable decisions

- [x] **REV-T03 — Persist append-only decisions, revisions, supersessions, and claims** (`REV-001`–`REV-004`, `REV-009`, `REV-016`; `REV-A05`, `REV-A10`, `REV-A11`, `REV-A12`)
  - Change: `resolutions` models, constraints, immutable revision/supersession behavior, active endpoint claim uniqueness, and workspace-scoped repositories.
  - Verify: database-local endpoint shape constraints, claim uniqueness, rejection without claims, revision immutability, multi-conflict supersession, history ordering, and foreign/absent indistinguishability. Locked cross-row side/ownership enforcement begins in REV-T04.
  - Evidence: database constraint inventory and persistence test results.

- [x] **REV-T04 — Commit initial authority with atomic concurrency checks** (`REV-001`–`REV-003`, `REV-007`, `REV-008`, `REV-012`, `REV-016`; `REV-A02`–`REV-A04`, `REV-A10`, `REV-A12`)
  - Change: LINK, ACCEPT_UNMATCHED, and REJECT_CANDIDATE commit services with book lock, expected generation, endpoint resolution, claims, scope dirtying, and typed conflicts.
  - Verify: successful action ledger, missing reason/incompatible target rejection, stale generation rollback, simultaneous competing links with at most one success, rejection persisted as an active no-claim relationship for REV-T06 engine mapping, and no foreign mutation.
  - Evidence: PostgreSQL concurrency result and atomic before/after snapshots.

- [x] **REV-T05 — Implement previewed reaffirmation, revocation, and replacement** (`REV-001`, `REV-004`, `REV-009`, `REV-012`, `REV-015`, `REV-016`; `REV-A05`, `REV-A09`–`REV-A12`)
  - Change: complete conflict preview, exact expected-revision supersession, REAFFIRM reviewed baseline, REVOKE claim release, REPLACE claim swap, immutable history, and one generation increment per successful command.
  - Verify: all affected conflicts shown, omitted/added/stale supersession rejection, multi-decision replacement, claim rollback on failure, revoked/replaced history, reaffirm compatibility, and workspace/book isolation.
  - Evidence: preview/commit decision table and history snapshots.

## Phase 3: immutable reconciliation runs

- [x] **REV-T06 — Freeze authorized manifests and persist complete run facts atomically** (`REV-005`–`REV-008`, `REV-010`, `REV-011`, `REV-015`, `REV-016`; `REV-A01`–`REV-A03`, `REV-A06`, `REV-A09`, `REV-A12`)
  - Change: reconciliation scope/run input/result models, manifest canonicalization, ORM-to-engine adapters, synchronous three-phase runner, complete result persistence, stale dependency handling, and current-run pointer update.
  - Verify: exact dataset/decision/policy/version manifest, engine-input authority mapping, terminal partition constraints, publication rollback injection, stale generation result retained without pointer advance, immutable completed facts, and foreign-run denial.
  - Evidence: manifest digest fixture, publication inventory, rollback proof, and run-fact snapshot.

- [x] **REV-T07 — Project decision health without changing authority** (`REV-005`–`REV-008`, `REV-015`; `REV-A01`–`REV-A03`, `REV-A09`, `REV-A13`)
  - Change: pure health classification and persisted per-run/current projection evidence for changed observations/comparisons, unavailable partners, accepted-unmatched candidates/limits, and rejected-reference conflicts.
  - Verify: exact four-status fixtures, manual-link correction keeps pair and flags comparison, accepted-unmatched remains reserved, rejection survives equal reference/corrections, reaffirm resets reviewed baseline, and health changes never alter claims or engine authority inputs.
  - Evidence: authority-versus-health matrix and correction/rerun snapshots.

## Phase 4: stable cases and lineage

- [ ] **REV-T08 — Create stable cases, immutable occurrences, and per-scope projections** (`REV-010`, `REV-011`, `REV-013`, `REV-016`; `REV-A06`–`REV-A08`, `REV-A12`)
  - Change: `cases` models/repositories, pair/unpaired/ambiguity materialization from run facts, append-only occurrences, and independently current per-scope projection rows.
  - Verify: same logical identities reuse cases across observation corrections/runs, ambiguity membership/policy changes create new keys, independent scopes do not overwrite each other, later review leaves historical facts/counts unchanged, and scoped access rejects foreign IDs.
  - Evidence: stable-key/occurrence table and before/after historical snapshots.

- [ ] **REV-T09 — Preserve complete merge and split lineage** (`REV-010`, `REV-013`, `REV-014`, `REV-016`; `REV-A07`, `REV-A08`, `REV-A12`)
  - Change: deterministic transition planner and immutable many-to-many predecessor/successor edges for unpaired-to-pair, pair-to-unpaired, and changed ambiguity membership.
  - Verify: pair case links both unpaired predecessors, pair split links every successor, overlapping ambiguity components link correctly, unrelated cases do not link, rerun idempotency, historical navigation, and cross-book/workspace denial.
  - Evidence: merge/split lineage fixtures and graph invariant checks.

- [ ] **REV-T10 — Add bounded scoped review query services** (`REV-004`, `REV-009`–`REV-011`, `REV-016`; `REV-A05`, `REV-A06`, `REV-A11`, `REV-A12`)
  - Change: cursor-paginated decision/case lists plus decision history, replacement preview, case occurrence, current review, and lineage detail projections for specification 005.
  - Verify: stable ordering, page-size cap 100, no duplicate/omitted rows across cursors, historical/current labels, complete affected decisions, bounded queries, and the full foreign/absent ID matrix.
  - Evidence: pagination/query measurements and isolation matrix.

## Phase 5: release evidence

- [ ] **REV-T11 — Close durable review and stable-case acceptance** (`REV-001`–`REV-016`; `REV-A01`–`REV-A13`)
  - Change: end-to-end correction/rerun corpus, final traceability, README scope update, verification record, and any defects found by the complete review.
  - Verify: all thirteen acceptance scenarios, concurrent PostgreSQL claims, migration consistency, domain boundary, full regression suite, diff hygiene, and clean Compose startup at one commit.
  - Evidence: acceptance matrix, concurrency/capacity measurements, clean-runtime record, limitations, and final verified commit.

## Final traceability

| Requirement | Task IDs | Acceptance/evidence | Complete |
|---|---|---|---|
| REV-001 | REV-T01, REV-T03–REV-T05, REV-T11 | REV-A05, REV-A10 | No |
| REV-002 | REV-T01, REV-T03, REV-T04, REV-T11 | REV-A01–REV-A03 | No |
| REV-003 | REV-T03, REV-T04, REV-T11 | REV-A04 | No |
| REV-004 | REV-T03, REV-T05, REV-T10, REV-T11 | REV-A05, REV-A10 | No |
| REV-005 | REV-T01, REV-T06, REV-T07, REV-T11 | REV-A01, REV-A02, REV-A13 | No |
| REV-006 | REV-T06, REV-T07, REV-T11 | REV-A01 | No |
| REV-007 | REV-T04, REV-T06, REV-T07, REV-T11 | REV-A03 | No |
| REV-008 | REV-T04, REV-T06, REV-T07, REV-T11 | REV-A02 | No |
| REV-009 | REV-T01, REV-T03, REV-T05, REV-T10, REV-T11 | REV-A11 | No |
| REV-010 | REV-T02, REV-T06, REV-T08, REV-T09, REV-T10, REV-T11 | REV-A07, REV-A08 | No |
| REV-011 | REV-T02, REV-T06, REV-T08, REV-T10, REV-T11 | REV-A06 | No |
| REV-012 | REV-T01–REV-T05, REV-T11 | REV-A04, REV-A11 | No |
| REV-013 | REV-T01, REV-T08, REV-T09, REV-T11 | REV-A07, REV-A08 | No |
| REV-014 | REV-T01, REV-T09, REV-T11 | REV-A07, REV-A08 | No |
| REV-015 | REV-T01, REV-T05–REV-T07, REV-T11 | REV-A03, REV-A09 | No |
| REV-016 | REV-T02–REV-T06, REV-T08–REV-T11 | REV-A12 | No |

## Deferred work

- Browser pages, forms, HTMX fragments, accessible decision dialogs, graph/table presentation, run comparison, and exports remain in [005-workbench](../005-workbench/spec.md).
- Work items, leases, fencing tokens, retries, coalescing, asynchronous progress, production publication ownership, retention execution, and deployment remain in [006-operations](../006-operations/spec.md).
- Multi-user attribution, roles, approval chains, comments, and external case-management integrations remain outside the first release as stated by this specification.
