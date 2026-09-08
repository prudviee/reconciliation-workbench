# Deployment

This document describes the verified, zero-cost release target for the reconciliation workbench. The target is a single-host Docker Compose installation. No cloud account or external file-storage service is required.

## 1. Target

Docker Compose runs PostgreSQL, the Django web process, and the background worker. Two named Docker volumes preserve database rows and private CSV artifacts across container rebuilds:

- `postgres-data` stores PostgreSQL data.
- `artifact-data` stores uploaded source files under `INGESTION_PRIVATE_ROOT`.

The artifact volume is mounted only into the web and worker containers. Downloads still pass through workspace authorization; the web server never exposes the volume as a public static directory.

## 2. One image, two application processes

```text
docker build -t reconciliation-workbench:<version> .
```

The same image runs both application processes; only the command differs:

| Process | Command | Local replicas |
|---|---|---:|
| web | `python manage.py runserver 0.0.0.0:8000` | 1 |
| worker | `python manage.py worker --interval 5` | 1 |

PostgreSQL-backed leases and fencing keep job execution safe. The local release deliberately uses one web and one worker process because the private filesystem volume is a single-host resource.

## 3. Environment configuration

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | Application secret; the Compose value is local-development-only |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | Local PostgreSQL connection |
| `INGESTION_PRIVATE_ROOT` | Private artifact directory mounted from `artifact-data` |
| `WORKER_ID` | Identifies the worker heartbeat; defaults to `default` |

`DJANGO_ENV=production` additionally requires explicit HTTPS hosts, trusted origins, a strong secret, and `DATABASE_URL`. Those controls remain available for a future hosted target, but a hosted release is not claimed until the platform provides a persistent private filesystem shared by its web and worker processes.

## 4. Migrations

The single local web process runs migrations before starting Django. A future multi-replica deployment must run migrations once as a controlled release step rather than racing migrations from every replica.

## 5. Health signals

| Signal | Source |
|---|---|
| Web readiness | `GET /health/ready` returning 200 |
| Database availability | The response's `database` field |
| Worker freshness | The response's `worker_status` and `worker_heartbeat_age_seconds` fields |

The worker also maintains its local heartbeat file for the Docker health check.

## 6. Retention

Workspace cleanup enforces the seven-day live expiry. It removes the workspace's database rows and deletes its files from the private artifact volume. Docker volumes persist until the operator explicitly removes them; ordinary container rebuilds do not delete uploads.

The application does not create external backups. If an operator copies or backs up the Docker volumes separately, that backup has its own retention policy and must be disclosed separately.

## 7. Measured capacity

Capacity evidence remains in `specs/006-operations/evidence/OPS-T09.md`. It was measured against the repository's Docker Compose PostgreSQL on the development machine, including the recorded 10,000-row reconciliation target miss. The evidence is a local benchmark, not a cloud-capacity claim.

## 8. Current limit

The verified target is suitable for the assignment, local demonstrations, and a single-host showcase. A public host with ephemeral storage would lose uploaded files when an instance is replaced, so it is not a supported deployment target. Persistent hosted storage can be designed later if a public deployment becomes necessary.
