"""Private, bounded CSV artifact staging and publication."""

from __future__ import annotations

import csv
import hashlib
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from threading import Lock
from typing import Iterable
from uuid import uuid4

from reconciliation.domain import WorkspaceId


SUPPORTED_DELIMITERS = frozenset({",", ";", "\t"})
_CSV_FIELD_LIMIT_LOCK = Lock()


class ArtifactFailureCode(StrEnum):
    BYTE_LIMIT = "BYTE_LIMIT"
    ROW_LIMIT = "ROW_LIMIT"
    COLUMN_LIMIT = "COLUMN_LIMIT"
    FIELD_LIMIT = "FIELD_LIMIT"
    INVALID_ENCODING = "INVALID_ENCODING"
    UNSUPPORTED_DELIMITER = "UNSUPPORTED_DELIMITER"
    EMPTY_FILE = "EMPTY_FILE"
    MALFORMED_CSV = "MALFORMED_CSV"
    INVALID_CHUNK = "INVALID_CHUNK"


@dataclass(frozen=True, slots=True)
class ArtifactIntakeError(ValueError):
    code: ArtifactFailureCode
    limit: int | None = None

    def __str__(self) -> str:
        if self.limit is None:
            return self.code.value
        return f"{self.code.value}: limit {self.limit}"


@dataclass(frozen=True, slots=True)
class IntakeLimits:
    max_bytes: int
    max_rows: int
    max_columns: int
    max_field_characters: int

    def __post_init__(self) -> None:
        values = (
            self.max_bytes,
            self.max_rows,
            self.max_columns,
            self.max_field_characters,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in values):
            raise ValueError("artifact intake limits must be positive integers")


@dataclass(frozen=True, slots=True)
class CsvScan:
    delimiter: str
    header: tuple[str, ...]
    row_count: int
    maximum_column_count: int


@dataclass(frozen=True, slots=True)
class StagedArtifact:
    path: Path
    physical_hash: str
    byte_size: int
    scan: CsvScan


@dataclass(frozen=True, slots=True)
class PublishedArtifact:
    storage_key: str
    path: Path


class PrivateArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def stage(
        self,
        chunks: Iterable[bytes],
        *,
        delimiter: str,
        limits: IntakeLimits,
    ) -> StagedArtifact:
        if delimiter not in SUPPORTED_DELIMITERS:
            raise ArtifactIntakeError(ArtifactFailureCode.UNSUPPORTED_DELIMITER)

        quarantine = self.root / ".quarantine"
        quarantine.mkdir(parents=True, exist_ok=True)
        path = quarantine / f"{uuid4().hex}.part"
        digest = hashlib.sha256()
        byte_size = 0
        try:
            with path.open("xb") as stream:
                for chunk in chunks:
                    if not isinstance(chunk, bytes):
                        raise ArtifactIntakeError(ArtifactFailureCode.INVALID_CHUNK)
                    byte_size += len(chunk)
                    if byte_size > limits.max_bytes:
                        raise ArtifactIntakeError(
                            ArtifactFailureCode.BYTE_LIMIT,
                            limits.max_bytes,
                        )
                    digest.update(chunk)
                    stream.write(chunk)
            scan = self._scan(path, delimiter=delimiter, limits=limits)
            return StagedArtifact(path, digest.hexdigest(), byte_size, scan)
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def publish(
        self,
        staged: StagedArtifact,
        *,
        workspace_id: WorkspaceId,
    ) -> PublishedArtifact:
        token = uuid4().hex
        storage_key = f"workspaces/{workspace_id.value}/{token[:2]}/{token}.csv"
        destination = self._resolve_key(storage_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged.path, destination)
        return PublishedArtifact(storage_key, destination)

    def discard_path(self, path: Path) -> None:
        resolved = path.resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError("artifact path is outside the private root")
        resolved.unlink(missing_ok=True)

    def resolve(self, storage_key: str) -> Path:
        return self._resolve_key(storage_key)

    def _resolve_key(self, storage_key: str) -> Path:
        candidate = (self.root / storage_key).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError("artifact storage key escapes the private root")
        return candidate

    @staticmethod
    def _scan(path: Path, *, delimiter: str, limits: IntakeLimits) -> CsvScan:
        with _CSV_FIELD_LIMIT_LOCK:
            previous_limit = csv.field_size_limit()
            csv.field_size_limit(limits.max_field_characters)
            try:
                return _scan_locked(path, delimiter=delimiter, limits=limits)
            finally:
                csv.field_size_limit(previous_limit)


def _scan_locked(path: Path, *, delimiter: str, limits: IntakeLimits) -> CsvScan:
    try:
        with path.open("r", encoding="utf-8-sig", errors="strict", newline="") as stream:
            reader = csv.reader(stream, delimiter=delimiter, strict=True)
            try:
                header = tuple(next(reader))
            except StopIteration:
                raise ArtifactIntakeError(ArtifactFailureCode.EMPTY_FILE) from None
            _check_column_limit(header, limits.max_columns)
            row_count = 0
            maximum_column_count = len(header)
            for row in reader:
                row_count += 1
                if row_count > limits.max_rows:
                    raise ArtifactIntakeError(
                        ArtifactFailureCode.ROW_LIMIT,
                        limits.max_rows,
                    )
                _check_column_limit(row, limits.max_columns)
                maximum_column_count = max(maximum_column_count, len(row))
    except UnicodeDecodeError:
        raise ArtifactIntakeError(ArtifactFailureCode.INVALID_ENCODING) from None
    except csv.Error as error:
        code = (
            ArtifactFailureCode.FIELD_LIMIT
            if "field larger than field limit" in str(error)
            else ArtifactFailureCode.MALFORMED_CSV
        )
        limit = limits.max_field_characters if code is ArtifactFailureCode.FIELD_LIMIT else None
        raise ArtifactIntakeError(code, limit) from None
    return CsvScan(delimiter, header, row_count, maximum_column_count)


def _check_column_limit(row: tuple[str, ...] | list[str], maximum: int) -> None:
    if len(row) > maximum:
        raise ArtifactIntakeError(ArtifactFailureCode.COLUMN_LIMIT, maximum)
