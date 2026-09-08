from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import boto3
import pytest
from botocore.stub import ANY, Stubber

from ingestion.artifacts import (
    ArtifactIntakeError,
    IntakeLimits,
    PrivateArtifactStore,
)
from ingestion.s3_artifacts import S3ArtifactStore
from ingestion.services import ArtifactIntakeService
from reconciliation.domain import QuotaAmounts, QuotaPolicy, WorkspaceId
from workspaces.models import Workspace
from workspaces.quotas import WorkspaceQuotaService


pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("isolated_aws_credentials"),
]
NOW = datetime(2026, 9, 8, tzinfo=UTC)
CSV_BYTES = b"trade_id,amount\nTX-1,100\n"


def create_workspace() -> Workspace:
    return Workspace.objects.create(
        session_digest=uuid4().hex * 2,
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
    )


def make_store(tmp_path: Path) -> tuple[S3ArtifactStore, Stubber]:
    client = boto3.client("s3", region_name="us-east-1")
    stubber = Stubber(client)
    store = S3ArtifactStore(
        bucket="cogweb-test-bucket", cache_root=tmp_path / "cache"
    )
    store._client = client
    return store, stubber


def default_limits() -> IntakeLimits:
    return IntakeLimits(
        max_bytes=1_024, max_rows=10, max_columns=10, max_field_characters=64
    )


def test_stage_is_purely_local_and_identical_to_the_filesystem_adapter(
    tmp_path: Path,
) -> None:
    store, stubber = make_store(tmp_path)
    local = PrivateArtifactStore(tmp_path / "local")

    with stubber:
        staged = store.stage([CSV_BYTES], delimiter=",", limits=default_limits())
    local_staged = local.stage([CSV_BYTES], delimiter=",", limits=default_limits())

    assert staged.physical_hash == local_staged.physical_hash
    assert staged.byte_size == local_staged.byte_size
    assert staged.scan == local_staged.scan


def test_publish_uploads_to_the_bucket_and_caches_locally(tmp_path: Path) -> None:
    store, stubber = make_store(tmp_path)
    workspace_id = WorkspaceId(create_workspace().id)
    staged = store.stage([CSV_BYTES], delimiter=",", limits=default_limits())

    stubber.add_response(
        "put_object",
        {},
        {"Bucket": "cogweb-test-bucket", "Key": ANY, "Body": ANY},
    )
    with stubber:
        published = store.publish(staged, workspace_id=workspace_id)

    assert published.storage_key.startswith(f"workspaces/{workspace_id.value}/")
    assert published.path.exists()
    assert published.path.read_bytes() == CSV_BYTES
    stubber.assert_no_pending_responses()


def test_resolve_downloads_once_then_serves_from_cache(tmp_path: Path) -> None:
    store, stubber = make_store(tmp_path)
    workspace_id = WorkspaceId(create_workspace().id)
    staged = store.stage([CSV_BYTES], delimiter=",", limits=default_limits())
    stubber.add_response("put_object", {}, {"Bucket": ANY, "Key": ANY, "Body": ANY})
    with stubber:
        published = store.publish(staged, workspace_id=workspace_id)
    store.discard_path(published.path)
    assert not published.path.exists()

    import io

    from botocore.response import StreamingBody

    body = StreamingBody(io.BytesIO(CSV_BYTES), len(CSV_BYTES))
    stubber.add_response(
        "get_object",
        {"Body": body, "ContentLength": len(CSV_BYTES)},
        {"Bucket": "cogweb-test-bucket", "Key": published.storage_key},
    )
    with stubber:
        resolved_path = store.resolve(published.storage_key)
        assert resolved_path.read_bytes() == CSV_BYTES

    again = store.resolve(published.storage_key)
    assert again == resolved_path
    stubber.assert_no_pending_responses()


def test_delete_published_removes_the_object_and_the_local_cache(
    tmp_path: Path,
) -> None:
    store, stubber = make_store(tmp_path)
    workspace_id = WorkspaceId(create_workspace().id)
    staged = store.stage([CSV_BYTES], delimiter=",", limits=default_limits())
    stubber.add_response("put_object", {}, {"Bucket": ANY, "Key": ANY, "Body": ANY})
    with stubber:
        published = store.publish(staged, workspace_id=workspace_id)

    stubber.add_response(
        "delete_object",
        {},
        {"Bucket": "cogweb-test-bucket", "Key": published.storage_key},
    )
    with stubber:
        store.delete_published(published.storage_key)

    assert not published.path.exists()
    stubber.assert_no_pending_responses()


def test_cache_path_cannot_escape_the_cache_root(tmp_path: Path) -> None:
    store, _ = make_store(tmp_path)
    with pytest.raises(ValueError, match="outside the local cache root"):
        store.discard_path(tmp_path / "elsewhere.csv")


def test_full_ingest_round_trip_through_artifact_intake_service(
    tmp_path: Path,
) -> None:
    store, stubber = make_store(tmp_path)
    workspace = create_workspace()
    service = ArtifactIntakeService(
        store=store,
        limits=default_limits(),
        quota_service=WorkspaceQuotaService(
            QuotaPolicy(QuotaAmounts(retained_bytes=10_000, books=10, active_jobs=2))
        ),
        clock=lambda: NOW,
    )

    stubber.add_response("put_object", {}, {"Bucket": ANY, "Key": ANY, "Body": ANY})
    with stubber:
        artifact = service.ingest(
            WorkspaceId(workspace.id),
            original_filename="ledger.csv",
            content_type="text/csv",
            delimiter=",",
            chunks=[CSV_BYTES],
        )

    assert artifact.byte_size == len(CSV_BYTES)
    assert artifact.storage_key.startswith(f"workspaces/{workspace.id}/")
    workspace.refresh_from_db()
    assert workspace.retained_bytes == len(CSV_BYTES)
    stubber.assert_no_pending_responses()


def test_resolve_translates_a_client_error_into_an_intake_error(
    tmp_path: Path,
) -> None:
    store, stubber = make_store(tmp_path)
    stubber.add_client_error(
        "get_object", service_error_code="NoSuchKey", http_status_code=404
    )
    with stubber, pytest.raises(ArtifactIntakeError):
        store.resolve("workspaces/missing/aa/missing.csv")
