# Architecture Decision Record

Each decision records the problem, chosen direction, why it fits, what was rejected, and the cost accepted. “Rejected” means rejected for this release, not universally inferior.

## ADR-001: Build an append-only modular monolith

**Status:** Accepted

**Decision:** Use one repository, one PostgreSQL database, and strong domain modules. Deploy separate web and worker processes from the same application version.

**Why:** The key difficulty is maintaining consistent evidence, decisions, and run publication. A single transactional boundary makes those invariants understandable and testable. Module boundaries still allow the pure engine to evolve independently.

**Rejected:**

- Mutable CRUD application: corrections destroy history and make old runs irreproducible.
- Full event sourcing: adds event evolution and projection machinery without a demonstrated need.
- Microservices and streaming: introduce distributed ordering, delivery, tracing, and deployment work before scale justifies it.

**Consequences:** Modules require discipline because process boundaries do not enforce separation. The database can become a shared dependency, so ownership and repository interfaces must remain explicit.

## ADR-002: Use Django, server-rendered templates, and HTMX

**Status:** Accepted

**Decision:** Build the application with Django, PostgreSQL, templates, HTMX, and small focused JavaScript components.

**Why:** Django provides forms, migrations, sessions, CSRF protection, and mature server-side conventions. The product is a workflow-heavy investigation tool; its key interactions can use HTML fragments without maintaining a separate API/frontend state model. This also follows the advanced design selected from the earlier conversation.

**Rejected:**

- FastAPI plus React: technically strong and initially considered, but it adds a separate frontend toolchain and duplicated contract/state concerns that do not create the project's algorithmic value.
- Django templates without progressive updates: functional, but case drawers, filters, and job-state refresh benefit from partial updates.

**Consequences:** The interface must still be deliberately designed and tested; server rendering does not create polish automatically. Rich graph evidence may need a small client-side visualization component.

## ADR-003: Use anonymous isolated workspaces instead of sign-in

**Status:** Accepted by user

**Decision:** Bind one server-side workspace to an opaque secure browser session. Apply workspace scope to every operation, enforce per-workspace resource quotas, and expire live data at a displayed fixed deadline seven days after creation.

**Why:** Visitors can try the showcase immediately. Authentication does not demonstrate reconciliation and would consume design and implementation time.

**Rejected:**

- Mandatory accounts: add registration, identity-provider configuration, recovery, and account lifecycle.
- Shared public demo state: visitors would interfere with one another and see other uploads.
- Read-only demo only: prevents people from experiencing the complete workflow.

**Consequences:** There is no verified actor identity, recovery, or cross-device access. Audit entries identify a workspace visitor. Losing the session cookie loses access. Activity does not extend expiry. Quota and backup-retention behavior must be visible and verified against deployment.

## ADR-004: Preserve evidence and version observations

**Status:** Accepted

**Decision:** Store original file evidence and immutable normalized observations. Build dataset revisions from memberships rather than overwriting transaction rows.

**Why:** The system must answer both what is currently effective and what a source previously said. Historical runs need their exact observation versions.

**Rejected:**

- Update one transaction row in place: destroys the earlier value.
- Keep only file versions and renormalize on demand: parser changes could alter historical interpretation.
- Global `is_current` on observations: cannot represent different historical dataset memberships accurately.

**Consequences:** Storage and queries are more complex. Current state must be resolved through dataset heads and membership. Cleanup must honor live and historical references.

## ADR-005: Distinguish physical, semantic-input, and dataset-state hashes

**Status:** Accepted

**Decision:** Calculate three separate digests for byte-level artifact identity, canonical input identity, and resulting complete dataset state.

**Why:** Different bytes can represent the same rows, and identical delta payloads can produce different resulting states when applied to different bases. A single hash cannot answer all three questions.

**Rejected:**

- Filename-based duplicate detection: names are neither stable nor unique.
- Physical hash only: misses formatting-equivalent content.
- Semantic patch hash as state identity: confuses an operation with its materialized result.

**Consequences:** Canonical serialization must be versioned and unambiguous. Reprocessing under a new mapping is an explicit action. A historical replay never silently restores old state.

## ADR-006: Declare full-snapshot versus delta semantics

**Status:** Accepted

**Decision:** Every versioned source contract declares whether a file replaces membership for its coverage or patches a prior revision. Delta rows declare upsert, cancellation, or retraction; omission has no effect, and activation is bound to the previewed base revision.

**Why:** An absent record means removal in a complete snapshot and means nothing in a delta. Guessing this from file contents is unsafe.

**Rejected:**

- Treat every upload as replacement: can incorrectly remove records from incremental files.
- Treat every upload as upsert: cannot represent removal from authoritative complete statements.
- Infer contract automatically: file shape rarely proves source coverage.

**Consequences:** Setup has one more explicit choice. Invalid full snapshots cannot activate because rejected rows could be misread as removals.

## ADR-007: Separate source identity from shared matching reference

**Status:** Accepted

**Decision:** A source record key identifies a logical transaction within one source. A separately configured business reference may establish a cross-source pair.

**Why:** Equal-looking IDs may belong to unrelated namespaces, while corrected amount and timestamp values must not change source identity.

**Rejected:**

- Use amount/time as transaction identity: corrections would create new identities.
- Assume every source ID is globally shared: can create false authoritative links.
- Use row position: ordering changes across uploads.

**Consequences:** First-release source contracts require a stable source key or explicitly configured stable composite. Providers without one cannot receive guaranteed correction tracking.

## ADR-008: Separate pairing from field comparison

**Status:** Accepted

**Decision:** Linkage decides whether records represent the same transaction. Comparison independently determines exact, tolerated, discrepant, or not-comparable values.

**Why:** A shared reference can prove identity precisely when the amount mismatch is the problem being investigated.

**Rejected:**

- Require values to agree before pairing: converts clear discrepancies into two misleading unmatched records.
- One generic MATCHED status: hides whether values agree and how the relationship was established.

**Consequences:** UI and schema use separate pair-origin, comparison, and current-review fields.

## ADR-009: Use weighted global one-to-one matching with abstention

**Status:** Accepted for the advanced first release

**Decision:** Lock manual and authoritative links, score the remaining candidate edges, solve complete connected components with optional unmatched choices, and apply a global sensitivity gate before automatic confirmation.

**Why:** Greedy selection can consume a counterpart required for a better total allocation. Global assignment respects one-to-one constraints. Sensitivity analysis exposes ties and unstable selections.

**Rejected:**

- Exact references only: misses useful imperfect linkage and reduces the project's learning value.
- Greedy highest score: can produce a worse allocation based on processing order.
- Force every record into an assignment: creates false matches from weak evidence.
- Mutual-best requirement: can reject an edge that is essential to the globally superior assignment.
- Machine learning first: there is no representative labelled production dataset.

**Consequences:** Scores, thresholds, graph completeness, and solver versions become auditable policy. Sensitivity requires repeated solving. Component limits must abstain safely. A score is not a calibrated probability.

## ADR-010: Use conservative blocking with complete component evidence

**Status:** Accepted

**Decision:** Union several strict candidate-generation passes and retain all eligible edges within bounded solved components.

**Why:** Comparing every left record with every right record grows quadratically. Blocking makes the problem tractable, while unioned passes protect candidate recall.

**Rejected:**

- Full Cartesian comparison: becomes wasteful quickly.
- Keep only top-k edges before assignment: can manufacture a false global margin by discarding alternatives.
- Use financial comparison tolerance as the search window: hides the very discrepancies reconciliation should reveal.

**Consequences:** Candidate recall is a separately measured metric. Dense or truncated partitions become review cases rather than automatic results.

## ADR-011: Store weighted scores as fixed-point integers

**Status:** Accepted

**Decision:** Calculate feature evidence with Decimal and quantize 0–100 scores into 0–10,000 basis points for assignment.

**Why:** Deterministic integer objectives avoid floating-point surprises and make thresholds unambiguous.

**Rejected:**

- Binary floating point for money and scoring: representation error can affect boundary behavior.
- Renormalize weights when fields are missing: sparse records could gain unjustified perfect scores.
- Display score as a probability: weights are uncalibrated design hypotheses.

**Consequences:** Rounding rules and units must be versioned. UI divides basis points by 100 for display.

## ADR-012: Preserve reviewer authority separately from decision health

**Status:** Accepted

**Decision:** Manual link, accept-unmatched, and reject-candidate decisions remain active until explicitly superseded or revoked. New evidence changes health and creates alerts.

**Why:** The assignment requires decisions to survive tomorrow's run, but corrections must remain visible. Authority and evidence freshness answer different questions.

**Rejected:**

- Delete decisions whenever values change: repeatedly discards human work.
- Silently trust every historical decision forever: conceals meaningful corrections.
- Allow automatic matching to override a rejection or acceptance: violates reviewer authority.

**Consequences:** The UI must show active decisions with `EVIDENCE_CHANGED`, `PARTNER_UNAVAILABLE`, or `NEW_CANDIDATE` health. Reaffirmation advances the reviewed baseline.

## ADR-013: Freeze and publish immutable runs conditionally

**Status:** Accepted

**Decision:** A run captures exact data, rules, decisions, and engine versions. Results publish atomically. Only a run whose dependencies remain current advances the scope's current pointer.

**Why:** Inputs can change during computation. Historical evidence should remain reproducible, while late work must not replace a newer result.

**Rejected:**

- Read live data during matching: creates internally inconsistent results.
- Hold a database transaction for the full run: creates unnecessary locks and contention.
- Discard a completed stale run: loses useful historical computation.

**Consequences:** Lifecycle and freshness are separate. Generation counters, manifest hashes, and publication checks are required.

## ADR-014: Use PostgreSQL-backed jobs with leases and fencing

**Status:** Accepted

**Decision:** Store asynchronous work in PostgreSQL; claim with short row locks, unique attempt tokens, and renewable leases.

**Why:** The application already requires PostgreSQL. A durable job table provides retries and atomic enqueue with run creation without introducing another service.

**Rejected:**

- Calculate inside the web request: long requests are fragile and offer poor progress behavior.
- Celery/Redis immediately: adds infrastructure before workload proves it necessary.
- Unfenced retry workers: a late attempt could overwrite newer work.

**Consequences:** The job implementation must handle lease expiry, retry categories, attempt isolation, heartbeats, and cleanup. Queue throughput is intentionally bounded.

## ADR-015: Keep AI advisory and outside the critical path

**Status:** Accepted

**Decision:** The first release demonstrates algorithmic matching without requiring an LLM. Future AI may propose source mappings or summarize stored evidence with human confirmation.

**Why:** Financial pairing needs deterministic, reproducible, testable evidence. The advanced graph algorithm already demonstrates substantial learning and technical depth.

**Rejected:**

- LLM-selected matches: difficult to reproduce, constrain, and evaluate.
- Generated explanations without evidence references: can invent fee or business narratives.
- Uncalibrated learned “confidence”: misleading without representative labels and calibration.

**Consequences:** Any future AI output is advisory, cites structured evidence, and cannot mutate transactions or decisions.

## Decision review triggers

Revisit these decisions when evidence changes:

| Trigger | Decision to revisit |
|---|---|
| Real labelled pairs become available | ADR-009 and ADR-015; probabilistic calibration |
| Candidate components repeatedly exceed caps | ADR-010; blocking and partitioning |
| PostgreSQL job contention becomes material | ADR-014; dedicated queue |
| Multiple people must collaborate and sign decisions | ADR-003; authentication and authorization |
| One-to-many settlement demand appears | Product scope and matching model |
| Independent team ownership or scaling emerges | ADR-001; service extraction |
| Rich client state becomes dominant | ADR-002; frontend architecture |
