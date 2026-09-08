from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command

from jobs.models import WorkerHeartbeat


@pytest.mark.django_db
def test_readiness_reports_web_database_and_unknown_worker_with_no_heartbeat_yet(
    client,
) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "ready",
        "worker_status": "unknown",
        "worker_heartbeat_age_seconds": None,
    }


@pytest.mark.django_db
def test_readiness_reports_healthy_worker_for_a_fresh_heartbeat(client) -> None:
    WorkerHeartbeat.objects.create(worker_id="default", updated_at=datetime.now(UTC))

    response = client.get("/health/ready")

    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["worker_status"] == "healthy"
    assert payload["worker_heartbeat_age_seconds"] < 5


@pytest.mark.django_db
def test_readiness_distinguishes_a_stale_worker_from_a_healthy_web_and_database(
    client,
) -> None:
    stale_at = datetime.now(UTC) - timedelta(minutes=5)
    WorkerHeartbeat.objects.create(worker_id="default", updated_at=stale_at)

    response = client.get("/health/ready")

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "ready"
    assert payload["database"] == "ready"
    assert payload["worker_status"] == "stale"
    assert payload["worker_heartbeat_age_seconds"] >= 300


@pytest.mark.django_db(transaction=True)
def test_worker_can_emit_one_database_backed_heartbeat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = StringIO()
    heartbeat_file = tmp_path / "worker-heartbeat"
    monkeypatch.setenv("WORKER_HEARTBEAT_FILE", str(heartbeat_file))

    call_command("worker", once=True, worker_id="default", stdout=output)

    assert output.getvalue().strip() == "worker heartbeat ready"
    heartbeat = datetime.fromisoformat(heartbeat_file.read_text(encoding="utf-8").strip())
    assert heartbeat.tzinfo is not None
    db_heartbeat = WorkerHeartbeat.objects.get(worker_id="default")
    assert db_heartbeat.updated_at.tzinfo is not None
