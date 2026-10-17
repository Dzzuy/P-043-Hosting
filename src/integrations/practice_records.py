"""SQL storage for advisor attempt history and manager decisions.

Separate tables avoid changing Chương's existing checkpoint schema. Old,
unowned checkpoints are intentionally excluded from per-advisor history.
"""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from uuid import uuid4

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from src.agents.roleplay.state import EvaluationStatus
from src.integrations.practice_persistence import normalize_database_url
from src.models.evaluation import CriterionStatus, CriterionType, ReviewStatus, SessionEvaluationResult
from src.services.practice_records import (
    AdvisorPerformance,
    ApprovedScore,
    AssignmentConflictError,
    AssignmentRecord,
    AssignmentStatus,
    AttemptNotFoundError,
    AttemptSummary,
    CreateAssignmentInput,
    ManagerReviewDecision,
    ManagerReviewRecord,
    ReviewConflictError,
    SkillSummary,
    TeamOverview,
    approved_evaluation,
)


class SQLPracticeRecordsRepository:
    def __init__(self, database_url: str, *, engine: Engine | None = None) -> None:
        self._engine = engine or create_engine(normalize_database_url(database_url), pool_pre_ping=True)
        metadata = MetaData()
        self._attempts = Table(
            "practice_attempts",
            metadata,
            Column("session_id", String(120), primary_key=True),
            Column("scenario_id", String(120), nullable=False),
            Column("advisor_id", String(120), nullable=False, index=True),
            Column("started_at", DateTime(timezone=True), nullable=False),
            Column("completed_at", DateTime(timezone=True)),
            Column("evaluation_status", String(20), nullable=False),
            Column("ai_draft_json", Text),
        )
        self._reviews = Table(
            "practice_manager_reviews",
            metadata,
            Column("session_id", String(120), ForeignKey("practice_attempts.session_id"), primary_key=True),
            Column("manager_id", String(120), nullable=False),
            Column("reviewed_at", DateTime(timezone=True), nullable=False),
            Column("change_reason", Text, nullable=False),
            Column("approved_result_json", Text, nullable=False),
        )
        self._assignments = Table(
            "practice_assignments",
            metadata,
            Column("assignment_id", String(120), primary_key=True),
            Column("manager_id", String(120), nullable=False),
            Column("advisor_id", String(120), nullable=False, index=True),
            Column("scenario_id", String(120), nullable=False),
            Column("title", String(200), nullable=False),
            Column("due_date", Date),
            Column("created_at", DateTime(timezone=True), nullable=False),
        )
        self._assignment_sessions = Table(
            "practice_assignment_sessions",
            metadata,
            Column("session_id", String(120), ForeignKey("practice_attempts.session_id"), primary_key=True),
            Column(
                "assignment_id",
                String(120),
                ForeignKey("practice_assignments.assignment_id"),
                nullable=False,
                index=True,
            ),
        )
        self._metadata = metadata
        self._schema_ready = False
        self._schema_lock = Lock()

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if not self._schema_ready:
                self._metadata.create_all(self._engine)
                self._schema_ready = True

    async def register(
        self, session_id: str, scenario_id: str, advisor_id: str, assignment_id: str | None = None
    ) -> None:
        if not all(value.strip() for value in (session_id, scenario_id, advisor_id)):
            raise ValueError("attempt identity fields must not be blank")
        self._ensure_schema()
        with self._engine.begin() as connection:
            if assignment_id:
                self._validate_assignment_in_connection(connection, assignment_id, advisor_id, scenario_id)
            connection.execute(
                insert(self._attempts).values(
                    session_id=session_id,
                    scenario_id=scenario_id,
                    advisor_id=advisor_id,
                    started_at=datetime.now(UTC),
                    evaluation_status=EvaluationStatus.NOT_STARTED.value,
                )
            )
            if assignment_id:
                connection.execute(
                    insert(self._assignment_sessions).values(session_id=session_id, assignment_id=assignment_id)
                )

    def _validate_assignment_in_connection(
        self, connection, assignment_id: str, advisor_id: str, scenario_id: str
    ) -> None:
        assignment = connection.execute(
            select(self._assignments.c.advisor_id, self._assignments.c.scenario_id).where(
                self._assignments.c.assignment_id == assignment_id
            )
        ).first()
        if assignment is None or assignment.advisor_id != advisor_id or assignment.scenario_id != scenario_id:
            raise AssignmentConflictError("Assignment does not match this advisor and scenario.")
        completed = connection.execute(
            select(self._attempts.c.session_id)
            .select_from(
                self._assignment_sessions.join(
                    self._attempts, self._assignment_sessions.c.session_id == self._attempts.c.session_id
                )
            )
            .where(self._assignment_sessions.c.assignment_id == assignment_id)
            .where(self._attempts.c.evaluation_status == EvaluationStatus.COMPLETE.value)
            .limit(1)
        ).first()
        if completed:
            raise AssignmentConflictError("Assignment is already completed.")

    async def validate_assignment(self, assignment_id: str, advisor_id: str, scenario_id: str) -> None:
        self._ensure_schema()
        with self._engine.connect() as connection:
            self._validate_assignment_in_connection(connection, assignment_id, advisor_id, scenario_id)

    async def create_assignment(self, manager_id: str, payload: CreateAssignmentInput) -> AssignmentRecord:
        self._ensure_schema()
        assignment_id = str(uuid4())
        created_at = datetime.now(UTC)
        with self._engine.begin() as connection:
            connection.execute(
                insert(self._assignments).values(
                    assignment_id=assignment_id,
                    manager_id=manager_id,
                    advisor_id=payload.advisor_id,
                    scenario_id=payload.scenario_id,
                    title=payload.title,
                    due_date=payload.due_date,
                    created_at=created_at,
                )
            )
        return AssignmentRecord(
            **payload.model_dump(),
            assignment_id=assignment_id,
            manager_id=manager_id,
            created_at=created_at,
            status=AssignmentStatus.ASSIGNED,
        )

    async def assignments(self, advisor_id: str | None = None) -> list[AssignmentRecord]:
        self._ensure_schema()
        query = select(self._assignments).order_by(
            self._assignments.c.created_at.desc(), self._assignments.c.assignment_id.desc()
        )
        if advisor_id is not None:
            query = query.where(self._assignments.c.advisor_id == advisor_id)
        with self._engine.connect() as connection:
            assignment_rows = list(connection.execute(query).mappings())
            if not assignment_rows:
                return []
            session_rows = list(
                connection.execute(
                    select(
                        self._assignment_sessions.c.assignment_id,
                        self._attempts.c.session_id,
                        self._attempts.c.evaluation_status,
                        self._attempts.c.started_at,
                    )
                    .select_from(self._assignment_sessions.join(self._attempts))
                    .where(
                        self._assignment_sessions.c.assignment_id.in_([row.assignment_id for row in assignment_rows])
                    )
                    .order_by(self._attempts.c.started_at.desc())
                ).mappings()
            )
        by_assignment: dict[str, list] = {}
        for row in session_rows:
            by_assignment.setdefault(row.assignment_id, []).append(row)
        results = []
        for row in assignment_rows:
            sessions = by_assignment.get(row.assignment_id, [])
            completed = next(
                (item for item in sessions if item.evaluation_status == EvaluationStatus.COMPLETE.value), None
            )
            status = (
                AssignmentStatus.COMPLETED
                if completed
                else AssignmentStatus.IN_PROGRESS
                if sessions
                else AssignmentStatus.ASSIGNED
            )
            results.append(
                AssignmentRecord(
                    assignment_id=row.assignment_id,
                    manager_id=row.manager_id,
                    advisor_id=row.advisor_id,
                    scenario_id=row.scenario_id,
                    title=row.title,
                    due_date=row.due_date,
                    created_at=row.created_at,
                    status=status,
                    session_id=(completed or sessions[0]).session_id if sessions else None,
                )
            )
        return results

    async def mark_evaluation_pending(self, session_id: str) -> None:
        """Expose the saved transcript in history before the evaluator runs."""
        self._ensure_schema()
        with self._engine.begin() as connection:
            changed = connection.execute(
                update(self._attempts)
                .where(self._attempts.c.session_id == session_id)
                .where(self._attempts.c.ai_draft_json.is_(None))
                .values(completed_at=datetime.now(UTC), evaluation_status=EvaluationStatus.PENDING.value)
            )
            if changed.rowcount == 0:
                exists = connection.execute(
                    select(self._attempts.c.session_id).where(self._attempts.c.session_id == session_id)
                ).scalar_one_or_none()
                if exists is None:
                    raise AttemptNotFoundError(session_id)

    async def mark_evaluation_failed(self, session_id: str) -> None:
        """Keep a finished attempt visible when the evaluator needs retry."""
        self._ensure_schema()
        with self._engine.begin() as connection:
            changed = connection.execute(
                update(self._attempts)
                .where(self._attempts.c.session_id == session_id)
                .where(self._attempts.c.ai_draft_json.is_(None))
                .values(completed_at=datetime.now(UTC), evaluation_status=EvaluationStatus.FAILED.value)
            )
            if changed.rowcount == 0:
                exists = connection.execute(
                    select(self._attempts.c.session_id).where(self._attempts.c.session_id == session_id)
                ).scalar_one_or_none()
                if exists is None:
                    raise AttemptNotFoundError(session_id)

    async def complete(self, session_id: str, ai_draft: SessionEvaluationResult) -> None:
        if ai_draft.session_id != session_id or ai_draft.review_status is not ReviewStatus.AI_DRAFT:
            raise ValueError("draft must match the attempt and remain provisional")
        self._ensure_schema()
        with self._engine.begin() as connection:
            attempt = connection.execute(
                select(self._attempts.c.scenario_id).where(self._attempts.c.session_id == session_id)
            ).scalar_one_or_none()
            if attempt is None:
                raise AttemptNotFoundError(session_id)
            if attempt != ai_draft.scenario_id:
                raise ValueError("draft scenario does not match the attempt")
            connection.execute(
                update(self._attempts)
                .where(self._attempts.c.session_id == session_id)
                .where(self._attempts.c.ai_draft_json.is_(None))
                .values(
                    completed_at=datetime.now(UTC),
                    evaluation_status=EvaluationStatus.COMPLETE.value,
                    ai_draft_json=ai_draft.model_dump_json(),
                )
            )

    async def history(self, advisor_id: str, scenario_id: str | None = None) -> list[AttemptSummary]:
        if not advisor_id.strip():
            raise ValueError("advisor_id must not be blank")
        self._ensure_schema()
        query = self._summary_query().where(
            self._attempts.c.advisor_id == advisor_id,
            self._attempts.c.completed_at.is_not(None),
        )
        if scenario_id is not None:
            query = query.where(self._attempts.c.scenario_id == scenario_id)
        query = query.order_by(self._attempts.c.completed_at.desc(), self._attempts.c.session_id.desc())
        with self._engine.connect() as connection:
            return [self._to_summary(row) for row in connection.execute(query).mappings()]

    async def owned_attempt(self, session_id: str, advisor_id: str) -> AttemptSummary:
        """Use the same not-found error for missing and other-advisor attempts."""
        if not advisor_id.strip():
            raise ValueError("advisor_id must not be blank")
        self._ensure_schema()
        query = self._summary_query().where(
            self._attempts.c.session_id == session_id,
            self._attempts.c.advisor_id == advisor_id,
        )
        with self._engine.connect() as connection:
            row = connection.execute(query).mappings().first()
        if row is None:
            raise AttemptNotFoundError(session_id)
        return self._to_summary(row)

    async def manager_attempt(self, session_id: str) -> AttemptSummary:
        """Caller must enforce manager role before invoking this method."""
        self._ensure_schema()
        query = self._summary_query().where(self._attempts.c.session_id == session_id)
        with self._engine.connect() as connection:
            row = connection.execute(query).mappings().first()
        if row is None:
            raise AttemptNotFoundError(session_id)
        return self._to_summary(row)

    async def review_details(self, session_id: str) -> ManagerReviewRecord | None:
        """Return the immutable AI draft and approved decision; manager-only caller."""
        self._ensure_schema()
        query = (
            select(
                self._attempts.c.ai_draft_json,
                self._reviews.c.manager_id,
                self._reviews.c.reviewed_at,
                self._reviews.c.change_reason,
                self._reviews.c.approved_result_json,
            )
            .select_from(self._attempts.join(self._reviews))
            .where(self._attempts.c.session_id == session_id)
        )
        with self._engine.connect() as connection:
            row = connection.execute(query).mappings().first()
        if row is None:
            return None
        return ManagerReviewRecord(
            session_id=session_id,
            manager_id=row.manager_id,
            reviewed_at=row.reviewed_at,
            change_reason=row.change_reason,
            ai_draft=SessionEvaluationResult.model_validate_json(row.ai_draft_json),
            approved_result=SessionEvaluationResult.model_validate_json(row.approved_result_json),
        )

    async def review_queue(self) -> list[AttemptSummary]:
        """Latest unreviewed completed attempt per advisor and scenario."""
        self._ensure_schema()
        query = (
            self._summary_query()
            .where(self._attempts.c.ai_draft_json.is_not(None))
            .where(self._reviews.c.session_id.is_(None))
            .order_by(self._attempts.c.completed_at.desc(), self._attempts.c.session_id.desc())
        )
        with self._engine.connect() as connection:
            rows = [self._to_summary(row) for row in connection.execute(query).mappings()]
        latest: dict[tuple[str, str], AttemptSummary] = {}
        for row in rows:
            latest.setdefault((row.advisor_id, row.scenario_id), row)
        return list(latest.values())

    async def manager_history(
        self, advisor_id: str | None = None, scenario_id: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[AttemptSummary]:
        """Completed attempts, including older attempts hidden by the grouped review queue."""
        self._ensure_schema()
        query = self._summary_query().where(self._attempts.c.completed_at.is_not(None))
        if advisor_id:
            query = query.where(self._attempts.c.advisor_id == advisor_id)
        if scenario_id:
            query = query.where(self._attempts.c.scenario_id == scenario_id)
        query = query.order_by(self._attempts.c.completed_at.desc(), self._attempts.c.session_id.desc())
        with self._engine.connect() as connection:
            rows = connection.execute(query.limit(limit).offset(offset)).mappings()
            return [self._to_summary(row) for row in rows]

    async def team_overview(self) -> TeamOverview:
        """Summarize persisted results; skill scores use manager-approved evaluations only."""
        self._ensure_schema()
        query = self._summary_query().where(self._attempts.c.completed_at.is_not(None))
        with self._engine.connect() as connection:
            rows = list(connection.execute(query).mappings())
        approved = [row for row in rows if row.approved_result_json]
        pending = [row for row in rows if row.ai_draft_json and not row.approved_result_json]
        failed = [row for row in rows if row.evaluation_status == EvaluationStatus.FAILED.value]
        scores: dict[CriterionType, list[int]] = {criterion: [] for criterion in CriterionType}
        for row in approved:
            result = SessionEvaluationResult.model_validate_json(row.approved_result_json)
            for item in result.evaluations:
                if item.status is CriterionStatus.ASSESSED and item.score is not None:
                    scores[item.criterion].append(item.score)
        return TeamOverview(
            completed_attempts=len(rows),
            approved_attempts=len(approved),
            pending_attempts=len(pending),
            failed_evaluations=len(failed),
            active_advisors=len({row.advisor_id for row in rows}),
            skill_summaries=[
                SkillSummary(
                    criterion=criterion,
                    average_score=sum(values) / len(values),
                    assessed_count=len(values),
                )
                for criterion, values in scores.items()
                if values
            ],
        )

    async def advisor_performance(self) -> dict[str, AdvisorPerformance]:
        """Aggregate only persisted manager-approved scores, grouped by advisor."""
        self._ensure_schema()
        query = select(
            self._attempts.c.advisor_id,
            self._attempts.c.session_id,
            self._attempts.c.scenario_id,
            self._attempts.c.completed_at,
            self._reviews.c.reviewed_at,
            self._reviews.c.approved_result_json,
        ).select_from(self._attempts.outerjoin(self._reviews))
        with self._engine.connect() as connection:
            rows = list(connection.execute(query).mappings())

        grouped: dict[str, list] = {}
        for row in rows:
            grouped.setdefault(row.advisor_id, []).append(row)
        result: dict[str, AdvisorPerformance] = {}
        for advisor_id, attempts in grouped.items():
            completed_count = sum(row.completed_at is not None for row in attempts)
            approved_rows = [row for row in attempts if row.approved_result_json]
            scores: list[float] = []
            skills: dict[CriterionType, list[int]] = {criterion: [] for criterion in CriterionType}
            recent: list[ApprovedScore] = []
            for row in approved_rows:
                evaluation = SessionEvaluationResult.model_validate_json(row.approved_result_json)
                if evaluation.overall_score is not None:
                    scores.append(evaluation.overall_score)
                    recent.append(
                        ApprovedScore(
                            session_id=row.session_id,
                            scenario_id=row.scenario_id,
                            score=evaluation.overall_score,
                            reviewed_at=row.reviewed_at,
                        )
                    )
                for item in evaluation.evaluations:
                    if item.status is CriterionStatus.ASSESSED and item.score is not None:
                        skills[item.criterion].append(item.score)
            recent.sort(key=lambda item: item.reviewed_at, reverse=True)
            result[advisor_id] = AdvisorPerformance(
                advisor_id=advisor_id,
                display_name=advisor_id,
                completed_sessions=completed_count,
                approved_sessions=len(approved_rows),
                scored_sessions=len(scores),
                average_score=sum(scores) / len(scores) if scores else None,
                rank=None,
                skill_summaries=[
                    SkillSummary(
                        criterion=criterion, average_score=sum(values) / len(values), assessed_count=len(values)
                    )
                    for criterion, values in skills.items()
                    if values
                ],
                recent_scores=recent[:5],
            )
        return result

    async def approve(self, session_id: str, manager_id: str, decision: ManagerReviewDecision) -> ManagerReviewRecord:
        if not manager_id.strip():
            raise ValueError("manager_id must not be blank")
        self._ensure_schema()
        with self._engine.begin() as connection:
            row = connection.execute(
                select(self._attempts.c.ai_draft_json, self._reviews.c.session_id)
                .select_from(self._attempts.outerjoin(self._reviews))
                .where(self._attempts.c.session_id == session_id)
            ).first()
            if row is None:
                raise AttemptNotFoundError(session_id)
            if row.ai_draft_json is None or row.session_id is not None:
                raise ReviewConflictError("attempt is unfinished or already reviewed")
            draft = SessionEvaluationResult.model_validate_json(row.ai_draft_json)
            approved = approved_evaluation(draft, decision)
            reviewed_at = datetime.now(UTC)
            try:
                connection.execute(
                    insert(self._reviews).values(
                        session_id=session_id,
                        manager_id=manager_id,
                        reviewed_at=reviewed_at,
                        change_reason=decision.change_reason.strip(),
                        approved_result_json=approved.model_dump_json(),
                    )
                )
            except IntegrityError as exc:
                raise ReviewConflictError("attempt is already reviewed") from exc
        return ManagerReviewRecord(
            session_id=session_id,
            manager_id=manager_id,
            reviewed_at=reviewed_at,
            change_reason=decision.change_reason.strip(),
            ai_draft=draft,
            approved_result=approved,
        )

    def _summary_query(self):
        return select(
            self._attempts.c.session_id,
            self._attempts.c.scenario_id,
            self._attempts.c.advisor_id,
            self._attempts.c.started_at,
            self._attempts.c.completed_at,
            self._attempts.c.evaluation_status,
            self._attempts.c.ai_draft_json,
            self._reviews.c.approved_result_json,
        ).select_from(self._attempts.outerjoin(self._reviews))

    @staticmethod
    def _to_summary(row) -> AttemptSummary:
        draft = SessionEvaluationResult.model_validate_json(row.ai_draft_json) if row.ai_draft_json else None
        approved = (
            SessionEvaluationResult.model_validate_json(row.approved_result_json) if row.approved_result_json else None
        )
        return AttemptSummary(
            session_id=row.session_id,
            scenario_id=row.scenario_id,
            advisor_id=row.advisor_id,
            started_at=row.started_at,
            completed_at=row.completed_at,
            evaluation_status=row.evaluation_status,
            review_status=(
                ReviewStatus.MANAGER_APPROVED
                if approved
                else ReviewStatus.PENDING_MANAGER_REVIEW
                if draft
                else ReviewStatus.AI_DRAFT
            ),
            ai_score=draft.overall_score if draft else None,
            approved_score=approved.overall_score if approved else None,
        )
