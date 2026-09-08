# OPS-T05 Verification Evidence

- **Task:** Extract `StorageAdapter` and add the object-storage implementation
- **Requirements:** `OPS-010`, `OPS-013`
- **Date:** 8 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence

## Implemented contracts

- `ingestion.artifacts.StorageAdapter`: a `Protocol` matching `PrivateArtifactStore`'s existing four methods (`stage`, `publish`, `discard_path`, `resolve`) exactly, as they were already written — a structural contract, not a rewrite. `PrivateArtifactStore` needed zero changes to satisfy it.
- `ingestion.s3_artifacts.S3ArtifactStore`: an S3-compatible implementation of the same protocol. Staging still writes to, and CSV-scans, a real local file — `stage()` delegates directly to an internal `PrivateArtifactStore` pointed at a local cache directory, because Python's `csv` module needs a real seekable file regardless of the durable backend. Only `publish` (`put_object`), `resolve` (`get_object`, cached locally after the first read), and a new `delete_published` (`delete_object`) reach the network, via low-level boto3 client calls rather than the high-level transfer manager (`upload_file`/`download_file`) — the transfer manager issues an extra `head_object` before every download and complicates testing without adding value at this artifact size (≤25 MiB, well under any multipart threshold).
- `ingestion.services.configured_artifact_store()` selects `S3ArtifactStore` when `settings.INGESTION_STORAGE_BACKEND == "s3"`, else the unchanged `PrivateArtifactStore` (default `"local"`). `ArtifactIntakeService.store` is now typed `StorageAdapter`. No caller (`ingestion/preview.py`, `ingestion/services.py`, `foundation/views.py`) changed — they all called the protocol's four methods already.
- New settings: `INGESTION_STORAGE_BACKEND`, `INGESTION_S3_BUCKET`, `INGESTION_S3_REGION`, `INGESTION_S3_ENDPOINT_URL` (set for R2/MinIO/any S3-compatible provider other than AWS), `INGESTION_S3_CACHE_ROOT`.
- `boto3`/`botocore` (plus their `s3transfer`, `jmespath`, `python-dateutil`, `six`, `urllib3` transitive pins) added to `requirements/runtime.lock`, `requirements/dev.lock`, and `pyproject.toml`'s direct dependency list. No conflicts (`pip check` clean).

## Known limitation (disclosed, not silently accepted)

If a workspace/book/scope transaction fails *after* `publish()` has already uploaded an object but before the owning database row commits, the local adapter's rollback path (`discard_path`) only removes the local cache copy — it does not call `delete_published` to remove the now-orphaned S3 object, since the existing call sites (`ingestion/services.py`) pass a `Path`, not a `storage_key`, to the shared rollback method. This is a narrow, existing-behavior-preserving choice: reworking every call site to thread the storage key through the rollback path was out of this task's scope (`plan.md`'s smallest-coherent-slice principle), and the risk is bounded — an orphaned object with no live database reference, which `OPS-T07`'s workspace-cleanup verification (`OPS-015`'s "verify live references before deleting") is the right place to reconcile if this is ever observed in practice, not a reason to block this task.

## Verification results

| Check | Result |
|---|---|
| `tests/test_s3_artifacts.py` (new, `botocore.stub.Stubber` — no live bucket/credentials needed) | 7 passed: local-identical staging/scanning, publish uploads + caches, resolve downloads-once-then-caches, delete removes object + cache, cache-path escape rejected, full `ArtifactIntakeService.ingest()` round trip, a `ClientError` translates to `ArtifactIntakeError` |
| `tests/test_artifact_intake.py` (specification 002's existing `PrivateArtifactStore` contract suite, unmodified) | 25 passed — proves the local adapter is untouched by the protocol extraction |
| `tests/test_ingestion_workflow.py`, `test_ingestion_preview.py`, `test_ingestion_downloads.py` | 61 passed (combined) — every existing caller of `store.stage/publish/discard_path/resolve` is unaffected |
| Full repository regression | 520 passed in 18.80 seconds |
| `pip check` | No broken requirements |
| `git diff --check` (whitespace) | Passed |

## Scope boundary

Import validation is not yet routed through the `jobs` claim mechanism — that is `OPS-T06`, which will exercise `S3ArtifactStore` (or `PrivateArtifactStore`, per `INGESTION_STORAGE_BACKEND`) from inside a claimed `IMPORT_VALIDATION` work item instead of inline in the request. The deployment target's actual bucket/credentials provisioning is an `OPS-T09` concern.
