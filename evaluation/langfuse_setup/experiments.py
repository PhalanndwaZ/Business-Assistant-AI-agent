from __future__ import annotations

import datetime as dt
import subprocess
from typing import Any, Iterable, Sequence

from evaluation.langfuse_setup.tracing import create_langfuse_client, tracing_enabled
from evaluation.runner.schema import EvaluationCase

__all__ = [
    "build_case_dataset_item",
    "build_experiment_run_name",
    "sync_cases_to_dataset",
    "run_evaluation_experiment",
]


def _git_commit() -> str | None:
    """Return the current HEAD hash when the repository is available."""
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value[:7] if value else None


def build_experiment_run_name(
    *,
    provider: str | None = None,
    config_version: str | None = None,
) -> str:
    """Create a stable, readable run name for Langfuse experiments."""
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    parts = ["eval", stamp]
    if provider:
        parts.append(provider)
    if config_version:
        parts.append(config_version)
    commit = _git_commit()
    if commit:
        parts.append(commit)
    return "-".join(parts)


def build_case_dataset_item(case: EvaluationCase) -> dict[str, Any]:
    """Convert one validated evaluation case to the Langfuse dataset item format."""
    turns = [
        {"q": turn.question, "conversation": turn.conversation}
        for turn in case.turns
    ]
    return {
        "id": case.case_id,
        "input": {
            "role": case.role,
            "group": case.group,
            "severity": case.severity,
            "status": case.status,
            "setup": [],
            "turns": turns,
        },
        "expected_output": case.expect,
        "metadata": {
            "case_id": case.case_id,
            "group": case.group,
            "role": case.role,
            "severity": case.severity,
            "status": case.status,
            "runs": str(case.runs),
        },
    }


def sync_cases_to_dataset(
    dataset_name: str,
    cases: Sequence[EvaluationCase] | Iterable[EvaluationCase],
    *,
    description: str | None = None,
) -> list[dict[str, Any]]:
    """Create a dataset and insert one Langfuse item per evaluation case."""
    if not tracing_enabled():
        return []
    client = create_langfuse_client()
    if client is None:
        return []
    items: list[dict[str, Any]] = []
    try:
        client.get_dataset(dataset_name)
    except Exception:
        client.create_dataset(
            name=dataset_name,
            description=description or "Evaluation cases",
            metadata={"kind": "evaluation-case-dataset"},
        )
    for case in cases:
        item = build_case_dataset_item(case)
        dataset_item = client.create_dataset_item(
            dataset_name=dataset_name,
            id=item["id"],
            input=item["input"],
            expected_output=item["expected_output"],
            metadata=item["metadata"],
        )
        items.append({
            "id": getattr(dataset_item, "id", item["id"]),
            "input": item["input"],
            "expected_output": item["expected_output"],
            "metadata": item["metadata"],
        })
    return items


def run_evaluation_experiment(
    dataset_name: str,
    cases: Sequence[EvaluationCase] | Iterable[EvaluationCase],
    *,
    task: Any,
    evaluators: list[Any] | None = None,
    run_name: str | None = None,
    provider: str | None = None,
    config_version: str | None = None,
    metadata: dict[str, str] | None = None,
    description: str | None = None,
    max_concurrency: int = 10,
) -> Any | None:
    """Load cases into a dataset and run an experiment over them when tracing is enabled."""
    if not tracing_enabled():
        return None
    client = create_langfuse_client()
    if client is None:
        return None
    dataset_items = sync_cases_to_dataset(
        dataset_name,
        cases,
        description=description or "Evaluation cases",
    )
    if not dataset_items:
        return None
    experiment_items = [
        {
            "id": item["id"],
            "input": item["input"],
            "expected_output": item["expected_output"],
            "metadata": item["metadata"],
        }
        for item in dataset_items
    ]
    experiment_metadata = {
        "kind": "evaluation-run",
        "dataset": dataset_name,
        **(metadata or {}),
    }
    if provider:
        experiment_metadata["provider"] = provider
    if config_version:
        experiment_metadata["config_version"] = config_version
    return client.run_experiment(
        name=dataset_name,
        run_name=run_name or build_experiment_run_name(
            provider=provider,
            config_version=config_version,
        ),
        description=description or "Evaluation experiment",
        data=experiment_items,
        task=task,
        evaluators=evaluators or [],
        max_concurrency=max_concurrency,
        metadata=experiment_metadata,
    )
