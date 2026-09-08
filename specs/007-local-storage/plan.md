# 007 Local-only Storage Simplification — Plan

- **Status:** Complete
- **Specification:** [spec.md](./spec.md)

## Approach

1. Collapse configured artifact storage to `PrivateArtifactStore` and remove the unused multi-backend protocol.
2. Remove cloud-specific settings, implementation modules, tests, and dependency pins.
3. Retain `delete_published` on the private store because workspace cleanup depends on it.
4. Update current architecture and deployment documents. Preserve specification 006 as historical evidence and label its external-storage sections as superseded.
5. Run focused storage/cleanup tests, dependency checks, the full suite, and a rebuilt Compose/browser verification.

## Why

The assignment and showcase run on a single host. An external storage adapter adds credentials, dependencies, failure modes, and documentation without improving that journey. A persistent Docker volume satisfies the current privacy, retention, and durability requirements at zero service cost.

## Rejected alternatives

| Alternative | Reason |
|---|---|
| Keep the unused adapter “for later” | Leaves unnecessary SDKs, configuration, and a feature that is not deployed or demonstrated |
| Select a free cloud provider now | Hosting has not been chosen; provider limits and account requirements would become new project scope |
| Store uploads in PostgreSQL | Increases database size and changes the proven file-evidence boundary without a current need |
| Use ephemeral container storage | Uploaded evidence would disappear when the container is replaced |

## Rollback

The removal changes no database schema or stored artifact key. Reverting the implementation commit restores the adapter without data migration.
