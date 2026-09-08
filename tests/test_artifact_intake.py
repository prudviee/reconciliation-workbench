from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from ingestion.artifacts import (
    ArtifactFailureCode,
    ArtifactIntakeError,
    IntakeLimits,
    PrivateArtifactStore,
)
from ingestion.models import FileArtifact
from ingestion.repositories import WorkspaceIngestionRepository
from ingestion.services import (
    ArtifactIntakeService,
    configured_artifact_store,
    configured_intake_limits,
    safe_content_type,
    safe_upload_filename,
)
from reconciliation.domain import (
    QuotaAmounts,
    QuotaExceeded,
    QuotaPolicy,
    WorkspaceId,
)
from workspaces.lifecycle import WorkspaceLifecycleService
from workspaces.models import Workspace
from workspaces.quotas import WorkspaceQuotaService
from workspaces.repositories import WorkspaceUnavailable


pytestmark = pytest.mark.django_db
NOW = datetime(2026, 9, 6, 10, tzinfo=UTC)


def create_workspace() -> Workspace:
    return Workspace.objects.create(
        session_digest=uuid4().hex * 2,
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
    )


def limits(
    *,
    max_bytes: int = 1_024,
    max_rows: int = 10,
    max_columns: int = 10,
    max_field_characters: int = 64,
) -> IntakeLimits:
    return IntakeLimits(
        max_bytes=max_bytes,
        max_rows=max_rows,
        max_columns=max_columns,
        max_field_characters=max_field_characters,
    )


def service(
    root: Path,
    *,
    intake_limits: IntakeLimits | None = None,
    byte_quota: int = 10_000,
) -> ArtifactIntakeService:
    return ArtifactIntakeService(
        store=PrivateArtifactStore(root),
        limits=intake_limits or limits(),
        quota_service=WorkspaceQuotaService(
            QuotaPolicy(
                QuotaAmounts(
                    retained_bytes=byte_quota,
                    books=10,
                    active_jobs=2,
                )
            )
        ),
        clock=lambda: NOW,
    )


def retained_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file()]


def test_configured_limits_match_the_ingestion_specification() -> None:
    assert configured_intake_limits() == IntakeLimits(
        max_bytes=25 * 1024 * 1024,
        max_rows=10_000,
        max_columns=100,
        max_field_characters=4_096,
    )


def test_configured_artifact_store_defaults_to_local(settings) -> None:
    settings.INGESTION_STORAGE_BACKEND = "local"

    assert isinstance(configured_artifact_store(), PrivateArtifactStore)


def test_configured_artifact_store_selects_s3_when_configured(
    settings,
    tmp_path: Path,
    isolated_aws_credentials,
) -> None:
    from ingestion.s3_artifacts import S3ArtifactStore

    settings.INGESTION_STORAGE_BACKEND = "s3"
    settings.INGESTION_S3_BUCKET = "cogweb-reconciliation-artifacts"
    settings.INGESTION_S3_REGION = "auto"
    settings.INGESTION_S3_ENDPOINT_URL = "https://example-r2-endpoint.example.com"
    settings.INGESTION_S3_CACHE_ROOT = tmp_path

    store = configured_artifact_store()

    assert isinstance(store, S3ArtifactStore)
    assert store.bucket == "cogweb-reconciliation-artifacts"
    assert store.cache_root == tmp_path.resolve()


def test_storage_keys_cannot_escape_the_private_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes"):
        PrivateArtifactStore(tmp_path).resolve("../../public/ledger.csv")


@pytest.mark.parametrize(
    ("delimiter", "payload"),
    [
        (",", b"id,name\n1,Ada\n"),
        (";", b"id;name\n1;Ada\n"),
        ("\t", b"id\tname\n1\tAda\n"),
    ],
)
def test_ingest_streams_supported_csv_to_generated_private_key(
    tmp_path: Path,
    delimiter: str,
    payload: bytes,
) -> None:
    workspace = create_workspace()
    intake = service(tmp_path)

    artifact = intake.ingest(
        WorkspaceId(workspace.id),
        original_filename="ledger.csv",
        content_type="text/csv",
        delimiter=delimiter,
        chunks=(payload[:3], payload[3:8], payload[8:]),
    )

    stored = intake.store.resolve(artifact.storage_key)
    workspace.refresh_from_db()
    assert stored.read_bytes() == payload
    assert artifact.physical_hash == hashlib.sha256(payload).hexdigest()
    assert artifact.byte_size == len(payload)
    assert artifact.storage_key.startswith(f"workspaces/{workspace.id}/")
    assert "ledger.csv" not in artifact.storage_key
    assert workspace.retained_bytes == len(payload)
    assert not retained_files(tmp_path / ".quarantine")


def test_utf8_bom_is_accepted_without_changing_retained_bytes(tmp_path: Path) -> None:
    workspace = create_workspace()
    payload = b"\xef\xbb\xbfid,name\n1,Ada\n"

    artifact = service(tmp_path).ingest(
        WorkspaceId(workspace.id),
        original_filename="bom.csv",
        content_type="text/csv",
        delimiter=",",
        chunks=(payload,),
    )

    assert artifact.byte_size == len(payload)
    assert PrivateArtifactStore(tmp_path).resolve(artifact.storage_key).read_bytes() == payload


def test_scan_preserves_selected_delimiter_header_and_row_count(tmp_path: Path) -> None:
    store = PrivateArtifactStore(tmp_path)

    staged = store.stage(
        (b"id;name\n1;Ada\n2;Lin\n",),
        delimiter=";",
        limits=limits(),
    )

    assert staged.scan.delimiter == ";"
    assert staged.scan.header == ("id", "name")
    assert staged.scan.row_count == 2
    assert staged.scan.maximum_column_count == 2
    store.discard_path(staged.path)


@pytest.mark.parametrize(
    ("payload", "intake_limits", "code"),
    [
        (b"a\n12\n", limits(max_bytes=4), ArtifactFailureCode.BYTE_LIMIT),
        (b"a\n1\n2\n", limits(max_rows=1), ArtifactFailureCode.ROW_LIMIT),
        (b"a,b,c\n1,2,3\n", limits(max_columns=2), ArtifactFailureCode.COLUMN_LIMIT),
        (b"a\n12345\n", limits(max_field_characters=4), ArtifactFailureCode.FIELD_LIMIT),
    ],
)
def test_each_hard_limit_rejects_one_over_without_retaining_evidence(
    tmp_path: Path,
    payload: bytes,
    intake_limits: IntakeLimits,
    code: ArtifactFailureCode,
) -> None:
    workspace = create_workspace()

    with pytest.raises(ArtifactIntakeError) as captured:
        service(tmp_path, intake_limits=intake_limits).ingest(
            WorkspaceId(workspace.id),
            original_filename="limit.csv",
            content_type="text/csv",
            delimiter=",",
            chunks=(payload,),
        )

    workspace.refresh_from_db()
    assert captured.value.code is code
    assert workspace.retained_bytes == 0
    assert not FileArtifact.objects.exists()
    assert retained_files(tmp_path) == []


@pytest.mark.parametrize(
    ("payload", "intake_limits"),
    [
        (b"a\n1\n", limits(max_bytes=4)),
        (b"a\n1\n", limits(max_rows=1)),
        (b"a,b\n1,2\n", limits(max_columns=2)),
        (b"a\n1234\n", limits(max_field_characters=4)),
    ],
)
def test_each_hard_limit_accepts_its_exact_boundary(
    tmp_path: Path,
    payload: bytes,
    intake_limits: IntakeLimits,
) -> None:
    workspace = create_workspace()

    artifact = service(tmp_path, intake_limits=intake_limits).ingest(
        WorkspaceId(workspace.id),
        original_filename="boundary.csv",
        content_type="text/csv",
        delimiter=",",
        chunks=(payload,),
    )

    assert artifact.byte_size == len(payload)


@pytest.mark.parametrize(
    ("payload", "delimiter", "code"),
    [
        (b"a\n\xff\n", ",", ArtifactFailureCode.INVALID_ENCODING),
        (b'a\n"unterminated', ",", ArtifactFailureCode.MALFORMED_CSV),
        (b"a|b\n1|2\n", "|", ArtifactFailureCode.UNSUPPORTED_DELIMITER),
        (b"", ",", ArtifactFailureCode.EMPTY_FILE),
    ],
)
def test_invalid_csv_inputs_are_typed_and_leave_no_file(
    tmp_path: Path,
    payload: bytes,
    delimiter: str,
    code: ArtifactFailureCode,
) -> None:
    workspace = create_workspace()

    with pytest.raises(ArtifactIntakeError) as captured:
        service(tmp_path).ingest(
            WorkspaceId(workspace.id),
            original_filename="invalid.csv",
            content_type="text/csv",
            delimiter=delimiter,
            chunks=(payload,),
        )

    assert captured.value.code is code
    assert retained_files(tmp_path) == []


def test_untrusted_metadata_never_controls_storage_path(tmp_path: Path) -> None:
    workspace = create_workspace()

    artifact = service(tmp_path).ingest(
        WorkspaceId(workspace.id),
        original_filename="..\\..\\secret\r\n.csv",
        content_type="text/csv\r\nX-Injected: yes",
        delimiter=",",
        chunks=(b"id\n1\n",),
    )

    assert artifact.original_filename == "secret__.csv"
    assert artifact.content_type == "application/octet-stream"
    assert "secret" not in artifact.storage_key
    assert service(tmp_path).store.resolve(artifact.storage_key).is_relative_to(
        tmp_path.resolve()
    )


def test_quota_refusal_removes_quarantine_and_rolls_back_database(tmp_path: Path) -> None:
    workspace = create_workspace()

    with pytest.raises(QuotaExceeded):
        service(tmp_path, byte_quota=3).ingest(
            WorkspaceId(workspace.id),
            original_filename="too-large-for-workspace.csv",
            content_type="text/csv",
            delimiter=",",
            chunks=(b"id\n1\n",),
        )

    workspace.refresh_from_db()
    assert workspace.retained_bytes == 0
    assert not FileArtifact.objects.exists()
    assert retained_files(tmp_path) == []


def test_database_failure_compensates_published_file_and_quota(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = create_workspace()

    def fail_create(*args, **kwargs):
        raise RuntimeError("injected persistence failure")

    monkeypatch.setattr(
        WorkspaceIngestionRepository,
        "create_artifact",
        fail_create,
    )
    with pytest.raises(RuntimeError, match="injected persistence failure"):
        service(tmp_path).ingest(
            WorkspaceId(workspace.id),
            original_filename="rollback.csv",
            content_type="text/csv",
            delimiter=",",
            chunks=(b"id\n1\n",),
        )

    workspace.refresh_from_db()
    assert workspace.retained_bytes == 0
    assert not FileArtifact.objects.exists()
    assert retained_files(tmp_path) == []


def test_revoked_workspace_cannot_retain_staged_bytes(tmp_path: Path) -> None:
    workspace = create_workspace()
    WorkspaceLifecycleService().delete(WorkspaceId(workspace.id), now=NOW)

    with pytest.raises(WorkspaceUnavailable):
        service(tmp_path).ingest(
            WorkspaceId(workspace.id),
            original_filename="revoked.csv",
            content_type="text/csv",
            delimiter=",",
            chunks=(b"id\n1\n",),
        )

    assert not FileArtifact.objects.exists()
    assert retained_files(tmp_path) == []


def test_metadata_sanitizers_have_deterministic_fallbacks() -> None:
    assert safe_upload_filename("../../") == "upload.csv"
    assert safe_content_type("\r\n") == "application/octet-stream"


def test_compose_gives_web_and_worker_the_same_private_artifact_volume() -> None:
    compose = Path("compose.yaml").read_text(encoding="utf-8")

    assert compose.count("artifact-data:/var/lib/reconciliation/artifacts") == 2
    assert "INGESTION_PRIVATE_ROOT: /var/lib/reconciliation/artifacts" in compose
