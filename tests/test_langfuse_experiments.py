from __future__ import annotations

from evaluation.langfuse_setup import experiments
from evaluation.runner.schema import EvaluationCase, EvaluationTurn


def test_build_experiment_run_name_includes_provider_and_commit(monkeypatch) -> None:
    calls: list[str] = []

    def fake_git() -> object:
        calls.append("git")
        class Completed:
            returncode = 0
            stdout = "abcdef123456\n"
        return Completed()

    monkeypatch.setattr(experiments, "_git_commit", lambda: "abcdef1")
    name = experiments.build_experiment_run_name(provider="groq", config_version="v2")

    assert name.startswith("eval-")
    assert "groq" in name
    assert "v2" in name
    assert "abcdef1" in name


def test_sync_cases_to_dataset_creates_langfuse_items(monkeypatch) -> None:
    recorded: dict[str, object] = {}

    class FakeClient:
        def get_dataset(self, name: str) -> object:
            raise KeyError(name)

        def create_dataset(self, **kwargs: object) -> object:
            recorded["dataset"] = kwargs
            return {"name": kwargs["name"]}

        def create_dataset_item(self, **kwargs: object) -> object:
            recorded.setdefault("items", []).append(kwargs)
            return type("Item", (), {"id": kwargs["id"]})()

    monkeypatch.setattr(experiments, "tracing_enabled", lambda: True)
    monkeypatch.setattr(experiments, "create_langfuse_client", lambda: FakeClient())

    case = EvaluationCase(
        case_id="seg-001",
        group="segments",
        role="sales",
        turns=(EvaluationTurn(question="Show me segment revenue"),),
        expect={"contains": ["Revenue"]},
        rubric=("Does it mention a next step?",),
        runs=3,
        severity="normal",
        status="active",
    )

    items = experiments.sync_cases_to_dataset("eval-cases", [case])

    assert recorded["dataset"]["name"] == "eval-cases"
    assert len(items) == 1
    assert items[0]["id"] == "seg-001"
    assert items[0]["input"]["role"] == "sales"
    assert items[0]["expected_output"]["contains"] == ["Revenue"]


def test_run_experiment_uses_langfuse_run_experiment(monkeypatch) -> None:
    recorded: dict[str, object] = {}

    class FakeClient:
        def get_dataset(self, name: str) -> object:
            raise KeyError(name)

        def create_dataset(self, **kwargs: object) -> object:
            return {"name": kwargs["name"]}

        def create_dataset_item(self, **kwargs: object) -> object:
            recorded.setdefault("items", []).append(kwargs)
            return type("Item", (), {"id": kwargs["id"]})()

        def run_experiment(self, **kwargs: object) -> dict[str, object]:
            recorded["run"] = kwargs
            return {"run_name": kwargs["run_name"], "count": len(kwargs["data"])}

    monkeypatch.setattr(experiments, "tracing_enabled", lambda: True)
    monkeypatch.setattr(experiments, "create_langfuse_client", lambda: FakeClient())

    case = EvaluationCase(
        case_id="doc-101",
        group="documents",
        role="manager",
        turns=(EvaluationTurn(question="What was uploaded?"),),
        expect={"not_refused": True},
        runs=5,
        severity="security",
        status="active",
    )

    result = experiments.run_evaluation_experiment(
        "eval-security",
        [case],
        task=lambda *, item, **_: item["input"],
        evaluators=[],
        provider="inception",
        config_version="v3",
    )

    assert result["count"] == 1
    assert recorded["run"]["run_name"].startswith("eval-")
    assert recorded["run"]["metadata"]["provider"] == "inception"
    assert recorded["run"]["metadata"]["config_version"] == "v3"
