"""Pure aggregation for the manager dashboard and the advisor progress view.

Everything is computed in Python from stored AI drafts and manager-approved
results, which is cheap at this scale. Weeks start on Monday in Vietnam time.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.agents.roleplay.state import EvaluationStatus
from src.models.auth import AuthenticatedUser
from src.models.evaluation import CriterionStatus, CriterionType, SessionEvaluationResult
from src.services.practice_records import (
    AdvisorProgress,
    AgreementRow,
    AssignmentRecord,
    AssignmentsSummary,
    AttemptSummary,
    CriterionCell,
    CriterionProgress,
    ManagerDashboard,
    OverdueAssignment,
    QueueSummary,
    ScenarioProgress,
    ScoredAttempt,
    SkillMatrixRow,
    TrendPoint,
)

LOCAL_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
SAMPLE_PREFIX = "showcase1_"
SAMPLE_ADVISOR_IDS = {"advisor-demo"}
MIN_CELL_SAMPLES = 2


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _monday(moment: datetime) -> date:
    local = _utc(moment).astimezone(LOCAL_TZ).date()
    return local - timedelta(days=local.weekday())


def _assessed(result: SessionEvaluationResult | None) -> dict[CriterionType, int]:
    if result is None:
        return {}
    return {
        item.criterion: item.score
        for item in result.evaluations
        if item.status is CriterionStatus.ASSESSED and item.score is not None
    }


def is_sample_advisor(advisor_id: str) -> bool:
    return advisor_id.startswith(SAMPLE_PREFIX) or advisor_id in SAMPLE_ADVISOR_IDS


def week_starts(now: datetime, weeks: int) -> list[date]:
    current = _monday(now)
    return [current - timedelta(weeks=offset) for offset in range(weeks - 1, -1, -1)]


def weekly_trend(attempts: list[ScoredAttempt], now: datetime, weeks: int) -> list[TrendPoint]:
    buckets: dict[date, list[float]] = defaultdict(list)
    for attempt in attempts:
        if attempt.approved is not None and attempt.approved.overall_score is not None:
            buckets[_monday(attempt.completed_at)].append(attempt.approved.overall_score)
    return [
        TrendPoint(
            week_start=start, avg_score=_round(_mean(buckets.get(start, []))), attempts=len(buckets.get(start, []))
        )
        for start in week_starts(now, weeks)
    ]


def _criterion_scores(attempts: list[ScoredAttempt]) -> dict[CriterionType, list[int]]:
    scores: dict[CriterionType, list[int]] = {criterion: [] for criterion in CriterionType}
    for attempt in attempts:
        for criterion, score in _assessed(attempt.approved).items():
            scores[criterion].append(score)
    return scores


def _overall(attempts: list[ScoredAttempt]) -> float | None:
    return _mean([a.approved.overall_score for a in attempts if a.approved and a.approved.overall_score is not None])


def build_dashboard(
    advisors: list[AuthenticatedUser],
    attempts: list[ScoredAttempt],
    queue: list[AttemptSummary],
    assignments: list[AssignmentRecord],
    now: datetime,
    weeks: int,
) -> ManagerDashboard:
    names = {advisor.user_id: advisor.display_name for advisor in advisors}
    approved = [a for a in attempts if a.approved is not None]
    by_advisor: dict[str, list[ScoredAttempt]] = defaultdict(list)
    for attempt in approved:
        by_advisor[attempt.advisor_id].append(attempt)

    rows: list[SkillMatrixRow] = []
    for advisor in advisors:
        mine = by_advisor.get(advisor.user_id, [])
        scores = _criterion_scores(mine)
        rows.append(
            SkillMatrixRow(
                advisor_id=advisor.user_id,
                display_name=advisor.display_name,
                is_sample=is_sample_advisor(advisor.user_id),
                approved_sessions=len(mine),
                overall_avg=_round(_overall(mine)),
                criteria={
                    criterion: CriterionCell(
                        avg=_round(_mean(values)), n=len(values), insufficient=len(values) < MIN_CELL_SAMPLES
                    )
                    for criterion, values in scores.items()
                },
            )
        )
    rows.sort(key=lambda row: (row.overall_avg is None, -(row.overall_avg or 0), row.display_name.casefold()))

    active_ids = set(names)
    team_attempts = [a for a in approved if a.advisor_id in active_ids]
    agreement = []
    for criterion in CriterionType:
        reviewed = changed = 0
        deltas: list[int] = []
        for attempt in team_attempts:
            ai = _assessed(attempt.ai_draft).get(criterion)
            final = _assessed(attempt.approved).get(criterion)
            if ai is None or final is None:
                continue
            reviewed += 1
            if ai != final:
                changed += 1
                deltas.append(ai - final)
        agreement.append(
            AgreementRow(
                criterion=criterion,
                reviewed=reviewed,
                changed=changed,
                changed_rate=round(changed / reviewed, 2) if reviewed else 0.0,
                mean_delta=_round(_mean(deltas)) or 0.0,
            )
        )

    pending_dates = [_utc(item.completed_at) for item in queue if item.completed_at is not None]
    today = now.astimezone(LOCAL_TZ).date()
    overdue: list[OverdueAssignment] = []
    open_count = 0
    for assignment in assignments:
        if assignment.session_id is not None:
            continue
        if assignment.due_date is not None and assignment.due_date < today:
            overdue.append(
                OverdueAssignment(
                    assignment_id=assignment.assignment_id,
                    advisor_id=assignment.advisor_id,
                    advisor_name=names.get(assignment.advisor_id, assignment.advisor_id),
                    title=assignment.title,
                    due_date=assignment.due_date,
                )
            )
        else:
            open_count += 1
    overdue.sort(key=lambda item: item.due_date)

    return ManagerDashboard(
        has_sample_data=any(row.is_sample for row in rows),
        advisor_count=len(rows),
        approved_attempts=len(team_attempts),
        weeks=weeks,
        skill_matrix=rows,
        team_trend=weekly_trend(team_attempts, now, weeks),
        advisor_trends={row.advisor_id: weekly_trend(by_advisor.get(row.advisor_id, []), now, weeks) for row in rows},
        ai_agreement=agreement,
        queue=QueueSummary(pending=len(queue), oldest_pending_at=min(pending_dates) if pending_dates else None),
        assignments=AssignmentsSummary(open=open_count, overdue=overdue),
    )


def build_progress(attempts: list[ScoredAttempt], now: datetime) -> AdvisorProgress:
    approved = [a for a in attempts if a.approved is not None]
    trend = weekly_trend(approved, now, 8)
    filled = [point.avg_score for point in trend if point.avg_score is not None]
    four_weeks = now - timedelta(days=28)
    eight_weeks = now - timedelta(days=56)
    recent = [a for a in approved if _utc(a.completed_at) >= four_weeks]
    previous = [a for a in approved if eight_weeks <= _utc(a.completed_at) < four_weeks]
    all_scores = _criterion_scores(approved)
    recent_scores = _criterion_scores(recent)
    previous_scores = _criterion_scores(previous)
    criteria = {}
    for criterion in CriterionType:
        latest = _mean(recent_scores[criterion]) if recent_scores[criterion] else _mean(all_scores[criterion])
        before = _mean(previous_scores[criterion])
        now_avg = _mean(recent_scores[criterion])
        criteria[criterion] = CriterionProgress(
            latest_avg=_round(latest),
            change_4w=_round(now_avg - before) if now_avg is not None and before is not None else None,
            n=len(all_scores[criterion]),
        )

    scenarios: dict[str, ScenarioProgress] = {}
    for attempt in sorted(attempts, key=lambda a: _utc(a.completed_at)):
        if attempt.approved is not None:
            status, score = "approved", attempt.approved.overall_score
        elif attempt.ai_draft is not None:
            status, score = "pending_review", attempt.ai_draft.overall_score
        elif attempt.evaluation_status is EvaluationStatus.FAILED:
            status, score = "failed", None
        else:
            status, score = "not_started", None
        scenarios[attempt.scenario_id] = ScenarioProgress(
            last_session_id=attempt.session_id,
            last_completed_at=_utc(attempt.completed_at),
            last_status=status,
            last_score=_round(score),
        )

    return AdvisorProgress(
        approved_sessions=len(approved),
        overall_avg=_round(_overall(approved)),
        current_week_avg=trend[-1].avg_score,
        change_8w=_round(filled[-1] - filled[0]) if len(filled) >= 2 else None,
        trend=trend,
        criteria=criteria,
        scenarios=scenarios,
    )
