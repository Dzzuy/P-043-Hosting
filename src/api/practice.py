"""HTTP contract for the advisor Practice Room."""

from typing import Annotated

from fastapi import APIRouter, Path, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.agents.roleplay.graph import (
    RoleplayScenarioNotFoundError,
    RoleplaySessionConflictError,
    RoleplaySessionNotFoundError,
)
from src.agents.roleplay.scenario_loader import ScenarioSummary
from src.agents.roleplay.state_reducer import StateTransitionError
from src.api.practice_errors import PracticeAPIError, PracticeRoute, session_conflict
from src.services.practice import (
    PracticeResultView,
    PracticeService,
    PracticeSessionView,
)


class CreatePracticeSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=1, max_length=120)
    max_turns: int | None = Field(default=None, ge=8, le=15)
    assignment_id: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("scenario_id")
    @classmethod
    def strip_scenario_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("scenario_id must not be blank")
        return normalized


class AdvisorMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be blank")
        return normalized


def create_practice_router(service: PracticeService) -> APIRouter:
    """Create a router with explicit service injection for app composition/tests."""
    router = APIRouter(prefix="/practice", tags=["practice"], route_class=PracticeRoute)

    @router.get("/scenarios", response_model=list[ScenarioSummary])
    async def list_scenarios() -> list[ScenarioSummary]:
        return service.list_scenarios()

    @router.post(
        "/sessions",
        response_model=PracticeSessionView,
        status_code=status.HTTP_201_CREATED,
    )
    async def start_session(
        request: CreatePracticeSessionRequest,
    ) -> PracticeSessionView:
        try:
            if request.max_turns is None:
                return await service.start_session(request.scenario_id)
            return await service.start_session(request.scenario_id, max_turns=request.max_turns)
        except RoleplayScenarioNotFoundError as exc:
            raise PracticeAPIError("session_not_found") from exc

    @router.post(
        "/{session_id}/message",
        response_model=PracticeSessionView,
    )
    async def send_message(
        session_id: Annotated[str, Path(min_length=1, max_length=120)],
        request: AdvisorMessageRequest,
    ) -> PracticeSessionView:
        try:
            return await service.send_message(session_id, request.message)
        except RoleplaySessionNotFoundError as exc:
            raise PracticeAPIError("session_not_found") from exc
        except (RoleplaySessionConflictError, StateTransitionError) as exc:
            raise session_conflict(exc) from exc

    @router.post("/{session_id}/finish", response_model=PracticeResultView)
    async def finish_session(
        session_id: Annotated[str, Path(min_length=1, max_length=120)],
    ) -> PracticeResultView:
        try:
            return await service.finish_session(session_id)
        except RoleplaySessionNotFoundError as exc:
            raise PracticeAPIError("session_not_found") from exc
        except RoleplaySessionConflictError as exc:
            raise session_conflict(exc) from exc

    @router.get("/{session_id}/result", response_model=PracticeResultView)
    async def get_result(
        session_id: Annotated[str, Path(min_length=1, max_length=120)],
    ) -> PracticeResultView:
        try:
            return await service.get_result(session_id)
        except RoleplaySessionNotFoundError as exc:
            raise PracticeAPIError("session_not_found") from exc

    @router.get("/{session_id}", response_model=PracticeSessionView)
    async def get_session(
        session_id: Annotated[str, Path(min_length=1, max_length=120)],
    ) -> PracticeSessionView:
        try:
            return await service.get_session(session_id)
        except RoleplaySessionNotFoundError as exc:
            raise PracticeAPIError("session_not_found") from exc

    return router
