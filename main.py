"""FastAPI application exposing the analyst workflow over HTTP."""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from groq import APIError as GroqAPIError
from openai import APIError as OpenAIAPIError
from pydantic import BaseModel, Field, SecretStr, field_validator
from mcp.shared.exceptions import McpError

from app.auth.dependencies import get_current_user
from app.auth.rate_limit import RateLimiter
from app.auth.tokens import (
    ACCESS_TOKEN_LIFETIME,
    AuthenticationConfigurationError,
    create_access_token,
    load_signing_secret,
)
from app.auth.users import UserAccount, UserStoreError, authenticate_user
from app.audit_log import AuditLog
from app.chart_specs import build_chart_specs
from app.config import ConfigurationError, PROJECT_ROOT, Settings, load_settings
from app.conversation_store import (
    ConversationOwnershipError,
    ConversationStore,
)
from app.graph import answer_question
from app.llm_factory import build_chat_model
from app.llm_fallback import ProviderUnavailableError
from app.mcp_client import AnalystMCPClient
from app.moderation.moderator import (
    ModerationError,
    check_input,
    moderate_output,
)
from app.policy.context import ACCESS_DENIED_MESSAGE, MCPUserContext
from app.report_access import ReportAccessStore

LOGGER = logging.getLogger(__name__)
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORT_FILENAME_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]*\.docx",
    re.IGNORECASE,
)
DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
GENERIC_REDACTION_NOTICE = "Some content was withheld because of your access level."


class AskRequest(BaseModel):
    """Validated request body for the question-answering endpoint."""

    question: str = Field(min_length=1)
    conversation_id: UUID | None = None

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        """Reject whitespace-only questions and normalize surrounding space."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("question must not be blank.")
        return normalized


class ModerationInfo(BaseModel):
    """Public moderation disposition without exposing matched content."""

    status: Literal["ok", "redacted", "refused"]
    notice: str | None


class AskResponse(BaseModel):
    """Stable HTTP response containing the answer and supporting evidence."""

    answer: str
    conversation_id: str
    figures: list[dict[str, Any]]
    charts: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[str]
    caveats: list[str]
    report_filename: str | None = None
    moderation: ModerationInfo


class LoginRequest(BaseModel):
    """Validated username and password submitted to the login endpoint."""

    username: str = Field(min_length=1, max_length=128)
    password: SecretStr = Field(min_length=1, max_length=1024)


class LoginResponse(BaseModel):
    """Signed bearer token returned after successful demo-account login."""

    access_token: str
    token_type: Literal["bearer"]
    expires_in: int


class MeResponse(BaseModel):
    """Public identity fields returned for an authenticated account."""

    user_id: str
    username: str
    name: str
    role: str


class AuditEventResponse(BaseModel):
    """Public audit metadata with hashed, never raw, user questions."""

    id: int
    timestamp: str
    user_id: str | None
    role: str | None
    conversation_id: str | None
    event_type: str
    target: str | None
    decision: str
    reason_code: str
    duration_ms: float | None
    question_hash: str | None


def _get_audit_log() -> AuditLog:
    """Create an audit store using the configured or local SQLite path."""
    audit_path = Path(os.getenv("AUDIT_DB_PATH", "data/audit.sqlite3"))
    if not audit_path.is_absolute():
        audit_path = PROJECT_ROOT / audit_path
    return AuditLog(audit_path.resolve())


def _get_report_access_store() -> ReportAccessStore:
    """Create a report ownership store using the configured SQLite path."""
    database_path = Path(
        os.getenv("REPORT_ACCESS_DB_PATH", "data/report_access.sqlite3")
    )
    if not database_path.is_absolute():
        database_path = PROJECT_ROOT / database_path
    return ReportAccessStore(database_path.resolve())


def _record_audit(
    *,
    user_id: str | None,
    role: str | None,
    conversation_id: str | None,
    event_type: str,
    target: str | None,
    decision: str,
    reason_code: str,
    duration_ms: float | None = None,
    question: str | None = None,
) -> None:
    """Persist an audit event or fail closed when SQLite is unavailable."""
    try:
        _get_audit_log().record(
            user_id=user_id,
            role=role,
            conversation_id=conversation_id,
            event_type=event_type,
            target=target,
            decision=decision,
            reason_code=reason_code,
            duration_ms=duration_ms,
            question=question,
        )
    except (OSError, sqlite3.Error) as exc:
        LOGGER.error("Audit log write failed type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Audit logging is temporarily unavailable.",
        ) from exc


def _register_report_access(filename: str, user: UserAccount) -> None:
    """Record ownership, failing rather than exposing an untracked report."""
    try:
        _get_report_access_store().register_report(
            filename,
            user.user_id,
            user.role,
        )
    except (OSError, sqlite3.Error, ValueError) as exc:
        LOGGER.error("Report ownership write failed type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Report access metadata is temporarily unavailable.",
        ) from exc


def _resolve_report_file(path: Path) -> Path | None:
    """Resolve an existing DOCX only when it remains inside the reports folder."""
    try:
        reports_directory = REPORTS_DIR.resolve()
        report_path = path.resolve(strict=True)
        report_path.relative_to(reports_directory)
    except (OSError, RuntimeError, ValueError):
        return None

    if (
        not REPORT_FILENAME_PATTERN.fullmatch(report_path.name)
        or not report_path.is_file()
    ):
        return None
    return report_path


def _response_fields(
    state: Mapping[str, Any],
    conversation_id: str = "",
    moderation: ModerationInfo | None = None,
) -> AskResponse:
    """Extract tool-backed figures, sources, and caveats from graph state."""
    figures: list[dict[str, Any]] = []
    charts = build_chart_specs(state.get("tool_results", []))
    sources: list[str] = []
    caveats: list[str] = []
    document_sources: set[str] = set()
    report_filename: str | None = None

    for tool_result in state.get("tool_results", []):
        if not tool_result.get("success"):
            continue
        tool_name = tool_result.get("tool_name")
        result = tool_result.get("result")
        if not isinstance(result, dict):
            continue

        if tool_name == "run_analysis":
            analysis_name = result.get("analysis")
            if isinstance(analysis_name, str):
                sources.append(f"run_analysis:{analysis_name}")
            figures.append(
                {
                    "analysis": analysis_name,
                    "period": result.get("period"),
                    "data": result.get("data", []),
                }
            )
            assumptions = result.get("assumptions", [])
            if isinstance(assumptions, list):
                caveats.extend(
                    item for item in assumptions if isinstance(item, str)
                )
        elif tool_name == "query_business_data":
            dataset = result.get("dataset")
            if isinstance(dataset, str):
                sources.append(f"query_business_data:{dataset}")
            figures.append(
                {
                    "dataset": dataset,
                    "total_matches": result.get("total_matches"),
                    "rows": result.get("rows", []),
                }
            )
        elif tool_name == "search_documents":
            sources.append("search_documents")
        elif tool_name == "generate_report" and report_filename is None:
            report_path = result.get("path")
            if isinstance(report_path, str):
                resolved_report = _resolve_report_file(Path(report_path))
                if resolved_report is not None:
                    report_filename = resolved_report.name

    for chunk in state.get("retrieved_chunks", []):
        if isinstance(chunk, dict):
            document_name = chunk.get("document_name")
            if isinstance(document_name, str):
                document_sources.add(document_name)
    sources.extend(sorted(document_sources))
    if document_sources:
        caveats.append(
            "Document-derived statements are limited to retrieved passages "
            "and may be incomplete or outdated."
        )
        caveats.append(
            "Reported explanations are not proof that a factor caused a "
            "measured business change."
        )

    for error in state.get("evidence_errors", []):
        if isinstance(error, str):
            caveats.append(f"Evidence check: {error}")
    for error in state.get("errors", []):
        if isinstance(error, str):
            caveats.append(error)

    moderation_info = moderation or ModerationInfo(status="ok", notice=None)
    if moderation_info.status == "redacted":
        response_fields: dict[str, Any] = {
            "answer": GENERIC_REDACTION_NOTICE,
            "conversation_id": conversation_id,
            "figures": [],
            "charts": [],
            "sources": [],
            "caveats": [moderation_info.notice or GENERIC_REDACTION_NOTICE],
            "moderation": moderation_info,
        }
    else:
        response_fields = {
            "answer": str(state.get("final_answer", "")),
            "conversation_id": conversation_id,
            "figures": figures,
            "charts": charts,
            "sources": list(dict.fromkeys(sources)),
            "caveats": list(dict.fromkeys(caveats)),
            "moderation": moderation_info,
        }
        if report_filename is not None:
            response_fields["report_filename"] = report_filename

    return AskResponse(
        **response_fields,
    )


def _record_workflow_audit(
    state: Mapping[str, Any],
    user: UserAccount,
    conversation_id: str,
    prior_tool_result_count: int,
) -> None:
    """Audit model-selected tools and retrieved-text moderation decisions."""
    trace = state.get("workflow_trace", [])
    trace_by_call_id = {
        event["call_id"]: event
        for event in trace
        if isinstance(event, dict) and isinstance(event.get("call_id"), str)
    }
    current_results = state.get("tool_results", [])[prior_tool_result_count:]
    for result in current_results:
        tool_name = result.get("tool_name")
        if not isinstance(tool_name, str):
            continue
        arguments = result.get("arguments", {})
        target = tool_name
        if (
            tool_name == "query_business_data"
            and isinstance(arguments, dict)
            and isinstance(arguments.get("dataset"), str)
        ):
            target = f"{tool_name}:{arguments['dataset']}"
        call_id = result.get("call_id")
        call_trace = (
            trace_by_call_id.get(call_id)
            if isinstance(call_id, str)
            else None
        )
        duration_ms = (
            call_trace.get("duration_ms")
            if isinstance(call_trace, dict)
            and isinstance(call_trace.get("duration_ms"), (int, float))
            else None
        )
        success = bool(result.get("success"))
        raw_result = result.get("result")
        result_text = str(raw_result)
        denied = (
            not success
            and ACCESS_DENIED_MESSAGE.casefold() in result_text.casefold()
        )
        event_type = (
            "tool_denied"
            if denied
            else "report"
            if tool_name == "generate_report"
            else "tool_call"
        )
        _record_audit(
            user_id=user.user_id,
            role=user.role,
            conversation_id=conversation_id,
            event_type=event_type,
            target=target,
            decision="denied" if denied else "allowed" if success else "failed",
            reason_code=(
                "policy_denied"
                if denied
                else "completed"
                if success
                else "tool_error"
            ),
            duration_ms=duration_ms,
        )

    for event in trace:
        if not isinstance(event, dict):
            continue
        raw_result = event.get("raw_result")
        dropped_chunks = (
            raw_result.get("dropped_chunks")
            if isinstance(raw_result, dict)
            and raw_result.get("moderation_filtered") is True
            else event.get("dropped_chunks")
            if event.get("event") == "moderation"
            and event.get("category") == "M9"
            else None
        )
        if isinstance(dropped_chunks, int) and dropped_chunks > 0:
            _record_audit(
                user_id=user.user_id,
                role=user.role,
                conversation_id=conversation_id,
                event_type="moderation",
                target="search_documents",
                decision="filtered",
                reason_code="M9",
                duration_ms=(
                    event.get("duration_ms")
                    if isinstance(event.get("duration_ms"), (int, float))
                    else None
                ),
            )


async def _run_question(
    question: str,
    conversation_id: UUID | None,
    user: UserAccount,
) -> AskResponse:
    """Run one question through the same model, MCP tools, and graph as the CLI."""
    settings: Settings = load_settings()
    store = ConversationStore(settings.conversation_db_path)
    active_conversation_id = conversation_id or uuid4()
    identity = store.claim_conversation(
        active_conversation_id,
        user.user_id,
        user.role,
    )
    if identity.role != user.role:
        active_conversation_id = uuid4()
        store.claim_conversation(
            active_conversation_id,
            user.user_id,
            user.role,
        )
        history: list[tuple[str, str]] = []
        prior_tool_results = []
        prior_retrieved_chunks = []
    else:
        stored_history = store.load_recent_turns(
            active_conversation_id,
            settings.max_history_turns,
            user_id=user.user_id,
        )
        history = stored_history or []
        prior_tool_results, prior_retrieved_chunks = store.load_recent_evidence(
            active_conversation_id,
            settings.max_history_turns,
            user_id=user.user_id,
        )

    moderation_decision = check_input(question, user.role)
    if moderation_decision is not None:
        LOGGER.warning(
            "moderation event=input_refusal user_id=%s role=%s reason=%s",
            user.user_id,
            user.role,
            moderation_decision.category,
        )
        _record_audit(
            user_id=user.user_id,
            role=user.role,
            conversation_id=str(active_conversation_id),
            event_type="moderation",
            target="input",
            decision="refused",
            reason_code=moderation_decision.category,
            question=question,
        )
        response = _response_fields(
            {
                "final_answer": moderation_decision.response,
                "tool_results": [],
                "retrieved_chunks": [],
                "evidence_errors": [],
                "errors": [],
            },
            str(active_conversation_id),
            ModerationInfo(status="refused", notice=None),
        )
        store.append_turn(
            active_conversation_id,
            question.strip(),
            response.answer,
            user_id=user.user_id,
            role=user.role,
        )
        return response

    model = build_chat_model(settings)
    async with AnalystMCPClient(
        settings,
        MCPUserContext(user.user_id, user.role),
    ) as mcp_client:
        tools = await mcp_client.list_tools()
        state = await answer_question(
            question,
            model,
            tools,
            mcp_client,
            settings.max_steps,
            settings.max_retries,
            history=history,
            prior_tool_results=prior_tool_results,
            prior_retrieved_chunks=prior_retrieved_chunks,
        )
    current_turn_state = dict(state)
    current_turn_state["tool_results"] = state.get("tool_results", [])[
        len(prior_tool_results) :
    ]
    current_turn_state["retrieved_chunks"] = state.get("retrieved_chunks", [])[
        len(prior_retrieved_chunks) :
    ]
    candidate_response = _response_fields(
        current_turn_state,
        str(active_conversation_id),
    )
    output_moderation = moderate_output(
        candidate_response.model_dump_json(),
        user.role,
        settings.data_dir,
        settings.vector_store_path,
        answer_text=candidate_response.answer,
    )
    if (
        output_moderation.status == "redacted"
        and candidate_response.report_filename is not None
    ):
        report_path = _resolve_report_file(
            REPORTS_DIR / candidate_response.report_filename
        )
        if report_path is not None:
            try:
                report_path.unlink()
            except OSError as exc:
                LOGGER.error(
                    "Could not remove a redacted report type=%s",
                    type(exc).__name__,
                )
                raise
    moderation_info = ModerationInfo(
        status=output_moderation.status,
        notice=output_moderation.notice,
    )
    for reason_code in output_moderation.reason_codes:
        LOGGER.warning(
            "moderation event=output_redaction user_id=%s role=%s reason=%s",
            user.user_id,
            user.role,
            reason_code,
        )
        _record_audit(
            user_id=user.user_id,
            role=user.role,
            conversation_id=str(active_conversation_id),
            event_type="moderation",
            target="output",
            decision="redacted",
            reason_code=reason_code,
            question=question,
        )
    response = _response_fields(
        current_turn_state,
        str(active_conversation_id),
        moderation_info,
    )
    _record_workflow_audit(
        state,
        user,
        str(active_conversation_id),
        len(prior_tool_results),
    )
    store.append_turn(
        active_conversation_id,
        question.strip(),
        response.answer,
        tool_results=[
            result
            for result in state.get("tool_results", [])[len(prior_tool_results) :]
            if result.get("success")
        ] if moderation_info.status != "redacted" else [],
        retrieved_chunks=(
            state.get("retrieved_chunks", [])[len(prior_retrieved_chunks) :]
            if moderation_info.status != "redacted"
            else []
        ),
        user_id=user.user_id,
        role=user.role,
    )
    if response.report_filename is not None:
        _register_report_access(response.report_filename, user)
    return response


def create_app() -> FastAPI:
    """Create the HTTP app without requiring secrets during module import."""
    application = FastAPI(
        title="Business Analyst AI",
        description="Question-answering API over approved synthetic business data.",
        version="1.0.0",
    )
    application.state.rate_limiter = RateLimiter()

    def enforce_rate_limit(request: Request, identity: str) -> None:
        """Return 429 when an identity exceeds its rolling request allowance."""
        retry_after = request.app.state.rate_limiter.retry_after(identity)
        if retry_after is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )

    @application.post("/auth/login", response_model=LoginResponse)
    def login(payload: LoginRequest, request: Request) -> LoginResponse:
        """Verify demo credentials and issue a short-lived signed token."""
        enforce_rate_limit(request, f"login:{payload.username.casefold()}")
        login_started = time.perf_counter()
        try:
            secret = load_signing_secret()
            user = authenticate_user(
                payload.username,
                payload.password.get_secret_value(),
            )
        except AuthenticationConfigurationError as exc:
            LOGGER.error("Authentication configuration failure: %s", exc)
            _record_audit(
                user_id=None,
                role=None,
                conversation_id=None,
                event_type="login",
                target=None,
                decision="failed",
                reason_code="authentication_configuration",
                duration_ms=round((time.perf_counter() - login_started) * 1000, 2),
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication is not configured.",
            ) from exc
        except UserStoreError as exc:
            LOGGER.error("Authentication user data failure: %s", exc)
            _record_audit(
                user_id=None,
                role=None,
                conversation_id=None,
                event_type="login",
                target=None,
                decision="failed",
                reason_code="user_store_unavailable",
                duration_ms=round((time.perf_counter() - login_started) * 1000, 2),
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication user data is unavailable.",
            ) from exc
        if user is None:
            _record_audit(
                user_id=None,
                role=None,
                conversation_id=None,
                event_type="login",
                target=None,
                decision="denied",
                reason_code="invalid_credentials",
                duration_ms=round((time.perf_counter() - login_started) * 1000, 2),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        _record_audit(
            user_id=user.user_id,
            role=user.role,
            conversation_id=None,
            event_type="login",
            target=None,
            decision="allowed",
            reason_code="authenticated",
            duration_ms=round((time.perf_counter() - login_started) * 1000, 2),
        )
        return LoginResponse(
            access_token=create_access_token(user.user_id, secret),
            token_type="bearer",
            expires_in=int(ACCESS_TOKEN_LIFETIME.total_seconds()),
        )

    @application.get("/me", response_model=MeResponse)
    def read_me(user: UserAccount = Depends(get_current_user)) -> MeResponse:
        """Return the authenticated user's display name and current role."""
        return MeResponse(
            user_id=user.user_id,
            username=user.username,
            name=user.name,
            role=user.role,
        )

    @application.get("/audit", response_model=list[AuditEventResponse])
    def read_audit(
        limit: int = Query(default=50, ge=1, le=500),
        user: UserAccount = Depends(get_current_user),
    ) -> list[AuditEventResponse]:
        """Return recent audit events to administrators only."""
        if user.role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Audit access requires an administrator account.",
            )
        try:
            events = _get_audit_log().list_recent(limit)
        except (OSError, sqlite3.Error) as exc:
            LOGGER.error("Audit log read failed type=%s", type(exc).__name__)
            raise HTTPException(
                status_code=503,
                detail="Audit logging is temporarily unavailable.",
            ) from exc
        return [AuditEventResponse(**event) for event in events]

    @application.post(
        "/ask",
        response_model=AskResponse,
        response_model_exclude_unset=True,
    )
    async def ask(
        payload: AskRequest,
        request: Request,
        user: UserAccount = Depends(get_current_user),
    ) -> AskResponse:
        """Answer a question with evidence-backed figures, sources, and caveats."""
        enforce_rate_limit(request, user.username)
        request_started = time.perf_counter()
        try:
            _record_audit(
                user_id=user.user_id,
                role=user.role,
                conversation_id=(
                    str(payload.conversation_id)
                    if payload.conversation_id is not None
                    else None
                ),
                event_type="ask",
                target="/ask",
                decision="started",
                reason_code="request_started",
                question=payload.question,
            )
            response = await _run_question(
                payload.question,
                payload.conversation_id,
                user,
            )
            _record_audit(
                user_id=user.user_id,
                role=user.role,
                conversation_id=response.conversation_id,
                event_type="ask",
                target="/ask",
                decision=response.moderation.status,
                reason_code={
                    "ok": "answered",
                    "redacted": "output_redacted",
                    "refused": "moderation_refusal",
                }[response.moderation.status],
                duration_ms=round(
                    (time.perf_counter() - request_started) * 1000,
                    2,
                ),
                question=payload.question,
            )
            return response
        except ConversationOwnershipError as exc:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found.",
            ) from exc
        except sqlite3.Error as exc:
            LOGGER.exception("Conversation storage failure: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Conversation memory is temporarily unavailable.",
            ) from exc
        except ConfigurationError as exc:
            LOGGER.error("API configuration failure: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="The question-answering service is not configured.",
            ) from exc
        except ProviderUnavailableError as exc:
            LOGGER.error("Model providers are unavailable.")
            raise HTTPException(
                status_code=502,
                detail=str(exc),
            ) from exc
        except ModerationError as exc:
            LOGGER.error(
                "Moderation service failed type=%s",
                type(exc).__name__,
            )
            raise HTTPException(
                status_code=503,
                detail="Moderation is temporarily unavailable.",
            ) from exc
        except (GroqAPIError, OpenAIAPIError) as exc:
            LOGGER.warning(
                "Model API request failed type=%s status=%s",
                type(exc).__name__,
                getattr(exc, "status_code", None),
            )
            raise HTTPException(
                status_code=502,
                detail="The answer model is temporarily unavailable.",
            ) from exc
        except (McpError, OSError, RuntimeError, TimeoutError) as exc:
            LOGGER.error(
                "Question workflow failed type=%s: %s",
                type(exc).__name__,
                exc,
            )
            raise HTTPException(
                status_code=503,
                detail="The question could not be completed because a required service failed.",
            ) from exc

    @application.get("/reports/{filename}", response_class=FileResponse)
    def download_report(
        filename: str,
        user: UserAccount = Depends(get_current_user),
    ) -> FileResponse:
        """Serve a registered DOCX report to its owner or an administrator."""
        if not REPORT_FILENAME_PATTERN.fullmatch(filename):
            raise HTTPException(status_code=404, detail="Report not found.")

        report_path = _resolve_report_file(REPORTS_DIR / filename)
        if report_path is None:
            raise HTTPException(status_code=404, detail="Report not found.")

        try:
            owner = _get_report_access_store().get_owner(filename)
        except (OSError, sqlite3.Error) as exc:
            LOGGER.error("Report ownership read failed type=%s", type(exc).__name__)
            raise HTTPException(
                status_code=503,
                detail="Report access metadata is temporarily unavailable.",
            ) from exc
        if owner is None or (
            owner.user_id != user.user_id and user.role != "admin"
        ):
            raise HTTPException(status_code=404, detail="Report not found.")

        return FileResponse(
            path=report_path,
            media_type=DOCX_MEDIA_TYPE,
            filename=filename,
        )

    return application


app = create_app()
