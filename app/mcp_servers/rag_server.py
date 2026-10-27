"""MCP server exposing thresholded search over the JSON chunk store."""

from __future__ import annotations

import logging
import time
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.config import load_settings
from app.rag.embeddings import MistralEmbedder
from app.rag.retriever import DocumentRetriever

LOGGER = logging.getLogger(__name__)
server = FastMCP("document-search")
_retriever: DocumentRetriever | None = None


def get_retriever() -> DocumentRetriever:
    """Load the vector store and its configured Mistral embedder once."""
    global _retriever
    if _retriever is None:
        settings = load_settings(require_groq_api_key=False)
        embedder = MistralEmbedder(
            settings.mistral_api_key,
            settings.mistral_embedding_model,
        )
        _retriever = DocumentRetriever(
            settings.vector_store_path,
            settings.mistral_embedding_model,
            embedder,
            settings.min_similarity,
            settings.top_k,
        )
    return _retriever


def _search_documents(
    query: str,
    document_type: str | None = None,
    document_date: str | None = None,
    k: int | None = None,
) -> dict[str, Any]:
    """Find relevant passages and return their source metadata and scores."""
    started_at = time.monotonic()
    result = get_retriever().search(query, document_type, document_date, k)
    LOGGER.info(
        "tool=search_documents duration_ms=%.2f results=%d",
        (time.monotonic() - started_at) * 1000,
        len(result["results"]),
    )
    return result


@server.tool()
def search_documents(
    query: str,
    document_type: str | None = None,
    document_date: str | None = None,
    k: int | None = None,
) -> dict[str, Any]:
    """Search business documents and return relevant passages with citations."""
    return _search_documents(query, document_type, document_date, k)


def main() -> None:
    """Validate retrieval configuration and run the local stdio MCP server."""
    logging.basicConfig(level=logging.INFO)
    get_retriever()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
