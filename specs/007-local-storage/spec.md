# 007 Local-only Storage Simplification — Specification

- **Status:** Verified
- **Prefix:** `STO`
- **Depends on:** 002, 006
- **Decision date:** 8 September 2026

## Outcome

The first release stores uploaded CSV evidence only on its private persistent filesystem volume. It requires no external storage account, credentials, SDK, or network call.

## Requirements

- **STO-001** Every upload, read, authorized download, and expiry deletion MUST use `PrivateArtifactStore` rooted at `INGESTION_PRIVATE_ROOT`.
- **STO-002** Runtime and development dependencies MUST contain no external object-storage SDK or its exclusive transitive packages.
- **STO-003** Docker Compose MUST mount the same private artifact volume into the web and worker processes and MUST preserve it across ordinary rebuilds.
- **STO-004** Current HLD, consolidated design, README, and deployment guidance MUST describe the local-only storage boundary and its hosted-deployment limitation truthfully.
- **STO-005** Removing the unused adapter MUST NOT change CSV limits, workspace authorization, artifact keys, ingestion behavior, cleanup, or the reconciliation workflow.

## Acceptance scenarios

1. A configured store is always a `PrivateArtifactStore` rooted at `INGESTION_PRIVATE_ROOT`.
2. A clean dependency installation contains no external storage SDK.
3. Existing ingestion, downloads, cleanup, jobs, and workbench tests pass without modification to their behavior.
4. The rebuilt Compose stack reports database and worker readiness and serves the existing workspace and workbench.
5. Current design documents do not claim that the verified release uses external object storage.

## Scope

This change removes only the unused external storage option. PostgreSQL, Docker volumes, job leasing, retention cleanup, and production security settings remain. A future public deployment may introduce a storage provider through a new specification after the actual hosting target and free-tier constraints are known.
