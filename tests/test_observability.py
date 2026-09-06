from __future__ import annotations

import json
import logging
from io import StringIO

import pytest
from django.test import Client

from observability.logging import PrivacySafeJsonFormatter, safe_event


pytestmark = pytest.mark.django_db


def request_events(caplog: pytest.LogCaptureFixture) -> list[dict[str, object]]:
    return [
        record.structured_event
        for record in caplog.records
        if record.name == "reconciliation.requests"
        and hasattr(record, "structured_event")
    ]


def test_success_log_has_correlation_and_omits_request_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_session_marker = "SESSION-SENTINEL-DO-NOT-LOG"
    financial_marker = "9876543.21-TRANSACTION-SENTINEL"
    client = Client()
    client.cookies["untrusted_cookie"] = private_session_marker
    caplog.set_level(logging.INFO, logger="reconciliation.requests")

    response = client.get(
        f"/?amount={financial_marker}",
        HTTP_X_CORRELATION_ID="review-flow-42",
    )

    events = request_events(caplog)
    serialized = json.dumps(events)
    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "review-flow-42"
    assert len(events) == 1
    assert events[0]["correlation_id"] == "review-flow-42"
    assert events[0]["route"] == "foundation:home"
    assert events[0]["workspace_ref"] is not None
    assert private_session_marker not in serialized
    assert financial_marker not in serialized


def test_failed_request_log_omits_body_cookie_and_session_secret(
    caplog: pytest.LogCaptureFixture,
) -> None:
    body_marker = "4111111111111111-RAW-FINANCIAL-SENTINEL"
    cookie_marker = "COOKIE-SECRET-SENTINEL"
    client = Client(enforce_csrf_checks=True)
    client.cookies["private_marker"] = cookie_marker
    client.get("/")
    session_key = client.session.session_key
    assert session_key is not None
    caplog.clear()
    caplog.set_level(logging.INFO, logger="reconciliation.requests")

    response = client.post("/books/demo", {"raw_amount": body_marker})

    events = request_events(caplog)
    serialized = json.dumps(events)
    assert response.status_code == 403
    assert len(events) == 1
    assert events[0]["status"] == 403
    assert events[0]["failure_category"] == "client_error"
    assert events[0]["correlation_id"] == response.headers["X-Correlation-ID"]
    for secret in (body_marker, cookie_marker, session_key):
        assert secret not in serialized
        assert all(secret not in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize(
    "untrusted_id",
    ["", "contains spaces", "line-break\r\ninjection", "x" * 65],
)
def test_invalid_inbound_correlation_id_is_replaced(
    caplog: pytest.LogCaptureFixture, untrusted_id: str
) -> None:
    caplog.set_level(logging.INFO, logger="reconciliation.requests")

    response = Client().get("/health/ready", HTTP_X_CORRELATION_ID=untrusted_id)

    returned = response.headers["X-Correlation-ID"]
    assert len(returned) == 32
    assert returned != untrusted_id
    assert request_events(caplog)[0]["correlation_id"] == returned


def test_event_allowlist_drops_unknown_and_non_scalar_values() -> None:
    event = safe_event(
        {
            "event": "quota_refused",
            "correlation_id": "abc",
            "route": "foundation:book-demo-create",
            "method": "POST",
            "status": 409,
            "duration_ms": 1.2,
            "workspace_ref": "safe-reference",
            "failure_category": "client_error",
            "password": "must-not-survive",
        }
    )

    assert "password" not in event
    assert set(event) == {
        "event",
        "correlation_id",
        "route",
        "method",
        "status",
        "duration_ms",
        "workspace_ref",
        "failure_category",
    }


def test_json_formatter_emits_only_fixed_schema() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(PrivacySafeJsonFormatter())
    isolated_logger = logging.getLogger("test.privacy-safe-formatter")
    isolated_logger.handlers = [handler]
    isolated_logger.propagate = False
    isolated_logger.setLevel(logging.INFO)

    isolated_logger.info(
        "ignored message with PRIVATE-SENTINEL",
        extra={
            "structured_event": safe_event(
                {
                    "event": "http_request_completed",
                    "correlation_id": "abc",
                    "status": 200,
                    "untrusted": "PRIVATE-SENTINEL",
                }
            )
        },
    )
    output = json.loads(stream.getvalue())

    assert output["event"] == "http_request_completed"
    assert output["correlation_id"] == "abc"
    assert output["status"] == 200
    assert "PRIVATE-SENTINEL" not in stream.getvalue()
