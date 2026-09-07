"""Lossless adapters between persisted policy JSON and domain policies."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from reconciliation.domain import (
    BlockingPassPolicy,
    CapacityLimits,
    CanonicalState,
    ComparisonPolicy,
    DecimalTolerance,
    FeatureWeight,
    MatchFeature,
    MatchingPolicy,
    NumericSimilarityPolicy,
    ReferenceContract,
    TimestampSimilarityPolicy,
)


def matching_policy_to_payload(policy: MatchingPolicy) -> dict[str, Any]:
    return {
        "policy_version": policy.policy_version,
        "engine_version": policy.engine_version,
        "solver_version": policy.solver_version,
        "reference_contract": policy.reference_contract.value,
        "blocking_passes": [
            {
                "pass_id": item.pass_id,
                "version": item.version,
                "time_window_microseconds": _duration_microseconds(item.time_window),
                "require_instrument": item.require_instrument,
                "require_side": item.require_side,
                "require_currency": item.require_currency,
                "use_shared_alias": item.use_shared_alias,
            }
            for item in policy.blocking_passes
        ],
        "feature_weights": [
            {"feature": item.feature.value, "weight_bp": item.weight_bp}
            for item in policy.feature_weights
        ],
        "quantity_similarity": _numeric_payload(policy.quantity_similarity),
        "timestamp_similarity": {
            "band_microseconds": _duration_microseconds(policy.timestamp_similarity.band)
        },
        "unit_price_similarity": _numeric_payload(policy.unit_price_similarity),
        "gross_amount_similarity": _numeric_payload(policy.gross_amount_similarity),
        "assignment_floor_bp": policy.assignment_floor_bp,
        "automatic_threshold_bp": policy.automatic_threshold_bp,
        "minimum_global_gap_bp": policy.minimum_global_gap_bp,
        "limits": {
            "max_component_nodes": policy.limits.max_component_nodes,
            "max_component_edges": policy.limits.max_component_edges,
            "max_run_candidate_edges": policy.limits.max_run_candidate_edges,
            "max_candidates_per_record": policy.limits.max_candidates_per_record,
        },
    }


def matching_policy_from_payload(payload: dict[str, Any]) -> MatchingPolicy:
    return MatchingPolicy(
        policy_version=str(payload["policy_version"]),
        engine_version=str(payload["engine_version"]),
        solver_version=str(payload["solver_version"]),
        reference_contract=ReferenceContract(payload["reference_contract"]),
        blocking_passes=tuple(
            BlockingPassPolicy(
                pass_id=str(item["pass_id"]),
                version=str(item["version"]),
                time_window=_microseconds_duration(item["time_window_microseconds"]),
                require_instrument=bool(item["require_instrument"]),
                require_side=bool(item["require_side"]),
                require_currency=bool(item["require_currency"]),
                use_shared_alias=bool(item["use_shared_alias"]),
            )
            for item in payload["blocking_passes"]
        ),
        feature_weights=tuple(
            FeatureWeight(MatchFeature(item["feature"]), int(item["weight_bp"]))
            for item in payload["feature_weights"]
        ),
        quantity_similarity=_numeric_from_payload(payload["quantity_similarity"]),
        timestamp_similarity=TimestampSimilarityPolicy(
            _microseconds_duration(payload["timestamp_similarity"]["band_microseconds"])
        ),
        unit_price_similarity=_numeric_from_payload(payload["unit_price_similarity"]),
        gross_amount_similarity=_numeric_from_payload(payload["gross_amount_similarity"]),
        assignment_floor_bp=int(payload["assignment_floor_bp"]),
        automatic_threshold_bp=int(payload["automatic_threshold_bp"]),
        minimum_global_gap_bp=int(payload["minimum_global_gap_bp"]),
        limits=CapacityLimits(**{key: int(value) for key, value in payload["limits"].items()}),
    )


def comparison_policy_to_payload(policy: ComparisonPolicy) -> dict[str, Any]:
    return {
        "policy_version": policy.policy_version,
        "timestamp_tolerance_microseconds": _duration_microseconds(policy.timestamp_tolerance),
        "quantity_tolerance": _tolerance_payload(policy.quantity_tolerance),
        "unit_price_tolerance": _tolerance_payload(policy.unit_price_tolerance),
        "gross_amount_tolerance": _tolerance_payload(policy.gross_amount_tolerance),
        "compatible_state_pairs": [
            [left.value, right.value] for left, right in policy.compatible_state_pairs
        ],
    }


def comparison_policy_from_payload(payload: dict[str, Any]) -> ComparisonPolicy:
    return ComparisonPolicy(
        policy_version=str(payload["policy_version"]),
        timestamp_tolerance=_microseconds_duration(payload["timestamp_tolerance_microseconds"]),
        quantity_tolerance=_tolerance_from_payload(payload["quantity_tolerance"]),
        unit_price_tolerance=_tolerance_from_payload(payload["unit_price_tolerance"]),
        gross_amount_tolerance=_tolerance_from_payload(payload["gross_amount_tolerance"]),
        compatible_state_pairs=tuple(
            (CanonicalState(left), CanonicalState(right))
            for left, right in payload.get("compatible_state_pairs", ())
        ),
    )


def _numeric_payload(policy: NumericSimilarityPolicy) -> dict[str, str]:
    return {"absolute_band": str(policy.absolute_band), "relative_band": str(policy.relative_band)}


def _numeric_from_payload(payload: dict[str, Any]) -> NumericSimilarityPolicy:
    return NumericSimilarityPolicy(Decimal(str(payload["absolute_band"])), Decimal(str(payload["relative_band"])))


def _tolerance_payload(tolerance: DecimalTolerance) -> dict[str, str]:
    return {"absolute": str(tolerance.absolute), "relative": str(tolerance.relative)}


def _tolerance_from_payload(payload: dict[str, Any]) -> DecimalTolerance:
    return DecimalTolerance(Decimal(str(payload["absolute"])), Decimal(str(payload["relative"])))


def _duration_microseconds(value: timedelta | None) -> int | None:
    if value is None:
        return None
    return value.days * 86_400_000_000 + value.seconds * 1_000_000 + value.microseconds


def _microseconds_duration(value: Any) -> timedelta | None:
    return None if value is None else timedelta(microseconds=int(value))
