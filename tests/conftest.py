from __future__ import annotations

import pytest


@pytest.fixture
def isolated_aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep S3 adapter tests independent of host credentials and metadata."""

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
