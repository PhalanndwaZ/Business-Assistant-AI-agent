from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvaluationTurn:
    """One prompt sent during an evaluation case."""

    question: str
    conversation: str = "new"


@dataclass(frozen=True)
class EvaluationCase:
    """Validated JSONL evaluation case used by the API runner."""

    case_id: str
    group: str
    role: str
    turns: tuple[EvaluationTurn, ...]
    expect: dict[str, Any]
    rubric: tuple[str, ...] = ()
    runs: int = 3
    severity: str = "normal"
    status: str = "active"
