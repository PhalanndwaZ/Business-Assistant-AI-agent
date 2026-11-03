from __future__ import annotations

from typing import Any, Iterable, Sequence


def agreement_rate(labels: Sequence[bool], predictions: Sequence[bool]) -> float:
    """Return the fraction of labels matched by the judge predictions."""
    if not labels or not predictions:
        return 0.0
    if len(labels) != len(predictions):
        raise ValueError("Labels and predictions must be the same length.")
    matches = sum(1 for left, right in zip(labels, predictions) if left == right)
    return matches / len(labels)


def calibrate_judgements(
    labelled: Iterable[tuple[bool, bool]],
) -> dict[str, float]:
    """Summarize agreement for a set of labeled judge results."""
    pairs = list(labelled)
    if not pairs:
        return {"agreement_rate": 0.0, "count": 0}
    labels = [case for case, _ in pairs]
    predictions = [pred for _, pred in pairs]
    return {
        "agreement_rate": agreement_rate(labels, predictions),
        "count": len(pairs),
    }


def evaluate_calibration(labels: Sequence[bool], predictions: Sequence[bool]) -> dict[str, Any]:
    """Convenience wrapper returning the agreement rate and sample count."""
    return calibrate_judgements(zip(labels, predictions))
