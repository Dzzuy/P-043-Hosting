"""Identity-aware Practice operations, ready for the shared auth dependency.

Only backend-authenticated IDs may be passed to this service. The public
FastAPI router is intentionally not registered until auth is available.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from src.agents.roleplay.scenario_loader import ScenarioSummary
from src.agents.roleplay.state import EvaluationStatus
from src.models.auth import AuthenticatedUser
from src.services.practice import (
    PracticeEvaluationUnavailableError,
    PracticeResultView,
    PracticeService,
    PracticeSessionView,
)
from src.services.practice_dashboard import build_dashboard, build_progress
from src.services.practice_records import (
    AdvisorPerformance,
    AdvisorProgress,
    AssignmentConflictError,
    AssignmentRecord,
    AttemptSummary,
    CreateAssignmentInput,
    ManagerDashboard,
    ManagerReviewDecision,
    ManagerReviewRecord,
    ManagerTodo,
    PracticeRecordsRepository,
    TeamOverview,
)


class AdvisorDirectory(Protocol):
    async def active_advisors(self) -> list[AuthenticatedUser]: ...

    async def active_advisor(self, user_id: str) -> AuthenticatedUser | None: ...


class RecordedAttemptDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt: AttemptSummary
    session: PracticeSessionView
    ai_evaluation: PracticeResultView
    manager_review: ManagerReviewRecord | None = None


class RecordedPracticeService:
    def __init__(
        self,
        practice: PracticeService,
        records: PracticeRecordsRepository,
        advisors: AdvisorDirectory | None = None,
    ) -> None:
        self._practice = practice
        self._records = records
        self._advisors = advisors

    def list_scenarios(self) -> list[ScenarioSummary]:
        return self._practice.list_scenarios()

    async def start_session(
        self,
        scenario_id: str,
        advisor_id: str,
        max_turns: int | None = None,
        assignment_id: str | None = None,
    ) -> PracticeSessionView:
        if assignment_id:
            await self._records.validate_assignment(assignment_id, advisor_id, scenario_id)
        session = (
            await self._practice.start_session(scenario_id, max_turns=max_turns)
            if max_turns is not None
            else await self._practice.start_session(scenario_id)
        )
        if assignment_id:
            await self._records.register(session.session_id, session.scenario_id, advisor_id, assignment_id)
        else:
            await self._records.register(session.session_id, session.scenario_id, advisor_id)
        return session

    async def advisor_assignments(self, advisor_id: str) -> list[AssignmentRecord]:
        return await self._records.assignments(advisor_id)

    async def manager_assignments(self) -> list[AssignmentRecord]:
        return await self._records.assignments()

    async def create_assignment(self, manager_id: str, payload: CreateAssignmentInput) -> AssignmentRecord:
        if self._advisors is None or await self._advisors.active_advisor(payload.advisor_id) is None:
            raise AssignmentConflictError("Advisor does not exist or is inactive.")
        if not any(item.scenario_id == payload.scenario_id for item in self.list_scenarios()):
            raise AssignmentConflictError("Practice scenario was not found.")
        if payload.due_date and payload.due_date < datetime.now(UTC).date():
            raise AssignmentConflictError("Due date cannot be in the past.")
        return await self._records.create_assignment(manager_id, payload)

    async def advisor_performance(self) -> list[AdvisorPerformance]:
        if self._advisors is None:
            return []
        advisors = await self._advisors.active_advisors()
        persisted = await self._records.advisor_performance()
        results = []
        for advisor in advisors:
            performance = persisted.get(advisor.user_id) or AdvisorPerformance(
                advisor_id=advisor.user_id,
                display_name=advisor.display_name,
                completed_sessions=0,
                approved_sessions=0,
                scored_sessions=0,
                average_score=None,
                rank=None,
                skill_summaries=[],
                recent_scores=[],
            )
            results.append(performance.model_copy(update={"display_name": advisor.display_name}))
        eligible = sorted(
            (item for item in results if item.scored_sessions >= 3 and item.average_score is not None),
            key=lambda item: (-item.average_score, item.advisor_id),
        )
        rank_by_id: dict[str, int] = {}
        previous_score: float | None = None
        current_rank = 0
        for position, item in enumerate(eligible, start=1):
            if item.average_score != previous_score:
                current_rank = position
                previous_score = item.average_score
            rank_by_id[item.advisor_id] = current_rank
        return sorted(
            [item.model_copy(update={"rank": rank_by_id.get(item.advisor_id)}) for item in results],
            key=lambda item: (item.rank is None, item.rank or 0, item.display_name.casefold()),
        )

    async def send_message(self, session_id: str, advisor_id: str, message: str) -> PracticeSessionView:
        await self._records.owned_attempt(session_id, advisor_id)
        return await self._practice.send_message(session_id, message)

    async def retry_customer_reply(self, session_id: str, advisor_id: str) -> PracticeSessionView:
        await self._records.owned_attempt(session_id, advisor_id)
        return await self._practice.retry_customer_reply(session_id)

    async def finish_session(self, session_id: str, advisor_id: str) -> PracticeResultView:
        attempt = await self._records.owned_attempt(session_id, advisor_id)
        try:
            evaluation = await self._practice.finish_session(
                session_id,
                started_at=attempt.started_at,
                on_saved=lambda: self._records.mark_evaluation_pending(session_id),
            )
        except PracticeEvaluationUnavailableError:
            await self._records.mark_evaluation_failed(session_id)
            raise
        if evaluation.evaluation_status is EvaluationStatus.COMPLETE and evaluation.result is not None:
            await self._records.complete(session_id, evaluation.result)
        return evaluation

    async def advisor_detail(self, session_id: str, advisor_id: str) -> RecordedAttemptDetail:
        attempt = await self._records.owned_attempt(session_id, advisor_id)
        session = await self._practice.get_session(session_id)
        evaluation = await self._practice.get_result(session_id)
        review = await self._records.review_details(session_id)
        return RecordedAttemptDetail(
            attempt=attempt,
            session=session,
            ai_evaluation=evaluation,
            manager_review=review,
        )

    async def advisor_session(self, session_id: str, advisor_id: str) -> PracticeSessionView:
        await self._records.owned_attempt(session_id, advisor_id)
        return await self._practice.get_session(session_id)

    async def advisor_result(self, session_id: str, advisor_id: str) -> PracticeResultView:
        await self._records.owned_attempt(session_id, advisor_id)
        return await self._practice.get_result(session_id)

    async def history(self, advisor_id: str, scenario_id: str | None = None) -> list[AttemptSummary]:
        return await self._records.history(advisor_id, scenario_id)

    async def review_queue(self) -> list[AttemptSummary]:
        return await self._records.review_queue()

    async def manager_history(
        self, advisor_id: str | None = None, scenario_id: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[AttemptSummary]:
        return await self._records.manager_history(advisor_id, scenario_id, limit, offset)

    async def manager_attempt(self, session_id: str) -> AttemptSummary:
        return await self._records.manager_attempt(session_id)

    async def team_overview(self) -> TeamOverview:
        return await self._records.team_overview()

    async def manager_detail(self, session_id: str) -> RecordedAttemptDetail:
        attempt = await self._records.manager_attempt(session_id)
        session = await self._practice.get_session(session_id)
        evaluation = await self._practice.get_result(session_id)
        review = await self._records.review_details(session_id)
        return RecordedAttemptDetail(
            attempt=attempt,
            session=session,
            ai_evaluation=evaluation,
            manager_review=review,
        )

    async def approve(self, session_id: str, manager_id: str, decision: ManagerReviewDecision) -> ManagerReviewRecord:
        return await self._records.approve(session_id, manager_id, decision)

    async def manager_dashboard(self, weeks: int = 8, now: datetime | None = None) -> ManagerDashboard:
        now = now or datetime.now(UTC)
        advisors = await self._advisors.active_advisors() if self._advisors is not None else []
        return build_dashboard(
            advisors,
            await self._records.scored_attempts(),
            await self._records.review_queue(),
            await self._records.assignments(),
            now,
            weeks,
        )

    async def advisor_progress(self, advisor_id: str, now: datetime | None = None) -> AdvisorProgress:
        return build_progress(await self._records.scored_attempts(advisor_id), now or datetime.now(UTC))

    async def list_todos(self, manager_id: str) -> list[ManagerTodo]:
        return await self._records.list_todos(manager_id)

    async def create_todo(self, manager_id: str, text: str) -> ManagerTodo:
        return await self._records.create_todo(manager_id, text)

    async def set_todo_done(self, manager_id: str, todo_id: str, done: bool) -> ManagerTodo:
        return await self._records.set_todo_done(manager_id, todo_id, done)
