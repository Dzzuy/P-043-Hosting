"""Auth-gated Practice history and manager-review routes."""

from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from pydantic import BaseModel

from src.agents.roleplay.graph import (
    RoleplayScenarioNotFoundError,
    RoleplaySessionConflictError,
    RoleplaySessionNotFoundError,
)
from src.agents.roleplay.scenario_loader import ScenarioSummary
from src.agents.roleplay.state_reducer import StateTransitionError
from src.api.practice import AdvisorMessageRequest, CreatePracticeSessionRequest
from src.api.practice_errors import PracticeAPIError, PracticeRoute, session_conflict
from src.integrations.voice_usage import VoiceUsageSummary
from src.models.auth import AuthenticatedUser
from src.services.practice import PracticeResultView, PracticeSessionView
from src.services.practice_records import (
    AdvisorPerformance,
    AssignmentRecord,
    AttemptNotFoundError,
    AttemptSummary,
    CreateAssignmentInput,
    ManagerReviewDecision,
    ManagerReviewRecord,
    TeamOverview,
)
from src.services.recorded_practice import RecordedAttemptDetail, RecordedPracticeService
from src.services.voice import (
    MAX_AUDIO_BYTES,
    VoiceInputError,
    VoiceProviderError,
    VoiceProviderUnavailableError,
    VoiceService,
)

IdentityDependency = Callable[..., Awaitable[AuthenticatedUser]]
SessionId = Annotated[str, Path(min_length=1, max_length=120)]


class CustomerSpeechRequest(BaseModel):
    message_id: str
    gender: Literal["female", "male"] = "female"


def create_recorded_practice_routers(
    service: RecordedPracticeService,
    get_identity: IdentityDependency,
    voice_service: VoiceService | None = None,
) -> tuple[APIRouter, APIRouter]:
    """Construct a replacement Practice router and manager router.

    Mount these instead of the legacy Practice router, never alongside it.
    """
    practice = APIRouter(prefix="/practice", tags=["practice"], route_class=PracticeRoute)
    manager = APIRouter(prefix="/manager", tags=["manager-review"], route_class=PracticeRoute)
    actor = Annotated[AuthenticatedUser, Depends(get_identity)]

    def require_role(identity: AuthenticatedUser, *roles: str) -> None:
        if identity.role not in roles:
            raise PracticeAPIError("forbidden")

    @practice.get("/scenarios", response_model=list[ScenarioSummary])
    async def list_scenarios(identity: actor) -> list[ScenarioSummary]:
        require_role(identity, "advisor", "manager")
        return service.list_scenarios()

    @practice.post("/sessions", response_model=PracticeSessionView, status_code=status.HTTP_201_CREATED)
    async def start_session(request: CreatePracticeSessionRequest, identity: actor) -> PracticeSessionView:
        require_role(identity, "advisor")
        try:
            return await service.start_session(
                request.scenario_id,
                identity.user_id,
                max_turns=request.max_turns,
                assignment_id=request.assignment_id,
            )
        except RoleplayScenarioNotFoundError as exc:
            raise PracticeAPIError("session_not_found") from exc

    @practice.get("/assignments", response_model=list[AssignmentRecord])
    async def advisor_assignments(identity: actor) -> list[AssignmentRecord]:
        require_role(identity, "advisor")
        return await service.advisor_assignments(identity.user_id)

    @practice.get("/history", response_model=list[AttemptSummary])
    async def history(identity: actor, scenario_id: str | None = Query(None, max_length=120)) -> list[AttemptSummary]:
        require_role(identity, "advisor")
        return await service.history(identity.user_id, scenario_id)

    @practice.post("/{session_id}/message", response_model=PracticeSessionView)
    async def send_message(
        session_id: SessionId, request: AdvisorMessageRequest, identity: actor
    ) -> PracticeSessionView:
        require_role(identity, "advisor")
        try:
            return await service.send_message(session_id, identity.user_id, request.message)
        except (AttemptNotFoundError, RoleplaySessionNotFoundError) as exc:
            raise PracticeAPIError("session_not_found") from exc
        except (RoleplaySessionConflictError, StateTransitionError) as exc:
            raise session_conflict(exc) from exc

    @practice.post("/{session_id}/retry-reply", response_model=PracticeSessionView)
    async def retry_customer_reply(session_id: SessionId, identity: actor) -> PracticeSessionView:
        require_role(identity, "advisor")
        try:
            return await service.retry_customer_reply(session_id, identity.user_id)
        except (AttemptNotFoundError, RoleplaySessionNotFoundError) as exc:
            raise PracticeAPIError("session_not_found") from exc
        except RoleplaySessionConflictError as exc:
            raise session_conflict(exc) from exc

    if voice_service is not None:

        @practice.post("/{session_id}/voice/transcribe")
        async def transcribe_voice(
            session_id: SessionId,
            request: Request,
            identity: actor,
            duration_seconds: float = Query(..., gt=0),
        ) -> dict[str, str]:
            require_role(identity, "advisor")
            mime_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
            audio = bytearray()
            async for chunk in request.stream():
                audio.extend(chunk)
                if len(audio) > MAX_AUDIO_BYTES:
                    raise PracticeAPIError("voice_invalid_audio", status_code=413)
            try:
                transcript = await voice_service.transcribe(
                    session_id, identity.user_id, bytes(audio), mime_type, duration_seconds
                )
                return {"transcript": transcript}
            except (AttemptNotFoundError, RoleplaySessionNotFoundError) as exc:
                raise PracticeAPIError("session_not_found") from exc
            except VoiceInputError as exc:
                raise PracticeAPIError(exc.code) from exc
            except VoiceProviderUnavailableError as exc:
                raise PracticeAPIError("voice_not_configured") from exc
            except VoiceProviderError as exc:
                raise PracticeAPIError("voice_failed") from exc

        @practice.post("/{session_id}/voice/speech")
        async def customer_speech(session_id: SessionId, request: CustomerSpeechRequest, identity: actor) -> Response:
            require_role(identity, "advisor")
            try:
                audio = await voice_service.synthesize(session_id, identity.user_id, request.message_id, request.gender)
                return Response(audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
            except (AttemptNotFoundError, RoleplaySessionNotFoundError) as exc:
                raise PracticeAPIError("session_not_found") from exc
            except VoiceInputError as exc:
                raise PracticeAPIError(exc.code) from exc
            except VoiceProviderUnavailableError as exc:
                raise PracticeAPIError("voice_not_configured") from exc
            except VoiceProviderError as exc:
                raise PracticeAPIError("voice_failed") from exc

    @practice.post("/{session_id}/finish", response_model=PracticeResultView)
    async def finish_session(session_id: SessionId, identity: actor) -> PracticeResultView:
        require_role(identity, "advisor")
        try:
            return await service.finish_session(session_id, identity.user_id)
        except (AttemptNotFoundError, RoleplaySessionNotFoundError) as exc:
            raise PracticeAPIError("session_not_found") from exc
        except RoleplaySessionConflictError as exc:
            raise session_conflict(exc) from exc

    @practice.get("/{session_id}/result", response_model=PracticeResultView)
    async def advisor_result(session_id: SessionId, identity: actor) -> PracticeResultView:
        require_role(identity, "advisor")
        try:
            return await service.advisor_result(session_id, identity.user_id)
        except (AttemptNotFoundError, RoleplaySessionNotFoundError) as exc:
            raise PracticeAPIError("session_not_found") from exc

    @practice.get("/{session_id}/attempt", response_model=RecordedAttemptDetail)
    async def advisor_detail(session_id: SessionId, identity: actor) -> RecordedAttemptDetail:
        require_role(identity, "advisor")
        try:
            return await service.advisor_detail(session_id, identity.user_id)
        except (AttemptNotFoundError, RoleplaySessionNotFoundError) as exc:
            raise PracticeAPIError("session_not_found") from exc

    @practice.get("/{session_id}", response_model=PracticeSessionView)
    async def advisor_session(session_id: SessionId, identity: actor) -> PracticeSessionView:
        require_role(identity, "advisor")
        try:
            return await service.advisor_session(session_id, identity.user_id)
        except (AttemptNotFoundError, RoleplaySessionNotFoundError) as exc:
            raise PracticeAPIError("session_not_found") from exc

    @manager.get("/reviews", response_model=list[AttemptSummary])
    async def review_queue(identity: actor) -> list[AttemptSummary]:
        require_role(identity, "manager")
        return await service.review_queue()

    @manager.get("/attempts", response_model=list[AttemptSummary])
    async def manager_history(
        identity: actor,
        advisor_id: str | None = Query(None, min_length=1, max_length=120),
        scenario_id: str | None = Query(None, min_length=1, max_length=120),
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ) -> list[AttemptSummary]:
        require_role(identity, "manager")
        return await service.manager_history(advisor_id, scenario_id, limit, offset)

    @manager.get("/overview", response_model=TeamOverview)
    async def team_overview(identity: actor) -> TeamOverview:
        require_role(identity, "manager")
        return await service.team_overview()

    @manager.get("/advisors", response_model=list[AdvisorPerformance])
    async def advisor_performance(identity: actor) -> list[AdvisorPerformance]:
        require_role(identity, "manager")
        return await service.advisor_performance()

    @manager.get("/assignments", response_model=list[AssignmentRecord])
    async def manager_assignments(identity: actor) -> list[AssignmentRecord]:
        require_role(identity, "manager")
        return await service.manager_assignments()

    @manager.post("/assignments", response_model=AssignmentRecord, status_code=status.HTTP_201_CREATED)
    async def create_assignment(request: CreateAssignmentInput, identity: actor) -> AssignmentRecord:
        require_role(identity, "manager")
        return await service.create_assignment(identity.user_id, request)

    @manager.get("/reviews/{session_id}", response_model=RecordedAttemptDetail)
    async def manager_detail(session_id: SessionId, identity: actor) -> RecordedAttemptDetail:
        require_role(identity, "manager")
        try:
            return await service.manager_detail(session_id)
        except (AttemptNotFoundError, RoleplaySessionNotFoundError) as exc:
            raise PracticeAPIError("session_not_found") from exc

    if voice_service is not None:

        @manager.get("/reviews/{session_id}/voice/usage", response_model=VoiceUsageSummary)
        async def manager_voice_usage(session_id: SessionId, identity: actor) -> VoiceUsageSummary:
            require_role(identity, "manager")
            try:
                return await voice_service.manager_usage_summary(session_id)
            except AttemptNotFoundError as exc:
                raise PracticeAPIError("session_not_found") from exc

    @manager.patch("/reviews/{session_id}", response_model=ManagerReviewRecord)
    async def approve(session_id: SessionId, decision: ManagerReviewDecision, identity: actor) -> ManagerReviewRecord:
        require_role(identity, "manager")
        try:
            return await service.approve(session_id, identity.user_id, decision)
        except AttemptNotFoundError as exc:
            raise PracticeAPIError("session_not_found") from exc

    return practice, manager
