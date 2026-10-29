"""HTTP API contract tests for the Phase 11 FastAPI endpoint."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest

import main
from app.auth.rate_limit import RateLimiter
from app.auth.tokens import create_access_token
from app.auth.users import UserAccount
from app.config import ConfigurationError, Settings
from app.llm_factory import groq_client_options
from app.llm_fallback import ProviderUnavailableError
from app.state import AnalystState

TEST_SALES_USER = UserAccount(
    user_id="user-sales-demo",
    username="sales.demo",
    name="Sales Demo",
    role="sales",
    password_hash="$argon2id$test-hash",
)
TEST_HR_USER = UserAccount(
    user_id="user-hr-demo",
    username="hr.demo",
    name="HR Demo",
    role="hr",
    password_hash="$argon2id$test-hash",
)
TEST_ADMIN_USER = UserAccount(
    user_id="user-admin-demo",
    username="admin.demo",
    name="Admin Demo",
    role="admin",
    password_hash="$argon2id$test-hash",
)


@pytest.fixture(autouse=True)
def isolate_audit_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Keep API audit events in the test's temporary directory."""
    monkeypatch.setenv("AUDIT_DB_PATH", str(tmp_path / "audit.sqlite3"))
    monkeypatch.setenv(
        "REPORT_ACCESS_DB_PATH",
        str(tmp_path / "report_access.sqlite3"),
    )


def client_for_user(user: UserAccount) -> TestClient:
    """Create a client whose authenticated identity is the supplied account."""
    application = main.create_app()
    application.dependency_overrides[main.get_current_user] = lambda: user
    return TestClient(application)


def authenticated_client(
    monkeypatch: Any,
    user_id: str = "user-sales-demo",
) -> TestClient:
    """Create a test client with a signed token for a demo account."""
    secret = "test-jwt-secret-that-is-at-least-32-bytes"
    monkeypatch.setenv("JWT_SECRET_KEY", secret)
    token = create_access_token(user_id, secret)
    client = TestClient(main.create_app())
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_gpt_oss_uses_parsed_reasoning_format() -> None:
    """GPT-OSS tool calls use Groq's structured reasoning response format."""
    settings = Settings(
        groq_api_key="test",
        mistral_api_key="test",
        groq_model="openai/gpt-oss-120b",
        mistral_embedding_model="test-embedding",
        as_of_date=date(2025, 1, 15),
        min_similarity=0.84,
        top_k=4,
        max_rows=100,
        max_steps=8,
        max_retries=2,
        data_dir=Path("data/sample_data"),
        documents_dir=Path("data/documents"),
        vector_store_path=Path("data/vector_store/chunks.json"),
    )

    assert groq_client_options(settings) == {
        "model": "openai/gpt-oss-120b",
        "api_key": SecretStr("test"),
        "temperature": 0,
        "max_retries": 0,
        "timeout": 20,
        "max_tokens": 1024,
        "reasoning_format": "parsed",
    }


def test_run_question_uses_the_same_graph_answer_as_the_cli(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    """The HTTP service delegates to answer_question and returns its answer."""
    settings = Settings(
        groq_api_key="test",
        mistral_api_key="test",
        groq_model="test-model",
        mistral_embedding_model="test-embedding",
        as_of_date=date(2025, 1, 15),
        min_similarity=0.84,
        top_k=4,
        max_rows=100,
        max_steps=8,
        max_retries=2,
        data_dir=Path("data/sample_data"),
        documents_dir=Path("data/documents"),
        vector_store_path=Path("data/vector_store/chunks.json"),
        conversation_db_path=tmp_path / "conversations.sqlite3",
    )
    observed: dict[str, Any] = {}
    reports_directory = tmp_path / "reports"
    reports_directory.mkdir()
    report_filename = "generated-report-0123456789abcdef.docx"
    report_path = reports_directory / report_filename
    report_path.write_bytes(b"generated report")
    monkeypatch.setattr(main, "REPORTS_DIR", reports_directory)

    class FakeClient:
        def __init__(self, actual_settings: Settings) -> None:
            observed["settings"] = actual_settings

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
            observed["client_closed"] = True
            observed["client_exit"] = (exc_type, exc, traceback)
            return None

        async def list_tools(self) -> list[object]:
            return []

    async def fake_answer_question(
        question: str,
        _model: Any,
        _tools: list[object],
        _client: Any,
        max_steps: int,
        max_retries: int,
        history: list[tuple[str, str]],
        prior_tool_results: list[dict[str, Any]],
        prior_retrieved_chunks: list[dict[str, object]],
    ) -> AnalystState:
        assert observed["settings"] is settings
        assert _model is fake_model
        assert _tools == []
        assert isinstance(_client, FakeClient)
        observed.update(
            question=question,
            max_steps=max_steps,
            max_retries=max_retries,
            history=history,
            prior_tool_results=prior_tool_results,
            prior_retrieved_chunks=prior_retrieved_chunks,
        )
        return {
            "final_answer": "The CLI-compatible graph answer.",
            "tool_results": [
                {
                    "tool_name": "run_analysis",
                    "success": True,
                    "call_id": "category-analysis-call",
                    "result": {
                        "analysis": "revenue_by_category",
                        "period": {
                            "start": "2024-11-01",
                            "end": "2024-11-30",
                        },
                        "data": [
                            {
                                "category": "Electronics",
                                "revenue_cents": 2300000,
                                "units": 130,
                            },
                            {
                                "category": "Furniture",
                                "revenue_cents": 1717949,
                                "units": 121,
                            },
                        ],
                    },
                },
                {
                    "tool_name": "generate_report",
                    "success": True,
                    "result": {"path": str(report_path)},
                }
            ],
            "retrieved_chunks": [],
            "evidence_errors": [],
            "errors": [],
        }

    fake_model = object()

    def fake_build_chat_model(actual_settings: Settings) -> object:
        """Return a sentinel model and record the settings passed by the API."""
        observed["settings"] = actual_settings
        observed["model_built"] = True
        return fake_model

    monkeypatch.setattr(main, "load_settings", lambda: settings)
    monkeypatch.setattr(main, "build_chat_model", fake_build_chat_model)
    monkeypatch.setattr(
        main,
        "AnalystMCPClient",
        lambda actual_settings, _user_context: FakeClient(actual_settings),
    )
    monkeypatch.setattr(main, "answer_question", fake_answer_question)

    response = asyncio.run(
        main._run_question("What changed?", None, TEST_SALES_USER)
    )

    assert observed == {
        "question": "What changed?",
        "settings": settings,
        "max_steps": 8,
        "max_retries": 2,
        "history": [],
        "prior_tool_results": [],
        "prior_retrieved_chunks": [],
        "model_built": True,
        "client_closed": True,
        "client_exit": (None, None, None),
    }
    assert response.answer == "The CLI-compatible graph answer."
    assert response.charts == [
        {
            "id": "category-analysis-call",
            "type": "ranking_bars",
            "title": "Revenue by category",
            "subtitle": "2024-11-01 to 2024-11-30 · Completed orders · money in cents",
            "unit": "money_cents",
            "series": [
                {"label": "Electronics", "value": 2300000},
                {"label": "Furniture", "value": 1717949},
            ],
            "highlight": "Electronics",
            "annotations": [],
            "source": {
                "analysis": "revenue_by_category",
                "result_id": "category-analysis-call",
                "as_of": "2024-11-30",
            },
            "alt_text": "Horizontal bars comparing returned category revenue.",
        }
    ]
    assert response.report_filename == report_filename
    owner = main._get_report_access_store().get_owner(report_filename)
    assert owner is not None
    assert owner.user_id == TEST_SALES_USER.user_id
    assert owner.role == TEST_SALES_USER.role
    assert isinstance(UUID(response.conversation_id), UUID)


def test_run_question_returns_current_turn_figures_not_historical_evidence(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    """Keep prior evidence for follow-ups without echoing it in the API response."""
    settings = Settings(
        groq_api_key="test",
        mistral_api_key="test",
        groq_model="test-model",
        mistral_embedding_model="test-embedding",
        as_of_date=date(2025, 1, 15),
        min_similarity=0.84,
        top_k=4,
        max_rows=100,
        max_steps=8,
        max_retries=2,
        data_dir=Path("data/sample_data"),
        documents_dir=Path("data/documents"),
        vector_store_path=Path("data/vector_store/chunks.json"),
        conversation_db_path=tmp_path / "conversations.sqlite3",
    )
    conversation_id = UUID("00000000-0000-0000-0000-000000000004")
    historical_result = {
        "call_id": "historical-analysis",
        "tool_name": "run_analysis",
        "arguments": {},
        "result": {
            "analysis": "revenue_by_product",
            "data": [{"product_name": "Standing Desk", "revenue_cents": 16645713}],
        },
        "success": True,
    }
    historical_chunk = {"document_name": "old_report.md", "text": "old evidence"}
    store = main.ConversationStore(settings.conversation_db_path)
    store.append_turn(
        conversation_id,
        "Which product led?",
        "Standing Desk led.",
        [historical_result],
        [historical_chunk],
        user_id=TEST_SALES_USER.user_id,
        role=TEST_SALES_USER.role,
    )
    observed: dict[str, Any] = {}

    class FakeClient:
        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
            return None

        async def list_tools(self) -> list[object]:
            return []

    current_result = {
        "call_id": "current-query",
        "tool_name": "query_business_data",
        "arguments": {},
        "result": {
            "dataset": "orders",
            "total_matches": 514,
            "rows": [],
        },
        "success": True,
    }

    async def fake_answer_question(
        _question: str,
        _model: Any,
        _tools: list[object],
        _client: Any,
        _max_steps: int,
        _max_retries: int,
        history: list[tuple[str, str]],
        prior_tool_results: list[dict[str, Any]],
        prior_retrieved_chunks: list[dict[str, object]],
    ) -> AnalystState:
        observed["history"] = history
        observed["prior_tool_results"] = prior_tool_results
        observed["prior_retrieved_chunks"] = prior_retrieved_chunks
        return {
            "final_answer": "There are 514 completed orders.",
            "tool_results": [*prior_tool_results, current_result],
            "retrieved_chunks": prior_retrieved_chunks,
            "evidence_errors": [],
            "errors": [],
        }

    monkeypatch.setattr(main, "load_settings", lambda: settings)
    monkeypatch.setattr(main, "build_chat_model", lambda _settings: object())
    monkeypatch.setattr(
        main,
        "AnalystMCPClient",
        lambda _settings, _user_context: FakeClient(),
    )
    monkeypatch.setattr(main, "answer_question", fake_answer_question)

    response = asyncio.run(
        main._run_question(
            "How many orders have been completed?",
            conversation_id,
            TEST_SALES_USER,
        )
    )

    assert observed["prior_tool_results"] == [historical_result]
    assert observed["prior_retrieved_chunks"] == [historical_chunk]
    assert response.answer == "There are 514 completed orders."
    assert response.figures == [
        {"dataset": "orders", "total_matches": 514, "rows": []}
    ]
    assert response.sources == ["query_business_data:orders"]
    assert "revenue_by_product" not in str(response.model_dump())
    assert "old_report.md" not in str(response.model_dump())


def test_ask_returns_same_answer_and_supporting_workflow_data(
    monkeypatch: Any,
) -> None:
    """The API returns the graph answer with figures, sources, and caveats."""
    async def fake_run_question(
        question: str,
        conversation_id: UUID | None = None,
        _user: UserAccount | None = None,
    ) -> main.AskResponse:
        """Return a deterministic result for answer-shape assertions."""
        assert question == "What changed?"
        return main._response_fields(
            {
                "final_answer": "Revenue decreased in December.",
                "tool_results": [
                    {
                        "tool_name": "run_analysis",
                        "success": True,
                        "result": {
                            "analysis": "period_change",
                            "period": {
                                "current": {"start": "2024-12-01"},
                                "previous": {"start": "2024-11-01"},
                            },
                            "data": [
                                {
                                    "current_value": 100,
                                    "previous_value": 200,
                                    "optional_value": None,
                                }
                            ],
                            "assumptions": ["Only completed orders are included."],
                        },
                    },
                    {
                        "tool_name": "search_documents",
                        "success": True,
                        "result": {"results": []},
                    },
                ],
                "retrieved_chunks": [
                    {"document_name": "management_report_2024-12.md"}
                ],
                "evidence_errors": [],
                "errors": [],
            },
            str(conversation_id or UUID("00000000-0000-0000-0000-000000000001")),
        )

    monkeypatch.setattr(main, "_run_question", fake_run_question)

    response = authenticated_client(monkeypatch).post(
        "/ask", json={"question": "  What changed?  "}
    )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "Revenue decreased in December.",
        "conversation_id": "00000000-0000-0000-0000-000000000001",
        "figures": [
            {
                "analysis": "period_change",
                "period": {
                    "current": {"start": "2024-12-01"},
                    "previous": {"start": "2024-11-01"},
                },
                "data": [
                    {
                        "current_value": 100,
                        "previous_value": 200,
                        "optional_value": None,
                    }
                ],
            }
        ],
        "charts": [],
        "sources": ["run_analysis:period_change", "search_documents", "management_report_2024-12.md"],
        "caveats": [
            "Only completed orders are included.",
            "Document-derived statements are limited to retrieved passages and may be incomplete or outdated.",
            "Reported explanations are not proof that a factor caused a measured business change.",
        ],
        "moderation": {"status": "ok", "notice": None},
    }


def test_response_fields_includes_generated_report_filename(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    """Expose the filename only for a valid generated file inside reports."""
    reports_directory = tmp_path / "reports"
    reports_directory.mkdir()
    filename = "revenue-report-2024-2025-0123456789abcdef.docx"
    report_path = reports_directory / filename
    report_path.write_bytes(b"docx")
    monkeypatch.setattr(main, "REPORTS_DIR", reports_directory)

    response = main._response_fields(
        {
            "final_answer": f"Report file: {report_path}",
            "tool_results": [
                {
                    "tool_name": "generate_report",
                    "success": True,
                    "result": {"path": str(report_path)},
                }
            ],
        }
    )

    assert response.report_filename == filename

    outside_path = tmp_path / filename
    outside_path.write_bytes(b"outside")
    response = main._response_fields(
        {
            "tool_results": [
                {
                    "tool_name": "generate_report",
                    "success": True,
                    "result": {"path": str(outside_path)},
                }
            ]
        }
    )
    assert response.report_filename is None


def test_ask_includes_report_filename_when_present(
    monkeypatch: Any,
) -> None:
    """Serialize the optional report filename in the API response."""
    async def fake_run_question(
        _question: str,
        _conversation_id: UUID | None = None,
        _user: UserAccount | None = None,
    ) -> main.AskResponse:
        return main.AskResponse(
            answer="Report created.",
            conversation_id="00000000-0000-0000-0000-000000000011",
            figures=[],
            sources=[],
            caveats=[],
            report_filename="revenue-report.docx",
            moderation=main.ModerationInfo(status="ok", notice=None),
        )

    monkeypatch.setattr(main, "_run_question", fake_run_question)

    response = authenticated_client(monkeypatch).post(
        "/ask",
        json={"question": "Create a report"},
    )

    assert response.status_code == 200
    assert response.json()["report_filename"] == "revenue-report.docx"


def test_download_report_serves_only_docx_files_inside_reports(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    """Reject invalid names and files that resolve outside the reports folder."""
    reports_directory = tmp_path / "reports"
    reports_directory.mkdir()
    filename = "revenue-report-0123456789abcdef.docx"
    report_path = reports_directory / filename
    report_path.write_bytes(b"docx test content")
    outside_report = tmp_path / "outside.docx"
    outside_report.write_bytes(b"private content")
    monkeypatch.setattr(main, "REPORTS_DIR", reports_directory)
    main._get_report_access_store().register_report(
        filename,
        TEST_SALES_USER.user_id,
        TEST_SALES_USER.role,
    )
    client = authenticated_client(monkeypatch)

    response = client.get(f"/reports/{filename}")

    assert response.status_code == 200
    assert response.content == b"docx test content"
    assert response.headers["content-type"] == main.DOCX_MEDIA_TYPE
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{filename}"'
    )

    invalid_names = (
        "missing.docx",
        "report.pdf",
        "../outside.docx",
        r"..\outside.docx",
        str(outside_report),
    )
    for invalid_name in invalid_names:
        encoded_name = quote(invalid_name, safe="")
        invalid_response = client.get(f"/reports/{encoded_name}")
        assert invalid_response.status_code == 404
        assert b"private content" not in invalid_response.content

    external_link = reports_directory / "external.docx"
    try:
        external_link.symlink_to(outside_report)
    except (OSError, NotImplementedError):
        pass
    else:
        assert client.get("/reports/external.docx").status_code == 404


def test_report_downloads_are_limited_to_owner_or_admin(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    """Allow the owner and admin while hiding another user's report as not found."""
    reports_directory = tmp_path / "reports"
    reports_directory.mkdir()
    filename = "owner-report-0123456789abcdef.docx"
    (reports_directory / filename).write_bytes(b"owned report")
    monkeypatch.setattr(main, "REPORTS_DIR", reports_directory)
    main._get_report_access_store().register_report(
        filename,
        TEST_SALES_USER.user_id,
        TEST_SALES_USER.role,
    )

    owner_response = client_for_user(TEST_SALES_USER).get(f"/reports/{filename}")
    other_user_response = client_for_user(TEST_HR_USER).get(f"/reports/{filename}")
    missing_response = client_for_user(TEST_HR_USER).get(
        "/reports/missing-report.docx"
    )
    admin_response = client_for_user(TEST_ADMIN_USER).get(f"/reports/{filename}")

    assert owner_response.status_code == 200
    assert owner_response.content == b"owned report"
    assert other_user_response.status_code == 404
    assert other_user_response.json() == {"detail": "Report not found."}
    assert missing_response.status_code == 404
    assert missing_response.json() == other_user_response.json()
    assert admin_response.status_code == 200
    assert admin_response.content == b"owned report"


def test_report_without_owner_record_is_not_downloadable(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    """Fail closed for reports created before ownership metadata was recorded."""
    reports_directory = tmp_path / "reports"
    reports_directory.mkdir()
    filename = "unregistered-report.docx"
    (reports_directory / filename).write_bytes(b"unregistered report")
    monkeypatch.setattr(main, "REPORTS_DIR", reports_directory)

    response = client_for_user(TEST_ADMIN_USER).get(f"/reports/{filename}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Report not found."}


def test_ask_rejects_missing_or_blank_question(monkeypatch: Any) -> None:
    """The request contract rejects missing, empty, and whitespace-only input."""
    client = authenticated_client(monkeypatch)

    assert client.post("/ask", json={}).status_code == 422
    assert client.post("/ask", json={"question": ""}).status_code == 422
    assert client.post("/ask", json={"question": "   "}).status_code == 422
    assert client.post(
        "/ask",
        json={"question": "Revenue?", "conversation_id": "not-a-uuid"},
    ).status_code == 422


def test_ask_returns_and_accepts_server_generated_conversation_id(
    monkeypatch: Any,
) -> None:
    """Clients can pass the returned UUID to continue the same conversation."""
    observed_ids: list[UUID | None] = []

    async def fake_run_question(
        question: str,
        conversation_id: UUID | None = None,
        _user: UserAccount | None = None,
    ) -> main.AskResponse:
        """Return a deterministic result for conversation ID assertions."""
        observed_ids.append(conversation_id)
        active_id = conversation_id or UUID(
            "00000000-0000-0000-0000-000000000002"
        )
        return main.AskResponse(
            answer=f"Answer to {question}",
            conversation_id=str(active_id),
            figures=[],
            sources=[],
            caveats=[],
            moderation=main.ModerationInfo(status="ok", notice=None),
        )

    monkeypatch.setattr(main, "_run_question", fake_run_question)
    client = authenticated_client(monkeypatch)

    first_response = client.post("/ask", json={"question": "First question"})
    generated_id = first_response.json()["conversation_id"]
    second_response = client.post(
        "/ask",
        json={
            "question": "Follow-up question",
            "conversation_id": generated_id,
        },
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert observed_ids == [None, UUID(generated_id)]
    assert second_response.json()["conversation_id"] == generated_id


def test_login_returns_token_and_me_returns_current_identity(
    monkeypatch: Any,
) -> None:
    """Login issues a bearer token and /me resolves its configured account."""
    secret = "test-jwt-secret-that-is-at-least-32-bytes"
    monkeypatch.setenv("JWT_SECRET_KEY", secret)
    account = UserAccount(
        user_id="user-hr-demo",
        username="hr.demo",
        name="HR Demo",
        role="hr",
        password_hash="$argon2id$test-hash",
    )
    monkeypatch.setattr(
        main,
        "authenticate_user",
        lambda username, password: (
            account if username == "hr.demo" and password == "test-password" else None
        ),
    )
    monkeypatch.setattr(
        "app.auth.dependencies.get_user_by_id",
        lambda user_id: account if user_id == "user-hr-demo" else None,
    )
    client = TestClient(main.create_app())

    login_response = client.post(
        "/auth/login",
        json={"username": "hr.demo", "password": "test-password"},
    )

    assert login_response.status_code == 200
    token_body = login_response.json()
    assert token_body["token_type"] == "bearer"
    assert token_body["expires_in"] == 1800
    profile_response = client.get(
        "/me",
        headers={"Authorization": f"Bearer {token_body['access_token']}"},
    )
    assert profile_response.status_code == 200
    assert profile_response.json() == {
        "user_id": "user-hr-demo",
        "username": "hr.demo",
        "name": "HR Demo",
        "role": "hr",
    }

    invalid_login = client.post(
        "/auth/login",
        json={"username": "hr.demo", "password": "wrong-password"},
    )
    assert invalid_login.status_code == 401


def test_ask_and_reports_require_a_valid_bearer_token(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    """Protected endpoints reject missing and expired credentials."""
    secret = "test-jwt-secret-that-is-at-least-32-bytes"
    monkeypatch.setenv("JWT_SECRET_KEY", secret)
    client = TestClient(main.create_app())

    missing_token = client.post("/ask", json={"question": "Revenue?"})
    assert missing_token.status_code == 401
    assert missing_token.headers["www-authenticate"] == "Bearer"

    expired_token = create_access_token(
        "user-sales-demo",
        secret,
        expires_delta=timedelta(seconds=-1),
    )
    expired_headers = {"Authorization": f"Bearer {expired_token}"}
    assert client.get("/me", headers=expired_headers).status_code == 401
    assert (
        client.get("/reports/missing.docx", headers=expired_headers).status_code
        == 401
    )


def test_openapi_marks_private_endpoints_as_bearer_secured() -> None:
    """OpenAPI documents authentication for protected endpoints only."""
    schema = main.create_app().openapi()

    assert schema["components"]["securitySchemes"]["HTTPBearer"]
    assert schema["paths"]["/ask"]["post"]["security"] == [{"HTTPBearer": []}]
    assert schema["paths"]["/me"]["get"]["security"] == [{"HTTPBearer": []}]
    assert "security" not in schema["paths"]["/auth/login"]["post"]


def test_ask_rate_limit_returns_429_and_retry_after(
    monkeypatch: Any,
) -> None:
    """Requests over the per-user window receive a 429 response."""
    async def fake_run_question(
        question: str,
        conversation_id: UUID | None = None,
        _user: UserAccount | None = None,
    ) -> main.AskResponse:
        """Return a deterministic result for rate-limit endpoint checks."""
        return main.AskResponse(
            answer=question,
            conversation_id=str(
                conversation_id or UUID("00000000-0000-0000-0000-000000000022")
            ),
            figures=[],
            sources=[],
            caveats=[],
            moderation=main.ModerationInfo(status="ok", notice=None),
        )

    monkeypatch.setattr(main, "_run_question", fake_run_question)
    client = authenticated_client(monkeypatch)
    client.app.state.rate_limiter = RateLimiter(max_requests=1, window_seconds=60)

    first = client.post("/ask", json={"question": "First"})
    second = client.post("/ask", json={"question": "Second"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) >= 1


def test_ask_accepts_client_supplied_id_for_new_conversation(
    monkeypatch: Any,
) -> None:
    """A valid client ID that is not stored yet starts a new conversation."""
    supplied_id = UUID("00000000-0000-0000-0000-000000000003")
    observed_ids: list[UUID | None] = []

    async def create_with_supplied_id(
        question: str,
        conversation_id: UUID | None = None,
        _user: UserAccount | None = None,
    ) -> main.AskResponse:
        """Return a deterministic result for a client-selected new ID."""
        observed_ids.append(conversation_id)
        assert question == "Start with my ID"
        return main.AskResponse(
            answer="Started a new conversation.",
            conversation_id=str(conversation_id),
            figures=[],
            sources=[],
            caveats=[],
            moderation=main.ModerationInfo(status="ok", notice=None),
        )

    monkeypatch.setattr(main, "_run_question", create_with_supplied_id)
    response = authenticated_client(monkeypatch).post(
        "/ask",
        json={
            "question": "Start with my ID",
            "conversation_id": str(supplied_id),
        },
    )

    assert response.status_code == 200
    assert response.json()["conversation_id"] == str(supplied_id)
    assert observed_ids == [supplied_id]


def test_ask_returns_404_for_another_users_conversation(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    """A user cannot distinguish a foreign conversation from an unknown ID."""
    settings = Settings(
        groq_api_key="test",
        mistral_api_key="test",
        groq_model="test-model",
        mistral_embedding_model="test-embedding",
        as_of_date=date(2025, 1, 15),
        min_similarity=0.84,
        top_k=4,
        max_rows=100,
        max_steps=8,
        max_retries=2,
        data_dir=Path("data/sample_data"),
        documents_dir=Path("data/documents"),
        vector_store_path=Path("data/vector_store/chunks.json"),
        conversation_db_path=tmp_path / "conversations.sqlite3",
    )
    monkeypatch.setattr(main, "load_settings", lambda: settings)
    conversation_id = UUID("00000000-0000-0000-0000-000000000033")
    store = main.ConversationStore(settings.conversation_db_path)
    store.claim_conversation(
        conversation_id,
        TEST_SALES_USER.user_id,
        TEST_SALES_USER.role,
    )
    client = authenticated_client(monkeypatch, user_id="user-hr-demo")

    response = client.post(
        "/ask",
        json={
            "question": "Can I resume this?",
            "conversation_id": str(conversation_id),
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Conversation not found."}


def test_role_change_starts_a_fresh_conversation(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    """A changed role never reuses history or evidence from the prior role."""
    secret = "test-jwt-secret-that-is-at-least-32-bytes"
    monkeypatch.setenv("JWT_SECRET_KEY", secret)
    settings = Settings(
        groq_api_key="test",
        mistral_api_key="test",
        groq_model="test-model",
        mistral_embedding_model="test-embedding",
        as_of_date=date(2025, 1, 15),
        min_similarity=0.84,
        top_k=4,
        max_rows=100,
        max_steps=8,
        max_retries=2,
        data_dir=Path("data/sample_data"),
        documents_dir=Path("data/documents"),
        vector_store_path=Path("data/vector_store/chunks.json"),
        conversation_db_path=tmp_path / "conversations.sqlite3",
    )
    monkeypatch.setattr(main, "load_settings", lambda: settings)
    current_user = UserAccount(
        user_id=TEST_SALES_USER.user_id,
        username=TEST_SALES_USER.username,
        name=TEST_SALES_USER.name,
        role="manager",
        password_hash=TEST_SALES_USER.password_hash,
    )
    monkeypatch.setattr(
        "app.auth.dependencies.get_user_by_id",
        lambda user_id: current_user if user_id == current_user.user_id else None,
    )
    conversation_id = UUID("00000000-0000-0000-0000-000000000034")
    store = main.ConversationStore(settings.conversation_db_path)
    store.claim_conversation(
        conversation_id,
        current_user.user_id,
        "sales",
    )
    store.append_turn(
        conversation_id,
        "Old-role question",
        "Old-role answer",
        user_id=current_user.user_id,
        role="sales",
    )
    observed: dict[str, Any] = {}

    class FakeClient:
        """Return no external tools while the request uses the graph path."""

        async def __aenter__(self) -> FakeClient:
            """Enter the fake async client context."""
            return self

        async def __aexit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
            """Exit the fake async client context."""
            return None

        async def list_tools(self) -> list[object]:
            """Return no tools for the deterministic graph test."""
            return []

    async def fake_answer_question(
        _question: str,
        _model: Any,
        _tools: list[object],
        _client: Any,
        _max_steps: int,
        _max_retries: int,
        history: list[tuple[str, str]],
        prior_tool_results: list[dict[str, Any]],
        prior_retrieved_chunks: list[dict[str, object]],
    ) -> AnalystState:
        """Record incoming history and return a deterministic answer."""
        observed["history"] = history
        observed["tool_results"] = prior_tool_results
        observed["chunks"] = prior_retrieved_chunks
        return {
            "final_answer": "Fresh conversation.",
            "tool_results": [],
            "retrieved_chunks": [],
            "evidence_errors": [],
            "errors": [],
        }

    monkeypatch.setattr(main, "build_chat_model", lambda _settings: object())
    monkeypatch.setattr(
        main,
        "AnalystMCPClient",
        lambda _settings, _user_context: FakeClient(),
    )
    monkeypatch.setattr(main, "answer_question", fake_answer_question)
    client = authenticated_client(monkeypatch, user_id=current_user.user_id)

    response = client.post(
        "/ask",
        json={
            "question": "New-role question",
            "conversation_id": str(conversation_id),
        },
    )

    new_conversation_id = UUID(response.json()["conversation_id"])
    assert response.status_code == 200
    assert new_conversation_id != conversation_id
    assert observed == {"history": [], "tool_results": [], "chunks": []}
    old_identity = store.get_conversation_identity(conversation_id)
    new_identity = store.get_conversation_identity(new_conversation_id)
    assert old_identity is not None and old_identity.role == "sales"
    assert new_identity is not None
    assert new_identity.user_id == current_user.user_id
    assert new_identity.role == "manager"


def test_ask_reports_configuration_failure_without_exposing_details(
    monkeypatch: Any,
) -> None:
    """Configuration failures have an explicit service error response."""
    async def fail_to_run(
        _question: str,
        _conversation_id: UUID | None = None,
        _user: UserAccount | None = None,
    ) -> main.AskResponse:
        assert _question == "Revenue?"
        raise ConfigurationError("Missing GROQ_API_KEY")

    monkeypatch.setattr(main, "_run_question", fail_to_run)

    response = authenticated_client(monkeypatch).post(
        "/ask", json={"question": "Revenue?"}
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "The question-answering service is not configured."
    }
    assert "GROQ_API_KEY" not in response.text


def test_provider_unavailable_returns_safe_existing_error(
    monkeypatch: Any,
) -> None:
    """Unavailable provider errors return a generic model-service response."""
    async def fail_to_run(
        _question: str,
        _conversation_id: UUID | None = None,
        _user: UserAccount | None = None,
    ) -> main.AskResponse:
        """Raise the simulated provider failure for API error mapping."""
        raise ProviderUnavailableError(
            "The answer model is temporarily unavailable."
        )

    monkeypatch.setattr(main, "_run_question", fail_to_run)

    response = authenticated_client(monkeypatch).post(
        "/ask", json={"question": "Revenue?"}
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "The answer model is temporarily unavailable."
    }


def test_api_response_has_no_figures_for_unanswerable_graph_state() -> None:
    """An honest graph fallback remains intact and does not invent figures."""
    state: AnalystState = {
        "final_answer": "I cannot answer from available sources.",
        "tool_results": [],
        "retrieved_chunks": [],
        "evidence_errors": [],
        "errors": [],
    }

    response = main._response_fields(state)

    assert response.answer == "I cannot answer from available sources."
    assert response.figures == []
    assert response.sources == []
    assert response.caveats == []
