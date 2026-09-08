# STO-T01 Verification Evidence

- **Task:** Remove unused external storage support
- **Requirements:** `STO-001`–`STO-005`
- **Date:** 8 September 2026
- **Result:** Pass

## Delivered state

- `configured_artifact_store()` always constructs `PrivateArtifactStore` from `INGESTION_PRIVATE_ROOT`.
- The alternate adapter module, backend settings, adapter-specific tests, and test credential fixture are removed.
- The runtime and development locks no longer include the external storage SDK or its exclusive transitive packages.
- `PrivateArtifactStore.delete_published()` remains the workspace-cleanup boundary, so seven-day expiry still deletes retained files.
- Docker Compose continues to mount the same `artifact-data` volume into web and worker containers.
- README, HLD, consolidated design, and deployment guidance now describe the verified single-host, local-only storage target.
- Specification 006 storage statements are labelled historical and superseded rather than rewritten as if they had never existed.

## Verification

| Check | Result |
|---|---|
| Focused intake, download, cleanup, import-job, worker, and architecture suite | 49 passed |
| Complete regression suite | 532 passed |
| Django system check | No issues |
| Migration consistency | No changes detected |
| Dependency integrity | No broken requirements |
| Current implementation/design reference scan | No cloud-storage implementation references |
| Clean rebuilt runtime image | External storage SDK absent |
| Docker services | Database, web, and worker healthy |
| Readiness | HTTP 200; database ready; worker healthy |
| Persistent artifact volume after rebuild | Two existing uploaded files retained |
| Browser workbench | Existing selected run, three pairs, filters, exports, and history rendered |

The two pytest warnings concern Windows refusing writes to pytest's optional cache directory. They do not affect collection or test behavior.

## Limit

The verified release is single-host. A public host must provide a persistent private filesystem before uploads are enabled; ephemeral hosting is not presented as durable.
