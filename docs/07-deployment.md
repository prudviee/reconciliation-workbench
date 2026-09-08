# Deployment

This document describes the deployment target `specification 006` resolved and implemented, and states exactly what each control in `OPS-A13` requires. It is the operational counterpart to [`02-hld.md`](./02-hld.md) §10, written after the target existed to configure against rather than before.

## 1. Target

A managed container platform runs the versioned web and worker images against managed PostgreSQL, matching [`ADR-001`](./05-architecture-decisions.md)'s process split with no new orchestration layer (Kubernetes is explicitly out of scope, per `specs/006-operations/spec.md`). Artifact bytes live in an S3-compatible object-storage bucket, addressed through `ingestion.artifacts.StorageAdapter` — the same interface `PrivateArtifactStore` (local filesystem) and `ingestion.s3_artifacts.S3ArtifactStore` both satisfy, selected at runtime by `INGESTION_STORAGE_BACKEND`.

S3-compatible was chosen over a vendor-specific SDK so the adapter speaks one protocol regardless of which bucket provider hosts it, and over self-hosting object storage because this deployment has no existing compute to host it on and the artifact volume is small and quota-bounded (25 MiB/file, per-workspace retained-bytes limit). The exact bucket provider is an environment-variable-configured endpoint/credential pair, not a code dependency.

## 2. One image, two processes

```
docker build -t reconciliation-workbench:<version> .
```

The same image runs both processes; only the command differs:

| Process | Command | Replicas |
|---|---|---|
| web | `python manage.py runserver 0.0.0.0:8000` (or a production WSGI/ASGI server) | ≥1, behind the platform's HTTPS ingress |
| worker | `python manage.py worker --interval 5` | ≥1; more replicas increase claim throughput, not correctness — `jobs.services.claim_batch`'s `SELECT ... FOR UPDATE SKIP LOCKED` already makes concurrent workers safe (`OPS-003`, verified in `specs/006-operations/evidence/OPS-T02.md`) |

Local `docker compose` (`compose.yaml`) runs the identical commands against a local PostgreSQL container and the local-filesystem storage adapter — it is a smaller instance of the same shape, not a different one.

## 3. Environment configuration

All required production values are validated at settings-import time (`config/settings.py`) — an incomplete production configuration fails to start rather than starting insecurely. This is exercised by `tests/test_workspace_sessions.py`'s `test_production_settings_require_explicit_security_and_database_values` and `test_complete_production_settings_enable_https_and_secure_cookies`, which run `config.settings` in a subprocess with production environment variables and assert on the resulting security settings — the closest verification available without a live deployment.

| Variable | Purpose |
|---|---|
| `DJANGO_ENV=production` | Enables every check below |
| `DJANGO_SECRET_KEY` | ≥32 characters, environment-held |
| `DJANGO_ALLOWED_HOSTS` | No wildcard permitted in production |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Every origin must be `https://` |
| `DATABASE_URL` | `postgresql://user:pass@host:port/db` — the managed PostgreSQL instance |
| `INGESTION_STORAGE_BACKEND=s3` | Selects `S3ArtifactStore` over the local filesystem adapter |
| `INGESTION_S3_BUCKET` | The private object-storage bucket |
| `INGESTION_S3_REGION` | Passed to the S3 client; omit for providers that ignore it |
| `INGESTION_S3_ENDPOINT_URL` | Set for a non-AWS S3-compatible endpoint (R2, MinIO, ...); omit for AWS S3 itself |
| `INGESTION_S3_CACHE_ROOT` | Local scratch directory for staging and read-through caching (ephemeral container storage is sufficient — nothing durable lives only here) |
| `WORKER_ID` | Distinguishes concurrent worker replicas' `jobs.WorkerHeartbeat` rows; defaults to `"default"` |

Setting `DJANGO_ENV=production` alone turns on `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_SSL_REDIRECT`, and HSTS (`SECURE_HSTS_SECONDS=31536000` with subdomains and preload) — these are not independently configured per environment; they follow from the same flag that also enforces the required-variable checks above.

## 4. Migrations as a release step

Every web replica's `compose.yaml` command runs `manage.py migrate` before `runserver` — correct for local Compose's single web instance, wrong for a deployed target with multiple replicas: concurrent replicas racing the same migration on boot is exactly the kind of uncoordinated concurrent write this project's evidence-immutability principle exists to prevent elsewhere. In production, migrations run once, as an explicit release step ahead of the new web/worker replicas starting, using the platform's release-phase mechanism (a pre-deploy hook, a one-off release task, or equivalent) — never baked into each replica's own startup command.

## 5. Health signals

| Signal | Source | Distinguishes |
|---|---|---|
| Web readiness | `GET /health/ready` returning 200 | The web process is running and routing |
| Database availability | The same response's `"database"` field | `SELECT 1` against the configured `DATABASE_URL` |
| Worker liveness/freshness | The same response's `"worker_status"`/`"worker_heartbeat_age_seconds"` fields | The most recent `jobs.WorkerHeartbeat` row, independent of whether the web or database checks pass — `OPS-014`/`OPS-A08`, verified live in `specs/006-operations/evidence/OPS-T08.md` |

The worker process itself exposes no HTTP endpoint; its liveness is read through the database, which the web process (and any external monitor) can already reach. `settings.JOBS_WORKER_STALE_SECONDS` (default 30s, roughly six missed 5-second poll cycles) is the staleness threshold.

## 6. Retention disclosure

`workspaces.cleanup.purge_workspace` (`OPS-T07`) enforces the seven-day live `Workspace.expires_at` window: past that point, a workspace's database rows and artifact bytes are actively deleted from the live store. This job has no visibility into, and does not touch, whatever backup retention the managed PostgreSQL and object-storage providers apply on their own schedule. **User-facing retention text must state both periods explicitly** — the seven-day live-store window this deployment enforces, and the provider's separate, typically longer, backup-retention window — so "your data is deleted after seven days" is never stated in a way that implies backup snapshots are also immediately gone (`OPS-016`/`OPS-A15`).

## 7. Measured capacity

Recorded in `specs/006-operations/evidence/OPS-T09.md`, from `scripts/measure_ingestion.py` and `scripts/evaluate_reconciliation.py --output ...` run against this repository's own `docker compose` PostgreSQL — the closest available stand-in for the "documented two-vCPU/four-GiB reference environment" named in [`06-verification-and-delivery.md`](./06-verification-and-delivery.md) §7, run on this development machine rather than a provisioned reference instance. Numbers are reported as measured, including where the 10-second target was missed.

## 8. What this deployment target does not include

Multi-region active-active operation, Kubernetes, Kafka, external workflow engines, and unlimited file/component sizes remain out of scope, per `specs/006-operations/spec.md`'s own stated boundary.
