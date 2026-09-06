from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.conf import settings
from django.test import Client, override_settings

from ingestion.artifacts import IntakeLimits, PrivateArtifactStore
from ingestion.services import ArtifactIntakeService
from reconciliation.domain import WorkspaceId
from workspaces.lifecycle import WorkspaceLifecycleService
from workspaces.models import Workspace
from workspaces.sessions import digest_session_key


pytestmark = pytest.mark.django_db
PAYLOAD = b"id,amount\nT-1,100\n"


def workspace_for(client: Client) -> Workspace:
    session_key = client.session.session_key
    assert session_key is not None
    return Workspace.objects.get(session_digest=digest_session_key(session_key))


def create_artifact(client: Client, root, *, filename: str = "ledger.csv"):
    client.get("/")
    workspace = workspace_for(client)
    artifact = ArtifactIntakeService(
        store=PrivateArtifactStore(root),
        limits=IntakeLimits(1_024, 10, 10, 100),
    ).ingest(
        WorkspaceId(workspace.id),
        original_filename=filename,
        content_type="text/csv",
        delimiter=",",
        chunks=(PAYLOAD,),
    )
    return workspace, artifact


@override_settings(DEBUG=False)
def test_owner_downloads_original_private_bytes_with_safe_headers(
    tmp_path,
) -> None:
    with override_settings(INGESTION_PRIVATE_ROOT=tmp_path):
        client = Client()
        _, artifact = create_artifact(
            client,
            tmp_path,
            filename='..\\private\r\nledger".csv',
        )

        response = client.get(f"/artifacts/{artifact.id}/download")

        assert response.status_code == 200
        assert b"".join(response.streaming_content) == PAYLOAD
        assert response.headers["Cache-Control"] == "private, no-store"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        disposition = response.headers["Content-Disposition"]
        assert "attachment" in disposition
        assert "private__ledger" in disposition
        assert "\r" not in disposition and "\n" not in disposition


@override_settings(DEBUG=False)
def test_foreign_random_and_missing_file_downloads_share_not_found_response(
    tmp_path,
) -> None:
    with override_settings(INGESTION_PRIVATE_ROOT=tmp_path):
        owner = Client()
        _, artifact = create_artifact(owner, tmp_path)
        outsider = Client()
        outsider.get("/")

        foreign = outsider.get(f"/artifacts/{artifact.id}/download")
        random = outsider.get(f"/artifacts/{uuid4()}/download")
        PrivateArtifactStore(tmp_path).resolve(artifact.storage_key).unlink()
        missing_file = owner.get(f"/artifacts/{artifact.id}/download")

        assert foreign.status_code == random.status_code == missing_file.status_code == 404
        assert foreign.content == random.content == missing_file.content
        assert artifact.original_filename.encode() not in foreign.content


@override_settings(DEBUG=False)
@pytest.mark.parametrize("lifecycle", ["expired", "deleted"])
def test_revoked_workspace_cannot_download_retained_bytes(
    tmp_path,
    lifecycle: str,
) -> None:
    with override_settings(INGESTION_PRIVATE_ROOT=tmp_path):
        client = Client()
        workspace, artifact = create_artifact(client, tmp_path)
        if lifecycle == "expired":
            expired_at = datetime.now(tz=UTC) - timedelta(seconds=1)
            Workspace.objects.filter(id=workspace.id).update(
                created_at=expired_at - timedelta(days=7),
                expires_at=expired_at,
            )
        else:
            WorkspaceLifecycleService().delete(
                WorkspaceId(workspace.id), now=datetime.now(tz=UTC)
            )

        response = client.get(f"/artifacts/{artifact.id}/download")

        assert response.status_code == 302
        assert response.headers["Location"] == "/workspace/unavailable"


@override_settings(DEBUG=False)
def test_download_logging_contains_no_filename_or_artifact_bytes(
    tmp_path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    marker = "PRIVATE-FILENAME-MARKER.csv"
    with override_settings(INGESTION_PRIVATE_ROOT=tmp_path):
        client = Client()
        _, artifact = create_artifact(client, tmp_path, filename=marker)
        caplog.set_level(logging.INFO, logger="reconciliation.requests")

        response = client.get(f"/artifacts/{artifact.id}/download")
        assert response.status_code == 200
        response.close()

    captured = caplog.text
    assert marker not in captured
    assert PAYLOAD.decode().strip() not in captured
    assert str(artifact.id) not in captured
