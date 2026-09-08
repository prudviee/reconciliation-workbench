# OPS-T09 Verification Evidence

> **Storage target superseded:** Specification 007 makes the verified release local-only. Capacity measurements remain valid; external-storage deployment statements below are historical.

- **Task:** Ship deployment configuration and measured capacity
- **Requirements:** `OPS-010`, `OPS-012`, `OPS-013`, `OPS-016`
- **Acceptance scenarios:** `OPS-A06`, `OPS-A13`, `OPS-A15`
- **Date:** 8 September 2026
- **Result:** Pass, with one target honestly missed (see below)

## Deployment documentation

[`docs/07-deployment.md`](../../../docs/07-deployment.md) is the deliverable: the resolved target (managed container platform + managed PostgreSQL + S3-compatible object storage, named in `plan.md`'s resolved decision), the one-image/two-command process topology, every required environment variable, why migrations must run as a release step rather than baked into each web replica's boot command (`compose.yaml`'s local single-replica `migrate && runserver` is correct for local Compose and would be wrong under multiple deployed replicas), the three independent health signals, and the `OPS-016`/`OPS-A15` retention disclosure requirement (live seven-day expiry vs. the provider's separate backup window).

There is no live cloud account in this environment, so nothing was actually deployed — this is configuration and documentation against the resolved target, not a deployment rehearsal log. That limit is stated here rather than implied by an evidence file that only shows what could be verified without one.

## What was independently verified without live infrastructure

- **Production settings validation** (`OPS-A13`'s HTTPS/secure-cookie/secret/database checks): already covered by `tests/test_workspace_sessions.py`'s `test_production_settings_require_explicit_security_and_database_values` and `test_complete_production_settings_enable_https_and_secure_cookies` (pre-existing, from specification 001) — re-run in this task and still passing. These run `config.settings` in a subprocess with production environment variables and assert the resulting security settings, which is the closest verification available without a live deployment.
- **Storage adapter selection** (`OPS-013`): new tests (`tests/test_artifact_intake.py`) prove `configured_artifact_store()` returns `PrivateArtifactStore` by default and `S3ArtifactStore` — with the configured bucket, region, and a non-AWS `endpoint_url` (an R2/MinIO-shaped example) — when `INGESTION_STORAGE_BACKEND=s3`.
- **Worker/database health independence** (`OPS-014`/`OPS-A13`'s "database readiness and worker freshness are independently verified"): covered by `OPS-T08`'s evidence, re-confirmed live in this task (see below).

## Measured capacity (`OPS-012`, `OPS-A06`)

Run via `scripts/measure_ingestion.py` and `scripts/evaluate_reconciliation.py --output ...` against this repository's own `docker compose` PostgreSQL container — the closest available stand-in for `docs/06-verification-and-delivery.md`'s "documented two-vCPU/four-GiB reference environment," on this development machine rather than a provisioned reference instance. Full JSON output: `OPS-T09-ingestion-capacity.json`, `OPS-T09-reconciliation-capacity.json` (this directory).

| Workload | Target | Measured | Result |
|---|---|---|---|
| Reconciliation, 10,000 records/side | Complete under 10 seconds | **11.012257 seconds** | **Missed by ~10%** |
| Full-snapshot ingestion activation, 10,000 rows | — (no stated target) | 26.122 seconds, 82 queries, 238.68 MiB peak | Measured, no target to compare against |
| Full-snapshot ingestion preview, 10,000 rows | — (no stated target) | 23.119 seconds, 41 queries, 102.16 MiB peak | Measured, no target to compare against |
| Delta activation, 10,000 base + 1,000 operations | — (no stated target) | 10.402 seconds, 47 queries | Measured, no target to compare against |
| Near-limit preview, 24.6 MB file | — (no stated target) | 24.565 seconds, 41 queries, 154.66 MiB peak | Measured, no target to compare against |

**The reconciliation capacity target was missed, reported honestly rather than rounded down.** Per `docs/06-verification-and-delivery.md` §7: *"A missed target triggers profiling of parsing, candidate enumeration, solver sensitivity, persistence, or queries before changing architecture."* That profiling is not part of this task — closing an 11.01s vs. 10s gap is a tuning exercise (candidate blocking width, batch size, or query shape), not an architectural change, and doing it responsibly means measuring where the time actually goes first rather than guessing. This is recorded as a known, disclosed gap for follow-up, consistent with constitution XI ("an unmet target is reported honestly") rather than silently accepted or hidden.

**A second finding this measurement surfaces directly justifies `OPS-T06`'s work**: ingestion preview/activation at 10,000 rows takes 23–26 seconds synchronously. Before `OPS-T06` moved import validation behind the claimed-job mechanism, this ran entirely inline in the upload request — a 23-second synchronous HTTP response is a real problem this measurement makes concrete, not hypothetical.

## Verification results

| Check | Result |
|---|---|
| `tests/test_artifact_intake.py` (2 new backend-selection tests) | 27 passed |
| `tests/test_workspace_sessions.py -k production` (pre-existing) | 4 passed |
| Full repository regression | 539 passed in 17.11 seconds |
| `git diff --check` (whitespace) | Passed |
| Capacity measurement | Executed against real PostgreSQL, real reconciliation engine, real ingestion pipeline — not simulated or estimated |

## Scope boundary

`OPS-T10` closes the specification: all sixteen acceptance scenarios together, the full traceability table, and the final release-gate check against `docs/06-verification-and-delivery.md` §11.
