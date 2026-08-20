from __future__ import annotations

from typing import Any, Callable, Iterable


def evaluate_scenarios(
    records: Iterable[dict[str, Any]],
    predict: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    tp = fp = tn = fn = 0
    routing_violations = 0
    results: list[dict[str, Any]] = []
    for record in records:
        request = record["request"]
        expected = bool(record["expected_fraud_suspected"])
        response = predict(request)
        predicted = bool(response.get("fraud_suspected"))
        tp += predicted and expected
        fp += predicted and not expected
        tn += not predicted and not expected
        fn += not predicted and expected
        if predicted and (not response.get("requires_human_review") or response.get("routing") != "human_review"):
            routing_violations += 1
        results.append({"claim_id": request.get("claim_id"), "expected": expected, "predicted": predicted, "reason_codes": response.get("fraud_reason_codes", [])})
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "true_positive": tp, "false_positive": fp, "true_negative": tn, "false_negative": fn,
        "precision": round(precision, 4), "recall": round(recall, 4),
        "f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0,
        "routing_invariant_violations": routing_violations, "results": results,
    }
