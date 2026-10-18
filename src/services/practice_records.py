"""Practice attempt history and manager-review business rules.

The caller must supply identities from a trusted authentication dependency.
This module deliberately does not accept user IDs from browser request bodies.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


class ReviewValidationError(ValueError):
    """The review body is well formed but breaks a review rule (for example, a missing reason)."""


class TodoNotFoundError(LookupError):
    """The to-do does not exist or belongs to another manager."""


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


class ScoreOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=1, le=3)
    reason: str = Field(default="", max_length=2000)


class ManagerReviewDecision(BaseModel):
    """Manager corrections; missing scores retain their AI-draft values.

    Overrides are either ``{criterion: {score, reason}}`` or the legacy
    ``{criterion: score}`` paired with one shared ``change_reason``.
    """

    model_config = ConfigDict(extra="forbid")

    score_overrides: dict[CriterionType, int | ScoreOverride] = Field(default_factory=dict)
    recommended_next_practice: RecommendedNextPractice | None = None
    change_reason: str | None = Field(default=None, max_length=2000)
    general_comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_reason(self) -> ManagerReviewDecision:
        if self.change_reason is not None and not self.change_reason.strip():
            raise ValueError("change_reason must not be blank")
        for value in self.score_overrides.values():
            score = value.score if isinstance(value, ScoreOverride) else value
            if score < 1 or score > 3:
                raise ValueError("score overrides must be between 1 and 3")
        if any(isinstance(value, int) for value in self.score_overrides.values()) and self.change_reason is None:
            raise ValueError("change_reason is required for score overrides without a reason")
        return self

    def normalized_overrides(self) -> dict[CriterionType, ScoreOverride]:
        shared = (self.change_reason or "").strip()
        return {
            criterion: value if isinstance(value, ScoreOverride) else ScoreOverride(score=value, reason=shared)
            for criterion, value in self.score_overrides.items()
        }

    def stored_comment(self) -> str:
        """Text kept in the review row: the general comment, else the legacy shared reason."""
        return (self.general_comment or self.change_reason or "").strip()


class ManagerReviewRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    manager_id: str
    reviewed_at: datetime
    change_reason: str
    general_comment: str | None = None
    ai_draft: SessionEvaluationResult
    approved_result: SessionEvaluationResult


class ScoredAttempt(BaseModel):
    """A completed attempt with parsed AI and approved results, for aggregation."""

    session_id: str
    advisor_id: str
    scenario_id: str
    completed_at: datetime
    evaluation_status: EvaluationStatus
    ai_draft: SessionEvaluationResult | None = None
    approved: SessionEvaluationResult | None = None


class CreateTodoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=300)

    @field_validator("text", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class UpdateTodoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    done: bool


class ManagerTodo(BaseModel):
    todo_id: str
    text: str
    done: bool
    created_at: datetime
    done_at: datetime | None = None


class CriterionCell(BaseModel):
    avg: float | None
    n: int
    insufficient: bool


class SkillMatrixRow(BaseModel):
    advisor_id: str
    display_name: str
    is_sample: bool
    approved_sessions: int
    overall_avg: float | None
    criteria: dict[CriterionType, CriterionCell]


class TrendPoint(BaseModel):
    week_start: date
    avg_score: float | None
    attempts: int


class AgreementRow(BaseModel):
    criterion: CriterionType
    reviewed: int
    changed: int
    changed_rate: float
    mean_delta: float


class QueueSummary(BaseModel):
    pending: int
    oldest_pending_at: datetime | None


class OverdueAssignment(BaseModel):
    assignment_id: str
    advisor_id: str
    advisor_name: str
    title: str
    due_date: date


class AssignmentsSummary(BaseModel):
    open: int
    overdue: list[OverdueAssignment]


class ManagerDashboard(BaseModel):
    has_sample_data: bool
    advisor_count: int
    approved_attempts: int
    weeks: int
    skill_matrix: list[SkillMatrixRow]
    team_trend: list[TrendPoint]
    advisor_trends: dict[str, list[TrendPoint]]
    ai_agreement: list[AgreementRow]
    queue: QueueSummary
    assignments: AssignmentsSummary


class CriterionProgress(BaseModel):
    latest_avg: float | None
    change_4w: float | None
    n: int


class ScenarioProgress(BaseModel):
    last_session_id: str
    last_completed_at: datetime
    last_status: str
    last_score: float | None


class AdvisorProgress(BaseModel):
    approved_sessions: int
    overall_avg: float | None
    current_week_avg: float | None
    change_8w: float | None
    trend: list[TrendPoint]
    criteria: dict[CriterionType, CriterionProgress]
    scenarios: dict[str, ScenarioProgress]


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

    async def scored_attempts(self, advisor_id: str | None = None) -> list[ScoredAttempt]: ...

    async def list_todos(self, manager_id: str) -> list[ManagerTodo]: ...

    async def create_todo(self, manager_id: str, text: str) -> ManagerTodo: ...

    async def set_todo_done(self, manager_id: str, todo_id: str, done: bool) -> ManagerTodo: ...

    async def approve(
        self, session_id: str, manager_id: str, decision: ManagerReviewDecision
    ) -> ManagerReviewRecord: ...


def approved_evaluation(draft: SessionEvaluationResult, decision: ManagerReviewDecision) -> SessionEvaluationResult:
    """Apply only evidence-backed score edits and recompute the aggregate in code."""
    updated = draft.model_copy(deep=True)
    criteria = {item.criterion: item for item in updated.evaluations}
    for criterion, override in decision.normalized_overrides().items():
        item = criteria.get(criterion)
        if item is None or item.status is not CriterionStatus.ASSESSED:
            raise ReviewConflictError("only assessed criteria may receive score overrides")
        if override.score == item.score:
            continue
        if not override.reason.strip():
            raise ReviewValidationError(f"Cần nhập lý do khi đổi điểm tiêu chí {criterion.value}.")
        item.score = override.score
        item.manager_reason = override.reason.strip()
    if decision.recommended_next_practice is not None:
        updated.recommended_next_practice = decision.recommended_next_practice
    scores = [item.score for item in updated.evaluations if item.status is CriterionStatus.ASSESSED]
    updated.overall_score = sum(scores) / len(scores) if scores else None
    updated.review_status = ReviewStatus.MANAGER_APPROVED
    return SessionEvaluationResult.model_validate(updated.model_dump())
