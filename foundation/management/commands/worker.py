from __future__ import annotations

import os
import time
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import close_old_connections, connection
from django.utils import timezone

from ingestion.preview import execute_claimed_import
from jobs.models import WorkerHeartbeat
from jobs.services import claim_and_execute
from reconciliation.domain import JobKind, RetryPolicy, WorkspaceId
from reconciliation.services import execute_claimed_run
from workspaces.cleanup import execute_claimed_cleanup
from workspaces.guards import WorkspaceBoundaryGuard
from workspaces.repositories import WorkspaceUnavailable


_JOB_CONFIG = (
    (
        JobKind.RECONCILIATION_RUN,
        execute_claimed_run,
        "JOBS_RUN_LEASE_SECONDS",
        "JOBS_RUN_MAX_ATTEMPTS",
        "JOBS_RUN_BACKOFF_SECONDS",
    ),
    (
        JobKind.IMPORT_VALIDATION,
        execute_claimed_import,
        "JOBS_IMPORT_LEASE_SECONDS",
        "JOBS_IMPORT_MAX_ATTEMPTS",
        "JOBS_IMPORT_BACKOFF_SECONDS",
    ),
    (
        JobKind.WORKSPACE_CLEANUP,
        execute_claimed_cleanup,
        "JOBS_CLEANUP_LEASE_SECONDS",
        "JOBS_CLEANUP_MAX_ATTEMPTS",
        "JOBS_CLEANUP_BACKOFF_SECONDS",
    ),
)


class Command(BaseCommand):
    help = "Poll for and execute leased background work across every job kind."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=float, default=5.0)
        parser.add_argument("--workspace-id")
        parser.add_argument("--worker-id", default=os.getenv("WORKER_ID", "default"))

    def handle(self, *args, **options) -> None:
        interval = options["interval"]
        if interval <= 0:
            raise ValueError("--interval must be greater than zero")

        workspace_id = options["workspace_id"]
        if workspace_id:
            try:
                WorkspaceBoundaryGuard().require_active(
                    WorkspaceId.parse(workspace_id),
                    now=timezone.now(),
                )
            except (ValueError, WorkspaceUnavailable) as error:
                raise CommandError("workspace unavailable") from error

        while True:
            close_old_connections()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()

            self._claim_and_run(options["worker_id"])

            now = timezone.now()
            WorkerHeartbeat.objects.update_or_create(
                worker_id=options["worker_id"], defaults={"updated_at": now}
            )
            heartbeat_path = os.getenv("WORKER_HEARTBEAT_FILE")
            if heartbeat_path:
                Path(heartbeat_path).write_text(
                    now.isoformat() + "\n",
                    encoding="utf-8",
                )
            self.stdout.write("worker heartbeat ready")

            if options["once"]:
                return
            time.sleep(interval)

    def _claim_and_run(self, worker_id: str) -> None:
        now = timezone.now()
        for kind, executor, lease_setting, attempts_setting, backoff_setting in _JOB_CONFIG:
            records = claim_and_execute(
                kind,
                now=now,
                lease_duration=timedelta(seconds=getattr(settings, lease_setting)),
                retry_policy=RetryPolicy(
                    max_attempts=getattr(settings, attempts_setting),
                    backoff=timedelta(seconds=getattr(settings, backoff_setting)),
                ),
                executor=executor,
                batch_size=settings.JOBS_WORKER_BATCH_SIZE,
            )
            if records:
                self.stdout.write(
                    f"{kind}: claimed {len(records)}, "
                    f"succeeded {sum(1 for r in records if r.succeeded)}"
                )
