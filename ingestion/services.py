"""Transactional artifact intake with quota and filesystem compensation."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from reconciliation.domain import QuotaAmounts, WorkspaceId
from workspaces.quotas import WorkspaceQuotaService
from workspaces.repositories import WorkspaceRepository

from .artifacts import IntakeLimits, PrivateArtifactStore, StorageAdapter
from .models import FileArtifact
from .repositories import WorkspaceIngestionRepository


def configured_intake_limits() -> IntakeLimits:
    return IntakeLimits(
        max_bytes=settings.INGESTION_MAX_BYTES,
        max_rows=settings.INGESTION_MAX_ROWS,
        max_columns=settings.INGESTION_MAX_COLUMNS,
        max_field_characters=settings.INGESTION_MAX_FIELD_CHARACTERS,
    )


def configured_artifact_store() -> StorageAdapter:
    if settings.INGESTION_STORAGE_BACKEND == "s3":
        from .s3_artifacts import S3ArtifactStore

        return S3ArtifactStore(
            bucket=settings.INGESTION_S3_BUCKET,
            cache_root=Path(settings.INGESTION_S3_CACHE_ROOT),
            region_name=settings.INGESTION_S3_REGION,
            endpoint_url=settings.INGESTION_S3_ENDPOINT_URL,
        )
    return PrivateArtifactStore(Path(settings.INGESTION_PRIVATE_ROOT))


@dataclass(slots=True)
class ArtifactIntakeService:
    store: StorageAdapter = field(default_factory=configured_artifact_store)
    limits: IntakeLimits = field(default_factory=configured_intake_limits)
    quota_service: WorkspaceQuotaService = field(default_factory=WorkspaceQuotaService)
    clock: Callable[[], datetime] = timezone.now

    def ingest(
        self,
        workspace_id: WorkspaceId,
        *,
        original_filename: str,
        content_type: str,
        delimiter: str,
        chunks: Iterable[bytes],
    ) -> FileArtifact:
        workspace = WorkspaceRepository().get(workspace_id)
        self.quota_service.lifecycle_service.require_active(
            workspace,
            now=self.clock(),
        )
        staged = self.store.stage(chunks, delimiter=delimiter, limits=self.limits)
        published_path: Path | None = None
        try:
            with transaction.atomic():
                self.quota_service.reserve(
                    workspace_id,
                    QuotaAmounts(retained_bytes=staged.byte_size),
                )
                published = self.store.publish(staged, workspace_id=workspace_id)
                published_path = published.path
                return WorkspaceIngestionRepository(workspace_id).create_artifact(
                    storage_key=published.storage_key,
                    physical_hash=staged.physical_hash,
                    original_filename=safe_upload_filename(original_filename),
                    content_type=safe_content_type(content_type),
                    byte_size=staged.byte_size,
                    created_at=self.clock(),
                )
        except Exception:
            self.store.discard_path(published_path or staged.path)
            raise


def safe_upload_filename(value: str) -> str:
    basename = value.replace("\\", "/").rsplit("/", 1)[-1].strip()
    safe = "".join(character if character.isprintable() else "_" for character in basename)
    return (safe or "upload.csv")[:255]


def safe_content_type(value: str) -> str:
    normalized = value.strip().lower()
    supported = {
        "application/csv",
        "application/vnd.ms-excel",
        "text/csv",
        "text/plain",
    }
    if normalized in supported:
        return normalized
    return "application/octet-stream"
