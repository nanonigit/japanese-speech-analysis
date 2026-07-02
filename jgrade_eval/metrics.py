from __future__ import annotations

from typing import Any

from .models import BenchmarkItem, Rating


LABELS = [Rating.EXCELLENT, Rating.PASS, Rating.NEAR_FAIL, Rating.FAIL]


def evaluate_against_humans(items: list[BenchmarkItem]) -> dict[str, Any]:
    """Compare AI consensus ratings against human teacher benchmark labels."""
    y_true = [item.human_rating for item in items]
    y_pred = [item.ai_rating for item in items]
    matrix = _confusion_matrix(y_true, y_pred)
    per_label = _per_label_metrics(matrix)
    total = len(items)
    correct = sum(true == pred for true, pred in zip(y_true, y_pred, strict=True))
    support = {label.value: sum(row) for label, row in zip(LABELS, matrix, strict=True)}

    macro_f1 = _safe_mean(label_metrics["f1"] for label_metrics in per_label.values())
    weighted_f1 = (
        sum(per_label[label.value]["f1"] * support[label.value] for label in LABELS)
        / total
        if total
        else 0.0
    )

    boundary_confusions = [
        item.sample_id
        for item in items
        if {item.human_rating, item.ai_rating} == {Rating.PASS, Rating.NEAR_FAIL}
    ]

    return {
        "n": total,
        "accuracy": correct / total if total else 0.0,
        "macro_f1": macro_f1,
        "weighted_f1": weighted_f1,
        "labels": [label.value for label in LABELS],
        "confusion_matrix": matrix,
        "per_label": per_label,
        "judge_disagreement_rate": (
            sum(item.judge_disagreement for item in items) / total if total else 0.0
        ),
        "boundary_confusions_pass_vs_near_fail": boundary_confusions,
        "mismatched_samples": [
            item.sample_id
            for item in items
            if item.human_rating != item.ai_rating
        ],
    }


def load_benchmark_items(payload: dict[str, Any] | list[dict[str, Any]]) -> list[BenchmarkItem]:
    records = payload["items"] if isinstance(payload, dict) else payload
    return [BenchmarkItem.from_dict(record) for record in records]


def _confusion_matrix(y_true: list[Rating], y_pred: list[Rating]) -> list[list[int]]:
    indexes = {label: index for index, label in enumerate(LABELS)}
    matrix = [[0 for _ in LABELS] for _ in LABELS]
    for true, pred in zip(y_true, y_pred, strict=True):
        matrix[indexes[true]][indexes[pred]] += 1
    return matrix


def _per_label_metrics(matrix: list[list[int]]) -> dict[str, dict[str, float]]:
    metrics: dict[str, dict[str, float]] = {}
    for index, label in enumerate(LABELS):
        true_positive = matrix[index][index]
        false_positive = sum(row[index] for row_index, row in enumerate(matrix) if row_index != index)
        false_negative = sum(value for col_index, value in enumerate(matrix[index]) if col_index != index)
        precision = _safe_div(true_positive, true_positive + false_positive)
        recall = _safe_div(true_positive, true_positive + false_negative)
        f1 = _safe_div(2 * precision * recall, precision + recall)
        metrics[label.value] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": float(sum(matrix[index])),
        }
    return metrics


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _safe_mean(values: Any) -> float:
    values_list = list(values)
    return sum(values_list) / len(values_list) if values_list else 0.0
