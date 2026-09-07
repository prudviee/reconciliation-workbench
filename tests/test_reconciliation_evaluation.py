from scripts.evaluate_reconciliation import evaluate


def test_labelled_synthetic_metric_denominators_and_expected_results() -> None:
    result = evaluate()
    assert result["label"] == "synthetic-v1-not-production-accuracy"
    assert result["eligible_truth_pairs"] == 30
    assert result["heuristic_truth_pairs"] == 20
    exact = result["strategies"]["exact_reference"]
    greedy = result["strategies"]["greedy_weighted"]
    advanced = result["strategies"]["weighted_global_abstention"]
    assert exact["automatic_precision"] == {"numerator": 10, "denominator": 10, "percent": 100.0}
    assert exact["automatic_recall"]["denominator"] == 30
    assert greedy["false_automatic_matches"] == 10
    assert advanced["automatic_precision"] == {"numerator": 20, "denominator": 20, "percent": 100.0}
    assert advanced["automatic_recall"] == {"numerator": 20, "denominator": 30, "percent": 66.6667}
    assert advanced["candidate_recall"] == {"numerator": 20, "denominator": 20, "percent": 100.0}
