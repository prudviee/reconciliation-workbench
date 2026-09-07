"""Deterministic, bounded candidate generation for reconciliation."""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_left, bisect_right
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .reconciliation import BlockingPassPolicy, MatchRecord, MatchingPolicy
from .references import ReferencePreprocessingResult
from .workspaces import DomainValidationError


class CandidateLimitReason(StrEnum):
    PER_RECORD_LIMIT = "PER_RECORD_LIMIT"
    RUN_EDGE_LIMIT = "RUN_EDGE_LIMIT"
    CONNECTED_TO_INCOMPLETE_PARTITION = "CONNECTED_TO_INCOMPLETE_PARTITION"


@dataclass(frozen=True, slots=True)
class CandidateEdge:
    left_id: str
    right_id: str
    blocking_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("left_id", "right_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise DomainValidationError(f"candidate edge {name} must be nonblank text")
        reasons = tuple(sorted(set(self.blocking_reasons)))
        if not reasons or any(not isinstance(value, str) or not value.strip() for value in reasons):
            raise DomainValidationError("candidate edge requires nonblank blocking reasons")
        object.__setattr__(self, "blocking_reasons", reasons)


@dataclass(frozen=True, slots=True)
class CandidatePartitionEvidence:
    partition_id: str
    blocking_pass: str
    left_ids: tuple[str, ...]
    right_ids: tuple[str, ...]
    enumerated_edge_count: int
    complete: bool
    limit_reason: CandidateLimitReason | None = None

    def __post_init__(self) -> None:
        for name in ("partition_id", "blocking_pass"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise DomainValidationError(f"candidate partition {name} must be nonblank text")
        left_ids = tuple(sorted(self.left_ids))
        right_ids = tuple(sorted(self.right_ids))
        if not left_ids or not right_ids:
            raise DomainValidationError("candidate partition requires records on both sides")
        if len(left_ids) != len(set(left_ids)) or len(right_ids) != len(set(right_ids)):
            raise DomainValidationError("candidate partition identities must be unique")
        if (
            isinstance(self.enumerated_edge_count, bool)
            or not isinstance(self.enumerated_edge_count, int)
            or self.enumerated_edge_count < 0
        ):
            raise DomainValidationError("enumerated_edge_count must be a nonnegative integer")
        if not isinstance(self.complete, bool):
            raise DomainValidationError("candidate partition complete must be boolean")
        if self.complete and self.limit_reason is not None:
            raise DomainValidationError("a complete candidate partition cannot have a limit reason")
        if not self.complete and not isinstance(self.limit_reason, CandidateLimitReason):
            raise DomainValidationError("an incomplete candidate partition requires a limit reason")
        object.__setattr__(self, "left_ids", left_ids)
        object.__setattr__(self, "right_ids", right_ids)


@dataclass(frozen=True, slots=True)
class CandidateGenerationResult:
    candidates: tuple[CandidateEdge, ...]
    partitions: tuple[CandidatePartitionEvidence, ...]
    limited_record_ids: tuple[str, ...]
    complete: bool

    def __post_init__(self) -> None:
        candidates = tuple(sorted(self.candidates, key=lambda item: (item.left_id, item.right_id)))
        partitions = tuple(sorted(self.partitions, key=lambda item: item.partition_id))
        limited = tuple(sorted(self.limited_record_ids))
        edges = [(item.left_id, item.right_id) for item in candidates]
        if len(edges) != len(set(edges)):
            raise DomainValidationError("candidate generation edges must be unique")
        partition_ids = [item.partition_id for item in partitions]
        if len(partition_ids) != len(set(partition_ids)):
            raise DomainValidationError("candidate partition identities must be unique")
        if len(limited) != len(set(limited)):
            raise DomainValidationError("limited record identities must be unique")
        if not isinstance(self.complete, bool):
            raise DomainValidationError("candidate generation complete must be boolean")
        expected_limited = {
            identity
            for partition in partitions
            if not partition.complete
            for identity in (*partition.left_ids, *partition.right_ids)
        }
        if set(limited) != expected_limited:
            raise DomainValidationError(
                "limited identities must equal the members of incomplete partitions"
            )
        if self.complete != all(item.complete for item in partitions):
            raise DomainValidationError("candidate generation completeness must match its partitions")
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "partitions", partitions)
        object.__setattr__(self, "limited_record_ids", limited)


@dataclass(slots=True)
class _MutablePartition:
    partition_id: str
    blocking_pass: str
    left_ids: tuple[str, ...]
    right_ids: tuple[str, ...]
    enumerated_edge_count: int = 0
    limit_reason: CandidateLimitReason | None = None


def generate_candidates(
    *,
    preprocessed: ReferencePreprocessingResult,
    policy: MatchingPolicy,
) -> CandidateGenerationResult:
    """Generate the union of all configured candidate blocking passes.

    Candidate caps bound retained work. If a cap prevents complete enumeration,
    every blocking partition connected to that uncertainty is marked incomplete.
    Downstream assignment must abstain for every listed limited identity.
    """

    prohibited = {
        (item.left_id, item.right_id) for item in preprocessed.prohibited_relationships
    }
    edges: dict[tuple[str, str], set[str]] = {}
    left_degree: defaultdict[str, int] = defaultdict(int)
    right_degree: defaultdict[str, int] = defaultdict(int)
    partitions: list[_MutablePartition] = []
    run_limited = False

    for blocking_pass in policy.blocking_passes:
        left_groups = _group_records(preprocessed.remaining_left, blocking_pass)
        right_groups = _group_records(preprocessed.remaining_right, blocking_pass)
        reason = _blocking_reason(blocking_pass)
        for key in sorted(set(left_groups).intersection(right_groups), key=_key_sort_value):
            left_records = left_groups[key]
            right_records = right_groups[key]
            partition = _MutablePartition(
                partition_id=_partition_id(reason, key),
                blocking_pass=reason,
                left_ids=tuple(record.observation_id for record in left_records),
                right_ids=tuple(record.observation_id for record in right_records),
            )
            partitions.append(partition)
            if run_limited:
                partition.limit_reason = CandidateLimitReason.RUN_EDGE_LIMIT
                continue

            right_times = (
                tuple(_required_time(record) for record in right_records)
                if blocking_pass.time_window is not None
                else ()
            )
            stop_partition = False
            for left in left_records:
                if blocking_pass.time_window is None:
                    first, last = 0, len(right_records)
                else:
                    executed_at = _required_time(left)
                    first = bisect_left(right_times, executed_at - blocking_pass.time_window)
                    last = bisect_right(right_times, executed_at + blocking_pass.time_window)
                for right in right_records[first:last]:
                    edge_key = (left.observation_id, right.observation_id)
                    if edge_key in prohibited:
                        continue
                    existing = edges.get(edge_key)
                    if existing is not None:
                        existing.add(reason)
                        partition.enumerated_edge_count += 1
                        continue
                    if (
                        left_degree[left.observation_id]
                        >= policy.limits.max_candidates_per_record
                        or right_degree[right.observation_id]
                        >= policy.limits.max_candidates_per_record
                    ):
                        partition.limit_reason = CandidateLimitReason.PER_RECORD_LIMIT
                        stop_partition = True
                        break
                    if len(edges) >= policy.limits.max_run_candidate_edges:
                        partition.limit_reason = CandidateLimitReason.RUN_EDGE_LIMIT
                        run_limited = True
                        stop_partition = True
                        break
                    edges[edge_key] = {reason}
                    left_degree[left.observation_id] += 1
                    right_degree[right.observation_id] += 1
                    partition.enumerated_edge_count += 1
                if stop_partition:
                    break

    _propagate_incomplete_partitions(partitions)
    evidence = tuple(
        CandidatePartitionEvidence(
            partition_id=item.partition_id,
            blocking_pass=item.blocking_pass,
            left_ids=item.left_ids,
            right_ids=item.right_ids,
            enumerated_edge_count=item.enumerated_edge_count,
            complete=item.limit_reason is None,
            limit_reason=item.limit_reason,
        )
        for item in partitions
    )
    limited_ids = {
        identity
        for partition in evidence
        if not partition.complete
        for identity in (*partition.left_ids, *partition.right_ids)
    }
    return CandidateGenerationResult(
        candidates=tuple(
            CandidateEdge(left_id, right_id, tuple(reasons))
            for (left_id, right_id), reasons in edges.items()
        ),
        partitions=evidence,
        limited_record_ids=tuple(limited_ids),
        complete=all(item.complete for item in evidence),
    )


def _group_records(
    records: tuple[MatchRecord, ...],
    blocking_pass: BlockingPassPolicy,
) -> dict[tuple[str | None, ...], tuple[MatchRecord, ...]]:
    groups: defaultdict[tuple[str | None, ...], list[MatchRecord]] = defaultdict(list)
    for record in records:
        if blocking_pass.time_window is not None and record.executed_at is None:
            continue
        if blocking_pass.require_instrument and record.instrument is None:
            continue
        if blocking_pass.require_side and record.side is None:
            continue
        if blocking_pass.require_currency and record.currency is None:
            continue
        if blocking_pass.use_shared_alias and record.shared_reference_alias is None:
            continue
        key = (
            record.instrument if blocking_pass.require_instrument else None,
            record.side.value if blocking_pass.require_side and record.side is not None else None,
            record.currency if blocking_pass.require_currency else None,
            record.shared_reference_alias if blocking_pass.use_shared_alias else None,
        )
        groups[key].append(record)
    return {
        key: tuple(
            sorted(
                values,
                key=lambda item: (
                    _required_time(item) if blocking_pass.time_window is not None else item.observation_id,
                    item.observation_id,
                ),
            )
        )
        for key, values in groups.items()
    }


def _required_time(record: MatchRecord) -> datetime:
    if record.executed_at is None:  # guarded by _group_records
        raise DomainValidationError("candidate partition record is missing executed_at")
    return record.executed_at


def _blocking_reason(blocking_pass: BlockingPassPolicy) -> str:
    return f"{blocking_pass.pass_id}@{blocking_pass.version}"


def _key_sort_value(key: tuple[str | None, ...]) -> str:
    return json.dumps(key, ensure_ascii=False, separators=(",", ":"))


def _partition_id(reason: str, key: tuple[str | None, ...]) -> str:
    payload = json.dumps(
        {"blocking_pass": reason, "key": key},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"partition-{hashlib.sha256(payload).hexdigest()[:16]}"


def _propagate_incomplete_partitions(partitions: list[_MutablePartition]) -> None:
    """Expand incompleteness through overlapping blocking partitions."""

    memberships: defaultdict[str, list[int]] = defaultdict(list)
    for index, partition in enumerate(partitions):
        for identity in (*partition.left_ids, *partition.right_ids):
            memberships[identity].append(index)

    queue = deque(
        index for index, partition in enumerate(partitions) if partition.limit_reason is not None
    )
    visited = set(queue)
    while queue:
        index = queue.popleft()
        partition = partitions[index]
        for identity in (*partition.left_ids, *partition.right_ids):
            for connected_index in memberships[identity]:
                connected = partitions[connected_index]
                if connected.limit_reason is None:
                    connected.limit_reason = CandidateLimitReason.CONNECTED_TO_INCOMPLETE_PARTITION
                if connected_index not in visited:
                    visited.add(connected_index)
                    queue.append(connected_index)
