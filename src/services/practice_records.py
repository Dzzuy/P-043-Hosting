"""Practice attempt history and manager-review business rules.

The caller must supply identities from a trusted authentication dependency.
This module deliberately does not accept user IDs from browser request bodies.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.agents.roleplay.state import EvaluationStatus
from src.models.evaluation import (
    CriterionStatus,
    CriterionType,
    RecommendedNextPractice,
    ReviewStatus,
    SessionEvaluationResult,
)


class AttemptNotFoundError(LookupError):
    """The attempt does not exist or is not visible to this advisor."""


class ReviewConflictError(ValueError):
    """The attempt cannot be reviewed in its current state."""


class AssignmentConflictError(ValueError):
    """The assignment cannot be used for this advisor or scenario."""


class AssignmentStatus(StrEnum):
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class CreateAssignmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    advisor_id: str = Field(min_length=1, max_length=120)
    scenario_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    due_date: date | None = None

    @model_validator(mode="after")
    def strip_fields(self) -> CreateAssignmentInput:
        self.advisor_id = self.advisor_id.strip()
        self.scenario_id = self.scenario_id.strip()
        self.title = self.title.strip()
        if not all((self.advisor_id, self.scenario_id, self.title)):
            raise ValueError("assignment fields must not be blank")
        return self


class AssignmentRecord(CreateAssignmentInput):
    assignment_id: str
    manager_id: str
    created_at: datetime
    status: AssignmentStatus
    session_id: str | None = None


class AttemptSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    scenario_id: str
    advisor_id: str
    started_at: datetime
    completed_at: datetime | None = None
    evaluation_status: EvaluationStatus = EvaluationStatus.NOT_STARTED
    review_status: ReviewStatus = ReviewStatus.AI_DRAFT
    ai_score: float | None = None
    approved_score: float | None = None


class SkillSummary(BaseModel):
    criterion: CriterionType
    average_score: float
    assessed_count: int


class TeamOverview(BaseModel):
    completed_attempts: int
    approved_attempts: int
    pending_attempts: int
    failed_evaluations: int
    active_advisors: int
    skill_summaries: list[SkillSummary]


class ApprovedScore(BaseModel):
    session_id: str
    scenario_id: str
    score: float
    reviewed_at: datetime


class AdvisorPerformance(BaseModel):
    advisor_id: str
    display_name: str
    completed_sessions: int
    approved_sessions: int
    scored_sessions: int
    average_score: float | None
    rank: int | None
    skill_summaries: list[SkillSummary]
    recent_scores: list[ApprovedScore]


class ManagerReviewDecision(BaseModel):
    """Manager corrections; missing scores retain their AI-draft values."""

    model_config = ConfigDict(extra="forbid")

    score_overrides: dict[CriterionType, int] = Field(default_factory=dict)
    recommended_next_practice: RecommendedNextPractice | None = None
    change_reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_reason(self) -> ManagerReviewDecision:
        if not self.change_reason.strip():
            raise ValueError("change_reason must not be blank")
        if any(score < 1 or score > 3 for score in self.score_overrides.values()):
            raise ValueError("score overrides must be between 1 and 3")
        return self


class ManagerReviewRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    manager_id: str
    reviewed_at: datetime
    change_reason: str
    ai_draft: SessionEvaluationResult
    approved_result: SessionEvaluationResult


class PracticeRecordsRepository(Protocol):
    async def register(
        self, session_id: str, scenario_id: str, advisor_id: str, assignment_id: str | None = None
    ) -> None: ...

    async def create_assignment(self, manager_id: str, payload: CreateAssignmentInput) -> AssignmentRecord: ...

    async def assignments(self, advisor_id: str | None = None) -> list[AssignmentRecord]: ...

    async def validate_assignment(self, assignment_id: str, advisor_id: str, scenario_id: str) -> None: ...

    async def advisor_performance(self) -> dict[str, AdvisorPerformance]: ...

    async def mark_evaluation_pending(self, session_id: str) -> None: ...

    async def mark_evaluation_failed(self, session_id: str) -> None: ...

    async def complete(self, session_id: str, ai_draft: SessionEvaluationResult) -> None: ...

    async def history(self, advisor_id: str, scenario_id: str | None = None) -> list[AttemptSummary]: ...

    async def owned_attempt(self, session_id: str, advisor_id: str) -> AttemptSummary: ...

    async def manager_attempt(self, session_id: str) -> AttemptSummary: ...

    async def review_details(self, session_id: str) -> ManagerReviewRecord | None: ...

    async def review_queue(self) -> list[AttemptSummary]: ...

    async def manager_history(
        self, advisor_id: str | None = None, scenario_id: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[AttemptSummary]: ...

    async def team_overview(self) -> TeamOverview: ...

    async def approve(
        self, session_id: str, manager_id: str, decision: ManagerReviewDecision
    ) -> ManagerReviewRecord: ...


def approved_evaluation(draft: SessionEvaluationResult, decision: ManagerReviewDecision) -> SessionEvaluationResult:
    """Apply only evidence-backed score edits and recompute the aggregate in code."""
    updated = draft.model_copy(deep=True)
    criteria = {item.criterion: item for item in updated.evaluations}
    for criterion, score in decision.score_overrides.items():
        item = criteria.get(criterion)
        if item is None or item.status is not CriterionStatus.ASSESSED:
            raise ReviewConflictError("only assessed criteria may receive score overrides")
        item.score = score
    if decision.recommended_next_practice is not None:
        updated.recommended_next_practice = decision.recommended_next_practice
    scores = [item.score for item in updated.evaluations if item.status is CriterionStatus.ASSESSED]
    updated.overall_score = sum(scores) / len(scores) if scores else None
    updated.review_status = ReviewStatus.MANAGER_APPROVED
    return SessionEvaluationResult.model_validate(updated.model_dump())
