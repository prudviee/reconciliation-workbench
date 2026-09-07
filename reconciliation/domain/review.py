"""Pure contracts for durable review authority and stable case identity."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from .reconciliation import RecordSide
from .workspaces import DomainValidationError


CASE_KEY_VERSION = "stable-case-key-v1"


class DecisionAction(StrEnum):
    LINK = "LINK"
    ACCEPT_UNMATCHED = "ACCEPT_UNMATCHED"
    REJECT_CANDIDATE = "REJECT_CANDIDATE"
    REAFFIRM = "REAFFIRM"
    REVOKE = "REVOKE"
    REPLACE = "REPLACE"


class DecisionAuthorityKind(StrEnum):
    LINK = "LINK"
    ACCEPT_UNMATCHED = "ACCEPT_UNMATCHED"
    REJECT_CANDIDATE = "REJECT_CANDIDATE"


class DecisionHealth(StrEnum):
    UNCHANGED = "UNCHANGED"
    EVIDENCE_CHANGED = "EVIDENCE_CHANGED"
    PARTNER_UNAVAILABLE = "PARTNER_UNAVAILABLE"
    NEW_CANDIDATE = "NEW_CANDIDATE"


class DecisionAttention(StrEnum):
    COMPARISON_CHANGED = "COMPARISON_CHANGED"
    AUTHORITATIVE_REFERENCE_CONFLICT = "AUTHORITATIVE_REFERENCE_CONFLICT"
    DIAGNOSTIC_INCOMPLETE = "DIAGNOSTIC_INCOMPLETE"


class ReviewConflictCode(StrEnum):
    STALE_GENERATION = "STALE_GENERATION"
    STALE_REVISION = "STALE_REVISION"
    ENDPOINT_CLAIMED = "ENDPOINT_CLAIMED"
    CONFLICT_SET_CHANGED = "CONFLICT_SET_CHANGED"


class CaseKind(StrEnum):
    PAIR = "PAIR"
    UNPAIRED = "UNPAIRED"
    AMBIGUITY = "AMBIGUITY"


class CaseResultKind(StrEnum):
    PAIR = "PAIR"
    UNPAIRED = "UNPAIRED"
    AMBIGUITY = "AMBIGUITY"


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(f"{name} must be nonblank text")
    return value


def _strict_enum(value: object, enum_type: type[StrEnum], name: str) -> None:
    if not isinstance(value, enum_type):
        raise DomainValidationError(f"{name} must be a {enum_type.__name__} value")


def _nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DomainValidationError(f"{name} must be a nonnegative integer")
    return value


def _canonical_texts(values: Iterable[str], name: str) -> tuple[str, ...]:
    result = tuple(sorted(_required_text(value, name) for value in values))
    if len(result) != len(set(result)):
        raise DomainValidationError(f"{name} values must be unique")
    return result


@dataclass(frozen=True, slots=True)
class DecisionAuthority:
    kind: DecisionAuthorityKind
    left_id: str | None = None
    right_id: str | None = None
    record_id: str | None = None
    record_side: RecordSide | None = None

    def __post_init__(self) -> None:
        _strict_enum(self.kind, DecisionAuthorityKind, "authority kind")
        pair_values = self.left_id is not None or self.right_id is not None
        single_values = self.record_id is not None or self.record_side is not None

        if self.kind in {
            DecisionAuthorityKind.LINK,
            DecisionAuthorityKind.REJECT_CANDIDATE,
        }:
            if not pair_values or self.left_id is None or self.right_id is None:
                raise DomainValidationError("pair authority requires left_id and right_id")
            _required_text(self.left_id, "left_id")
            _required_text(self.right_id, "right_id")
            if self.left_id == self.right_id:
                raise DomainValidationError("pair authority endpoints must be distinct")
            if single_values:
                raise DomainValidationError("pair authority cannot carry a single endpoint")
            return

        if pair_values:
            raise DomainValidationError("accepted-unmatched authority cannot carry pair endpoints")
        if self.record_id is None or self.record_side is None:
            raise DomainValidationError(
                "accepted-unmatched authority requires record_id and record_side"
            )
        _required_text(self.record_id, "record_id")
        _strict_enum(self.record_side, RecordSide, "record_side")

    @classmethod
    def link(cls, left_id: str, right_id: str) -> DecisionAuthority:
        return cls(DecisionAuthorityKind.LINK, left_id=left_id, right_id=right_id)

    @classmethod
    def accept_unmatched(
        cls, record_id: str, record_side: RecordSide
    ) -> DecisionAuthority:
        return cls(
            DecisionAuthorityKind.ACCEPT_UNMATCHED,
            record_id=record_id,
            record_side=record_side,
        )

    @classmethod
    def reject_candidate(cls, left_id: str, right_id: str) -> DecisionAuthority:
        return cls(
            DecisionAuthorityKind.REJECT_CANDIDATE,
            left_id=left_id,
            right_id=right_id,
        )

    @property
    def endpoint_ids(self) -> tuple[str, ...]:
        if self.kind is DecisionAuthorityKind.ACCEPT_UNMATCHED:
            assert self.record_id is not None
            return (self.record_id,)
        assert self.left_id is not None and self.right_id is not None
        return (self.left_id, self.right_id)

    @property
    def reserves_endpoints(self) -> bool:
        return self.kind is not DecisionAuthorityKind.REJECT_CANDIDATE


@dataclass(frozen=True, slots=True, order=True)
class ExpectedDecisionRevision:
    decision_id: str
    revision_id: str

    def __post_init__(self) -> None:
        _required_text(self.decision_id, "decision_id")
        _required_text(self.revision_id, "revision_id")


@dataclass(frozen=True, slots=True)
class DecisionCommand:
    action: DecisionAction
    reason: str
    actor: str
    expected_resolution_generation: int
    authority: DecisionAuthority | None = None
    target: ExpectedDecisionRevision | None = None
    approved_conflicts: tuple[ExpectedDecisionRevision, ...] = ()
    reviewed_observation_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _strict_enum(self.action, DecisionAction, "decision action")
        _required_text(self.reason, "reason")
        _required_text(self.actor, "actor")
        _nonnegative_int(
            self.expected_resolution_generation,
            "expected_resolution_generation",
        )
        if any(
            not isinstance(item, ExpectedDecisionRevision)
            for item in self.approved_conflicts
        ):
            raise DomainValidationError(
                "approved conflicts must be ExpectedDecisionRevision values"
            )
        conflicts = tuple(sorted(self.approved_conflicts))
        if len({item.decision_id for item in conflicts}) != len(conflicts):
            raise DomainValidationError(
                "approved conflicts must contain each decision exactly once"
            )
        reviewed = _canonical_texts(
            self.reviewed_observation_ids,
            "reviewed observation identity",
        )

        initial_kind = {
            DecisionAction.LINK: DecisionAuthorityKind.LINK,
            DecisionAction.ACCEPT_UNMATCHED: DecisionAuthorityKind.ACCEPT_UNMATCHED,
            DecisionAction.REJECT_CANDIDATE: DecisionAuthorityKind.REJECT_CANDIDATE,
        }.get(self.action)
        if initial_kind is not None:
            if self.authority is None or self.authority.kind is not initial_kind:
                raise DomainValidationError(
                    f"{self.action.value} requires {initial_kind.value} authority"
                )
            if self.target is not None or conflicts:
                raise DomainValidationError(
                    f"{self.action.value} cannot target or supersede a decision"
                )
            self._require_reviewed_cardinality(reviewed, self.authority)
        elif self.action is DecisionAction.REAFFIRM:
            if self.target is None or self.authority is not None or conflicts:
                raise DomainValidationError(
                    "REAFFIRM requires one target and cannot replace authority"
                )
            if not reviewed:
                raise DomainValidationError(
                    "REAFFIRM requires a fresh reviewed observation baseline"
                )
            if len(reviewed) > 2:
                raise DomainValidationError(
                    "REAFFIRM reviewed baseline contains at most two observations"
                )
        elif self.action is DecisionAction.REVOKE:
            if self.target is None or self.authority is not None or conflicts or reviewed:
                raise DomainValidationError(
                    "REVOKE requires one target and no authority, conflicts, or baseline"
                )
        else:
            if self.target is None or self.authority is None:
                raise DomainValidationError(
                    "REPLACE requires a target and replacement authority"
                )
            if any(item.decision_id == self.target.decision_id for item in conflicts):
                raise DomainValidationError(
                    "replacement conflicts cannot repeat its target decision"
                )
            self._require_reviewed_cardinality(reviewed, self.authority)

        object.__setattr__(self, "approved_conflicts", conflicts)
        object.__setattr__(self, "reviewed_observation_ids", reviewed)

    @staticmethod
    def _require_reviewed_cardinality(
        reviewed: tuple[str, ...], authority: DecisionAuthority
    ) -> None:
        expected = len(authority.endpoint_ids)
        if len(reviewed) != expected:
            raise DomainValidationError(
                f"{authority.kind.value} requires {expected} reviewed observation identities"
            )


@dataclass(frozen=True, slots=True, order=True)
class DecisionConflict:
    decision_id: str
    revision_id: str
    claimed_record_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _required_text(self.decision_id, "conflict decision_id")
        _required_text(self.revision_id, "conflict revision_id")
        claimed = _canonical_texts(self.claimed_record_ids, "claimed record identity")
        if not claimed:
            raise DomainValidationError("decision conflict requires a claimed endpoint")
        object.__setattr__(self, "claimed_record_ids", claimed)


@dataclass(frozen=True, slots=True)
class ReplacementPreview:
    authority: DecisionAuthority
    target: ExpectedDecisionRevision
    conflicts: tuple[DecisionConflict, ...]
    resolution_generation: int

    def __post_init__(self) -> None:
        if not isinstance(self.authority, DecisionAuthority):
            raise DomainValidationError("preview authority must be DecisionAuthority")
        if not isinstance(self.target, ExpectedDecisionRevision):
            raise DomainValidationError("preview target must be ExpectedDecisionRevision")
        _nonnegative_int(self.resolution_generation, "resolution_generation")
        if any(not isinstance(item, DecisionConflict) for item in self.conflicts):
            raise DomainValidationError(
                "replacement conflicts must be DecisionConflict values"
            )
        conflicts = tuple(sorted(self.conflicts))
        if len({item.decision_id for item in conflicts}) != len(conflicts):
            raise DomainValidationError(
                "replacement preview must contain each conflicting decision once"
            )
        if any(item.decision_id == self.target.decision_id for item in conflicts):
            raise DomainValidationError(
                "replacement preview conflicts cannot repeat its target"
            )
        object.__setattr__(self, "conflicts", conflicts)

    @property
    def expected_conflicts(self) -> tuple[ExpectedDecisionRevision, ...]:
        return tuple(
            ExpectedDecisionRevision(item.decision_id, item.revision_id)
            for item in self.conflicts
        )


@dataclass(frozen=True, slots=True)
class ReviewConflict:
    code: ReviewConflictCode
    message: str
    affected: tuple[ExpectedDecisionRevision, ...] = ()

    def __post_init__(self) -> None:
        _strict_enum(self.code, ReviewConflictCode, "review conflict code")
        _required_text(self.message, "review conflict message")
        if any(
            not isinstance(item, ExpectedDecisionRevision) for item in self.affected
        ):
            raise DomainValidationError(
                "review conflict affected values must be ExpectedDecisionRevision values"
            )
        affected = tuple(sorted(self.affected))
        if len({item.decision_id for item in affected}) != len(affected):
            raise DomainValidationError(
                "review conflict must contain each affected decision once"
            )
        object.__setattr__(self, "affected", affected)


@dataclass(frozen=True, slots=True)
class DecisionHealthProjection:
    decision_id: str
    revision_id: str
    run_id: str
    health: DecisionHealth
    attention: tuple[DecisionAttention, ...] = ()

    def __post_init__(self) -> None:
        _required_text(self.decision_id, "health decision_id")
        _required_text(self.revision_id, "health revision_id")
        _required_text(self.run_id, "health run_id")
        _strict_enum(self.health, DecisionHealth, "decision health")
        if any(not isinstance(item, DecisionAttention) for item in self.attention):
            raise DomainValidationError(
                "decision attention reasons must be DecisionAttention values"
            )
        attention = tuple(sorted(self.attention, key=lambda item: item.value))
        if len(attention) != len(set(attention)):
            raise DomainValidationError("decision attention reasons must be unique")
        object.__setattr__(self, "attention", attention)


@dataclass(frozen=True, slots=True)
class DecisionHealthEvidence:
    authority_kind: DecisionAuthorityKind
    endpoints_available: bool
    evidence_changed: bool
    new_candidate: bool = False
    diagnostic_complete: bool = True
    comparison_changed: bool = False
    authoritative_reference_conflict: bool = False

    def __post_init__(self) -> None:
        _strict_enum(self.authority_kind, DecisionAuthorityKind, "health authority kind")
        for name in (
            "endpoints_available",
            "evidence_changed",
            "new_candidate",
            "diagnostic_complete",
            "comparison_changed",
            "authoritative_reference_conflict",
        ):
            if not isinstance(getattr(self, name), bool):
                raise DomainValidationError(f"{name} must be boolean")
        if self.authority_kind is not DecisionAuthorityKind.ACCEPT_UNMATCHED and (
            self.new_candidate or not self.diagnostic_complete
        ):
            raise DomainValidationError(
                "new-candidate and diagnostic-completeness evidence belongs to accepted-unmatched authority"
            )
        if self.authority_kind is not DecisionAuthorityKind.LINK and self.comparison_changed:
            raise DomainValidationError("comparison-change attention belongs to link authority")
        if (
            self.authority_kind is not DecisionAuthorityKind.REJECT_CANDIDATE
            and self.authoritative_reference_conflict
        ):
            raise DomainValidationError(
                "authoritative-reference conflict belongs to rejected relationships"
            )


def project_decision_health(
    *,
    decision_id: str,
    revision_id: str,
    run_id: str,
    evidence: DecisionHealthEvidence,
) -> DecisionHealthProjection:
    """Classify current evidence without changing reviewer authority."""

    if not isinstance(evidence, DecisionHealthEvidence):
        raise DomainValidationError("health evidence must be DecisionHealthEvidence")
    attention: list[DecisionAttention] = []
    if evidence.comparison_changed:
        attention.append(DecisionAttention.COMPARISON_CHANGED)
    if evidence.authoritative_reference_conflict:
        attention.append(DecisionAttention.AUTHORITATIVE_REFERENCE_CONFLICT)
    if not evidence.diagnostic_complete:
        attention.append(DecisionAttention.DIAGNOSTIC_INCOMPLETE)

    if not evidence.endpoints_available:
        health = DecisionHealth.PARTNER_UNAVAILABLE
    elif (
        evidence.authority_kind is DecisionAuthorityKind.ACCEPT_UNMATCHED
        and evidence.new_candidate
    ):
        health = DecisionHealth.NEW_CANDIDATE
    elif evidence.evidence_changed or evidence.comparison_changed:
        health = DecisionHealth.EVIDENCE_CHANGED
    else:
        health = DecisionHealth.UNCHANGED
    return DecisionHealthProjection(
        decision_id=decision_id,
        revision_id=revision_id,
        run_id=run_id,
        health=health,
        attention=tuple(attention),
    )


@dataclass(frozen=True, slots=True)
class CaseKey:
    kind: CaseKind
    digest: str

    def __post_init__(self) -> None:
        _strict_enum(self.kind, CaseKind, "case kind")
        if len(self.digest) != 64 or self.digest != self.digest.lower():
            raise DomainValidationError("case digest must be a lowercase SHA-256 digest")
        try:
            bytes.fromhex(self.digest)
        except ValueError:
            raise DomainValidationError(
                "case digest must be a lowercase SHA-256 digest"
            ) from None

    def __str__(self) -> str:
        return f"{self.kind.value.lower()}:{self.digest}"


def pair_case_key(*, book_id: str, left_id: str, right_id: str) -> CaseKey:
    return _case_key(
        CaseKind.PAIR,
        (
            ("book", _required_text(book_id, "book_id")),
            ("left", _required_text(left_id, "left_id")),
            ("right", _required_text(right_id, "right_id")),
        ),
    )


def unpaired_case_key(
    *, book_id: str, side: RecordSide, record_id: str
) -> CaseKey:
    _strict_enum(side, RecordSide, "unpaired side")
    return _case_key(
        CaseKind.UNPAIRED,
        (
            ("book", _required_text(book_id, "book_id")),
            ("side", side.value),
            ("record", _required_text(record_id, "record_id")),
        ),
    )


def ambiguity_case_key(
    *,
    book_id: str,
    scope_id: str,
    policy_digest: str,
    left_ids: Iterable[str],
    right_ids: Iterable[str],
) -> CaseKey:
    _validate_sha256(policy_digest, "policy_digest")
    left = _canonical_texts(left_ids, "ambiguity left identity")
    right = _canonical_texts(right_ids, "ambiguity right identity")
    if not left or not right:
        raise DomainValidationError(
            "ambiguity case requires complete members on both sides"
        )
    if set(left).intersection(right):
        raise DomainValidationError(
            "ambiguity member identities must be unique across sides"
        )
    parts = [
        ("book", _required_text(book_id, "book_id")),
        ("scope", _required_text(scope_id, "scope_id")),
        ("policy", policy_digest),
        ("left-count", str(len(left))),
    ]
    parts.extend(("left-member", item) for item in left)
    parts.append(("right-count", str(len(right))))
    parts.extend(("right-member", item) for item in right)
    return _case_key(CaseKind.AMBIGUITY, tuple(parts))


def _case_key(kind: CaseKind, parts: tuple[tuple[str, str], ...]) -> CaseKey:
    digest = hashlib.sha256()
    for value in (CASE_KEY_VERSION, kind.value):
        _update_length_prefixed(digest, value)
    for label, value in parts:
        _update_length_prefixed(digest, label)
        _update_length_prefixed(digest, value)
    return CaseKey(kind, digest.hexdigest())


def _update_length_prefixed(digest: object, value: str) -> None:
    encoded = value.encode("utf-8")
    digest.update(len(encoded).to_bytes(8, "big"))  # type: ignore[attr-defined]
    digest.update(encoded)  # type: ignore[attr-defined]


def _validate_sha256(value: str, name: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or value != value.lower():
        raise DomainValidationError(f"{name} must be a lowercase SHA-256 digest")
    try:
        bytes.fromhex(value)
    except ValueError:
        raise DomainValidationError(
            f"{name} must be a lowercase SHA-256 digest"
        ) from None


@dataclass(frozen=True, slots=True)
class CaseOccurrenceDescriptor:
    case_key: CaseKey
    run_id: str
    result_kind: CaseResultKind
    result_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.case_key, CaseKey):
            raise DomainValidationError("occurrence case_key must be CaseKey")
        _required_text(self.run_id, "occurrence run_id")
        _strict_enum(self.result_kind, CaseResultKind, "occurrence result_kind")
        _required_text(self.result_id, "occurrence result_id")
        if self.case_key.kind.value != self.result_kind.value:
            raise DomainValidationError(
                "case occurrence result kind must match its stable case kind"
            )


@dataclass(frozen=True, slots=True, order=True)
class CaseLineageEdge:
    predecessor: CaseKey
    successor: CaseKey

    def __post_init__(self) -> None:
        if not isinstance(self.predecessor, CaseKey) or not isinstance(
            self.successor, CaseKey
        ):
            raise DomainValidationError("lineage endpoints must be CaseKey values")
        if self.predecessor == self.successor:
            raise DomainValidationError("case lineage cannot contain a self-edge")


@dataclass(frozen=True, slots=True)
class CaseTransitionPlan:
    edges: tuple[CaseLineageEdge, ...]

    def __post_init__(self) -> None:
        if any(not isinstance(item, CaseLineageEdge) for item in self.edges):
            raise DomainValidationError(
                "case transition edges must be CaseLineageEdge values"
            )
        edges = tuple(
            sorted(
                self.edges,
                key=lambda item: (
                    item.predecessor.kind.value,
                    item.predecessor.digest,
                    item.successor.kind.value,
                    item.successor.digest,
                ),
            )
        )
        if len(edges) != len(set(edges)):
            raise DomainValidationError("case lineage edges must be unique")
        object.__setattr__(self, "edges", edges)
