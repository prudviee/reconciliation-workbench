"""Immutable contracts for the deterministic reconciliation engine.

This module deliberately contains values and invariant checks only. Matching stages
consume these values in later modules without database, HTTP, file, clock, network,
or framework access.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import TypeAlias

from .ingestion import CanonicalSide, CanonicalState
from .workspaces import DomainValidationError


SCORE_SCALE_BP = 10_000
INITIAL_QUANTITY_WEIGHT_BP = 3_500
INITIAL_TIMESTAMP_WEIGHT_BP = 2_500
INITIAL_UNIT_PRICE_WEIGHT_BP = 1_500
INITIAL_GROSS_AMOUNT_WEIGHT_BP = 2_500
INITIAL_ASSIGNMENT_FLOOR_BP = 7_000
INITIAL_AUTOMATIC_THRESHOLD_BP = 9_000
INITIAL_GLOBAL_GAP_BP = 800


class RecordSide(StrEnum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"


class ReferenceContract(StrEnum):
    SHARED_MUST_AGREE = "SHARED_MUST_AGREE"
    SOURCE_LOCAL_OR_ALIAS = "SOURCE_LOCAL_OR_ALIAS"


class MatchFeature(StrEnum):
    QUANTITY = "QUANTITY"
    TIMESTAMP = "TIMESTAMP"
    UNIT_PRICE = "UNIT_PRICE"
    GROSS_AMOUNT = "GROSS_AMOUNT"


class PairOrigin(StrEnum):
    MANUAL = "MANUAL"
    AUTHORITATIVE_REFERENCE = "AUTHORITATIVE_REFERENCE"
    WEIGHTED_GLOBAL = "WEIGHTED_GLOBAL"


class UnpairedReason(StrEnum):
    ACCEPTED_UNMATCHED = "ACCEPTED_UNMATCHED"
    CANCELLED_EXCLUDED = "CANCELLED_EXCLUDED"
    REVIEWER_RESERVED = "REVIEWER_RESERVED"
    MANUAL_ATTENTION = "MANUAL_ATTENTION"
    DUPLICATE_REFERENCE = "DUPLICATE_REFERENCE"
    PROHIBITED = "PROHIBITED"
    NO_CANDIDATE = "NO_CANDIDATE"
    BELOW_ASSIGNMENT_FLOOR = "BELOW_ASSIGNMENT_FLOOR"
    AMBIGUOUS = "AMBIGUOUS"
    COMPUTATION_LIMITED = "COMPUTATION_LIMITED"


class ComparisonStatus(StrEnum):
    EXACT = "EXACT"
    WITHIN_TOLERANCE = "WITHIN_TOLERANCE"
    DISCREPANT = "DISCREPANT"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    MISSING = "MISSING"


class DiagnosticKind(StrEnum):
    ACCEPTED_UNMATCHED_CANDIDATE = "ACCEPTED_UNMATCHED_CANDIDATE"
    INCOMPLETE_SEARCH = "INCOMPLETE_SEARCH"


ScalarValue: TypeAlias = str | Decimal | datetime | None
DifferenceValue: TypeAlias = Decimal | timedelta | None


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(f"{name} must be nonblank text")
    return value


def _optional_text(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, name)


def _finite_decimal(value: object, name: str, *, nonnegative: bool = False) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise DomainValidationError(f"{name} must be a finite Decimal")
    if nonnegative and value < 0:
        raise DomainValidationError(f"{name} must be nonnegative")
    return value


def _optional_decimal(value: object, name: str, *, nonnegative: bool = False) -> Decimal | None:
    if value is None:
        return None
    return _finite_decimal(value, name, nonnegative=nonnegative)


def _nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DomainValidationError(f"{name} must be a nonnegative integer")
    return value


def _positive_int(value: object, name: str) -> int:
    result = _nonnegative_int(value, name)
    if result == 0:
        raise DomainValidationError(f"{name} must be greater than zero")
    return result


def _score_bp(value: object, name: str) -> int:
    result = _nonnegative_int(value, name)
    if result > SCORE_SCALE_BP:
        raise DomainValidationError(f"{name} must be between 0 and {SCORE_SCALE_BP}")
    return result


def _aware_utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DomainValidationError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _enum_member(value: object, enum_type: type[StrEnum], name: str) -> None:
    if not isinstance(value, enum_type):
        raise DomainValidationError(f"{name} must be a {enum_type.__name__} value")


def _boolean(value: object, name: str) -> None:
    if not isinstance(value, bool):
        raise DomainValidationError(f"{name} must be boolean")


def _validate_scalar(value: ScalarValue, name: str) -> ScalarValue:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, Decimal):
        return _finite_decimal(value, name)
    if isinstance(value, datetime):
        return _aware_utc(value, name)
    raise DomainValidationError(f"{name} has an unsupported value type")


def _validate_difference(value: DifferenceValue, name: str) -> DifferenceValue:
    if value is None or isinstance(value, timedelta):
        return value
    if isinstance(value, Decimal):
        return _finite_decimal(value, name)
    raise DomainValidationError(f"{name} must be Decimal, timedelta, or None")


def _unique(values: tuple[str, ...], name: str) -> tuple[str, ...]:
    if len(values) != len(set(values)):
        raise DomainValidationError(f"{name} must be unique")
    return values


@dataclass(frozen=True, slots=True)
class MatchRecord:
    observation_id: str
    logical_transaction_id: str
    source_record_key: str
    state: CanonicalState
    instrument: str | None
    side: CanonicalSide | None
    currency: str | None
    quantity: Decimal | None
    executed_at: datetime | None
    unit_price: Decimal | None = None
    gross_amount: Decimal | None = None
    reference_value: str | None = None
    shared_reference_alias: str | None = None

    def __post_init__(self) -> None:
        for name in ("observation_id", "logical_transaction_id", "source_record_key"):
            _required_text(getattr(self, name), name)
        for name in ("instrument", "currency", "reference_value", "shared_reference_alias"):
            _optional_text(getattr(self, name), name)
        _enum_member(self.state, CanonicalState, "state")
        if self.side is not None:
            _enum_member(self.side, CanonicalSide, "side")
        for name in ("quantity", "unit_price", "gross_amount"):
            _optional_decimal(getattr(self, name), name, nonnegative=True)
        if self.executed_at is not None:
            object.__setattr__(self, "executed_at", _aware_utc(self.executed_at, "executed_at"))

    @property
    def eligible(self) -> bool:
        return self.state is not CanonicalState.CANCELLED


@dataclass(frozen=True, slots=True)
class EngineSnapshot:
    left_revision_id: str
    right_revision_id: str
    left: tuple[MatchRecord, ...]
    right: tuple[MatchRecord, ...]

    def __post_init__(self) -> None:
        _required_text(self.left_revision_id, "left_revision_id")
        _required_text(self.right_revision_id, "right_revision_id")
        ordered_left = tuple(sorted(self.left, key=lambda record: record.observation_id))
        ordered_right = tuple(sorted(self.right, key=lambda record: record.observation_id))
        left_ids = tuple(record.observation_id for record in ordered_left)
        right_ids = tuple(record.observation_id for record in ordered_right)
        _unique(left_ids, "left observation identities")
        _unique(right_ids, "right observation identities")
        if set(left_ids).intersection(right_ids):
            raise DomainValidationError("observation identities must be unique across sides")
        object.__setattr__(self, "left", ordered_left)
        object.__setattr__(self, "right", ordered_right)

    @property
    def input_left_ids(self) -> tuple[str, ...]:
        return tuple(record.observation_id for record in self.left)

    @property
    def input_right_ids(self) -> tuple[str, ...]:
        return tuple(record.observation_id for record in self.right)


@dataclass(frozen=True, slots=True)
class ManualLink:
    decision_id: str
    revision_id: str
    left_id: str
    right_id: str

    def __post_init__(self) -> None:
        for name in ("decision_id", "revision_id", "left_id", "right_id"):
            _required_text(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class AcceptedUnmatched:
    decision_id: str
    revision_id: str
    record_id: str

    def __post_init__(self) -> None:
        for name in ("decision_id", "revision_id", "record_id"):
            _required_text(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class RejectedRelationship:
    decision_id: str
    revision_id: str
    left_id: str
    right_id: str

    def __post_init__(self) -> None:
        for name in ("decision_id", "revision_id", "left_id", "right_id"):
            _required_text(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class ReservedIdentity:
    decision_id: str
    revision_id: str
    record_id: str

    def __post_init__(self) -> None:
        for name in ("decision_id", "revision_id", "record_id"):
            _required_text(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class DecisionInputs:
    manual_links: tuple[ManualLink, ...] = ()
    accepted_unmatched: tuple[AcceptedUnmatched, ...] = ()
    rejected_relationships: tuple[RejectedRelationship, ...] = ()
    reserved_identities: tuple[ReservedIdentity, ...] = ()

    def __post_init__(self) -> None:
        manual = tuple(sorted(self.manual_links, key=lambda item: (item.left_id, item.right_id, item.decision_id)))
        accepted = tuple(sorted(self.accepted_unmatched, key=lambda item: (item.record_id, item.decision_id)))
        rejected = tuple(sorted(self.rejected_relationships, key=lambda item: (item.left_id, item.right_id, item.decision_id)))
        reserved = tuple(sorted(self.reserved_identities, key=lambda item: (item.record_id, item.decision_id)))
        decision_ids = tuple(
            item.decision_id for group in (manual, accepted, rejected, reserved) for item in group
        )
        _unique(decision_ids, "active decision identities")
        manual_left = tuple(item.left_id for item in manual)
        manual_right = tuple(item.right_id for item in manual)
        _unique(manual_left, "manual-link left identities")
        _unique(manual_right, "manual-link right identities")
        single_reservations = tuple(item.record_id for item in accepted) + tuple(
            item.record_id for item in reserved
        )
        _unique(single_reservations, "single-record reservation identities")
        manual_ids = set(manual_left) | set(manual_right)
        if manual_ids.intersection(single_reservations):
            raise DomainValidationError(
                "an identity cannot be both manually linked and singly reserved"
            )
        rejected_edges = tuple((item.left_id, item.right_id) for item in rejected)
        _unique(tuple(f"{left}\0{right}" for left, right in rejected_edges), "rejected relationships")
        object.__setattr__(self, "manual_links", manual)
        object.__setattr__(self, "accepted_unmatched", accepted)
        object.__setattr__(self, "rejected_relationships", rejected)
        object.__setattr__(self, "reserved_identities", reserved)


@dataclass(frozen=True, slots=True)
class BlockingPassPolicy:
    pass_id: str
    version: str
    time_window: timedelta | None
    require_instrument: bool = True
    require_side: bool = True
    require_currency: bool = True
    use_shared_alias: bool = False

    def __post_init__(self) -> None:
        _required_text(self.pass_id, "pass_id")
        _required_text(self.version, "blocking pass version")
        if self.time_window is not None and (
            not isinstance(self.time_window, timedelta)
            or self.time_window <= timedelta(0)
        ):
            raise DomainValidationError("blocking time_window must be None or greater than zero")
        for name in (
            "require_instrument",
            "require_side",
            "require_currency",
            "use_shared_alias",
        ):
            _boolean(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class NumericSimilarityPolicy:
    absolute_band: Decimal
    relative_band: Decimal = Decimal("0.01")

    def __post_init__(self) -> None:
        _finite_decimal(self.absolute_band, "absolute_band", nonnegative=True)
        relative = _finite_decimal(self.relative_band, "relative_band", nonnegative=True)
        if relative > 1:
            raise DomainValidationError("relative_band must be between zero and one")


@dataclass(frozen=True, slots=True)
class TimestampSimilarityPolicy:
    band: timedelta = timedelta(minutes=10)

    def __post_init__(self) -> None:
        if not isinstance(self.band, timedelta) or self.band < timedelta(0):
            raise DomainValidationError("timestamp similarity band must be nonnegative")


@dataclass(frozen=True, slots=True)
class FeatureWeight:
    feature: MatchFeature
    weight_bp: int

    def __post_init__(self) -> None:
        _enum_member(self.feature, MatchFeature, "feature")
        _score_bp(self.weight_bp, "feature weight_bp")


@dataclass(frozen=True, slots=True)
class CapacityLimits:
    max_component_nodes: int = 100
    max_component_edges: int = 2_500
    max_run_candidate_edges: int = 250_000
    max_candidates_per_record: int = 200

    def __post_init__(self) -> None:
        for name in (
            "max_component_nodes",
            "max_component_edges",
            "max_run_candidate_edges",
            "max_candidates_per_record",
        ):
            _positive_int(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class MatchingPolicy:
    policy_version: str
    engine_version: str
    solver_version: str
    reference_contract: ReferenceContract
    blocking_passes: tuple[BlockingPassPolicy, ...]
    feature_weights: tuple[FeatureWeight, ...]
    quantity_similarity: NumericSimilarityPolicy
    timestamp_similarity: TimestampSimilarityPolicy
    unit_price_similarity: NumericSimilarityPolicy
    gross_amount_similarity: NumericSimilarityPolicy
    assignment_floor_bp: int = INITIAL_ASSIGNMENT_FLOOR_BP
    automatic_threshold_bp: int = INITIAL_AUTOMATIC_THRESHOLD_BP
    minimum_global_gap_bp: int = INITIAL_GLOBAL_GAP_BP
    limits: CapacityLimits = CapacityLimits()

    def __post_init__(self) -> None:
        for name in ("policy_version", "engine_version", "solver_version"):
            _required_text(getattr(self, name), name)
        _enum_member(self.reference_contract, ReferenceContract, "reference_contract")
        if not self.blocking_passes:
            raise DomainValidationError("matching policy requires at least one blocking pass")
        ordered_passes = tuple(sorted(self.blocking_passes, key=lambda item: (item.pass_id, item.version)))
        _unique(tuple(item.pass_id for item in ordered_passes), "blocking pass identities")
        ordered_weights = tuple(sorted(self.feature_weights, key=lambda item: item.feature.value))
        features = tuple(item.feature.value for item in ordered_weights)
        _unique(features, "feature weights")
        if set(features) != {feature.value for feature in MatchFeature}:
            raise DomainValidationError("matching policy must weight every matching feature exactly once")
        if sum(item.weight_bp for item in ordered_weights) != SCORE_SCALE_BP:
            raise DomainValidationError(f"feature weights must total {SCORE_SCALE_BP} basis points")
        floor = _score_bp(self.assignment_floor_bp, "assignment_floor_bp")
        threshold = _score_bp(self.automatic_threshold_bp, "automatic_threshold_bp")
        gap = _score_bp(self.minimum_global_gap_bp, "minimum_global_gap_bp")
        if floor >= threshold:
            raise DomainValidationError("assignment floor must be lower than automatic threshold")
        if gap > threshold:
            raise DomainValidationError("minimum global gap cannot exceed automatic threshold")
        object.__setattr__(self, "blocking_passes", ordered_passes)
        object.__setattr__(self, "feature_weights", ordered_weights)

    @classmethod
    def initial_demo(
        cls,
        *,
        policy_version: str = "demo-matching-v1",
        engine_version: str = "reconciliation-engine-v1",
        solver_version: str = "scipy-1.18.1-linear-sum-assignment-v1",
        reference_contract: ReferenceContract = ReferenceContract.SHARED_MUST_AGREE,
    ) -> MatchingPolicy:
        return cls(
            policy_version=policy_version,
            engine_version=engine_version,
            solver_version=solver_version,
            reference_contract=reference_contract,
            blocking_passes=(
                BlockingPassPolicy(
                    pass_id="general-compatible-24h",
                    version="1",
                    time_window=timedelta(hours=24),
                ),
            ),
            feature_weights=(
                FeatureWeight(MatchFeature.QUANTITY, INITIAL_QUANTITY_WEIGHT_BP),
                FeatureWeight(MatchFeature.TIMESTAMP, INITIAL_TIMESTAMP_WEIGHT_BP),
                FeatureWeight(MatchFeature.UNIT_PRICE, INITIAL_UNIT_PRICE_WEIGHT_BP),
                FeatureWeight(MatchFeature.GROSS_AMOUNT, INITIAL_GROSS_AMOUNT_WEIGHT_BP),
            ),
            quantity_similarity=NumericSimilarityPolicy(Decimal("0")),
            timestamp_similarity=TimestampSimilarityPolicy(timedelta(minutes=10)),
            unit_price_similarity=NumericSimilarityPolicy(Decimal("0.01")),
            gross_amount_similarity=NumericSimilarityPolicy(Decimal("0.01")),
        )


@dataclass(frozen=True, slots=True)
class DecimalTolerance:
    absolute: Decimal
    relative: Decimal

    def __post_init__(self) -> None:
        _finite_decimal(self.absolute, "decimal tolerance absolute", nonnegative=True)
        relative = _finite_decimal(self.relative, "decimal tolerance relative", nonnegative=True)
        if relative > 1:
            raise DomainValidationError("decimal tolerance relative must be between zero and one")


@dataclass(frozen=True, slots=True)
class ComparisonPolicy:
    policy_version: str
    timestamp_tolerance: timedelta
    quantity_tolerance: DecimalTolerance
    unit_price_tolerance: DecimalTolerance
    gross_amount_tolerance: DecimalTolerance
    compatible_state_pairs: tuple[tuple[CanonicalState, CanonicalState], ...] = ()

    def __post_init__(self) -> None:
        _required_text(self.policy_version, "comparison policy_version")
        if not isinstance(self.timestamp_tolerance, timedelta) or self.timestamp_tolerance < timedelta(0):
            raise DomainValidationError("timestamp_tolerance must be nonnegative")
        normalized_pairs = tuple(
            sorted(
                set(self.compatible_state_pairs),
                key=lambda pair: (pair[0].value, pair[1].value),
            )
        )
        for left, right in normalized_pairs:
            _enum_member(left, CanonicalState, "compatible state left")
            _enum_member(right, CanonicalState, "compatible state right")
        object.__setattr__(self, "compatible_state_pairs", normalized_pairs)

    @classmethod
    def initial_demo(cls) -> ComparisonPolicy:
        return cls(
            policy_version="demo-comparison-v1",
            timestamp_tolerance=timedelta(seconds=60),
            quantity_tolerance=DecimalTolerance(Decimal("0.00000001"), Decimal("0")),
            unit_price_tolerance=DecimalTolerance(Decimal("0.01"), Decimal("0")),
            gross_amount_tolerance=DecimalTolerance(Decimal("0.05"), Decimal("0")),
            compatible_state_pairs=((CanonicalState.SETTLED, CanonicalState.SETTLED),),
        )


@dataclass(frozen=True, slots=True)
class FeatureEvidence:
    feature: MatchFeature
    left_value: ScalarValue
    right_value: ScalarValue
    difference: DifferenceValue
    band: Decimal | timedelta
    present: bool
    similarity_bp: int
    weight_bp: int
    contribution_bp: int
    rule: str

    def __post_init__(self) -> None:
        _enum_member(self.feature, MatchFeature, "feature")
        _score_bp(self.similarity_bp, "similarity_bp")
        _score_bp(self.weight_bp, "weight_bp")
        _score_bp(self.contribution_bp, "contribution_bp")
        _required_text(self.rule, "feature rule")
        _boolean(self.present, "feature present")
        if not self.present and (self.similarity_bp != 0 or self.contribution_bp != 0):
            raise DomainValidationError("a missing feature must contribute zero")
        if self.contribution_bp > self.weight_bp:
            raise DomainValidationError("feature contribution cannot exceed its weight")
        if isinstance(self.band, Decimal):
            _finite_decimal(self.band, "feature band", nonnegative=True)
        elif not isinstance(self.band, timedelta) or self.band < timedelta(0):
            raise DomainValidationError("feature band must be a nonnegative Decimal or timedelta")
        object.__setattr__(self, "left_value", _validate_scalar(self.left_value, "feature left_value"))
        object.__setattr__(self, "right_value", _validate_scalar(self.right_value, "feature right_value"))
        object.__setattr__(self, "difference", _validate_difference(self.difference, "feature difference"))
        if self.feature is MatchFeature.TIMESTAMP:
            values_valid = all(
                value is None or isinstance(value, datetime)
                for value in (self.left_value, self.right_value)
            )
            shape_valid = isinstance(self.band, timedelta) and (
                self.difference is None or isinstance(self.difference, timedelta)
            )
        else:
            values_valid = all(
                value is None or isinstance(value, Decimal)
                for value in (self.left_value, self.right_value)
            )
            shape_valid = isinstance(self.band, Decimal) and (
                self.difference is None or isinstance(self.difference, Decimal)
            )
        if not values_valid or not shape_valid:
            raise DomainValidationError("feature evidence values, difference, and band must match its feature")
        values_present = self.left_value is not None and self.right_value is not None
        if self.present != values_present or self.present != (self.difference is not None):
            raise DomainValidationError("feature presence must match its values and difference")


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    left_id: str
    right_id: str
    blocking_reasons: tuple[str, ...]
    features: tuple[FeatureEvidence, ...]
    contradictions: tuple[str, ...]
    coverage_failures: tuple[str, ...]
    coverage_sufficient: bool
    complete_computation: bool
    score_bp: int
    score_label: str = "Rule score"

    def __post_init__(self) -> None:
        _required_text(self.left_id, "candidate left_id")
        _required_text(self.right_id, "candidate right_id")
        if not self.blocking_reasons:
            raise DomainValidationError("candidate evidence requires a blocking reason")
        reasons = tuple(sorted({_required_text(value, "blocking reason") for value in self.blocking_reasons}))
        contradictions = tuple(sorted({_required_text(value, "contradiction") for value in self.contradictions}))
        coverage_failures = tuple(
            sorted({_required_text(value, "coverage failure") for value in self.coverage_failures})
        )
        ordered_features = tuple(sorted(self.features, key=lambda item: item.feature.value))
        feature_names = tuple(item.feature.value for item in ordered_features)
        _unique(feature_names, "candidate feature evidence")
        if set(feature_names) != {feature.value for feature in MatchFeature}:
            raise DomainValidationError("candidate evidence must record every matching feature")
        score = _score_bp(self.score_bp, "candidate score_bp")
        if score != sum(item.contribution_bp for item in ordered_features):
            raise DomainValidationError("candidate score must equal feature contributions")
        _boolean(self.coverage_sufficient, "candidate coverage_sufficient")
        _boolean(self.complete_computation, "candidate complete_computation")
        if self.coverage_sufficient == bool(coverage_failures):
            raise DomainValidationError(
                "coverage_sufficient must be true exactly when coverage failures are empty"
            )
        if self.score_label != "Rule score":
            raise DomainValidationError("candidate score label must be 'Rule score'")
        object.__setattr__(self, "blocking_reasons", reasons)
        object.__setattr__(self, "features", ordered_features)
        object.__setattr__(self, "contradictions", contradictions)
        object.__setattr__(self, "coverage_failures", coverage_failures)


@dataclass(frozen=True, slots=True)
class ProposalEvidence:
    left_id: str
    right_id: str
    score_bp: int
    counterfactual_objective_bp: int
    global_gap_bp: int
    accepted: bool
    gate_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        _required_text(self.left_id, "proposal left_id")
        _required_text(self.right_id, "proposal right_id")
        _score_bp(self.score_bp, "proposal score_bp")
        _nonnegative_int(self.counterfactual_objective_bp, "counterfactual_objective_bp")
        _nonnegative_int(self.global_gap_bp, "global_gap_bp")
        _boolean(self.accepted, "proposal accepted")
        reasons = tuple(sorted({_required_text(value, "gate reason") for value in self.gate_reasons}))
        if self.accepted and reasons:
            raise DomainValidationError("an accepted proposal cannot contain failing gate reasons")
        if not self.accepted and not reasons:
            raise DomainValidationError("a rejected proposal requires at least one gate reason")
        object.__setattr__(self, "gate_reasons", reasons)


@dataclass(frozen=True, slots=True)
class AssignmentComponentEvidence:
    component_id: str
    graph_digest: str
    solver_version: str
    left_ids: tuple[str, ...]
    right_ids: tuple[str, ...]
    candidate_count: int
    optimal_utility_bp: int
    complete: bool
    limit_reason: str | None
    proposals: tuple[ProposalEvidence, ...]

    def __post_init__(self) -> None:
        for name in ("component_id", "graph_digest", "solver_version"):
            _required_text(getattr(self, name), name)
        left_ids = tuple(sorted(self.left_ids))
        right_ids = tuple(sorted(self.right_ids))
        _unique(left_ids, "component left identities")
        _unique(right_ids, "component right identities")
        if not left_ids and not right_ids:
            raise DomainValidationError("assignment component cannot be empty")
        _nonnegative_int(self.candidate_count, "candidate_count")
        _nonnegative_int(self.optimal_utility_bp, "optimal_utility_bp")
        _boolean(self.complete, "component complete")
        reason = _optional_text(self.limit_reason, "limit_reason")
        if self.complete == (reason is not None):
            raise DomainValidationError("complete components have no limit reason; incomplete components require one")
        proposals = tuple(sorted(self.proposals, key=lambda item: (item.left_id, item.right_id)))
        proposal_edges = tuple(f"{item.left_id}\0{item.right_id}" for item in proposals)
        _unique(proposal_edges, "component proposals")
        if not self.complete and proposals:
            raise DomainValidationError("an incomplete component cannot contain proposals")
        if any(
            item.left_id not in left_ids or item.right_id not in right_ids
            for item in proposals
        ):
            raise DomainValidationError("component proposals must reference component members")
        if any(
            item.counterfactual_objective_bp > self.optimal_utility_bp
            or item.global_gap_bp
            != self.optimal_utility_bp - item.counterfactual_objective_bp
            for item in proposals
        ):
            raise DomainValidationError(
                "component proposal gaps must equal base minus counterfactual objective"
            )
        object.__setattr__(self, "left_ids", left_ids)
        object.__setattr__(self, "right_ids", right_ids)
        object.__setattr__(self, "proposals", proposals)


@dataclass(frozen=True, slots=True)
class FieldComparison:
    field: str
    status: ComparisonStatus
    left_value: ScalarValue
    right_value: ScalarValue
    signed_difference: DifferenceValue
    allowed_difference: DifferenceValue
    explanation: str

    def __post_init__(self) -> None:
        _required_text(self.field, "comparison field")
        _enum_member(self.status, ComparisonStatus, "comparison status")
        _required_text(self.explanation, "comparison explanation")
        object.__setattr__(self, "left_value", _validate_scalar(self.left_value, "comparison left_value"))
        object.__setattr__(self, "right_value", _validate_scalar(self.right_value, "comparison right_value"))
        signed = _validate_difference(self.signed_difference, "comparison signed_difference")
        allowed = _validate_difference(self.allowed_difference, "comparison allowed_difference")
        if (signed is None) != (allowed is None):
            raise DomainValidationError(
                "comparison signed and allowed differences must both be present or absent"
            )
        if signed is not None and type(signed) is not type(allowed):
            raise DomainValidationError(
                "comparison signed and allowed differences must have the same type"
            )
        if isinstance(allowed, Decimal) and allowed < 0:
            raise DomainValidationError("comparison allowed decimal difference must be nonnegative")
        if isinstance(allowed, timedelta) and allowed < timedelta(0):
            raise DomainValidationError("comparison allowed elapsed difference must be nonnegative")
        if self.status in (ComparisonStatus.MISSING, ComparisonStatus.NOT_COMPARABLE) and (
            signed is not None or allowed is not None
        ):
            raise DomainValidationError(
                "missing and not-comparable comparisons cannot contain calculated differences"
            )
        object.__setattr__(self, "signed_difference", signed)
        object.__setattr__(self, "allowed_difference", allowed)


@dataclass(frozen=True, slots=True)
class PairOutcome:
    left_id: str
    right_id: str
    origin: PairOrigin
    score_bp: int | None = None
    global_gap_bp: int | None = None
    comparisons: tuple[FieldComparison, ...] = ()

    def __post_init__(self) -> None:
        _required_text(self.left_id, "pair left_id")
        _required_text(self.right_id, "pair right_id")
        _enum_member(self.origin, PairOrigin, "pair origin")
        if self.origin is PairOrigin.WEIGHTED_GLOBAL:
            if self.score_bp is None or self.global_gap_bp is None:
                raise DomainValidationError("weighted-global pairs require score and global gap")
            _score_bp(self.score_bp, "pair score_bp")
            _nonnegative_int(self.global_gap_bp, "pair global_gap_bp")
        elif self.score_bp is not None or self.global_gap_bp is not None:
            raise DomainValidationError("manual and authoritative pairs do not carry heuristic scores")
        comparisons = tuple(sorted(self.comparisons, key=lambda item: item.field))
        _unique(tuple(item.field for item in comparisons), "pair comparison fields")
        object.__setattr__(self, "comparisons", comparisons)


@dataclass(frozen=True, slots=True)
class UnpairedOutcome:
    record_id: str
    side: RecordSide
    reason: UnpairedReason
    explanation: str
    related_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _required_text(self.record_id, "unpaired record_id")
        _enum_member(self.side, RecordSide, "unpaired side")
        _enum_member(self.reason, UnpairedReason, "unpaired reason")
        _required_text(self.explanation, "unpaired explanation")
        related = tuple(sorted(self.related_ids))
        _unique(related, "unpaired related identities")
        object.__setattr__(self, "related_ids", related)


@dataclass(frozen=True, slots=True)
class DecisionHealthDiagnostic:
    kind: DiagnosticKind
    record_id: str
    candidate_id: str | None
    candidate_current_pair_id: str | None
    complete: bool
    explanation: str

    def __post_init__(self) -> None:
        _enum_member(self.kind, DiagnosticKind, "diagnostic kind")
        _required_text(self.record_id, "diagnostic record_id")
        _optional_text(self.candidate_id, "diagnostic candidate_id")
        _optional_text(self.candidate_current_pair_id, "diagnostic candidate_current_pair_id")
        _required_text(self.explanation, "diagnostic explanation")
        _boolean(self.complete, "diagnostic complete")


@dataclass(frozen=True, slots=True)
class EngineResult:
    left_revision_id: str
    right_revision_id: str
    matching_policy_version: str
    comparison_policy_version: str
    engine_version: str
    solver_version: str
    input_left_ids: tuple[str, ...]
    input_right_ids: tuple[str, ...]
    pairs: tuple[PairOutcome, ...]
    unpaired: tuple[UnpairedOutcome, ...]
    candidates: tuple[CandidateEvidence, ...] = ()
    components: tuple[AssignmentComponentEvidence, ...] = ()
    diagnostics: tuple[DecisionHealthDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "left_revision_id",
            "right_revision_id",
            "matching_policy_version",
            "comparison_policy_version",
            "engine_version",
            "solver_version",
        ):
            _required_text(getattr(self, name), name)
        left_ids = tuple(sorted(self.input_left_ids))
        right_ids = tuple(sorted(self.input_right_ids))
        _unique(left_ids, "result input left identities")
        _unique(right_ids, "result input right identities")
        if set(left_ids).intersection(right_ids):
            raise DomainValidationError("result input identities must be unique across sides")
        pairs = tuple(sorted(self.pairs, key=lambda item: (item.left_id, item.right_id, item.origin.value)))
        unpaired = tuple(sorted(self.unpaired, key=lambda item: (item.side.value, item.record_id)))
        candidates = tuple(sorted(self.candidates, key=lambda item: (item.left_id, item.right_id)))
        components = tuple(sorted(self.components, key=lambda item: item.component_id))
        diagnostics = tuple(
            sorted(
                self.diagnostics,
                key=lambda item: (item.record_id, item.candidate_id or "", item.kind.value),
            )
        )
        paired_left = tuple(item.left_id for item in pairs)
        paired_right = tuple(item.right_id for item in pairs)
        _unique(paired_left, "paired left identities")
        _unique(paired_right, "paired right identities")
        unpaired_left = tuple(item.record_id for item in unpaired if item.side is RecordSide.LEFT)
        unpaired_right = tuple(item.record_id for item in unpaired if item.side is RecordSide.RIGHT)
        _unique(unpaired_left, "unpaired left identities")
        _unique(unpaired_right, "unpaired right identities")
        if set(paired_left).intersection(unpaired_left) or set(paired_right).intersection(unpaired_right):
            raise DomainValidationError("a record cannot be both paired and unpaired")
        terminal_left = set(paired_left) | set(unpaired_left)
        terminal_right = set(paired_right) | set(unpaired_right)
        if terminal_left != set(left_ids) or terminal_right != set(right_ids):
            raise DomainValidationError(
                "every input record must have exactly one terminal pair or unpaired outcome"
            )
        candidate_edges = tuple(f"{item.left_id}\0{item.right_id}" for item in candidates)
        _unique(candidate_edges, "candidate edges")
        if any(
            item.left_id not in left_ids or item.right_id not in right_ids
            for item in candidates
        ):
            raise DomainValidationError("candidate edges must reference result inputs")
        component_ids = tuple(item.component_id for item in components)
        _unique(component_ids, "assignment component identities")
        if any(
            not set(item.left_ids).issubset(left_ids)
            or not set(item.right_ids).issubset(right_ids)
            for item in components
        ):
            raise DomainValidationError("assignment components must reference result inputs")
        candidate_by_edge = {
            (item.left_id, item.right_id): item for item in candidates
        }
        proposals = tuple(
            proposal for component in components for proposal in component.proposals
        )
        if any(
            (item.left_id, item.right_id) not in candidate_by_edge
            or candidate_by_edge[(item.left_id, item.right_id)].score_bp != item.score_bp
            for item in proposals
        ):
            raise DomainValidationError(
                "assignment proposals must match result candidate evidence"
            )
        accepted_by_edge = {
            (item.left_id, item.right_id): item for item in proposals if item.accepted
        }
        weighted_by_edge = {
            (item.left_id, item.right_id): item
            for item in pairs
            if item.origin is PairOrigin.WEIGHTED_GLOBAL
        }
        if set(accepted_by_edge) != set(weighted_by_edge) or any(
            weighted_by_edge[edge].score_bp != proposal.score_bp
            or weighted_by_edge[edge].global_gap_bp != proposal.global_gap_bp
            for edge, proposal in accepted_by_edge.items()
        ):
            raise DomainValidationError(
                "weighted-global pairs must exactly match accepted assignment proposals"
            )
        object.__setattr__(self, "input_left_ids", left_ids)
        object.__setattr__(self, "input_right_ids", right_ids)
        object.__setattr__(self, "pairs", pairs)
        object.__setattr__(self, "unpaired", unpaired)
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "components", components)
        object.__setattr__(self, "diagnostics", diagnostics)
