"""History/review persistence tests use a real SQLite database, not a mock."""

import pytest
from pydantic import ValidationError

from src.integrations.practice_records import SQLPracticeRecordsRepository
from src.models.evaluation import CriterionStatus, CriterionType, ReviewStatus, SessionEvaluationResult
from src.services.practice_records import (
    AssignmentConflictError,
    AttemptNotFoundError,
    CreateAssignmentInput,
    ManagerReviewDecision,
    ReviewConflictError,
    ReviewValidationError,
)


def draft(session_id: str, scenario_id: str = "scenario-1") -> SessionEvaluationResult:
    evaluations = [
        {
            "criterion": criterion,
            "status": "assessed" if criterion is CriterionType.NEED_DISCOVERY else "unassessed",
            "score": 3 if criterion is CriterionType.NEED_DISCOVERY else None,
            "evidence": (
                [{"message_id": "advisor-1", "quote": "What do you need?"}]
                if criterion is CriterionType.NEED_DISCOVERY
                else []
            ),
            "reason": "Recorded conversation evidence.",
        }
        for criterion in CriterionType
    ]
    return SessionEvaluationResult(
        session_id=session_id,
        scenario_id=scenario_id,
        rubric_version="test-v1",
        assessed_criteria_count=1,
        overall_score=3,
        evaluations=evaluations,
    )


@pytest.mark.asyncio
async def test_history_is_scoped_to_advisor_and_retains_every_attempt(tmp_path):
    url = f"sqlite:///{tmp_path / 'records.db'}"
    records = SQLPracticeRecordsRepository(url)
    await records.register("attempt-1", "scenario-1", "advisor-a")
    await records.register("attempt-2", "scenario-1", "advisor-a")
    await records.register("attempt-3", "scenario-2", "advisor-b")
    await records.complete("attempt-1", draft("attempt-1"))
    await records.complete("attempt-2", draft("attempt-2"))

    reopened = SQLPracticeRecordsRepository(url)
    history = await reopened.history("advisor-a", "scenario-1")

    assert [item.session_id for item in history] == ["attempt-2", "attempt-1"]
    assert all(item.advisor_id == "advisor-a" for item in history)
    assert await reopened.history("advisor-b", "scenario-1") == []
    assert all(item.ai_score == 3 for item in history)
    assert await reopened.history("advisor-b") == []  # An unfinished attempt is not history yet.
    assert (await reopened.owned_attempt("attempt-1", "advisor-a")).session_id == "attempt-1"
    with pytest.raises(AttemptNotFoundError):
        await reopened.owned_attempt("attempt-1", "advisor-b")


@pytest.mark.asyncio
async def test_saved_pending_attempt_survives_repository_restart_and_can_be_retried(tmp_path):
    url = f"sqlite:///{tmp_path / 'records.db'}"
    records = SQLPracticeRecordsRepository(url)
    await records.register("attempt-1", "scenario-1", "advisor-a")
    await records.mark_evaluation_pending("attempt-1")

    reopened = SQLPracticeRecordsRepository(url)
    history = await reopened.history("advisor-a")
    assert len(history) == 1
    assert history[0].completed_at is not None
    assert history[0].evaluation_status.value == "pending"

    await reopened.mark_evaluation_failed("attempt-1")
    assert (await reopened.history("advisor-a"))[0].evaluation_status.value == "failed"
    await reopened.mark_evaluation_pending("attempt-1")
    await reopened.complete("attempt-1", draft("attempt-1"))
    assert (await reopened.history("advisor-a"))[0].evaluation_status.value == "complete"


@pytest.mark.asyncio
async def test_manager_queue_shows_latest_unreviewed_per_advisor_scenario(tmp_path):
    records = SQLPracticeRecordsRepository(f"sqlite:///{tmp_path / 'records.db'}")
    for session_id in ("attempt-1", "attempt-2"):
        await records.register(session_id, "scenario-1", "advisor-a")
        await records.complete(session_id, draft(session_id))
    await records.register("unfinished", "scenario-1", "advisor-b")

    assert [item.session_id for item in await records.review_queue()] == ["attempt-2"]

    await records.approve("attempt-2", "manager-1", ManagerReviewDecision(change_reason="Checked transcript."))
    assert [item.session_id for item in await records.review_queue()] == ["attempt-1"]


@pytest.mark.asyncio
async def test_manager_history_and_overview_include_older_attempts_without_mixing_draft_scores(tmp_path):
    records = SQLPracticeRecordsRepository(f"sqlite:///{tmp_path / 'records.db'}")
    for session_id in ("attempt-1", "attempt-2"):
        await records.register(session_id, "scenario-1", "advisor-a")
        await records.complete(session_id, draft(session_id))
    await records.register("failed", "scenario-2", "advisor-b")
    await records.mark_evaluation_failed("failed")
    await records.approve(
        "attempt-1",
        "manager-1",
        ManagerReviewDecision(score_overrides={CriterionType.NEED_DISCOVERY: 2}, change_reason="Checked evidence."),
    )

    assert [item.session_id for item in await records.review_queue()] == ["attempt-2"]
    history = await records.manager_history(advisor_id="advisor-a", scenario_id="scenario-1")
    assert [item.session_id for item in history] == ["attempt-2", "attempt-1"]
    assert [item.session_id for item in await records.manager_history(limit=1, offset=1)] == ["attempt-2"]
    overview = await records.team_overview()
    assert (overview.completed_attempts, overview.approved_attempts, overview.pending_attempts) == (3, 1, 1)
    assert (overview.failed_evaluations, overview.active_advisors) == (1, 2)
    assert len(overview.skill_summaries) == 1
    assert overview.skill_summaries[0].criterion is CriterionType.NEED_DISCOVERY
    assert overview.skill_summaries[0].average_score == 2
    assert overview.skill_summaries[0].assessed_count == 1


@pytest.mark.asyncio
async def test_manager_review_preserves_ai_draft_and_audits_score_change(tmp_path):
    records = SQLPracticeRecordsRepository(f"sqlite:///{tmp_path / 'records.db'}")
    await records.register("attempt-1", "scenario-1", "advisor-a")
    await records.complete("attempt-1", draft("attempt-1"))

    review = await records.approve(
        "attempt-1",
        "manager-1",
        ManagerReviewDecision(
            score_overrides={CriterionType.NEED_DISCOVERY: 2},
            change_reason="The follow-up question met the higher anchor.",
        ),
    )

    assert review.ai_draft.overall_score == 3
    assert review.ai_draft.review_status is ReviewStatus.AI_DRAFT
    assert review.approved_result.overall_score == 2
    assert review.approved_result.review_status is ReviewStatus.MANAGER_APPROVED
    assert review.manager_id == "manager-1"
    history = await records.history("advisor-a")
    assert history[0].approved_score == 2
    assert history[0].review_status is ReviewStatus.MANAGER_APPROVED
    reopened = SQLPracticeRecordsRepository(f"sqlite:///{tmp_path / 'records.db'}")
    saved_review = await reopened.review_details("attempt-1")
    assert saved_review is not None
    assert saved_review.change_reason == "The follow-up question met the higher anchor."
    assert saved_review.ai_draft.overall_score == 3
    assert (await reopened.manager_attempt("attempt-1")).advisor_id == "advisor-a"
    with pytest.raises(ReviewConflictError, match="already reviewed"):
        await records.approve("attempt-1", "manager-2", ManagerReviewDecision(change_reason="Repeat."))


@pytest.mark.asyncio
async def test_review_rejects_unfinished_missing_or_unassessed_attempt(tmp_path):
    records = SQLPracticeRecordsRepository(f"sqlite:///{tmp_path / 'records.db'}")
    await records.register("unfinished", "scenario-1", "advisor-a")
    decision = ManagerReviewDecision(change_reason="Reviewed.")
    with pytest.raises(ReviewConflictError, match="unfinished"):
        await records.approve("unfinished", "manager-1", decision)
    with pytest.raises(AttemptNotFoundError):
        await records.approve("missing", "manager-1", decision)
    await records.register("attempt-1", "scenario-1", "advisor-a")
    await records.complete("attempt-1", draft("attempt-1"))
    with pytest.raises(ReviewConflictError, match="assessed"):
        await records.approve(
            "attempt-1",
            "manager-1",
            ManagerReviewDecision(score_overrides={CriterionType.POLICY_ACCURACY: 3}, change_reason="Invalid edit."),
        )


def test_review_decision_rejects_invalid_scores_and_blank_reason():
    with pytest.raises(ValidationError):
        ManagerReviewDecision(score_overrides={CriterionType.NEED_DISCOVERY: 4}, change_reason="Reviewed.")
    with pytest.raises(ValidationError):
        ManagerReviewDecision(change_reason="   ")


@pytest.mark.asyncio
async def test_assignment_link_and_status_survive_repository_reopen(tmp_path):
    url = f"sqlite:///{tmp_path / 'assignments.db'}"
    records = SQLPracticeRecordsRepository(url)
    assignment = await records.create_assignment(
        "manager-a", CreateAssignmentInput(advisor_id="advisor-a", scenario_id="scenario-1", title="Practice scenario")
    )
    with pytest.raises(AssignmentConflictError):
        await records.register("wrong", "scenario-1", "advisor-b", assignment.assignment_id)
    assert await records.assignments("advisor-b") == []
    assert (await records.assignments("advisor-a"))[0].status == "assigned"
    await records.register("attempt-1", "scenario-1", "advisor-a", assignment.assignment_id)
    assert (await records.assignments("advisor-a"))[0].status == "in_progress"
    await records.complete("attempt-1", draft("attempt-1"))
    reopened = SQLPracticeRecordsRepository(url)
    saved = (await reopened.assignments("advisor-a"))[0]
    assert (saved.status, saved.session_id) == ("completed", "attempt-1")
    with pytest.raises(AssignmentConflictError, match="already completed"):
        await reopened.register("attempt-2", "scenario-1", "advisor-a", assignment.assignment_id)
    assert (await reopened.advisor_performance())["advisor-a"].average_score is None
    await reopened.approve("attempt-1", "manager-a", ManagerReviewDecision(change_reason="Evidence checked."))
    performance = (await reopened.advisor_performance())["advisor-a"]
    assert (performance.completed_sessions, performance.approved_sessions, performance.scored_sessions) == (1, 1, 1)
    assert performance.average_score == 3


@pytest.mark.asyncio
async def test_old_reviews_without_manager_reason_or_general_comment_stay_readable(tmp_path):
    records = SQLPracticeRecordsRepository(f"sqlite:///{tmp_path / 'old.db'}")
    await records.register("attempt-1", "scenario-1", "advisor-a")
    await records.complete("attempt-1", draft("attempt-1"))
    legacy_json = draft("attempt-1").model_dump_json(exclude={"evaluations": {"__all__": {"manager_reason"}}})
    assert "manager_reason" not in legacy_json
    assert SessionEvaluationResult.model_validate_json(legacy_json).evaluations[0].manager_reason is None
    await records.approve("attempt-1", "manager-1", ManagerReviewDecision(change_reason="Reviewed."))
    saved = await records.review_details("attempt-1")
    assert saved is not None
    assert saved.change_reason == "Reviewed."
    assert saved.general_comment == "Reviewed."


@pytest.mark.asyncio
async def test_per_criterion_reason_is_required_and_stored_only_on_changed_scores(tmp_path):
    records = SQLPracticeRecordsRepository(f"sqlite:///{tmp_path / 'reasons.db'}")
    await records.register("attempt-1", "scenario-1", "advisor-a")
    await records.complete("attempt-1", draft("attempt-1"))
    with pytest.raises(ReviewValidationError, match="need_discovery"):
        await records.approve(
            "attempt-1",
            "manager-1",
            ManagerReviewDecision.model_validate({"score_overrides": {"need_discovery": {"score": 2}}}),
        )
    review = await records.approve(
        "attempt-1",
        "manager-1",
        ManagerReviewDecision.model_validate(
            {
                "score_overrides": {"need_discovery": {"score": 2, "reason": "Follow-up missing."}},
                "general_comment": "Watch the opening.",
            }
        ),
    )
    item = next(e for e in review.approved_result.evaluations if e.criterion is CriterionType.NEED_DISCOVERY)
    assert item.status is CriterionStatus.ASSESSED
    assert (item.score, item.manager_reason) == (2, "Follow-up missing.")
    assert review.general_comment == "Watch the opening."
    assert review.ai_draft.evaluations[0].manager_reason is None


@pytest.mark.asyncio
async def test_todos_persist_per_manager_and_order_open_items_first(tmp_path):
    url = f"sqlite:///{tmp_path / 'todos.db'}"
    records = SQLPracticeRecordsRepository(url)
    first = await records.create_todo("manager-a", "First")
    await records.create_todo("manager-a", "Second")
    await records.create_todo("manager-b", "Other")
    await records.set_todo_done("manager-a", first.todo_id, True)
    reopened = SQLPracticeRecordsRepository(url)
    assert [(t.text, t.done) for t in await reopened.list_todos("manager-a")] == [("Second", False), ("First", True)]
    assert [t.text for t in await reopened.list_todos("manager-b")] == ["Other"]
