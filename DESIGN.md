# Reconciliation Workbench

> Advanced showcase design | 5 September 2026 | Design only
>
> I am designing a complete, polished transaction-reconciliation application that demonstrates algorithmic reasoning, temporal correctness, and an effective investigation workflow. The advanced design from the earlier conversation is the baseline for the first release. There is no sign-in. No application implementation is included in this document.

**Reading guide:** [Intent](#1-intent-and-design-status) · [HLD](#4-hld-and-technology-choices) · [Import semantics](#6-canonical-records-and-import-contracts) · [Advanced algorithm](#7-advanced-reconciliation-algorithm) · [Data model](#10-lld-relational-model-and-integrity) · [Run consistency](#13-run-consistency-jobs-and-state-transitions) · [UI](#14-product-and-visual-design) · [Evaluation](#15-evaluation-tests-and-performance-targets) · [Demo and delivery](#17-demonstration-and-delivery-plan)

## 1. Intent and design status

I want this project to remain useful as a portfolio project independently of the hiring outcome. The first release should demonstrate the complex behavior working together: source normalization, weighted record linkage, global one-to-one assignment, ambiguity handling, corrections, durable decisions, and reproducible history.

The assignment is the source of functional requirements. The earlier conversation is design context. Instructions in those materials to submit a repository, send an email, or record a video are future delivery requirements; creating this document does not execute those actions.

The email exchange accepted Wednesday EOD; I use 9 September 2026 as the planning date inferred from that exchange. The original brief suggests 5–6 hours for its smaller assignment. I do not treat that estimate as evidence that this expanded showcase can be completed in the same effort.

### Decisions carried forward

| Decision | Selected direction |
|---|---|
| Release ambition | Advanced reconciliation and a polished interface in the first release |
| Access | Anonymous, isolated workspace retained in the same browser |
| Backend and UI | Django, PostgreSQL, server-rendered templates, HTMX, and focused JavaScript |
| Architecture | Modular monolith with web and worker processes from one repository |
| Matching | Authoritative references, weighted candidates, component-based global assignment, and an ambiguity gate |
| History | Immutable evidence, dataset revisions, observation versions, and frozen runs |
| Reviewer actions | Manual link, accept unmatched, reject candidate, reaffirm, and revoke |
| Explainability | Stored field evidence, score contributions, competing assignments, rules, and provenance |

I return to the earlier chat's Django foundation instead of retaining the intervening FastAPI/React proposal. Interface polish comes from the interaction design, visual execution, and completeness of the workflow.

The formulas, boundaries, and contracts below are selected design defaults. Numeric thresholds, resource limits, and performance figures are hypotheses or targets to validate, not measured achievements. The final dependency patch versions, hosting vendor, and visual brand name can be selected during implementation without changing these domain decisions.

## 2. The hard problem and its boundaries

Two systems describe overlapping sets of transactions. Their representations, identifiers, values, and coverage differ. New evidence can change yesterday's understanding. A reviewer can also establish a relationship the algorithm could not infer.

I separate four concepts:

1. **Evidence:** the original file and row received.
2. **Observation:** a versioned canonical interpretation of that row.
3. **Link assertion:** an automatic or manual claim that two records describe the same transaction.
4. **Investigation case:** an issue that remains understandable across runs and reviewer actions.

Linkage answers identity. Comparison answers agreement. A manually linked pair can still have an amount discrepancy.

### First-release scope

- Two predefined source formats and a configurable third-format mapping workflow.
- CSV upload, parsing preview, atomic validation, duplicate recognition, and corrections.
- Explicit full-snapshot and delta import contracts.
- One-to-one reconciliation, weighted scoring, global assignment, and deliberate abstention.
- Exact, tolerated, discrepant, unmatched, ambiguous, excluded, and review-required outcomes.
- Persistent manual actions and stable investigation cases.
- Historical runs, comparison evidence, source revision timelines, and exports.
- Background processing, stale-result protection, anonymous workspace isolation, and expiry.
- Curated demonstration data, synthetic evaluation, property tests, accessible UI, and deployment documentation.

One-to-many allocations, settlement netting, FX conversion, live bank integrations, accounting journal posting, user accounts, and team approvals require additional domain contracts and are outside this release. The application compares evidence; it does not move funds or close an external accounting system.

## 3. Correctness invariants

1. Original evidence is immutable during the workspace retention period.
2. A correction never overwrites a historical observation.
3. One left or right observation appears in at most one confirmed pair in a run.
4. A logical transaction has at most one active reserving reviewer decision in its reconciliation book.
5. Identical frozen inputs, policy versions, and engine versions produce identical domain outcomes.
6. Pairing and financial comparison are independent dimensions.
7. Incomplete or tied candidate evidence cannot establish an automatic heuristic pair.
8. Every automatic pair has a reproducible explanation.
9. Formatting-only changes do not revoke reviewer decisions.
10. Material changes trigger decision-health review; they do not erase decision history.
11. Cancelled records remain inspectable and do not enter financial comparison.
12. Invalid required values never become zero, empty strings, or silently omitted records.
13. Replaying an already-applied upload cannot roll current state backward.
14. Completed run evidence is immutable; current review state is a separate projection.
15. A run based on older inputs cannot replace the current-input result pointer.
16. Every resource lookup and mutation is scoped to the authorized anonymous workspace.

## 4. HLD and technology choices

I use an append-only domain model inside a modular monolith. Mutable pointers identify current revisions; immutable rows preserve what was known before. I do not need a full event-sourced infrastructure to provide that history.

~~~mermaid
flowchart LR
    B["Browser: templates and HTMX"] --> W["Django web application"]
    W --> A["Application services"]
    A --> P[("PostgreSQL")]
    A --> F[("Private file storage")]
    J["Python worker"] --> P
    J --> F
    J --> N["Canonicalization"]
    J --> E["Pure reconciliation engine"]
    E --> C["Candidate scoring and assignment"]
    E --> D["Field comparison"]
    E --> R["Results and review evidence"]
~~~

| Component | Choice and responsibility |
|---|---|
| Web framework | Django 5.2 line; request handling, forms, migrations, sessions, CSRF protection |
| UI | Templates and HTMX; JavaScript for drawer focus, keyboard shortcuts, and small interactive evidence views |
| Styling | Tailwind CSS with a small documented set of reusable components |
| Database | PostgreSQL; relational integrity, exact numeric values, revision pointers, jobs |
| Assignment solver | SciPy linear assignment solver behind a pure domain adapter |
| Jobs | PostgreSQL-backed job records and a separate Python worker |
| Files | Private object storage in deployment; filesystem adapter in local development |
| Tests | Pytest, pytest-django, Hypothesis, and Playwright |
| Packaging | One repository and container image, separate web/worker commands, Docker Compose locally |

The core engine accepts plain immutable value objects. It imports no Django models, reads no clock, queries no database, and makes no network calls.

Django's explicit transaction blocks support short atomic mutations. HTMX supports HTML responses and partial updates, which fit the workbench and drawer interactions. These are framework capabilities; the reconciliation decisions remain my own design. [Django transactions](https://docs.djangoproject.com/en/5.2/topics/db/transactions/), [HTMX documentation](https://htmx.org/docs/)

### Alternatives considered

| Alternative | Assessment |
|---|---|
| Mutable transaction table | Cannot preserve earlier evidence adequately; rejected |
| Full event sourcing | Valuable replay model but larger projection and event-versioning surface than needed |
| Distributed reconciliation services | Adds ordering and coordination work without a demonstrated scaling need |
| FastAPI and React | Viable, but the selected earlier baseline is Django; a separate frontend is not required by these interactions |
| Exact-reference matching alone | Useful baseline, insufficient for the selected algorithmic showcase |
| Greedy best-candidate matching | Can consume a counterpart needed for a better overall assignment |
| Weighted global assignment with abstention | Selected; demonstrates constrained optimization while preserving uncertainty |

## 5. Anonymous workspace and reconciliation scope

### Access without sign-in

Opening the product creates a workspace associated with a server-side Django session. The browser receives a secure, HttpOnly, SameSite cookie. Workspace IDs in URLs are identifiers, not access credentials. Queries resolve resources through the session's workspace; knowing another workspace's UUID grants no access.

The default retention target is seven days from workspace creation, displayed with an exact expiry time. The same browser can return until expiry. Clearing the session cookie loses access; there is no account recovery or automatic cross-device access. The user can export results or explicitly delete the workspace.

Each workspace receives independent sample data. Loading another sample creates another reconciliation book and never resets uploaded work. CSRF checks apply to every state-changing form or endpoint. Session support is an authentication-free access mechanism here, not a claim of verified user identity. [Django sessions](https://docs.djangoproject.com/en/5.2/topics/http/sessions/)

Audit events identify the anonymous session actor and timestamp, not a verified person. Data is private within this access model and expires under the published retention policy.

### Long-lived book versus run scope

- **Reconciliation book:** a durable source/account pair, reference namespace, and review history. It owns decisions and cases across days.
- **Book source:** one side of a book, its source system, account, and mapping configuration.
- **Dataset identity:** book source + declared coverage period + statement identifier.
- **Dataset revision:** a materialized set of observations active for that dataset at one revision.
- **Run scope:** the selected left and right datasets and coverage policy within a book.

A new provider can reuse a mapping profile and participate in a new book. One-to-one constraints apply within a book/run, so comparing a ledger against another provider is not accidentally prohibited.

A run never searches the entire workspace. Coverage is explicitly selected. Candidate windows may cross midnight within that coverage; a UTC calendar-date equality rule must not hide a valid nearby candidate. Reference matching is scoped by account and configured reference namespace, not by mutable amount or currency.

Decisions belong to the long-lived book, not merely a dated run. If their transactions are absent from a particular run, the decisions remain stored and can apply when those identities reappear.

## 6. Canonical records and import contracts

### Canonical observation

| Field | Meaning |
|---|---|
| logical_transaction_id | Internal stable identity in a book source |
| source_record_id | Required stable source key or an explicitly configured stable composite key |
| business_reference | Optional shared matching reference, separate from source identity |
| executed_at | Timezone-aware UTC instant |
| instrument | Explicitly normalized instrument |
| side | Canonical BUY or SELL |
| quantity | Finite exact decimal |
| unit_price | Finite exact decimal |
| gross_amount | Finite exact decimal |
| currency | Explicit source field or declared mapping default |
| state | Canonical state including SETTLED, PENDING, and CANCELLED |
| provenance | Artifact, row number, mapping revision, contract revision, and observation revision |

An adapter owns column mapping, decimal parsing, date format, timezone, instrument aliases, enum mapping, and natural-key interpretation. Mappings use allowlisted transformations, not user-supplied executable expressions.

Ambiguous dates, unknown enum values, missing required fields, non-finite numbers, and unsupported numeric precision block activation. The default supports positive trade quantities and nonnegative prices/amounts, with direction in side; other sign conventions must be explicitly normalized.

The proposed database precision is NUMERIC(38,12), with validation before persistence and decimal calculations at higher intermediate precision. Unsupported precision is reported rather than silently rounded. Different output precision is a presentation choice. Python Decimal provides exact decimal representation; construction uses source strings, never binary floats. [Python decimal documentation](https://docs.python.org/3/library/decimal.html)

### Full snapshot and delta

Each source contract declares one import mode:

| Mode | Meaning of the new file | Meaning of an omitted record |
|---|---|---|
| FULL_SNAPSHOT | Complete replacement membership for the declared dataset coverage | No longer present in that dataset revision; historical evidence remains |
| DELTA | A patch against the current dataset revision | Unchanged; it remains present |

The curated statement example uses full snapshots. The uploader must see and confirm the selected contract, coverage, and change preview. A delta constructs a new materialized membership from its base plus changes. Cancellation is an explicit state change; deletion by omission is never inferred for deltas.

An empty full snapshot is a deliberate empty replacement and needs an explicit preview confirmation. A file with malformed required rows cannot become a full snapshot: treating rejected rows as absent would produce false removals.

### Three distinct hashes

1. **Physical hash:** SHA-256 of the original bytes. Artifact storage may be reused, but import identity also includes dataset and interpretation.
2. **Semantic input hash:** digest of sorted normalized rows, including multiplicity, mapping/contract versions, and dataset identity.
3. **Resolved state hash:** digest of the resulting complete dataset membership. A delta's patch hash is not its resolved state hash.

Canonical hashing preserves significant values, normalizes equivalent decimal formatting, and uses an unambiguous serialization. Conflicting or repeated source keys in a file are reported with row numbers; the default rejects duplicate keys instead of choosing a row by order.

An ordinary repeat of an already-applied physical or semantic payload returns the prior import result. It does not reactivate that revision. Intentional restoration of historical values uses an explicit restore-as-new-correction action or a trusted newer provider revision; hashes alone cannot distinguish an old replay from an intended reversal.

The same bytes interpreted under a new mapping revision require an explicit reprocess preview. Recognizing stored bytes must not prevent a legitimate corrected interpretation.

### Atomic import workflow

~~~mermaid
sequenceDiagram
    participant U as User
    participant A as Import service
    participant W as Worker
    participant D as Database
    U->>A: Upload file and select contract
    A->>D: Store artifact metadata and validation job
    W->>D: Claim job
    W->>W: Parse, normalize, validate, calculate preview
    W->>D: Store preview and row errors
    U->>A: Confirm preview with expected base revision
    A->>D: Lock book and verify base revision
    alt Valid and unchanged base
        A->>D: Create observations and dataset membership atomically
        A->>D: Advance dataset pointer and book generation
    else Errors or stale preview
        A-->>U: Explain errors or request refreshed preview
    end
~~~

Raw evidence and validation errors may be retained from a rejected file, but no normalized dataset is activated from it. A failed right-side upload does not remove a successful left-side import.

## 7. Advanced reconciliation algorithm

### Pure engine contract

~~~text
reconcile(snapshot, matching_policy, comparison_policy, decisions)
    -> EngineResult
~~~

Inputs contain exact observation IDs and values, dataset revisions, policy revisions, decision revisions, engine version, and solver version. Output contains confirmed pairs, comparisons, candidates, ambiguity evidence, unmatched observations, exclusions, and decision-health alerts.

### Pipeline

~~~mermaid
flowchart TD
    A["Frozen canonical observations"] --> B["Exclusions and durable decisions"]
    B --> C["Lock authoritative reference pairs"]
    C --> D["Generate candidate graph"]
    D --> E["Calculate weighted evidence"]
    E --> F["Solve each connected component"]
    F --> G["Measure global ambiguity"]
    G --> H["Confirmed links and review cases"]
    C --> I["Field comparison"]
    H --> I
    I --> J["Reproducible result"]
~~~

#### 7.1 Eligibility and decisions

Only active membership observations enter the run. Cancelled observations are recorded as excluded. Saved manual links and accepted-unmatched decisions reserve identities before automatic matching. Active rejected-candidate decisions forbid the corresponding relationship in every automatic stage, including authoritative-reference pairing. A newly shared reference that conflicts with a saved rejection creates an attention case; it does not override the rejection.

A manual link with both eligible endpoints establishes a pair even when values differ. If an endpoint is cancelled or absent, the decision remains stored and the eligible endpoint requires attention; it cannot silently acquire a different automatic partner.

After normal assignment, a separate read-only decision-health pass examines changed evidence and possible counterparts for accepted-unmatched identities present in the snapshot. It may inspect eligible opposite-side observations even when already allocated, and reports that allocation in its evidence. This pass produces alerts only: it never releases reservations, creates assignment edges for reserved records, or changes the chosen matching. An incomplete diagnostic search is labelled limited, not interpreted as proof that no counterpart exists.

#### 7.2 Authoritative references

Build hash indexes for a configured trustworthy cross-source reference namespace. Automatically link only references unique on both sides within the input scope. Source-local identifiers are not automatically shared references.

An authoritative pair with conflicting currency, instrument, side, time, or amount remains linked and receives field discrepancies. Heuristic compatibility gates must not hide those errors. A duplicate shared reference produces an ambiguity case.

The source contract declares reference semantics. Under SHARED_MUST_AGREE, two present but unequal references in the same guaranteed shared namespace prohibit heuristic automatic pairing. Under SOURCE_LOCAL_OR_ALIAS, different source-local IDs are allowed, while only explicitly mapped shared aliases can provide authoritative evidence. Missing shared references do not establish a contradiction; the remaining evidence and coverage gate govern candidates. Manual linking can resolve a reference contradiction through an explicit recorded decision.

Expected reference-pass work is O(n + m), excluding ingestion and persistence.

#### 7.3 Candidate graph

For remaining records, union versioned blocking passes using account compatibility, instrument, side, currency, and broad time or quantity ranges. Blocking reduces candidate enumeration; it does not prove a match. [Splink blocking documentation](https://moj-analytical-services.github.io/splink/topic_guides/blocking/blocking_rules.html)

The initial general pass uses compatible instrument/side/currency and a 24-hour time window within selected coverage. A source can add a secondary-reference pass with a wider declared window. Heuristic automatic pairs require compatible instrument, side, and currency; manual search can surface conflicting records with explicit differences.

The search window is independent of comparison tolerance and similarity decay. For example: search within 24 hours, give time similarity over ten minutes, and accept timestamp agreement within 60 seconds. These settings serve three different purposes.

I retain all eligible edges for a component before solving it. Cutting every row down to its top five candidates before solving can fabricate certainty. A shortlist is a display optimization after the full bounded computation.

#### 7.4 Versioned weighted evidence

Initial weights are design hypotheses:

| Feature | Weight | Initial broad similarity band |
|---|---:|---|
| Quantity | 35 | max(configured asset absolute band, 1% of larger absolute value) |
| Timestamp | 25 | 600 seconds |
| Unit price | 15 | max(configured currency absolute band, 1% of larger absolute value) |
| Gross amount | 25 | max(configured currency absolute band, 1% of larger absolute value) |

For a numeric feature with difference d and band b:

~~~text
feature = max(0, 1 - d / b)
if b is zero: feature = 1 for equality, otherwise 0
score = sum(weight * feature)
~~~

Missing features contribute zero; weights are not renormalized over available fields. Required evidence coverage must be satisfied for automatic acceptance. Score arithmetic uses Decimal, followed by an explicit ROUND_HALF_EVEN quantization to integers from 0 to 10,000 for the solver.

All solver arithmetic uses the integer scale consistently: score_bp = ROUND_HALF_EVEN(score * 100), assignment floor = 7000, automatic threshold = 9000, and global margin = 800. Utilities and counterfactual objectives use these same units. Divide by 100 only for the 0–100 user-facing score and example tables.

The UI shows a matching score on a 0–100 scale, never a probability. Evidence includes field values, bands, differences, feature values, contributions, and contradiction flags. Price and amount are correlated; evaluation must test whether their combined weight creates unjustified reassurance.

#### 7.5 Optional-unmatched global assignment

Partition the eligible candidate graph into connected components. For each component, select a partial one-to-one matching maximizing:

~~~text
utility(edge) = score(edge) - assignment_floor
objective = sum(utility(edge) for selected edges)
unmatched utility = 0
~~~

Illustrative policy: assignment floor 70/100, automatic threshold 90/100, minimum global margin 8 score points. Edges at or below the floor remain review evidence but do not enter automatic assignment.

I use a linear assignment solver, whose SciPy implementation is documented as modified Jonker–Volgenant. I do not describe that implementation as Hungarian. [SciPy assignment documentation](https://docs.scipy.org/doc/scipy-1.13.0/reference/generated/scipy.optimize.linear_sum_assignment.html)

For n left nodes and m right nodes, construct an n by (m+n) cost matrix. Real allowed edges have cost -utility; forbidden real edges have a positive cost; n dummy columns have zero cost. Every left record can remain unmatched via a dummy, and unused real columns are unmatched right records. Enough zero-cost dummy choices ensure weak real pairs are never forced.

#### 7.6 Global ambiguity gate

Let W be the optimal component utility. For each proposed edge e, forbid only that edge and solve the same complete component again, retaining unmatched choices:

~~~text
global_gap(e) = W - best_utility_without(e)
~~~

Automatically confirm a heuristic pair only if its score reaches the automatic threshold, evidence coverage is adequate, no hard contradiction applies, its global gap reaches the margin, and the complete computation finished within limits.

Equal optimal assignments give a zero gap and require review. Stable IDs may order presentation but never turn a tie into evidence.

I do not require a mutual-best local candidate as an extra gate: that would reject some of the globally beneficial assignments this algorithm exists to find. Local differences remain useful explanations. After the gate, I keep its accepted subset and abstain on the rest; I do not iteratively remove alternatives until weaker pairs appear certain.

#### 7.7 Demonstrable global-assignment example

| Matching score | R1 | R2 |
|---|---:|---:|
| L1 | 94 | 92 |
| L2 | 93 | 20 |

With a floor of 70, greedy selection of L1–R1 yields utility 24 and leaves L2 unmatched. Global assignment chooses L1–R2 and L2–R1, with utility 22+23=45.

Forbidding either global edge leaves a best utility of 24, so each has a global gap of 21. Both scores exceed 90. This example belongs in the UI evidence view and demo.

If all four scores are 94, either complete assignment is equally good. The gaps are zero and all four records require review.

These numbers demonstrate solver behavior; they are not claims about measured real-world matching accuracy.

#### 7.8 Complexity and computational limits

Candidate enumeration is output-sensitive. Dense groups can still approach O(nm); blocking does not eliminate that worst case.

Initial caps are 100 total real nodes and 2,500 eligible edges per solved component, 250,000 candidate edges per run, and 200 enumerated candidates per record. Sensitivity needs one base solve plus one solve per proposed edge. These limits require benchmarking.

If complete component enumeration exceeds a cap, it becomes a review case. If enumeration truncates before component boundaries are known, heuristic automatic matching is withheld for the affected blocking partition. The UI explains that a limit prevented a complete assessment. It never presents a margin computed from a truncated shortlist as reliable.

## 8. Comparison policy

Comparison runs after identity is established, for manual, authoritative, and weighted-global pairs alike.

| Field | Policy |
|---|---|
| Instrument, side, currency | Canonical equality |
| Timestamp | Absolute elapsed duration; inclusive tolerance |
| Quantity, price, gross amount | Explicit absolute/relative decimal tolerance |
| State | Versioned compatibility matrix; SETTLED versus PENDING is a discrepancy by default |
| Reference | Show equality/difference and matching role; local-ID differences are not financial discrepancies |

The selected numeric formula is symmetric:

~~~text
signed_difference = right - left
allowed = max(abs_tolerance, rel_tolerance * max(abs(left), abs(right)))
passes = abs(signed_difference) <= allowed
~~~

This explicitly chooses the larger absolute value as relative scale. With relative tolerance zero it becomes a fixed absolute rule. Relative differences at a zero denominator are shown as not applicable unless both values are zero.

The seeded USD demonstration policy uses gross-amount absolute tolerance 0.05 USD, price tolerance 0.01 USD, quantity tolerance 0.00000001 units, and time tolerance 60 seconds; relative comparison tolerances are zero. Its broad similarity absolute bands are 1.00 USD for amount, 0.01 USD for price, and 0.00000001 units for quantity, combined with the 1% bands in section 7.4. These are illustrative source-policy values. A new currency or instrument requires an explicit applicable policy rather than silently inheriting a financial standard.

I do not subtract unlike currencies and label the result a monetary variance. Currency mismatch is displayed and the amount comparison is not comparable.

An optional source-contract quality check can evaluate gross_amount against quantity * price. It is enabled only when that source's gross/fee semantics justify the relationship. Net consideration must not be mapped to gross amount merely because both are monetary fields.

Results expose independent dimensions:

- Pair origin: AUTHORITATIVE_REFERENCE, WEIGHTED_GLOBAL, MANUAL, or NONE.
- Comparison: EXACT, WITHIN_TOLERANCE, DISCREPANT, NOT_COMPARABLE, or NOT_APPLICABLE.
- Current review: OPEN, ACCEPTED_UNMATCHED, PENDING_RERUN, REQUIRES_ATTENTION, or CLOSED.

The explanation reports observations such as an amount difference of 170. It does not infer fees, fraud, settlement intent, or any other cause without source evidence.

## 9. Reviewer decisions and stable cases

Decisions reference logical identities in a book and record the observation versions reviewed. An append-only revision chain preserves creation, reaffirmation, replacement, and revocation.

| Action | Effect |
|---|---|
| LINK | Reserve one left and one right identity as a manual pair |
| ACCEPT_UNMATCHED | Reserve one identity from automatic linking; it remains unmatched |
| REJECT_CANDIDATE | Exclude one proposed relationship; neither transaction disappears |
| REAFFIRM | Record inspection of newer evidence and advance the reviewed baseline |
| REVOKE / REPLACE | Append a new decision event and release or replace relevant reservations atomically |

Every action requires a concise reason. The actor is the anonymous session identity.

Decision status and health are separate. Active decisions can have UNCHANGED, EVIDENCE_CHANGED, PARTNER_UNAVAILABLE, or NEW_CANDIDATE health.

| New evidence | Behavior |
|---|---|
| Formatting-only reupload | No observation or decision change |
| Amount/time correction to a manual pair | Keep pair, compare current observations, flag changed evidence |
| Instrument/side/currency correction | Preserve decision, require attention, show incompatible fields |
| Cancellation or declared snapshot removal | Keep decision; unavailable endpoint cannot be compared or silently replaced |
| Possible counterpart to accepted-unmatched record | Retain acceptance and create an attention case; explicit reopen is required |
| Changed evidence behind a rejected candidate | Preserve rejection and flag for review; no silent reuse of the edge |

A fingerprint detects which reviewed fields changed; it does not decide business identity by itself. The UI presents an active historical decision with an attention flag, rather than erasing it or silently claiming it remains fully justified.

A stable case is attached to its book and logical transaction identities. Each run creates a case occurrence with that run's evidence. Case identity and lineage are book-wide, but current occurrence/state are scoped by (case, reconciliation scope) and derived from that scope's published run plus its labelled current-review projection. Two independently current period scopes cannot overwrite one book-wide case status in worker completion order. When pairing changes within a scope, related unmatched cases close there with an explicit transition and link to the new pair case. Splits and replacements retain navigable case lineage.

Current decisions save immediately. Changes affecting matching are labelled pending rerun. The old run's selected links and counts are unchanged. Accept-unmatched can update the current review column immediately while its original run fact remains unmatched.

## 10. LLD: relational model and integrity

All domain tables carry workspace ownership directly or through an enforced parent relationship. Composite ownership constraints prevent cross-workspace references. UUIDs identify public resources; they do not authorize access.

| Entity | Key fields and relationships |
|---|---|
| workspace | id, session binding, created_at, expires_at, deletion state, quota counters |
| source_system | workspace_id, name, type |
| mapping_revision | source_id, revision, field mappings, enum/alias maps, parser version |
| source_contract_revision | source_id, mapping_revision_id, mode, timezone, natural-key policy, coverage rules |
| reconciliation_book | workspace_id, name, generation, resolution_generation |
| book_source | book_id, LEFT/RIGHT role, source_id, account, identity namespace |
| reconciliation_scope | book_id, left_dataset_id, right_dataset_id, coverage, current_run_id, dirty flag |
| dataset | book_source_id, coverage key, statement key, current_revision_id |
| file_artifact | workspace_id, physical_hash, private_storage_key, original_name, byte_size |
| ingestion_attempt | artifact_id, dataset_id, contract_revision_id, semantic_hash, expected_base_revision_id, state, duplicate_of |
| raw_row | ingestion_id, row_number, raw values, validation errors |
| logical_transaction | book_source_id, source_record_key |
| transaction_observation | logical_transaction_id, canonical fields, raw_row_id, mapping/contract revision, fingerprint |
| dataset_revision | dataset_id, parent_revision_id, ingestion_id, resolved_state_hash, created_at |
| dataset_membership | dataset_revision_id, logical_transaction_id, observation_id |
| policy_revision | book_id, immutable matching/comparison configuration, revision, digest |
| decision | book_id, type, current_revision_id |
| decision_revision | decision_id, predecessor_id, endpoints, reviewed observation IDs, action, reason, actor, timestamp |
| active_decision_claim | book_id, logical_transaction_id, decision_revision_id |
| reconciliation_run | scope_id, manifest_hash, generations, policy/engine/solver versions, lifecycle, freshness |
| run_input | run_id, side, logical_transaction_id, observation_id |
| run_decision_input | run_id, decision_revision_id |
| candidate_evidence | run_id, left/right observation IDs, feature values, score, compatibility flags, component_id |
| assignment_component | run_id, graph digest, solver objective, limits, ambiguity diagnostics |
| run_pair | run_id, left/right observation IDs, origin, score if applicable, global_gap if applicable |
| field_comparison | run_pair_id, field, values, signed/absolute difference, tolerance, outcome |
| run_unpaired | run_id, observation_id, unmatched/ambiguous/excluded/accepted disposition, reason |
| investigation_case | book_id, stable key, logical endpoints, lineage references |
| case_occurrence | case_id, run_id, result references, state in that run |
| case_scope_projection | case_id, scope_id, current_occurrence_id, derived state, applied review generation |
| audit_event | book_id, case/decision/import/run references, actor, action, structured details, timestamp |
| work_item | target_id, kind, state, available_at, lease_until, current_attempt_token |
| job_attempt | work_item_id, attempt token, started/finished timestamps, error category |

### Critical constraints

- Unique book source role per book.
- Unique source record key within a book source's identity namespace.
- Unique logical identity in each dataset revision.
- Dataset membership's observation must belong to its stated logical transaction.
- Unique physical artifact hash within the workspace; interpretation attempts remain separate.
- One dataset head pointer; immutable revisions can share historical observations.
- One active reserving decision claim per (book, logical transaction).
- Reject-candidate decisions have no endpoint claim but cannot coexist with an active manual link for that pair.
- One left and one right usage per run pair, enforced with separate unique constraints.
- Every run input has exactly one terminal accounting outcome: paired once, or unpaired once with a reason. A publication validator checks the cross-table invariant.
- Unique successful domain run identity per manifest; retries are attempts of the same run.
- One current-result pointer per scope. A result's lifecycle and freshness are separate.

Current observations are selected through dataset membership, never through a global observation.is_current flag. A correction changes future membership; it cannot change historical membership.

Useful indexes cover source identity, dataset membership, run outcome, case state, and candidate lookup by scope/instrument/side/currency/time. I benchmark range scans before adding further indexes.

~~~mermaid
erDiagram
    WORKSPACE ||--o{ BOOK : owns
    BOOK ||--o{ BOOK_SOURCE : defines
    BOOK ||--o{ SCOPE : contains
    BOOK_SOURCE ||--o{ DATASET : receives
    DATASET ||--o{ DATASET_REVISION : versions
    DATASET_REVISION ||--o{ MEMBERSHIP : contains
    LOGICAL_TRANSACTION ||--o{ OBSERVATION : versions
    OBSERVATION ||--o{ MEMBERSHIP : selected_by
    SCOPE ||--o{ RUN : executes
    RUN ||--o{ RUN_INPUT : freezes
    OBSERVATION ||--o{ RUN_INPUT : used_in
    RUN ||--o{ PAIR : produces
    PAIR ||--o{ FIELD_COMPARISON : explains
    BOOK ||--o{ DECISION : preserves
    DECISION ||--o{ DECISION_REVISION : versions
    BOOK ||--o{ CASE : tracks
    CASE ||--o{ CASE_OCCURRENCE : appears_in
    RUN ||--o{ CASE_OCCURRENCE : contains
~~~

## 11. LLD: application and engine boundaries

| Module | Responsibilities and interface |
|---|---|
| workspaces | Resolve anonymous access, quotas, expiry, deletion |
| sources | Version source contracts and mappings; validate configuration |
| ingestion | Store evidence, validate previews, deduplicate, construct dataset revisions |
| books | Define source/account pairs, scopes, generations, and mutation locks |
| domain.normalization | Canonical values and parser contracts |
| domain.candidates | Generate complete bounded candidate sets and compatibility evidence |
| domain.scoring | Calculate versioned features, fixed-point scores, and evidence coverage |
| domain.assignment | Connected components, optional assignment, sensitivity, abstention |
| domain.comparison | Decimal/time/status comparison independent of linkage |
| reconciliation | Freeze inputs, orchestrate runs, verify outputs, conditionally publish |
| resolutions | Append decision revisions and maintain endpoint claims |
| cases | Stable identity, occurrences, transitions, current review projections |
| jobs | Claim, heartbeat, retry, fence publication, and clean up expired work |
| web | Full pages, HTMX fragments, forms, exports, accessibility behavior |

Domain value objects include CanonicalObservation, SnapshotManifest, DecisionInput, CandidateEdge, FeatureEvidence, AssignmentProposal, FieldDifference, DecisionHealth, and EngineResult.

Repositories and file storage are adapters called by application services. They load all referenced inputs before calling the pure engine. Database objects do not leak into its value objects.

## 12. LLD: web contracts

The browser primarily receives server-rendered HTML. HTMX requests receive corresponding fragments; ordinary navigation remains usable. A small JSON response is appropriate for job progress and exported machine-readable results.

| Method and route | Contract |
|---|---|
| GET / | Resolve or create workspace; show books and sample-data entry |
| POST /books | Create a named book and source/account roles |
| POST /books/{id}/demo | Create isolated curated data without replacing existing books |
| POST /books/{id}/imports | Stage file with dataset identity and mapping/contract revision; return import/job ID |
| GET /imports/{id} | Show validation, duplicate status, interpreted rows, and proposed changes |
| POST /imports/{id}/activate | Require expected base revision; atomically publish valid dataset membership |
| POST /imports/{id}/restore | Explicitly reapply historical contents as a new correction with reason |
| POST /sources/{id}/mapping-revisions | Validate and create a new immutable mapping revision |
| POST /books/{id}/policy-revisions | Validate and create new scoring/comparison policy; mark affected scopes dirty |
| POST /scopes/{id}/runs | Freeze current manifest and enqueue or return equivalent run |
| GET /runs/{id} | Render result or truthful progress stage |
| GET /runs/{id}/cases | Server-side search, filters, stable ordering, and pagination |
| GET /cases/{id} | Evidence, candidates, decisions, and history |
| POST /cases/{id}/decisions | Type, endpoint IDs, reason, reviewed observation IDs, expected generations |
| POST /decisions/{id}/revoke | Append reversal with reason and expected revision |
| GET /runs/{id}/export | Workspace-authorized CSV or JSON export with revision metadata |
| GET /artifacts/{id}/download | Check session ownership before private file access |
| POST /workspace/delete | Explicitly invalidate access and schedule deletion |

Validation failures return 422 with field/row explanations. Stale previews and decisions return 409 with a refresh path. Resources outside the workspace return 404. Job creation returns 202 when asynchronous. Normal server-rendered form submission uses redirect-after-post after successful mutations.

Decision creation locks the book, rechecks generations and observation membership, validates all affected claims, appends the decision, updates claims, increments resolution_generation, and marks relevant scopes dirty in one transaction. A conflicting link is never silently replaced; the user sees a replacement preview and explicitly supersedes the earlier decision.

Exports preserve decimal strings and timezone labels. CSV cells originating from untrusted input are escaped against spreadsheet formula execution. Exports identify whether they represent original run facts or current review state.

## 13. Run consistency, jobs, and state transitions

### Snapshot and publication

All state mutations affecting a book acquire its row lock briefly. This serializes publication boundaries within the book while leaving engine computation outside database transactions. When touching multiple books, acquire locks in stable ID order.

At run creation, capture exact dataset revisions, input membership, matching/comparison policy revision, active decision revisions, resolution_generation, book generation, engine version, and solver version. Hash the canonical manifest and enqueue the work item in the same transaction.

The worker computes from immutable references. A run does not read live dataset heads midway through matching.

At publication, check the worker attempt token, validate the complete result partition, and compare the frozen manifest dependencies with current heads and generations. Store the complete result and atomically update the current pointer only if those dependencies still agree.

Intermediate worker results are isolated by attempt token and remain unpublished. At the selected scale, the simplest implementation computes in memory and writes all result rows in one publication transaction. If staging is needed, the winning attempt's complete staging set is promoted atomically; rows from different attempts can never mix under the logical run. A failed or fenced attempt cannot update case projections.

If newer data or decisions arrived, keep the completed run as historical with STALE freshness. Do not replace the scope's current-input pointer or current case projection. Coalesce a replacement request for the newest manifest. A previous result can remain visible with a clear inputs-changed banner.

This uses short database transactions around state changes, consistent with PostgreSQL's concurrency model. The application manifest defines what constitutes a current result. [PostgreSQL transaction isolation](https://www.postgresql.org/docs/current/transaction-iso.html)

~~~mermaid
sequenceDiagram
    participant U as User
    participant A as Application
    participant D as Database
    participant W as Worker
    U->>A: Start run
    A->>D: Lock book, freeze manifest, enqueue
    W->>D: Claim job with attempt token
    W->>W: Compute from frozen inputs
    opt Correction or decision while computing
        U->>A: Save change
        A->>D: Advance generation and mark scope dirty
    end
    W->>D: Verify attempt and current dependencies
    alt Dependencies unchanged
        W->>D: Publish complete result and advance current pointer
    else Dependencies changed
        W->>D: Save historical result and coalesce replacement run
    end
~~~

### State machines

| Object | States and transitions |
|---|---|
| Import | UPLOADED → VALIDATING → INVALID / DUPLICATE / READY → ACTIVATED; stale base returns to preview |
| Run lifecycle | QUEUED → RUNNING → COMPLETED / FAILED |
| Run freshness | CURRENT / STALE; independent of lifecycle |
| Work item | READY → LEASED → SUCCEEDED; expired/transient failure → READY; exhausted retries → FAILED |
| Decision | ACTIVE → SUPERSEDED / REVOKED; health changes independently |
| Case | OPEN → RESOLVED / SUPERSEDED; later evidence creates an occurrence with required attention |
| Workspace | ACTIVE → EXPIRED / DELETING → DELETED |

Work claims use short row locks with SKIP LOCKED. Each attempt receives a unique fencing token and renewable lease. A worker whose lease was reclaimed cannot publish with its earlier token. Retry transient failures up to a documented limit; preserve each attempt and an intelligible failure reason.

Same-manifest repeated requests reuse the logical run; a failed run can be retried through a new attempt. Historical successful data is not rewritten by that retry.

The app exposes manual rerun. A daily trigger can call the same run-creation service for configured open scopes, using a unique scope/local-date schedule key and explicit timezone. It does not require a separate reconciliation path. Expired workspaces cannot receive new scheduled work.

## 14. Product and visual design

The central screen answers: **What still needs my attention, and what evidence supports the next decision?**

### Five surfaces

| Surface | Main interactions |
|---|---|
| Workspace | Start sample workflow, create book, upload files, see latest results and expiry |
| Import and prepare | Map columns, inspect parsed dates/decimals, validate, preview additions/corrections/removals, activate |
| Reconciliation workbench | Run selection, outcome summary, complete-result search/filtering, case table, pending-change banner |
| Case evidence | Side-by-side values, weighted features, global allocation, candidate rejection/linking, decisions, history |
| Runs and activity | Historical snapshots, case changes between runs, imports, decisions, and exports |

Source and rule configuration are reachable from setup and the book menu. Case evidence is a desktop drawer with its own stable URL; smaller screens use the dedicated page.

~~~text
Reconciliations / Exchange A settlement                 Workspace expires 12 Sep

Run 12 · Completed       Ledger revision 3 ↔ Statement revision 2   [History]
2 saved decisions await rerun                                        [Rerun]

Needs review 18     Exact 241     Tolerated 7     Excluded 4

[Search reference or case] [Outcome] [Pair origin] [Current review]

CASE     LEDGER           STATEMENT       DIFFERENCE      CURRENT REVIEW
C-1042   T-901 / $520.00   C-180 / $500.00  -$20.00        Needs review
C-1043   T-902 / $860.00   —               —              Ambiguous
C-1044   —                C-182 / $240.00  —              Accepted unmatched

                                       CASE C-1042
                                       Manually paired · Amount mismatch
                                       [Fields] [Candidates] [Decisions] [History]
                                       Value in this run / Current saved evidence
~~~

### Evidence that demonstrates the advanced algorithm

The primary field table shows source values, differences, tolerance, and result. An expandable explanation shows:

1. Why the pair entered the candidate set.
2. Each scoring contribution and missing/contradictory evidence.
3. The selected global assignment and relevant competing edges.
4. The alternative objective when this edge is forbidden.
5. Why the pair passed the gate or remained ambiguous.

A compact candidate matrix illustrates the greedy counterexample. An optional graph is useful for small components; the table remains accessible and readable without it.

There is no generic green matched badge that conceals a discrepancy. Labels such as Manually paired · Amount mismatch and Accepted unmatched state both facts.

### Interaction details

- Default the workbench to needs-review cases.
- Search and filters operate on the entire result set, with stable server pagination.
- Keep the last successful result visible during reruns and failures.
- Show actual stages and processed counts, not invented progress percentages.
- Show pending decisions separately from decisions effective in the selected run.
- Historical views open with a historical banner and a link to current evidence.
- Import errors point to row, column, original value, and expected interpretation.
- Corrections use an uploaded replacement/delta or explicit historical restore. Direct editing of a source's financial values is not required for this release.
- Every reviewer action shows the affected records and requires a reason.
- Revoke and replacement actions append history; they do not erase earlier actions.

### Visual and accessibility specification

Use a light neutral background, dark navy text, one primary accent, restrained semantic colors, tabular numerals, right-aligned amounts, explicit currencies, stable column widths, and generous evidence-panel spacing.

Every state has text in addition to color. All forms have labels and announced errors. Keyboard users can open a row, navigate the evidence panel, perform actions, and return focus to the originating row. Drawers trap focus appropriately and support Escape. Table headers remain understandable with assistive technology.

Desktop supports the complete table workflow. Tablet uses a wider case panel. Mobile supports summary, search, case evidence, and basic decisions through dedicated pages. It does not squeeze a dense desktop table into unreadable columns.

## 15. Evaluation, tests, and performance targets

### Algorithm evaluation

I generate labelled synthetic datasets with a hidden ground-truth correspondence map. The truth labels are not exposed to the matcher. Separate seeds and scenario families form development and held-out evaluation sets.

Compare three strategies using identical inputs and candidate rules where applicable:

1. Exact-reference baseline.
2. Greedy weighted baseline.
3. Selected weighted-global matcher with abstention.

Report true automatic pairs, false automatic pairs, precision, recall, candidate recall, unmatched/ambiguous counts, review rate, duration, and component sizes. Only AUTHORITATIVE_REFERENCE and WEIGHTED_GLOBAL pairs enter automatic TP/FP; manual links never inflate automatic performance. Precision is TP/(TP+FP). Recall is TP divided by true pairs eligible for automatic matching after exclusions and reviewer constraints, so manually reserved endpoints are excluded. No automatic predictions means precision is not applicable, not 100%. Candidate recall is measured on true pairs eligible for the heuristic stage after authoritative links and all reviewer constraints. Report total workflow coverage, including manual resolutions, separately.

The showcase report labels all measurements as synthetic. Zero errors on a small fixture is not evidence of production accuracy. Threshold tuning uses development data only.

### Required tests

| Area | Cases |
|---|---|
| Normalization | Third format, aliases, explicit timezones, ambiguous dates, decimal formatting, invalid numbers |
| Ingestion | Exact and semantic duplicate, historical replay, explicit restoration, stale preview, malformed snapshot |
| Membership | Snapshot omission versus delta omission; unchanged rows reused; old observations preserved |
| Authoritative matching | Shared reference with amount/time/currency discrepancy; duplicate shared reference |
| Weighted evidence | Feature boundaries, missingness, score quantization, correlated price/amount scenarios |
| Assignment | Greedy counterexample, tied optimum, threshold/margin boundaries, unequal sides, all weak edges |
| Solver correctness | Exhaustive enumeration on tiny graphs agrees with solver objective; disconnected components agree with equivalent combined solution |
| Limits | Oversized component and incomplete enumeration abstain explicitly |
| Decisions | Manual precedence, accept unmatched, reject candidate across reference and heuristic stages, new-candidate diagnostics, reaffirm, revoke, replacement conflict |
| Corrections | Manual pair remains paired with changed difference; cancellation leaves partner requiring attention |
| Concurrency | Correction during run, late stale worker, conflicting endpoint claims, generation conflict, independent scope case projections, attempt-isolated publication |
| Isolation | Other workspace IDs fail on reads, mutations, jobs, downloads, and exports |
| UI | Upload → run → inspect → reject/link/accept → correction → rerun → historical inspection |

Property tests require row-order invariance, repeatability, no double pairing, complete endpoint accounting, equivalent decimal normalization, formatting-only decision stability, and no change to unrelated disconnected components.

### Targets to benchmark

- 10,000 records per source and 25 MiB per file as initial supported limits.
- Run computation target under 10 seconds for the documented 10,000-by-10,000 synthetic workload on a stated two-vCPU/four-GiB reference environment, subject to component caps.
- Typical paginated workbench responses below 500 ms p95 on that environment.
- Immediate acknowledgement of asynchronous work without tying the request to the calculation.
- Complete core demonstration in five minutes without developer tools.

If a target is missed, report the measurement and improve the relevant algorithm, query, or limit. Do not claim the target as achieved because the design names it.

## 16. Failure handling, operations, and deployment

| Failure | Visible and durable behavior |
|---|---|
| Unsupported schema or invalid required row | Preserve evidence/errors; keep existing dataset active |
| Unknown currency/timezone/status semantics | Require explicit source mapping; no silent guess |
| Replayed historical import | Return prior import with current-head context; no rollback |
| Conflicting activation base | Refresh change preview; no last-write-wins |
| Ambiguous/oversized candidate graph | Review case with reason; no fabricated automatic result |
| Worker crash | Lease/retry/fencing; previous successful result remains available |
| Database publication error | No completed partial result or half-updated current pointer |
| New evidence during computation | Historical completed result marked stale; coalesced replacement |
| Expired workspace | Revoke access, stop new work, apply retention cleanup |
| Missing file object | Explain unavailable evidence and flag storage inconsistency; do not invent source values |

Structured logs include workspace/book/scope/run/import/job IDs and stage durations. They exclude raw transaction payloads and session secrets. Metrics include ingestion errors, duplicate uploads, candidate counts, component overflow, match/review rates, stale runs, retries, and processing duration.

Uploads have byte, row, field-length, and processing limits. Filenames never become trusted storage paths. Private downloads recheck workspace authorization. HTML output escapes uploaded strings. The deployment uses HTTPS, secure cookies, CSRF protection, private storage, and environment-held secrets.

Local development runs web, worker, and PostgreSQL through Docker Compose with persistent volumes. Deployment runs web and worker from the same versioned image, uses managed PostgreSQL and private object storage, and applies migrations once as a release step. Health checks distinguish web readiness, database availability, and worker heartbeat.

Expiry cleanup invalidates access before deleting rows and files, coalesces or cancels jobs, and checks live references before removing shared artifacts. Backup retention can outlive live-store expiry; the deployed retention notice must name that period rather than promise immediate erasure from backups.

## 17. Demonstration and delivery plan

The curated dataset must include exact/tolerated pairs, amount and time discrepancies, unmatched records on both sides, cancellations, duplicate references, a global-assignment benefit, tied ambiguity, a correction, and persistent reviewer decisions.

| Demo time | What I demonstrate |
|---|---|
| 0:00–0:30 | Open an anonymous workspace and explain the reconciliation problem |
| 0:30–1:05 | Inspect a source mapping and activate prepared inputs |
| 1:05–1:40 | Run and show exact, tolerated, discrepant, unmatched, and excluded outcomes |
| 1:40–2:25 | Inspect the global-assignment counterexample and evidence behind the chosen pairs |
| 2:25–3:15 | Reject a candidate, manually link a pair, and show that its amount discrepancy remains |
| 3:15–3:45 | Accept a genuinely unmatched record and upload a prepared correction |
| 3:45–4:30 | Rerun, show persistent decisions and changed cases, then inspect the earlier immutable run |

### Implementation sequence for the selected first release

These are dependency-ordered checkpoints, not an assignment-only release followed by an advanced release.

| Checkpoint | Concrete exit evidence |
|---|---|
| Domain and contracts | Canonical schema, source contracts, pure comparison, labelled fixtures |
| Advanced matching | Weighted evidence, global solver, sensitivity gate, exhaustive small-graph validation |
| Temporal persistence | Imports, semantic hashes, dataset memberships, decisions, snapshots, safe publication |
| Product workflow | Mapping preview, workbench, evidence, cases, manual actions, history |
| Integration and polish | Background jobs, isolation, errors, exports, accessibility, responsive inspection |
| Release verification | Held-out synthetic evaluation, complete browser flow, deployment check, demo rehearsal |

For the available calendar window, I should finish an executable vertical flow early and add the remaining planned depth in these checkpoints. Algorithm evidence, temporal behavior, and UI quality are reviewed throughout; polish is not reserved for the last hour.

The release is ready when the required tests pass, the full demo works, results and evaluation are honestly documented, and no known issue contradicts the core invariants. The date is a planning constraint, not permission to claim unverified behavior.

The future implementation README should include setup, sample data, assumptions, algorithm explanation, measured evaluation, known limits, architectural decisions, and demo instructions. A public repository and video are planned deliverables; this design document does not publish either.

## 18. Research extension and AI boundary

The first release already demonstrates nontrivial algorithms through weighted linkage, graph decomposition, global optimization, and sensitivity-based abstention.

The earlier discussion also proposed probabilistic record linkage and LLM assistance. I preserve those as researched alternatives without presenting untrained heuristics as probabilities. A meaningful probabilistic experiment would need labels, representative negative pairs, calibration, a held-out split, and comparison against the weighted baseline. The Fellegi–Sunter framework describes agreement evidence through match/non-match likelihoods. [Splink model explanation](https://moj-analytical-services.github.io/splink/topic_guides/theory/fellegi_sunter.html)

Optional learned ranking can later use explicitly reviewed examples; it must account for selection bias because reviewed cases are not a random sample. Any experiment reports synthetic versus real evidence separately.

An LLM is not required to run this application. If added, it can propose mappings or summarize stored evidence with source references and human confirmation. It cannot silently alter values, assert a fee explanation, approve a pairing, or change a reconciliation decision. The earlier phrase CA algorithms was interpreted as AI in that chat; it does not by itself specify an additional model requirement.

## 19. Reference projects and attribution

I use these sources as architectural references, not as evidence that this application has been implemented or validated.

| Reference | Specific pattern informing this design |
|---|---|
| [Beangulp importer interface](https://github.com/beancount/beangulp/blob/master/beangulp/importer.py) | A consistent boundary for source-specific identification and extraction |
| [Firefly III import configuration](https://github.com/firefly-iii/data-importer/blob/main/resources/schemas/v3.json) | Explicit, versioned field roles and import configuration |
| [Actual Budget imports](https://actualbudget.org/docs/transactions/importing/) | Previewing interpreted columns and dates before committing |
| [Actual Budget reconciliation](https://actualbudget.org/docs/accounts/reconciliation/) | Inspectable reconciliation and review states |
| [ERPNext bank transaction model](https://github.com/frappe/erpnext/blob/develop/erpnext/accounts/doctype/bank_transaction/bank_transaction.py) | Explicit reconciliation relationships and lifecycle integrity |

No implementation code from these projects is included. Any later code reuse requires checking its applicable license and retaining the required attribution.

The assignment PDF supplies the functional problem and delivery requirements. The prior design conversation supplies the selected advanced baseline. This document refines ambiguous areas: optional-unmatched assignment, global sensitivity instead of mutual-best gating, explicit snapshot/delta semantics, version-aware hashes, persistent decision authority with separate health, and conditional current-run publication.

## 20. First-person design statement

I model source records as immutable evidence and normalized, versioned observations. I establish transaction identity separately from financial agreement. I lock authoritative and manual relationships, score the remaining candidates, and solve complete bounded components as optional one-to-one assignments.

I test the stability of each proposed assignment against competing solutions and deliberately retain ambiguity when the evidence is insufficient. Corrections create new evidence, reviewer decisions remain traceable, and each run captures the exact inputs and rules it used.

The interface makes those decisions inspectable through field differences, candidate evidence, assignment alternatives, and a continuous case history. That is the behavior I intend to demonstrate in the showcase.
