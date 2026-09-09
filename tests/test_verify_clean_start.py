from __future__ import annotations

import io
import json

import pytest

from scripts import verify_clean_start


class ReadinessResponse(io.BytesIO):
    status = 200


def response_for(payload: dict[str, object]) -> ReadinessResponse:
    return ReadinessResponse(json.dumps(payload).encode("utf-8"))


def test_clean_start_readiness_accepts_current_worker_health_shape(monkeypatch) -> None:
    payload = {
        "status": "ready",
        "database": "ready",
        "worker_status": "healthy",
        "worker_heartbeat_age_seconds": 1.25,
    }
    monkeypatch.setattr(
        verify_clean_start,
        "urlopen",
        lambda *_args, **_kwargs: response_for(payload),
    )

    assert verify_clean_start.readiness() == payload


def test_clean_start_readiness_rejects_a_stale_worker(monkeypatch) -> None:
    monkeypatch.setattr(
        verify_clean_start,
        "urlopen",
        lambda *_args, **_kwargs: response_for(
            {
                "status": "ready",
                "database": "ready",
                "worker_status": "stale",
                "worker_heartbeat_age_seconds": 45.0,
            }
        ),
    )

    with pytest.raises(verify_clean_start.VerificationFailure):
        verify_clean_start.readiness()
