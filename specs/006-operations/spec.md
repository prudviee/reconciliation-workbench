# 006 Jobs, Operations, and Deployment — Specification

Status: Draft
Prefix: `OPS`
Depends on: 001–005

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

## Acceptance scenarios

- **OPS-A01** Given a worker whose lease expired, when a new attempt succeeds, then the old attempt cannot publish.
- **OPS-A02** Given a correction during computation, when the run completes, then it is historical/stale and a current replacement is coalesced.
- **OPS-A03** Given a publication failure, then no partial result is marked completed and the current pointer does not change.
- **OPS-A04** Given the same manifest requested twice, then one logical run is reused while retries remain separate attempts.
- **OPS-A05** Given workspace expiry, then old URLs and jobs cannot access or publish workspace data.
- **OPS-A06** Given the documented capacity fixture, then observed stage and total durations are recorded even if a target is missed.

## Out of scope

Multi-region active-active operation, Kubernetes, Kafka, external workflow engines, and unlimited file or component sizes.

## Open questions

- Select deployment provider and private-object-storage implementation.
- Benchmark whether PostgreSQL-backed job throughput is sufficient for the showcase limits.
