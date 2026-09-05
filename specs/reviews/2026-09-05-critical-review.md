# Critical Design and Specification Review

- **Reviewed:** 5 September 2026
- **Scope:** `DESIGN.md`, HLD, LLD, algorithm, ADRs, delivery plan, constitution, roadmap, templates, and feature specifications 001-006
- **Source constraint:** The assignment PDF was treated as problem evidence. Its text did not override the user's request to produce a polished public showcase without sign-in.
- **Decision:** The six behavioral specifications are Ready for implementation planning after the corrections recorded below.

## Overall judgement

The selected architecture is coherent: a Django/PostgreSQL modular monolith, framework-independent reconciliation core, server-rendered workbench, PostgreSQL-backed worker, immutable evidence, and global one-to-one matching with explicit abstention. It satisfies the assignment while showing deeper reasoning through temporal history, constrained optimization, durable review decisions, and operational safety.

Before this review, the documentation was strong conceptually but not implementation-ready. Several matrices asserted coverage that their scenarios did not prove, important matching safety rules existed only in explanatory prose, and some temporal/security decisions remained ambiguous. Those gaps have been converted into normative requirements and observable scenarios.

The main delivery risk is scope. The assignment suggests roughly five to six hours, while this design is a full showcase product. The user deliberately selected that scope. The response is to implement it in dependency order with evidence gates, not to quietly remove the advanced behavior. Performance, accuracy, accessibility, and security statements remain targets until verification records evidence.

## Assignment coverage

| Assignment expectation | Design coverage | Review result |
|---|---|---|
| Design database tables | HLD boundaries and LLD tables, constraints, memberships, decisions, runs, cases, and jobs | Covered |
| Load different file formats | Versioned adapters, configurable mapping, UTF-8 CSV rules, snapshot/delta semantics, validation preview | Covered |
| Match and compare | Trusted references, candidate blocking, weighted global assignment, ambiguity gate, independent field comparison | Covered |
| Logic testable without database/browser | Pure immutable engine contract and isolation acceptance scenario `REC-A12` | Covered |
| Start run and inspect results | Workbench, evidence, run history, truthful background progress | Covered |
| Manually match unmatched rows | Durable LINK action with preview, reason, endpoint claims, concurrency control, and history | Covered |
| Preserve corrections and repeat decisions | Immutable observations, dataset membership, stable identities, append-only decision revisions | Covered |
| Tests for important logic | Project verification strategy plus per-spec acceptance and traceability | Covered by design; execution pending |
| README decisions, omissions, next steps | Root/design documentation, ADRs, exclusions, roadmap | Covered by design; runnable instructions pending implementation |
| Public repository and 3-5 minute video | Demo script and delivery checklist | Delivery work remains after implementation |

## Findings and dispositions

| Severity | Finding | Correction incorporated |
|---|---|---|
| Critical | Requirement matrices existed only as a process rule; feature specs had no matrices or change histories. | Added complete requirement-to-scenario matrices and histories to all six specs. |
| Critical | Some first-pass matrix links were nominal: the scenario did not actually exercise the mapped requirement. | Added focused scenarios for CSRF/cookies, logging privacy, local startup, evidence preservation, adapter parity, cancellation, solver purity, action conflicts, import errors, retries, deployment, and retention. |
| Critical | “Adequate evidence” for heuristic matching was undefined and could allow a sparse high score to auto-match. | `REC-016` requires instrument, side, currency, quantity, timestamp, and at least one monetary field; policies may only strengthen this floor. |
| Critical | Shared-reference disagreement and duplicate-reference behavior lived outside the feature contract. | Added `REC-020`/`REC-A17` for reference semantics and `REC-021`/`REC-A18` for duplicate-reference ambiguity. |
| High | Ambiguity handling did not normatively prohibit repeated elimination/rerunning that can make weak edges appear certain. | Added `REC-018`/`REC-A11`; accepted edges come from one complete proposal and the engine abstains on the remainder. |
| High | Candidate/component caps were described but not part of a traceable behavior contract. | Added `REC-022`, mapped to the over-limit abstention scenario. |
| High | Seven-day retention could be interpreted as sliding inactivity retention. | Fixed live expiry at seven days from workspace creation; activity never extends it. Backup retention is separate and disclosed. |
| High | Public anonymous access had no explicit resource-abuse contract. | Added per-workspace storage, book-count, and active-job quotas with non-destructive refusal behavior. |
| High | Workspace isolation was centralized in the foundation spec, leaving later data types without concrete cross-workspace evidence. | Added feature-level isolation requirements and adversarial scenarios for ingestion data, decisions/cases, UI/exports, and worker manifests. |
| High | Delta semantics covered omission but not explicit operation types or stale bases. | Added upsert, cancellation, retraction, omission, and preview-base rules in `ING-016`/`ING-A13`. |
| High | CSV input limits covered file size/rows but not pathological columns or fields. | Added byte, row, column, and field-length enforcement in `ING-017`/`ING-A14`. |
| High | Hashing did not explicitly protect row multiplicity or distinguish missing, null, and empty before validation. | Added `ING-015` and a duplicate-row hash scenario. |
| High | Case identity and merge/split history were underspecified. | Added stable pair/unpaired/ambiguity keys and explicit predecessor/successor lineage in `REV-013` and `REV-014`. |
| High | The lifetime of a rejected candidate after corrections was ambiguous. | Added `REV-015`: rejection remains active until an explicit later decision; changed evidence updates health. |
| High | Exported untrusted text could become a spreadsheet formula, and export temporal meaning was not explicit in the spec. | Added `UX-017`/`UX-A13` for formula neutralization, exact decimal/time labels, and historical/current-view identification. |
| Medium | Candidate graphs could become inaccessible or contain unique evidence. | Required the table to be the complete accessible explanation; graphs are progressive enhancement only. |
| Medium | Async progress could imply fake precision. | Required persisted stages and real counts, with no invented percentage. |
| Medium | Deployment behavior was tied to an unnamed provider while the spec was marked ready. | Kept provider choice at plan level and made the observable contract provider-independent: managed PostgreSQL, private object storage, HTTPS, release migrations, and separate health signals. |
| Medium | Cleanup and backup language could overpromise deletion. | Added idempotent reference-aware cleanup and explicit live-versus-backup retention disclosure. |
| Medium | Design prose and feature specs used different strength for retention and evidence coverage. | Synchronized consolidated design, product design, algorithm, and ADR wording with the reviewed contracts. |
| Low | The template constitution check omitted two principles. | Added “Specifications precede behavior” and “Complexity earns its place.” |
| Low | The workflow claimed every normative sentence needed an ID while templates encouraged untagged invariants. | Refined the rule: independently testable behavior needs an ID; supporting invariants must cite the requirement or constitutional principle they refine. |
| Low | The two-letter `UX` prefix failed an earlier audit pattern expecting three letters. | Standardized prefixes as two to four uppercase letters and corrected the audit rule. |

## Reconciliation algorithm decision

The engine uses a staged deterministic pipeline:

1. Freeze dataset, policy, decision, engine, and solver versions.
2. Exclude cancelled observations and reserve manual or accepted-unmatched identities.
3. Apply active relationship rejections to every automatic stage.
4. Lock only unique trusted shared references; keep value differences as comparison discrepancies.
5. Build the union of complete versioned blocking passes.
6. Calculate fixed-point weighted rule scores without renormalizing missing features.
7. Solve bounded connected components as optional-unmatched one-to-one assignments.
8. Re-solve each proposed edge's complete component with that edge forbidden to calculate its global gap.
9. Confirm only edges meeting score, evidence, contradiction, completeness, and global-gap gates.
10. Keep that accepted subset and return the remainder as explicit unmatched, ambiguous, excluded, or review-required outcomes.
11. Compare fields independently with exact decimal, currency, timezone, and inclusive-tolerance semantics.

This is preferred over greedy matching because local choices can block a much better one-to-one allocation. It is preferred over fuzzy matching alone because the global sensitivity test can abstain when two allocations are equally plausible. It is preferred over an ML-first or LLM matcher because the assignment data is small, labelled training evidence is absent, and deterministic explanations are more credible for this showcase. Scores are rule scores, not probabilities.

## Traceability audit

After correction:

| Spec | Requirements | Acceptance scenarios | Missing requirement mappings | Missing scenario mappings |
|---|---:|---:|---:|---:|
| 001 Foundation | 13 | 12 | 0 | 0 |
| 002 Ingestion | 18 | 17 | 0 | 0 |
| 003 Reconciliation engine | 22 | 18 | 0 | 0 |
| 004 Review and cases | 16 | 13 | 0 | 0 |
| 005 Workbench | 18 | 17 | 0 | 0 |
| 006 Operations | 17 | 16 | 0 | 0 |
| **Total** | **104** | **93** | **0** | **0** |

The count measures structural coverage only. A mapped scenario can still be implemented incorrectly; `verification.md` must record actual evidence before a feature becomes Verified.

## Decisions intentionally deferred to implementation plans

- Exact dependency patch versions and lockfile.
- Named deployment, managed PostgreSQL, and private object-storage providers.
- Concrete workspace quota values beyond the file/run limits already in the specs.
- CSS token values and whether the optional component graph needs a library.
- Measured performance limits after profiling on the named reference workload.
- Exact migration, rollback/recovery, backup, and release commands for the selected host.

These choices may affect implementation and operations but cannot weaken the reviewed behavior contracts.

## Readiness and next gate

All six feature specs are Ready for implementation planning. “Ready” means their behavior is coherent and testable; it does not mean code exists or evidence has passed.

The next spec-driven artifact is `specs/001-foundation/plan.md`, followed by traceable tasks and an initially Pending verification record. Implementation must not start until that plan maps every `FND` requirement to components, transactions, and evidence.
