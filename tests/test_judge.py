from __future__ import annotations

import pytest

from evaluation.judge import agreement_rate, calibrate_judgements, judge_answer
from evaluation.judge.judge import JudgeVerdict


class FakeResponse:
    def __init__(self, content: str, metadata: dict[str, str] | None = None) -> None:
        self.content = content
        self.response_metadata = metadata or {"llm_model": "fake-judge"}


class FakeModel:
    async def ainvoke(self, messages: list[object]) -> FakeResponse:
        prompt = str(messages[-1].content)
        if "invent" in prompt.casefold():
            return FakeResponse('{"passed": false, "reason": "Invented a cause without evidence."}')
        if "next step" in prompt.casefold():
            return FakeResponse('{"passed": true, "reason": "Includes a next step."}')
        return FakeResponse('{"passed": false, "reason": "No next step was included."}')


@pytest.mark.asyncio
async def test_judge_answer_returns_verdicts_for_rubric_items() -> None:
    verdicts = await judge_answer(
        "What changed?",
        "Revenue rose 6% and the next step is to review costs.",
        tool_results={"revenue_delta": 0.06},
        rubric_items=["Does it include a suggested next step?", "Does it avoid inventing a cause?"],
        model=FakeModel(),
    )

    assert len(verdicts) == 2
    assert verdicts[0].passed is True
    assert verdicts[0].tagged == "judge"
    assert verdicts[1].passed is False


def test_calibration_agreement_rate_matches_predictions() -> None:
    assert agreement_rate([True, False, True], [True, False, False]) == 2 / 3
    assert calibrate_judgements([(True, True), (False, False)]) == {"agreement_rate": 1.0, "count": 2}


def test_judge_verdict_has_expected_shape() -> None:
    verdict = JudgeVerdict(item="Tone is polite.", passed=True, reason="Polite and clear.")
    assert verdict.passed is True
    assert verdict.model == "judge"
    assert "Polite" in verdict.reason
