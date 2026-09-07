"""Measure the supported ingestion capacity on a named local environment."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import timedelta
import gc
import json
import os
from pathlib import Path
import platform
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
import tracemalloc


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.db import connection, transaction  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402
from django.utils import timezone  # noqa: E402

from books.models import BookKind, ReconciliationBook  # noqa: E402
from ingestion.activation import FullSnapshotActivationService  # noqa: E402
from ingestion.artifacts import IntakeLimits, PrivateArtifactStore  # noqa: E402
from ingestion.models import DatasetMembership  # noqa: E402
from ingestion.preview import PreviewService  # noqa: E402
from ingestion.services import ArtifactIntakeService  # noqa: E402
from ingestion.workflow import SourcePreparationService  # noqa: E402
from reconciliation.domain import (  # noqa: E402
    BookId,
    DatasetMode,
    IngestionOperation,
    WorkspaceId,
)
from sources.adapters import ledger_contract  # noqa: E402
from sources.models import SourceRole  # noqa: E402
from workspaces.models import Workspace  # noqa: E402


LIMITS = IntakeLimits(25 * 1024 * 1024, 10_000, 100, 4_096)
HEADER = "trade_id,traded_at,instrument,side,quantity,price,gross_amount,state\n"
DELTA_HEADER = HEADER.rstrip("\n") + ",operation\n"


def full_row(number: int, *, gross: str = "100", state: str = "SETTLED") -> str:
    return (
        f"T-{number:06d},2026-09-01T09:15:00Z,BTC-USD,BUY,1,100,"
        f"{gross},{state}\n"
    )


def delta_row(number: int, operation: str) -> str:
    if operation == "RETRACT":
        return f"T-{number:06d},,,,,,,,RETRACT\n"
    state = "CANCELLED" if operation == "CANCEL" else "SETTLED"
    return full_row(number, gross="101", state=state).rstrip("\n") + f",{operation}\n"


def measure(callable_):
    gc.collect()
    tracemalloc.start()
    started = perf_counter()
    with CaptureQueriesContext(connection) as queries:
        result = callable_()
    elapsed = perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, {
        "seconds": round(elapsed, 3),
        "peak_mib": round(peak / (1024 * 1024), 2),
        "queries": len(queries),
    }


def run() -> dict[str, object]:
    with TemporaryDirectory(prefix="reconciliation-ingestion-") as root_value:
        root = Path(root_value)
        store = PrivateArtifactStore(root)
        now = timezone.now()
        with transaction.atomic():
            workspace = Workspace.objects.create(
                session_digest="capacity-" + os.urandom(27).hex(),
                created_at=now,
                expires_at=now + timedelta(days=7),
            )
            workspace_id = WorkspaceId(workspace.id)
            book = ReconciliationBook.objects.create(
                workspace=workspace,
                name="Ingestion capacity measurement",
                kind=BookKind.USER,
                created_at=now,
            )
            prepared = SourcePreparationService(workspace_id).prepare(
                book_id=BookId(book.id),
                role=SourceRole.LEFT,
                contract=ledger_contract(),
            )
            full_payload = (
                HEADER + "".join(full_row(number) for number in range(1, 10_001))
            ).encode()
            artifact = ArtifactIntakeService(store=store, limits=LIMITS).ingest(
                workspace_id,
                original_filename="capacity-full.csv",
                content_type="text/csv",
                delimiter=",",
                chunks=(full_payload,),
            )
            preview_service = PreviewService(store, LIMITS)
            padding = "x" * 2_400
            near_limit_payload = (
                HEADER.rstrip("\n")
                + ",padding\n"
                + "".join(
                    full_row(number).rstrip("\n") + f",{padding}\n"
                    for number in range(1, 10_001)
                )
            ).encode()
            near_limit_artifact = ArtifactIntakeService(
                store=store,
                limits=LIMITS,
            ).ingest(
                workspace_id,
                original_filename="capacity-near-limit.csv",
                content_type="text/csv",
                delimiter=",",
                chunks=(near_limit_payload,),
            )
            near_limit_attempt, near_limit_metrics = measure(
                lambda: preview_service.preview(
                    workspace_id,
                    artifact_id=near_limit_artifact.id,
                    dataset_id=prepared.dataset.id,
                    contract_revision_id=prepared.contract_revision.id,
                    delimiter=",",
                )
            )
            full_attempt, preview_metrics = measure(
                lambda: preview_service.preview(
                    workspace_id,
                    artifact_id=artifact.id,
                    dataset_id=prepared.dataset.id,
                    contract_revision_id=prepared.contract_revision.id,
                    delimiter=",",
                )
            )
            full_revision, activation_metrics = measure(
                lambda: FullSnapshotActivationService().activate(
                    workspace_id,
                    attempt_id=full_attempt.id,
                )
            )

            delta_contract = replace(
                ledger_contract(),
                mode=DatasetMode.DELTA,
                operation_field="operation",
                operation_mapping=(
                    ("UPSERT", IngestionOperation.UPSERT),
                    ("CANCEL", IngestionOperation.CANCEL),
                    ("RETRACT", IngestionOperation.RETRACT),
                ),
            )
            delta_prepared = SourcePreparationService(workspace_id).prepare(
                book_id=BookId(book.id),
                role=SourceRole.LEFT,
                contract=delta_contract,
            )
            delta_payload = (
                DELTA_HEADER
                + "".join(delta_row(number, "UPSERT") for number in range(1, 801))
                + "".join(delta_row(number, "CANCEL") for number in range(801, 901))
                + "".join(delta_row(number, "RETRACT") for number in range(901, 1001))
            ).encode()
            delta_artifact = ArtifactIntakeService(store=store, limits=LIMITS).ingest(
                workspace_id,
                original_filename="capacity-delta.csv",
                content_type="text/csv",
                delimiter=",",
                chunks=(delta_payload,),
            )
            delta_attempt = preview_service.preview(
                workspace_id,
                artifact_id=delta_artifact.id,
                dataset_id=delta_prepared.dataset.id,
                contract_revision_id=delta_prepared.contract_revision.id,
                delimiter=",",
            )
            delta_revision, delta_metrics = measure(
                lambda: FullSnapshotActivationService().activate(
                    workspace_id,
                    attempt_id=delta_attempt.id,
                )
            )
            membership_count = DatasetMembership.objects.filter(
                dataset_revision=delta_revision
            ).count()
            result = {
                "environment": {
                    "python": platform.python_version(),
                    "django": django.get_version(),
                    "platform": platform.platform(),
                    "database": connection.vendor,
                },
                "workloads": {
                    "full_snapshot_rows": 10_000,
                    "full_snapshot_bytes": len(full_payload),
                    "near_limit_preview_bytes": len(near_limit_payload),
                    "delta_operations": 1_000,
                    "delta_base_members": 10_000,
                    "delta_result_members": membership_count,
                },
                "measurements": {
                    "full_preview": preview_metrics,
                    "near_limit_preview": near_limit_metrics,
                    "full_activation": activation_metrics,
                    "delta_activation": delta_metrics,
                },
                "invariants": {
                    "full_ready": full_attempt.state == "READY",
                    "near_limit_ready": near_limit_attempt.state == "READY",
                    "full_members": full_revision.memberships.count(),
                    "delta_ready": delta_attempt.state == "READY",
                    "delta_members": membership_count,
                },
            }
            transaction.set_rollback(True)
        return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = run()
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
