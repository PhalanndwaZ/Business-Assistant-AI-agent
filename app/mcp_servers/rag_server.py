"""MCP server exposing thresholded search over MongoDB or legacy JSON chunks."""

from __future__ import annotations

import logging
import time
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from app.config import load_settings
from app.mongodb import get_mongo_store, load_access_policy
from app.policy.context import MCPUserContext, PolicyAccessDenied, resolve_mcp_user
from app.policy.policy import AccessPolicy
from app.rag.embeddings import MistralEmbedder
from app.rag.retriever import DocumentRetriever
from app.uploads import UploadStore

LOGGER = logging.getLogger(__name__)
server = FastMCP("document-search")
_retriever: DocumentRetriever | None = None
_policy: AccessPolicy | None = None


def get_retriever() -> DocumentRetriever:
    """Load configured chunks and the Mistral embedder once per process."""
    global _retriever
    if _retriever is None:
        settings = load_settings(require_groq_api_key=False)
        embedder = MistralEmbedder(
            settings.mistral_api_key,
            settings.mistral_embedding_model,
        )
        mongo_store = (
            get_mongo_store(settings.mongodb_uri, settings.mongodb_database)
            if settings.mongodb_enabled
            else None
        )
        _retriever = DocumentRetriever(
            None if mongo_store is not None else settings.vector_store_path,
            settings.mistral_embedding_model,
            embedder,
            settings.min_similarity,
            settings.top_k,
            mongo_store=mongo_store,
        )
    return _retriever


def get_policy() -> AccessPolicy:
    """Return the process-wide validated access policy."""
    global _policy
    if _policy is None:
        settings = load_settings(require_groq_api_key=False)
        _policy = (
            load_access_policy(
                get_mongo_store(
                    settings.mongodb_uri,
                    settings.mongodb_database,
                )
            )
            if settings.mongodb_enabled
            else AccessPolicy()
        )
    return _policy


def _search_documents(
    user: MCPUserContext,
    query: str,
    document_type: str | None = None,
    document_date: str | None = None,
    k: int | None = None,
    conversation_id: str | None = None,
    document_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Find relevant passages and return their source metadata and scores."""
    policy = get_policy()
    if not policy.can_use_tool(user.role, "search_documents"):
        raise PolicyAccessDenied()
    started_at = time.monotonic()
    settings = load_settings(require_groq_api_key=False)
    result = get_retriever().search(
        query,
        document_type,
        document_date,
        k,
        access_policy=policy,
        role=user.role,
    )
    result_limit = k or settings.top_k
    company_results = result["results"]
    for chunk in company_results:
        chunk["origin"] = "company"
    uploaded_results: list[dict[str, Any]] = []
    if conversation_id:
        settings = load_settings(require_groq_api_key=False)
        store = UploadStore(settings.conversation_db_path)
        query_vector = get_retriever()._embedder.embed([query])[0]
        uploaded_results = store.search(
            conversation_id=conversation_id,
            user_id=user.user_id,
            query_vector=query_vector,
            document_ids=document_ids,
            min_similarity=settings.min_similarity,
            top_k=k or settings.top_k,
            embedder_model=settings.mistral_embedding_model,
        )
    all_results = sorted(
        [*company_results, *uploaded_results],
        key=lambda chunk: (-float(chunk["similarity"]), str(chunk["chunk_id"])),
    )

    result["results"] = all_results[:result_limit]
    if not result["results"]:
        if conversation_id:
            result["message"] = "The documents do not cover this question."
        else:
            result["message"] = "No relevant passages found."
    LOGGER.info(
        "tool=search_documents duration_ms=%.2f results=%d",
        (time.monotonic() - started_at) * 1000,
        len(result["results"]),
    )
    return result


@server.tool()
def search_documents(
    ctx: Context,
    query: str,
    document_type: str | None = None,
    document_date: str | None = None,
    k: int | None = None,
    conversation_id: str | None = None,
    document_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Search business documents and return relevant passages with citations."""
    return _search_documents(
        resolve_mcp_user(ctx),
        query,
        document_type,
        document_date,
        k,
        conversation_id,
        document_ids,
    )


def main() -> None:
    """Validate retrieval configuration and run the local stdio MCP server."""
    logging.basicConfig(level=logging.INFO)
    get_retriever()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
