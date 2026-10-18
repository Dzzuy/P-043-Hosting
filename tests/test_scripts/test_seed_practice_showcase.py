"""The showcase seed must build valid, idempotent sample data for the dashboard."""

import json
from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, insert, select

from scripts import seed_practice_showcase as seed_script
from src.agents.roleplay.state import RoleplayState
from src.integrations.auth_repository import SQLAuthRepository
from src.integrations.practice_records import SQLPracticeRecordsRepository
from src.models.evaluation import SessionEvaluationResult
from src.services.auth import AuthService
from src.services.recorded_practice import RecordedPracticeService

NOW = datetime(2026, 10, 18, 3, 0, tzinfo=UTC)


def row_counts(url: str) -> dict[str, int]:
    records = SQLPracticeRecordsRepository(url)
    records._ensure_schema()
    tables = [records._attempts, records._reviews, records._assignments, records._assignment_sessions, records._todos]
    engine = create_engine(url)
    with engine.connect() as connection:
        counts = {t.name: connection.execute(select(func.count()).select_from(t)).scalar_one() for t in tables}
        users = SQLAuthRepository(url, engine=engine)._users
        counts["users"] = connection.execute(select(func.count()).select_from(users)).scalar_one()
    engine.dispose()
    return counts


@pytest.fixture
def demo_passwords(monkeypatch):
    monkeypatch.setenv("DEMO_ADVISOR_PASSWORD", "DemoPassword123!")
    monkeypatch.setenv("DEMO_MANAGER_PASSWORD", "DemoPassword123!")


@pytest.mark.asyncio
async def test_dry_run_writes_nothing_and_missing_demo_passwords_exit(tmp_path, monkeypatch, demo_passwords):
    url = f"sqlite:///{tmp_path / 'seed.db'}"
    result = await seed_script.seed(url, apply=False, now=NOW)
    assert result["applied"] is False
    assert result["rows_planned"]["attempts"] == 80
    monkeypatch.delenv("DEMO_ADVISOR_PASSWORD")
    with pytest.raises(SystemExit, match="DEMO_ADVISOR_PASSWORD"):
        await seed_script.seed(f"sqlite:///{tmp_path / 'other.db'}", apply=False, now=NOW)


@pytest.mark.asyncio
async def test_apply_feeds_dashboard_and_second_run_is_idempotent(tmp_path, demo_passwords):
    url = f"sqlite:///{tmp_path / 'seed.db'}"
    first = await seed_script.seed(url, apply=True, now=NOW)
    counts = row_counts(url)
    assert counts["practice_attempts"] == 80
    assert counts["practice_manager_reviews"] == 73
    assert counts["manager_todos"] == 4
    assert counts["users"] == 9
    assert first["sample_advisors_created"] == 7

    second = await seed_script.seed(url, apply=True, now=NOW)
    assert row_counts(url) == counts
    assert second["sample_advisors_created"] == 0
    assert all(value == 0 for value in second["rows_inserted"].values())

    records = SQLPracticeRecordsRepository(url)
    service = RecordedPracticeService(None, records, AuthService(SQLAuthRepository(url)))
    dashboard = await service.manager_dashboard(now=NOW)
    assert len(dashboard.skill_matrix) == 8
    assert dashboard.has_sample_data is True
    assert next(r for r in dashboard.skill_matrix if r.advisor_id == "advisor-demo").display_name == "Phạm Đình Duy"
    assert all(any(point.attempts for point in trend) for trend in dashboard.advisor_trends.values())
    assert all(6 <= point.attempts <= 13 for point in dashboard.team_trend[:-1])  # newest week is mostly pending
    demo_trend = dashboard.advisor_trends["advisor-demo"]
    assert all(1.6 <= point.avg_score <= 1.8 for point in demo_trend[:3])
    assert all(2.6 <= point.avg_score <= 2.8 for point in demo_trend[-2:])
    assert len(dashboard.assignments.overdue) == 2
    assert dashboard.assignments.open == 5
    assert dashboard.queue.pending > 0
    assert any(row.changed for row in dashboard.ai_agreement if row.criterion.value == "policy_accuracy")
    progress = await service.advisor_progress("advisor-demo", now=NOW)
    assert progress.approved_sessions >= 10
    assert progress.change_8w is not None and progress.change_8w > 0


@pytest.mark.asyncio
async def test_seeded_transcripts_validate_and_evidence_quotes_are_real(tmp_path, demo_passwords):
    url = f"sqlite:///{tmp_path / 'seed.db'}"
    await seed_script.seed(url, apply=True, now=NOW)
    engine = create_engine(url)
    records = SQLPracticeRecordsRepository(url, engine=engine)
    from src.integrations.practice_persistence import SQLCheckpointRepository

    checkpoints = SQLCheckpointRepository(url, engine=engine)
    with engine.connect() as connection:
        states = [json.loads(v) for v in connection.execute(select(checkpoints._table.c.state_json)).scalars()]
        drafts = list(connection.execute(select(records._attempts.c.ai_draft_json)).scalars())
        approved = list(connection.execute(select(records._reviews.c.approved_result_json)).scalars())
    assert len(states) == len(drafts) == 80
    for raw in states:
        state = RoleplayState.model_validate(raw)
        assert 8 <= len(state.messages) <= 12
        assert state.evaluation_result is not None
        by_id = {message.message_id: message for message in state.messages}
        for criterion in state.evaluation_result.evaluations:
            assert criterion.evidence
            for evidence in [*criterion.evidence, *(e for check in criterion.checks for e in check.evidence)]:
                assert by_id[evidence.message_id].role == "advisor"
                assert evidence.quote in by_id[evidence.message_id].content
    for raw in [*drafts, *approved]:
        result = SessionEvaluationResult.model_validate_json(raw)
        state = next(state for state in states if state["session_id"] == result.session_id)
        by_id = {m["message_id"]: m for m in state["messages"]}
        for criterion in result.evaluations:
            for evidence in [*criterion.evidence, *(e for check in criterion.checks for e in check.evidence)]:
                assert by_id[evidence.message_id]["role"] == "advisor"
                assert evidence.quote in by_id[evidence.message_id]["content"]
    reasons = [
        item.manager_reason
        for raw in approved
        for item in SessionEvaluationResult.model_validate_json(raw).evaluations
        if item.manager_reason
    ]
    assert reasons
    engine.dispose()


@pytest.mark.parametrize("now", [NOW, datetime(2026, 10, 19, 0, 0, tzinfo=seed_script.TZ)])
def test_calendar_distribution_pending_ages_and_open_demo_assignments(now):
    ids = {slug: seed_script.DEMO_ADVISOR_ID if slug == "demo" else slug for slug, *_ in seed_script.ADVISORS}
    rows = seed_script.build_dataset(now, ids)
    reviewed = {row["session_id"] for row in rows["reviews"]}
    pending = [row for row in rows["attempts"] if row["session_id"] not in reviewed]
    ages = [now - row["completed_at"] for row in pending]
    assert all(timedelta(0) <= age < timedelta(days=5) for age in ages)
    if now == NOW:
        assert timedelta(days=4) <= max(ages) < timedelta(days=4.1)
    weeks = Counter()
    for row in rows["attempts"]:
        day = row["completed_at"].astimezone(seed_script.TZ).date()
        weeks[day - timedelta(days=day.weekday())] += 1
    assert len(weeks) == 8
    assert all(6 <= count <= 13 for count in weeks.values())
    links = {row["assignment_id"] for row in rows["assignment_sessions"]}
    open_demo = [
        row for row in rows["assignments"] if row["advisor_id"] == "advisor-demo" and row["assignment_id"] not in links
    ]
    assert sorted((row["due_date"] - now.astimezone(seed_script.TZ).date()).days for row in open_demo) == [2, 7]
    assert all(row["manager_id"] == "manager-demo" for row in open_demo)


@pytest.mark.asyncio
async def test_reset_refreshes_all_seed_tables_preserves_users_and_non_seed_rows(tmp_path, demo_passwords):
    url = f"sqlite:///{tmp_path / 'seed.db'}"
    await seed_script.seed(url, apply=True, now=NOW)
    engine = create_engine(url)
    records = SQLPracticeRecordsRepository(url, engine=engine)
    from src.integrations.practice_persistence import SQLCheckpointRepository

    checkpoints = SQLCheckpointRepository(url, engine=engine)
    tables = {
        records._attempts: "session_id",
        checkpoints._table: "session_id",
        records._reviews: "session_id",
        records._assignments: "assignment_id",
        records._assignment_sessions: "session_id",
        records._todos: "todo_id",
    }
    # Obsolete seed rows must be removed even when not in the new dataset.
    # A lookalike prefix catches accidental SQL LIKE underscore wildcards.
    lookalike = seed_script.PREFIX.replace("_", "X")
    with engine.begin() as connection:
        for table, key in tables.items():
            original = dict(connection.execute(select(table)).mappings().first())
            for prefix in (seed_script.PREFIX, lookalike):
                extra = dict(original, **{key: prefix + "obsolete"})
                if "assignment_id" in extra:
                    extra["assignment_id"] = prefix + "obsolete"
                connection.execute(insert(table), extra)
        before = {table.name: list(connection.execute(select(table)).mappings()) for table in tables}
        users = list(connection.execute(select(SQLAuthRepository(url, engine=engine)._users)).mappings())
    later = NOW + timedelta(days=14)
    preview = await seed_script.seed(url, reset=True, now=later)
    assert all(count > 0 for count in preview["rows_would_delete"].values())
    with engine.connect() as connection:
        assert before == {table.name: list(connection.execute(select(table)).mappings()) for table in tables}
    result = await seed_script.seed(url, apply=True, reset=True, now=later)
    assert result["rows_inserted"]["attempts"] == 80
    with engine.connect() as connection:
        assert users == list(connection.execute(select(SQLAuthRepository(url, engine=engine)._users)).mappings())
        for table, key in tables.items():
            after = list(connection.execute(select(table)).mappings())
            assert all(row[key] != seed_script.PREFIX + "obsolete" for row in after)
            assert [row for row in before[table.name] if row[key].startswith(lookalike)] == [
                row for row in after if row[key].startswith(lookalike)
            ]
        completed = connection.execute(
            select(records._attempts.c.completed_at).where(
                records._attempts.c.session_id == seed_script.PREFIX + "s_demo_18"
            )
        ).scalar_one()
        assert completed.replace(tzinfo=UTC) > NOW
    again = await seed_script.seed(url, apply=True, now=later)
    assert all(count == 0 for count in again["rows_inserted"].values())
    engine.dispose()
