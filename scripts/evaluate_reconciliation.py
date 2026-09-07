"""Reproducible labelled synthetic evaluation and bounded capacity measurement."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import tracemalloc
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from reconciliation.domain import (
    CanonicalSide, CanonicalState, ComparisonPolicy, DecisionInputs, EngineSnapshot,
    MatchRecord, MatchingPolicy, PairOrigin, reconcile,
)
from reconciliation.solvers import ScipyAssignmentSolver

NOW = datetime(2026, 9, 7, 12, tzinfo=UTC)


def record(identity: str, instrument: str, reference: str | None = None) -> MatchRecord:
    return MatchRecord(identity, f"logical-{identity}", f"source-{identity}",
        CanonicalState.SETTLED, instrument, CanonicalSide.BUY, "USD", Decimal("2"),
        NOW, Decimal("100"), Decimal("200"), reference, None)


def corpus():
    left, right, truth, heuristic_truth = [], [], set(), set()
    for index in range(10):
        l, r = f"LA{index}", f"RA{index}"
        left.append(record(l, f"AUTH-{index}", f"T-{index}")); right.append(record(r, f"AUTH-{index}", f"T-{index}"))
        truth.add((l, r))
    for index in range(10):
        l, r = f"LH{index}", f"RH{index}"
        left.append(record(l, f"HEUR-{index}")); right.append(record(r, f"HEUR-{index}"))
        truth.add((l, r)); heuristic_truth.add((l, r))
    for group in range(5):
        l1, l2, r1, r2 = f"LX{group}a", f"LX{group}b", f"RX{group}a", f"RX{group}b"
        instrument = f"AMB-{group}"
        left.extend((record(l1, instrument), record(l2, instrument)))
        right.extend((record(r1, instrument), record(r2, instrument)))
        truth.update(((l1, r2), (l2, r1))); heuristic_truth.update(((l1, r2), (l2, r1)))
    for index in range(5):
        left.append(record(f"LN{index}", f"LEFT-NOISE-{index}"))
        right.append(record(f"RN{index}", f"RIGHT-NOISE-{index}"))
    return tuple(left), tuple(right), truth, heuristic_truth


def metric(predictions, truth, eligible_truth, candidate_edges, heuristic_truth, total_records):
    correct = len(predictions & truth)
    return {
        "automatic_precision": {"numerator": correct, "denominator": len(predictions), "percent": None if not predictions else round(100 * correct / len(predictions), 4)},
        "automatic_recall": {"numerator": correct, "denominator": len(eligible_truth), "percent": round(100 * correct / len(eligible_truth), 4)},
        "candidate_recall": {"numerator": len(candidate_edges & heuristic_truth), "denominator": len(heuristic_truth), "percent": round(100 * len(candidate_edges & heuristic_truth) / len(heuristic_truth), 4)},
        "false_automatic_matches": len(predictions - truth),
        "review_rate": {"numerator": total_records - 2 * len(predictions), "denominator": total_records, "percent": round(100 * (total_records - 2 * len(predictions)) / total_records, 4)},
        "workflow_coverage_percent": 100.0,
    }


def evaluate():
    left, right, truth, heuristic_truth = corpus(); policy = MatchingPolicy.initial_demo()
    started = perf_counter()
    result = reconcile(snapshot=EngineSnapshot("synthetic-left-v1", "synthetic-right-v1", left, right), matching_policy=policy, comparison_policy=ComparisonPolicy.initial_demo(), decisions=DecisionInputs(), solver=ScipyAssignmentSolver())
    runtime = perf_counter() - started
    candidate_edges = {(c.left_id, c.right_id) for c in result.candidates}
    exact = {(p.left_id, p.right_id) for p in result.pairs if p.origin is PairOrigin.AUTHORITATIVE_REFERENCE}
    advanced = {(p.left_id, p.right_id) for p in result.pairs}
    used_left, used_right, greedy = set(), set(), set(exact)
    for edge in sorted(result.candidates, key=lambda c: (-c.score_bp, c.left_id, c.right_id)):
        if edge.score_bp < policy.automatic_threshold_bp or not edge.coverage_sufficient or edge.contradictions or edge.left_id in used_left or edge.right_id in used_right:
            continue
        greedy.add((edge.left_id, edge.right_id)); used_left.add(edge.left_id); used_right.add(edge.right_id)
    total = len(left) + len(right)
    return {"label": "synthetic-v1-not-production-accuracy", "records_per_side": len(left), "eligible_truth_pairs": len(truth), "heuristic_truth_pairs": len(heuristic_truth), "runtime_seconds": round(runtime, 6), "strategies": {
        "exact_reference": metric(exact, truth, truth, set(), heuristic_truth, total),
        "greedy_weighted": metric(greedy, truth, truth, candidate_edges, heuristic_truth, total),
        "weighted_global_abstention": metric(advanced, truth, truth, candidate_edges, heuristic_truth, total),
    }}


def capacity():
    left = tuple(record(f"CL{i:05d}", "DENSE") for i in range(10_000)); right = tuple(record(f"CR{i:05d}", "DENSE") for i in range(10_000))
    tracemalloc.start(); started = perf_counter()
    result = reconcile(snapshot=EngineSnapshot("capacity-left", "capacity-right", left, right), matching_policy=MatchingPolicy.initial_demo(), comparison_policy=ComparisonPolicy.initial_demo(), decisions=DecisionInputs(), solver=ScipyAssignmentSolver())
    runtime = perf_counter() - started; _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
    return {"rows_per_side": 10_000, "cartesian_relationships": 100_000_000, "retained_candidates": len(result.candidates), "component_count": len(result.components), "incomplete_components": sum(not c.complete for c in result.components), "automatic_pairs": len(result.pairs), "computation_limited_records": sum(u.reason.value == "COMPUTATION_LIMITED" for u in result.unpaired), "runtime_seconds": round(runtime, 6), "tracemalloc_peak_mib": round(peak / 1024 / 1024, 3), "cpu_count": os.cpu_count(), "platform": platform.platform()}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True); parser.add_argument("--skip-capacity", action="store_true"); args = parser.parse_args()
    payload = {"evaluation": evaluate(), "capacity": None if args.skip_capacity else capacity()}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"); print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__": main()
