from io import StringIO

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_readiness_reports_web_and_database(client) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ready"}


@pytest.mark.django_db(transaction=True)
def test_worker_can_emit_one_database_backed_heartbeat() -> None:
    output = StringIO()

    call_command("worker", once=True, stdout=output)

    assert output.getvalue().strip() == "worker heartbeat ready"
