"""S3-compatible object-storage implementation of `StorageAdapter`.

Staging and CSV scanning stay local (Python's csv module needs a real,
seekable file); only publish/resolve/discard reach the network. A local
cache directory holds both the pre-publish quarantine copy and, after
publish, a readable copy of every object this process has resolved, so
`resolve()` avoids a redundant download when the same artifact is read
again within one process lifetime.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError

from reconciliation.domain import WorkspaceId

from .artifacts import (
    ArtifactFailureCode,
    ArtifactIntakeError,
    IntakeLimits,
    PublishedArtifact,
    PrivateArtifactStore,
    StagedArtifact,
)


class S3ArtifactStore:
    def __init__(
        self,
        *,
        bucket: str,
        cache_root: Path,
        region_name: str | None = None,
        endpoint_url: str | None = None,
    ) -> None:
        self.bucket = bucket
        self.cache_root = cache_root.resolve()
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self._client = boto3.client(
            "s3", region_name=region_name, endpoint_url=endpoint_url
        )
        self._local = PrivateArtifactStore(self.cache_root)

    def stage(
        self, chunks, *, delimiter: str, limits: IntakeLimits
    ) -> StagedArtifact:
        return self._local.stage(chunks, delimiter=delimiter, limits=limits)

    def publish(
        self, staged: StagedArtifact, *, workspace_id: WorkspaceId
    ) -> PublishedArtifact:
        token = uuid4().hex
        storage_key = f"workspaces/{workspace_id.value}/{token[:2]}/{token}.csv"
        with staged.path.open("rb") as stream:
            self._client.put_object(Bucket=self.bucket, Key=storage_key, Body=stream)
        cached = self._cache_path(storage_key)
        cached.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged.path, cached)
        return PublishedArtifact(storage_key, cached)

    def discard_path(self, path: Path) -> None:
        resolved = path.resolve()
        if not resolved.is_relative_to(self.cache_root):
            raise ValueError("artifact path is outside the local cache root")
        resolved.unlink(missing_ok=True)

    def resolve(self, storage_key: str) -> Path:
        cached = self._cache_path(storage_key)
        if cached.exists():
            return cached
        cached.parent.mkdir(parents=True, exist_ok=True)
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=storage_key)
            with cached.open("wb") as stream:
                stream.write(response["Body"].read())
        except ClientError as error:
            cached.unlink(missing_ok=True)
            raise ArtifactIntakeError(ArtifactFailureCode.INVALID_CHUNK) from error
        return cached

    def delete_published(self, storage_key: str) -> None:
        """Delete a durably published object, e.g. on a later rollback."""
        self._client.delete_object(Bucket=self.bucket, Key=storage_key)
        self._cache_path(storage_key).unlink(missing_ok=True)

    def _cache_path(self, storage_key: str) -> Path:
        digest = hashlib.sha256(storage_key.encode()).hexdigest()
        candidate = (self.cache_root / "objects" / digest[:2] / digest).resolve()
        if not candidate.is_relative_to(self.cache_root):
            raise ValueError("artifact storage key escapes the local cache root")
        return candidate
