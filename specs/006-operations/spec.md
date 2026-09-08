# 006 Jobs, Operations, and Deployment — Specification

> **Storage note:** The external object-storage requirement records the release decision at the time this specification was verified. Specification 007 supersedes that choice for the current release with private persistent local storage. Job, fencing, cleanup, health, and capacity requirements remain current.

- **Status:** Verified
- **Prefix:** `OPS`
- **Depends on:** 001–005
- **Reviewed:** 5 September 2026

## Outcome

Imports and reconciliation runs execute reliably in the background, publish atomically, expose truthful operational state, respect retention, and deploy reproducibly.

## Requirements

- **OPS-001** Run creation MUST freeze and persist the exact dependency manifest before enqueueing work.
- **OPS-002** Enqueue and logical-run creation MUST occur in one database transaction.
- **OPS-003** Work claims MUST use leases and unique attempt fencing tokens.
- **OPS-004** A worker without the current attempt token MUST NOT publish results or case projections.
- **OPS-005** Publication MUST validate complete endpoint partitioning and write a complete result atomically.
- **OPS-006** A completed run whose data, policy, or decision generation is superseded MUST remain historical/stale and MUST NOT replace the current-input pointer.
- **OPS-007** Transient failures MUST retry to a documented limit; permanent failures MUST remain inspectable and preserve the last successful result.
- **OPS-008** Progress MUST show real stages and counts rather than fabricated percentages.
- **OPS-009** Workspace expiry MUST stop new work, revoke access, and safely clean database/file data according to published retention.
- **OPS-010** Deployment MUST use private file storage, HTTPS, environment-held secrets, migrations as a controlled release step, and separate readiness/worker health signals.
- **OPS-011** Structured logs and metrics MUST omit raw financial rows and secrets.
- **OPS-012** Capacity and performance claims MUST be measured on a named workload and environment.
- **OPS-013** The first deployment plan MUST choose a managed PostgreSQL service and private object storage with a documented local filesystem adapter.
- **OPS-014** Health reporting MUST distinguish web readiness, database availability, and worker liveness/freshness.
- **OPS-015** Cleanup MUST be idempotent, MUST verify live references before deleting stored artifacts, and MUST record terminal failures for repair.
- **OPS-016** Deployed retention text MUST state both live-store expiry and any longer backup retention; deletion claims MUST match measured operational behavior.
- **OPS-017** Logical runs, work attempts, staging data, progress, health details, and result publication MUST preserve workspace ownership; a worker MUST validate ownership from its frozen manifest rather than trust caller-supplied IDs.

## Acceptance scenarios

- **OPS-A01** Given a worker whose lease expired, when a new attempt succeeds, then the old attempt cannot publish.
- **OPS-A02** Given a correction during computation, when the run completes, then it is historical/stale and a current replacement is coalesced.
- **OPS-A03** Given a publication failure, then no partial result is marked completed and the current pointer does not change.
- **OPS-A04** Given the same manifest requested twice, then one logical run is reused while retries remain separate attempts.
- **OPS-A05** Given workspace expiry, then old URLs and jobs cannot access or publish workspace data.
- **OPS-A06** Given the documented capacity fixture, then observed stage and total durations are recorded even if a target is missed.
- **OPS-A07** Given repeated cleanup delivery, then the workspace remains revoked and referenced/shared artifacts are not removed prematurely.
- **OPS-A08** Given a healthy web process but stale worker heartbeat, then health reporting distinguishes those states.
- **OPS-A09** Given database rollback or enqueue failure during logical-run creation, then no runnable orphan exists; a retry either creates or resolves exactly one logical run for the manifest.
- **OPS-A10** Given a queued run followed by policy, mapping, dataset, or decision changes, when its worker starts, then it uses the frozen manifest and can publish only as historical/stale when the manifest is no longer current.
- **OPS-A11** Given transient failures through the configured retry limit and a permanent validation failure, when attempts finish, then retries are separately inspectable, the logical run reaches the documented terminal state, and the last successful result remains available.
- **OPS-A12** Given each import and reconciliation stage, when work progresses, then the UI receives only persisted stage names and measured counts; no estimated percentage is emitted without a measured denominator.
- **OPS-A13** Given the release candidate configuration, when deployment checks run, then HTTPS, secure cookies, private artifact access, environment-held secrets, controlled migration execution, database readiness, and worker freshness are independently verified.
- **OPS-A14** Given jobs containing representative session and financial values, when logs, traces, metrics, and error reports are captured, then correlation and stage metadata remain while raw rows and secrets are absent.
- **OPS-A15** Given a deployment with backup retention longer than the seven-day live workspace period, when retention text and deletion behavior are verified, then access ends at live expiry and the longer backup period is disclosed without claiming immediate backup erasure.
- **OPS-A16** Given a forged or internally inconsistent manifest containing resource IDs from different workspaces, when a worker claims it, then execution fails before reading financial data or publishing results and the owning workspaces remain unchanged.

## Invariants and failure behavior

- Logical run identity and worker attempt identity are separate. (`OPS-001`, `OPS-003`)
- Enqueue occurs only after the owning transaction commits successfully. (`OPS-002`)
- Attempt-specific staging cannot mix across retries. (`OPS-003`, `OPS-004`, `OPS-005`)
- Only the current fencing token may publish or alter case projections. (`OPS-004`)
- Cleanup revokes access before deleting content and is safe to retry. (`OPS-009`, `OPS-015`)
- Backup retention may outlive live data; deployed user-facing retention text must state the actual backup policy. (`OPS-016`)
- Logs, traces, metrics, and error reporting exclude raw transaction fields and session secrets. (`OPS-011`)

## Performance and capacity

Planning target: on a documented two-vCPU/four-GiB reference environment, reconcile 10,000 records per side in under 10 seconds subject to component caps and accept files up to 25 MiB. This remains a target until measured. The PostgreSQL job approach remains selected until measured queue latency, lock contention, or throughput fails an explicit deployment target. (`OPS-012`, Constitution XI)

## Out of scope

Multi-region active-active operation, Kubernetes, Kafka, external workflow engines, and unlimited file or component sizes.

## Resolved decisions

- Provider selection is a plan-level decision because deployment credentials and availability can change. The required contract is managed PostgreSQL, private object storage, HTTPS, and one versioned web/worker image; the plan must name the chosen provider before implementation of deployment tasks.
- PostgreSQL-backed jobs are the first-release decision. Benchmarks validate the decision; failing measured targets triggers ADR review rather than leaving the spec behavior undefined.

## Requirement-to-scenario matrix

| Requirement | Scenarios |
|---|---|
| OPS-001 | OPS-A10 |
| OPS-002 | OPS-A09 |
| OPS-004, OPS-006 | OPS-A02, OPS-A04, OPS-A10 |
| OPS-003, OPS-004 | OPS-A01 |
| OPS-005 | OPS-A03 |
| OPS-007 | OPS-A11 |
| OPS-008 | OPS-A12 |
| OPS-009, OPS-015 | OPS-A05, OPS-A07 |
| OPS-010, OPS-013 | OPS-A13 |
| OPS-014 | OPS-A08, OPS-A13 |
| OPS-011 | OPS-A14 |
| OPS-012 | OPS-A06 |
| OPS-016 | OPS-A15 |
| OPS-017 | OPS-A16 |

## Change history

| Date | Change | Reason |
|---|---|---|
| 5 September 2026 | Initial draft | Define jobs, publication, retention, and deployment behavior |
| 5 September 2026 | Fixed provider decision boundary, cleanup/health behavior, capacity contract, and traceability; marked Ready | Critical SDD review |
