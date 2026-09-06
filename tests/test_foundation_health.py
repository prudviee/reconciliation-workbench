from datetime import datetime
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_readiness_reports_web_and_database(client) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ready"}


@pytest.mark.django_db(transaction=True)
def test_worker_can_emit_one_database_backed_heartbeat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = StringIO()
    heartbeat_file = tmp_path / "worker-heartbeat"
    monkeypatch.setenv("WORKER_HEARTBEAT_FILE", str(heartbeat_file))

    call_command("worker", once=True, stdout=output)

    assert output.getvalue().strip() == "worker heartbeat ready"
    heartbeat = datetime.fromisoformat(heartbeat_file.read_text(encoding="utf-8").strip())
    assert heartbeat.tzinfo is not None
