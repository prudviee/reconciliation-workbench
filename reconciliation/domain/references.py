"""Pure reservation, exclusion, and authoritative-reference preprocessing."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from .reconciliation import (
    DecisionInputs,
    EngineSnapshot,
    MatchRecord,
    PairOrigin,
    PairOutcome,
    RecordSide,
    ReferenceContract,
    UnpairedOutcome,
    UnpairedReason,
)
from .workspaces import DomainValidationError


@dataclass(frozen=True, slots=True)
class ProhibitedRelationship:
    left_id: str
    right_id: str
    decision_id: str
    revision_id: str

    def __post_init__(self) -> None:
        for name in ("left_id", "right_id", "decision_id", "revision_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise DomainValidationError(f"prohibited relationship {name} must be nonblank text")


@dataclass(frozen=True, slots=True)
class ReferenceConflict:
    reference_key: str
    left_ids: tuple[str, ...]
    right_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.reference_key.strip():
            raise DomainValidationError("reference conflict key must not be blank")
        left_ids = tuple(sorted(self.left_ids))
        right_ids = tuple(sorted(self.right_ids))
        if len(left_ids) != len(set(left_ids)) or len(right_ids) != len(set(right_ids)):
            raise DomainValidationError("reference conflict identities must be unique")
        if len(left_ids) <= 1 and len(right_ids) <= 1:
            raise DomainValidationError("reference conflict requires a duplicate on at least one side")
        object.__setattr__(self, "left_ids", left_ids)
        object.__setattr__(self, "right_ids", right_ids)


@dataclass(frozen=True, slots=True)
class ReferencePreprocessingResult:
    input_left_ids: tuple[str, ...]
    input_right_ids: tuple[str, ...]
    pairs: tuple[PairOutcome, ...]
    terminal_unpaired: tuple[UnpairedOutcome, ...]
    remaining_left: tuple[MatchRecord, ...]
    remaining_right: tuple[MatchRecord, ...]
    prohibited_relationships: tuple[ProhibitedRelationship, ...]
    reference_conflicts: tuple[ReferenceConflict, ...]

    def __post_init__(self) -> None:
        input_left = tuple(sorted(self.input_left_ids))
        input_right = tuple(sorted(self.input_right_ids))
        pairs = tuple(sorted(self.pairs, key=lambda item: (item.left_id, item.right_id)))
        terminal = tuple(
            sorted(self.terminal_unpaired, key=lambda item: (item.side.value, item.record_id))
        )
        remaining_left = tuple(sorted(self.remaining_left, key=lambda item: item.observation_id))
        remaining_right = tuple(sorted(self.remaining_right, key=lambda item: item.observation_id))
        prohibited = tuple(
            sorted(
                self.prohibited_relationships,
                key=lambda item: (item.left_id, item.right_id, item.decision_id),
            )
        )
        conflicts = tuple(sorted(self.reference_conflicts, key=lambda item: item.reference_key))

        if len(input_left) != len(set(input_left)) or len(input_right) != len(set(input_right)):
            raise DomainValidationError("preprocessing input identities must be unique")
        if set(input_left).intersection(input_right):
            raise DomainValidationError("preprocessing input identities must be unique across sides")

        paired_left = [item.left_id for item in pairs]
        paired_right = [item.right_id for item in pairs]
        terminal_left = [
            item.record_id for item in terminal if item.side is RecordSide.LEFT
        ]
        terminal_right = [
            item.record_id for item in terminal if item.side is RecordSide.RIGHT
        ]
        remaining_left_ids = [item.observation_id for item in remaining_left]
        remaining_right_ids = [item.observation_id for item in remaining_right]
        for values, name in (
            (paired_left, "paired left"),
            (paired_right, "paired right"),
            (terminal_left, "terminal left"),
            (terminal_right, "terminal right"),
            (remaining_left_ids, "remaining left"),
            (remaining_right_ids, "remaining right"),
        ):
            if len(values) != len(set(values)):
                raise DomainValidationError(f"preprocessing {name} identities must be unique")
        if set(paired_left) | set(terminal_left) | set(remaining_left_ids) != set(input_left):
            raise DomainValidationError("preprocessing must partition every left input")
        if set(paired_right) | set(terminal_right) | set(remaining_right_ids) != set(input_right):
            raise DomainValidationError("preprocessing must partition every right input")
        if (
            set(paired_left).intersection(terminal_left)
            or set(paired_left).intersection(remaining_left_ids)
            or set(terminal_left).intersection(remaining_left_ids)
            or set(paired_right).intersection(terminal_right)
            or set(paired_right).intersection(remaining_right_ids)
            or set(terminal_right).intersection(remaining_right_ids)
        ):
            raise DomainValidationError("preprocessing partitions cannot overlap")

        object.__setattr__(self, "input_left_ids", input_left)
        object.__setattr__(self, "input_right_ids", input_right)
        object.__setattr__(self, "pairs", pairs)
        object.__setattr__(self, "terminal_unpaired", terminal)
        object.__setattr__(self, "remaining_left", remaining_left)
        object.__setattr__(self, "remaining_right", remaining_right)
        object.__setattr__(self, "prohibited_relationships", prohibited)
        object.__setattr__(self, "reference_conflicts", conflicts)


def preprocess_references(
    *,
    snapshot: EngineSnapshot,
    decisions: DecisionInputs,
    reference_contract: ReferenceContract,
) -> ReferencePreprocessingResult:
    """Reserve reviewer-controlled identities, then establish trusted pairs.

    The returned remaining records are the only records eligible for candidate
    generation. Active rejected relationships remain explicit prohibitions for
    all later automatic stages.
    """

    if not isinstance(reference_contract, ReferenceContract):
        raise DomainValidationError("reference_contract must be a ReferenceContract value")

    left_by_id = {record.observation_id: record for record in snapshot.left}
    right_by_id = {record.observation_id: record for record in snapshot.right}
    _validate_relationship_orientation(decisions, left_by_id, right_by_id)

    remaining_left = set(left_by_id)
    remaining_right = set(right_by_id)
    pairs: list[PairOutcome] = []
    terminal: dict[str, UnpairedOutcome] = {}

    for side, records in ((RecordSide.LEFT, snapshot.left), (RecordSide.RIGHT, snapshot.right)):
        for record in records:
            if not record.eligible:
                terminal[record.observation_id] = UnpairedOutcome(
                    record_id=record.observation_id,
                    side=side,
                    reason=UnpairedReason.CANCELLED_EXCLUDED,
                    explanation="The source marked this record cancelled, so automatic matching excluded it.",
                )
                _remove(record.observation_id, side, remaining_left, remaining_right)

    for link in decisions.manual_links:
        left_available = link.left_id in remaining_left
        right_available = link.right_id in remaining_right
        if left_available and right_available:
            pairs.append(PairOutcome(link.left_id, link.right_id, PairOrigin.MANUAL))
            remaining_left.remove(link.left_id)
            remaining_right.remove(link.right_id)
            continue
        if left_available:
            terminal[link.left_id] = UnpairedOutcome(
                record_id=link.left_id,
                side=RecordSide.LEFT,
                reason=UnpairedReason.MANUAL_ATTENTION,
                explanation="Its saved manual counterpart is absent or excluded in this snapshot; reviewer attention is required.",
                related_ids=(link.right_id,),
            )
            remaining_left.remove(link.left_id)
        if right_available:
            terminal[link.right_id] = UnpairedOutcome(
                record_id=link.right_id,
                side=RecordSide.RIGHT,
                reason=UnpairedReason.MANUAL_ATTENTION,
                explanation="Its saved manual counterpart is absent or excluded in this snapshot; reviewer attention is required.",
                related_ids=(link.left_id,),
            )
            remaining_right.remove(link.right_id)

    for accepted in decisions.accepted_unmatched:
        _reserve_single(
            record_id=accepted.record_id,
            reason=UnpairedReason.ACCEPTED_UNMATCHED,
            explanation="A reviewer accepted this record as unmatched; it remains reserved from automatic matching.",
            left_by_id=left_by_id,
            right_by_id=right_by_id,
            remaining_left=remaining_left,
            remaining_right=remaining_right,
            terminal=terminal,
        )
    for reserved in decisions.reserved_identities:
        _reserve_single(
            record_id=reserved.record_id,
            reason=UnpairedReason.REVIEWER_RESERVED,
            explanation="A reviewer decision reserves this identity from automatic matching.",
            left_by_id=left_by_id,
            right_by_id=right_by_id,
            remaining_left=remaining_left,
            remaining_right=remaining_right,
            terminal=terminal,
        )

    prohibited = tuple(
        ProhibitedRelationship(
            left_id=item.left_id,
            right_id=item.right_id,
            decision_id=item.decision_id,
            revision_id=item.revision_id,
        )
        for item in decisions.rejected_relationships
        if item.left_id in left_by_id and item.right_id in right_by_id
    )
    prohibited_edges = {(item.left_id, item.right_id) for item in prohibited}

    left_references = _reference_index(
        (left_by_id[identity] for identity in remaining_left), reference_contract
    )
    right_references = _reference_index(
        (right_by_id[identity] for identity in remaining_right), reference_contract
    )
    conflicts: list[ReferenceConflict] = []
    all_reference_keys = sorted(set(left_references) | set(right_references))
    for key in all_reference_keys:
        left_ids = tuple(sorted(left_references.get(key, ())))
        right_ids = tuple(sorted(right_references.get(key, ())))
        if len(left_ids) <= 1 and len(right_ids) <= 1:
            continue
        conflict = ReferenceConflict(key, left_ids, right_ids)
        conflicts.append(conflict)
        all_ids = tuple(sorted(left_ids + right_ids))
        for identity in left_ids:
            terminal[identity] = UnpairedOutcome(
                record_id=identity,
                side=RecordSide.LEFT,
                reason=UnpairedReason.DUPLICATE_REFERENCE,
                explanation="This trusted reference is not unique in the current scope, so it cannot establish an authoritative pair.",
                related_ids=all_ids,
            )
            remaining_left.remove(identity)
        for identity in right_ids:
            terminal[identity] = UnpairedOutcome(
                record_id=identity,
                side=RecordSide.RIGHT,
                reason=UnpairedReason.DUPLICATE_REFERENCE,
                explanation="This trusted reference is not unique in the current scope, so it cannot establish an authoritative pair.",
                related_ids=all_ids,
            )
            remaining_right.remove(identity)

    for key in all_reference_keys:
        left_ids = left_references.get(key, ())
        right_ids = right_references.get(key, ())
        if len(left_ids) != 1 or len(right_ids) != 1:
            continue
        left_id = left_ids[0]
        right_id = right_ids[0]
        if (
            left_id not in remaining_left
            or right_id not in remaining_right
            or (left_id, right_id) in prohibited_edges
        ):
            continue
        pairs.append(PairOutcome(left_id, right_id, PairOrigin.AUTHORITATIVE_REFERENCE))
        remaining_left.remove(left_id)
        remaining_right.remove(right_id)

    return ReferencePreprocessingResult(
        input_left_ids=snapshot.input_left_ids,
        input_right_ids=snapshot.input_right_ids,
        pairs=tuple(pairs),
        terminal_unpaired=tuple(terminal.values()),
        remaining_left=tuple(left_by_id[identity] for identity in remaining_left),
        remaining_right=tuple(right_by_id[identity] for identity in remaining_right),
        prohibited_relationships=prohibited,
        reference_conflicts=tuple(conflicts),
    )


def _validate_relationship_orientation(
    decisions: DecisionInputs,
    left_by_id: dict[str, MatchRecord],
    right_by_id: dict[str, MatchRecord],
) -> None:
    relationships = (*decisions.manual_links, *decisions.rejected_relationships)
    for relationship in relationships:
        if relationship.left_id in right_by_id:
            raise DomainValidationError(
                f"decision {relationship.decision_id} uses a right-side record as left_id"
            )
        if relationship.right_id in left_by_id:
            raise DomainValidationError(
                f"decision {relationship.decision_id} uses a left-side record as right_id"
            )


def _remove(
    record_id: str,
    side: RecordSide,
    remaining_left: set[str],
    remaining_right: set[str],
) -> None:
    if side is RecordSide.LEFT:
        remaining_left.discard(record_id)
    else:
        remaining_right.discard(record_id)


def _reserve_single(
    *,
    record_id: str,
    reason: UnpairedReason,
    explanation: str,
    left_by_id: dict[str, MatchRecord],
    right_by_id: dict[str, MatchRecord],
    remaining_left: set[str],
    remaining_right: set[str],
    terminal: dict[str, UnpairedOutcome],
) -> None:
    if record_id in remaining_left:
        terminal[record_id] = UnpairedOutcome(
            record_id=record_id,
            side=RecordSide.LEFT,
            reason=reason,
            explanation=explanation,
        )
        remaining_left.remove(record_id)
    elif record_id in remaining_right:
        terminal[record_id] = UnpairedOutcome(
            record_id=record_id,
            side=RecordSide.RIGHT,
            reason=reason,
            explanation=explanation,
        )
        remaining_right.remove(record_id)
    elif record_id in left_by_id or record_id in right_by_id:
        # Cancellation or a manual decision already produced the stronger outcome.
        return


def _reference_index(
    records: Iterable[MatchRecord],
    contract: ReferenceContract,
) -> dict[str, tuple[str, ...]]:
    values: defaultdict[str, list[str]] = defaultdict(list)
    for record in records:
        key = (
            record.reference_value
            if contract is ReferenceContract.SHARED_MUST_AGREE
            else record.shared_reference_alias
        )
        if key is not None:
            values[key].append(record.observation_id)
    return {key: tuple(sorted(identities)) for key, identities in values.items()}
