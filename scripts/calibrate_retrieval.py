"""Score representative document-search questions against the live chunk store."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import load_settings
from app.rag.embeddings import MistralEmbedder
from app.rag.vector_store import JsonVectorStore


@dataclass(frozen=True)
class CalibrationCase:
    """A query with its expected relevant sample documents."""

    case_id: str
    query: str
    expected_document_ids: frozenset[str]


CASES = (
    CalibrationCase(
        "december_dip",
        "What factors did management report when discussing fewer completed "
        "orders in December compared with November?",
        frozenset({"management-report-2024-12"}),
    ),
    CalibrationCase(
        "returns_policy",
        "How many days do customers have to report damaged products and what "
        "can support offer?",
        frozenset({"returns-policy"}),
    ),
    CalibrationCase(
        "november_report",
        "What did management report about November revenue and fulfilment "
        "lead times?",
        frozenset({"management-report-2024-11"}),
    ),
    CalibrationCase(
        "employee_count_unanswerable",
        "How many engineers are employed by the company?",
        frozenset(),
    ),
    CalibrationCase(
        "supplier_attribution_unanswerable",
        "How much of the December revenue decline was caused by supplier "
        "delays?",
        frozenset(),
    ),
    CalibrationCase(
        "customer_rank_unanswerable",
        "Which customer generated the highest revenue last year?",
        frozenset(),
    ),
)


def _rank_chunks(
    chunks: list[dict[str, Any]],
    chunk_matrix: np.ndarray,
    query_vector: list[float],
    top_k: int,
    min_similarity: float,
) -> tuple[list[tuple[dict[str, Any], float]], list[tuple[dict[str, Any], float]]]:
    """Return all ranked chunks and the subset that passes the configured cutoff."""
    vector = np.asarray(query_vector, dtype=float)
    denominators = np.linalg.norm(chunk_matrix, axis=1) * np.linalg.norm(vector)
    scores = np.divide(
        chunk_matrix @ vector,
        denominators,
        out=np.zeros(len(chunks), dtype=float),
        where=denominators != 0,
    )
    ranked = sorted(
        zip(chunks, scores.tolist(), strict=True),
        key=lambda item: item[1],
        reverse=True,
    )
    accepted = [
        (chunk, score)
        for chunk, score in ranked
        if np.isfinite(score) and score >= min_similarity
    ][:top_k]
    return ranked, accepted


def main() -> int:
    """Embed the calibration queries and report relevance at the configured cutoff."""
    settings = load_settings()
    store = JsonVectorStore(settings.vector_store_path).load()
    if store["embedding_model"] != settings.mistral_embedding_model:
        raise ValueError("Stored vectors do not match the configured embedding model.")
    embedder = MistralEmbedder(
        settings.mistral_api_key,
        settings.mistral_embedding_model,
    )
    query_vectors = embedder.embed([case.query for case in CASES])
    if len(query_vectors) != len(CASES):
        raise RuntimeError("Embedding service returned an incomplete query batch.")

    chunks: list[dict[str, Any]] = store["chunks"]
    chunk_matrix = np.asarray(
        [chunk["embedding"] for chunk in chunks],
        dtype=float,
    )
    failures = 0
    for case, query_vector in zip(CASES, query_vectors, strict=True):
        ranked, accepted = _rank_chunks(
            chunks,
            chunk_matrix,
            query_vector,
            settings.top_k,
            settings.min_similarity,
        )
        retrieved_ids = {chunk["document_id"] for chunk, _score in accepted}
        passed = (
            bool(retrieved_ids & case.expected_document_ids)
            if case.expected_document_ids
            else not retrieved_ids
        )
        failures += not passed
        print(
            json.dumps(
                {
                    "case": case.case_id,
                    "expected_document_ids": sorted(case.expected_document_ids),
                    "top_scores": [
                        {
                            "document_id": chunk["document_id"],
                            "similarity": round(score, 4),
                        }
                        for chunk, score in ranked[:3]
                    ],
                    "retrieved_document_ids": sorted(retrieved_ids),
                    "min_similarity": settings.min_similarity,
                    "passed": passed,
                },
                ensure_ascii=False,
            )
        )
    print(
        f"Threshold {settings.min_similarity:.2f}: "
        f"{len(CASES) - failures}/{len(CASES)} calibration cases passed."
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
