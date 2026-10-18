"""Protected router contract with a test-only identity dependency."""

from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI, Header, HTTPException
from sqlalchemy import update

from src.agents.roleplay.customer_agent import CustomerResponseError
from src.agents.roleplay.graph import RoleplaySessionConflictError
from src.agents.roleplay.scenario_loader import ScenarioRepository
from src.api.auth import CurrentUserDependency, create_auth_router
from src.api.practice_errors import PracticeAPIError, practice_exception_handler
from src.api.recorded_practice import create_recorded_practice_routers
from src.config import Settings
from src.integrations.auth_repository import SQLAuthRepository
from src.integrations.practice_records import SQLPracticeRecordsRepository
from src.models.auth import AuthenticatedUser, UserRole
from src.models.evaluation import CriterionType, SessionEvaluationResult
from src.services.auth import AuthService
from src.services.practice import PracticeEvaluationUnavailableError, PracticeResultView, PracticeSessionView
from src.services.practice_records import CreateAssignmentInput
from src.services.recorded_practice import RecordedPracticeService


class AdvisorDirectoryStub:
    def __init__(self):
        self.users = [
            AuthenticatedUser(
                user_id="advisor-a", username="advisor.a", display_name="Advisor A", role=UserRole.ADVISOR
            ),
            AuthenticatedUser(
                user_id="advisor-b", username="advisor.b", display_name="Advisor B", role=UserRole.ADVISOR
            ),
        ]

    async def active_advisors(self):
        return self.users

    async def active_advisor(self, user_id):
        return next((user for user in self.users if user.user_id == user_id), None)


class StubPractice:
    def __init__(self):
        self.sessions = {}
        self.counter = 0

    def list_scenarios(self):
        return ScenarioRepository().list_public()

    async def start_session(self, scenario_id, max_turns=None):
        self.counter += 1
        session_id = f"session-{self.counter}"
        session = PracticeSessionView(
            session_id=session_id,
            scenario_id=scenario_id,
            difficulty="Medium",
            conversation_stage="opening",
            turn_count=0,
            max_turns=max_turns or 10,
            visible_context="Customer asks about a car.",
            termination_status="active",
            messages=[],
        )
        self.sessions[session_id] = session
        return session

    async def get_session(self, session_id):
        return self.sessions[session_id]

    async def retry_customer_reply(self, session_id):
        session = self.sessions[session_id]
        if not session.pending_customer_reply:
            raise RoleplaySessionConflictError("no customer reply is pending")
        updated = session.model_copy(update={"pending_customer_reply": False})
        self.sessions[session_id] = updated
        return updated

    async def get_result(self, session_id):
        return PracticeResultView(session_id=session_id, evaluation_status="not_started")

    async def finish_session(self, session_id, *, started_at=None, on_saved=None):
        self.finish_started_at = started_at
        if on_saved is not None:
            await on_saved()
        raise PracticeEvaluationUnavailableError("Evaluator is unavailable")


async def fake_identity(x_test_identity: str | None = Header(None)) -> AuthenticatedUser:
    if not x_test_identity:
        raise HTTPException(status_code=401, detail="Authentication required.")
    user_id, role = x_test_identity.split(":", 1)
    return AuthenticatedUser(
        user_id=user_id,
        username=f"{user_id}.test",
        display_name=user_id,
        role=role,
    )


@pytest.mark.asyncio
async def test_retry_reply_route_requires_owner_and_pending_turn(tmp_path):
    records = SQLPracticeRecordsRepository(f"sqlite:///{tmp_path / 'records.db'}")
    practice = StubPractice()
    service = RecordedPracticeService(practice, records)
    practice_router, _ = create_recorded_practice_routers(service, fake_identity)
    app = FastAPI()
    app.add_exception_handler(PracticeAPIError, practice_exception_handler)
    app.include_router(practice_router, prefix="/api/v1")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/practice/sessions",
            headers={"X-Test-Identity": "advisor-a:advisor"},
            json={"scenario_id": "SCENARIO_01_VF5_TAXI"},
        )
        session_id = created.json()["session_id"]
        path = f"/api/v1/practice/{session_id}/retry-reply"
        practice.sessions[session_id] = practice.sessions[session_id].model_copy(
            update={"pending_customer_reply": True}
        )
        assert (await client.post(path)).status_code == 401
        assert (await client.post(path, headers={"X-Test-Identity": "manager-a:manager"})).status_code == 403
        assert (await client.post(path, headers={"X-Test-Identity": "advisor-b:advisor"})).status_code == 404
        retried = await client.post(path, headers={"X-Test-Identity": "advisor-a:advisor"})
        assert retried.status_code == 200
        assert retried.json()["pending_customer_reply"] is False
        assert (await client.post(path, headers={"X-Test-Identity": "advisor-a:advisor"})).status_code == 409


@pytest.mark.asyncio
async def test_history_and_review_routes_enforce_identity_and_ownership(tmp_path):
    records = SQLPracticeRecordsRepository(f"sqlite:///{tmp_path / 'records.db'}")
    service = RecordedPracticeService(StubPractice(), records)
    practice_router, manager_router = create_recorded_practice_routers(service, fake_identity)
    app = FastAPI()
    app.add_exception_handler(PracticeAPIError, practice_exception_handler)
    app.include_router(practice_router, prefix="/api/v1")
    app.include_router(manager_router, prefix="/api/v1")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/v1/practice/history")).status_code == 401
        created = await client.post(
            "/api/v1/practice/sessions",
            headers={"X-Test-Identity": "advisor-a:advisor"},
            json={"scenario_id": "SCENARIO_01_VF5_TAXI", "max_turns": 15},
        )
        assert created.status_code == 201
        assert created.json()["max_turns"] == 15
        session_id = created.json()["session_id"]
        # Ownership exists at start, but history only lists finished/evaluated attempts.
        await records.complete(session_id, draft_for(session_id))
        own = await client.get("/api/v1/practice/history", headers={"X-Test-Identity": "advisor-a:advisor"})
        other = await client.get("/api/v1/practice/history", headers={"X-Test-Identity": "advisor-b:advisor"})
        assert [item["session_id"] for item in own.json()] == [session_id]
        assert other.json() == []
        assert (
            await client.get(f"/api/v1/practice/{session_id}/attempt", headers={"X-Test-Identity": "advisor-b:advisor"})
        ).status_code == 404
        assert (
            await client.get("/api/v1/manager/reviews", headers={"X-Test-Identity": "advisor-a:advisor"})
        ).status_code == 403
        assert (
            await client.get("/api/v1/practice/history", headers={"X-Test-Identity": "manager-a:manager"})
        ).status_code == 403
        manager_queue = await client.get("/api/v1/manager/reviews", headers={"X-Test-Identity": "manager-a:manager"})
        assert [item["session_id"] for item in manager_queue.json()] == [session_id]
        assert (
            await client.get("/api/v1/manager/attempts", headers={"X-Test-Identity": "advisor-a:advisor"})
        ).status_code == 403
        assert (
            await client.get("/api/v1/manager/overview", headers={"X-Test-Identity": "advisor-a:advisor"})
        ).status_code == 403
        manager_history = await client.get("/api/v1/manager/attempts", headers={"X-Test-Identity": "manager-a:manager"})
        assert [item["session_id"] for item in manager_history.json()] == [session_id]
        overview = await client.get("/api/v1/manager/overview", headers={"X-Test-Identity": "manager-a:manager"})
        assert overview.json()["completed_attempts"] == 1
        assert overview.json()["pending_attempts"] == 1


@pytest.mark.asyncio
async def test_manager_can_review_finished_attempt_once_and_advisor_sees_result(tmp_path):
    records = SQLPracticeRecordsRepository(f"sqlite:///{tmp_path / 'records.db'}")
    service = RecordedPracticeService(StubPractice(), records)
    practice_router, manager_router = create_recorded_practice_routers(service, fake_identity)
    app = FastAPI()
    app.add_exception_handler(PracticeAPIError, practice_exception_handler)
    app.include_router(practice_router, prefix="/api/v1")
    app.include_router(manager_router, prefix="/api/v1")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/practice/sessions",
            headers={"X-Test-Identity": "advisor-a:advisor"},
            json={"scenario_id": "SCENARIO_01_VF5_TAXI"},
        )
        session_id = created.json()["session_id"]
        await records.complete(session_id, draft_for(session_id))
        assert [
            item["session_id"]
            for item in (
                await client.get("/api/v1/manager/reviews", headers={"X-Test-Identity": "manager-a:manager"})
            ).json()
        ] == [session_id]
        approved = await client.patch(
            f"/api/v1/manager/reviews/{session_id}",
            headers={"X-Test-Identity": "manager-a:manager"},
            json={"score_overrides": {"need_discovery": 2}, "change_reason": "Follow-up was strong."},
        )
        assert approved.status_code == 200
        assert approved.json()["ai_draft"]["overall_score"] == 3
        assert approved.json()["approved_result"]["overall_score"] == 2
        assert (
            await client.patch(
                f"/api/v1/manager/reviews/{session_id}",
                headers={"X-Test-Identity": "manager-a:manager"},
                json={"change_reason": "Duplicate."},
            )
        ).status_code == 409
        history = await client.get("/api/v1/practice/history", headers={"X-Test-Identity": "advisor-a:advisor"})
        assert history.json()[0]["review_status"] == "manager_approved"


@pytest.mark.asyncio
async def test_failed_evaluation_attempt_remains_in_history_but_not_review_queue(tmp_path):
    records = SQLPracticeRecordsRepository(f"sqlite:///{tmp_path / 'records.db'}")
    service = RecordedPracticeService(StubPractice(), records)
    practice_router, manager_router = create_recorded_practice_routers(service, fake_identity)
    app = FastAPI()
    app.add_exception_handler(PracticeAPIError, practice_exception_handler)
    app.include_router(practice_router, prefix="/api/v1")
    app.include_router(manager_router, prefix="/api/v1")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/practice/sessions",
            headers={"X-Test-Identity": "advisor-a:advisor"},
            json={"scenario_id": "SCENARIO_01_VF5_TAXI"},
        )
        session_id = created.json()["session_id"]
        failed = await client.post(
            f"/api/v1/practice/{session_id}/finish", headers={"X-Test-Identity": "advisor-a:advisor"}
        )
        assert failed.status_code == 503
        history = await client.get("/api/v1/practice/history", headers={"X-Test-Identity": "advisor-a:advisor"})
        assert history.json()[0]["evaluation_status"] == "failed"
        queue = await client.get("/api/v1/manager/reviews", headers={"X-Test-Identity": "manager-a:manager"})
        assert queue.json() == []


def draft_for(session_id: str) -> SessionEvaluationResult:
    evaluations = [
        {
            "criterion": criterion,
            "status": "assessed" if criterion is CriterionType.NEED_DISCOVERY else "unassessed",
            "score": 3 if criterion is CriterionType.NEED_DISCOVERY else None,
            "evidence": (
                [{"message_id": "a-1", "quote": "What matters most?"}]
                if criterion is CriterionType.NEED_DISCOVERY
                else []
            ),
            "reason": "Transcript checked.",
        }
        for criterion in CriterionType
    ]
    return SessionEvaluationResult(
        session_id=session_id,
        scenario_id="SCENARIO_01_VF5_TAXI",
        rubric_version="test-v1",
        assessed_criteria_count=1,
        overall_score=3,
        evaluations=evaluations,
    )


@pytest.mark.asyncio
async def test_assignment_flow_and_approved_performance_use_real_attempts(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'assignments.db'}"
    records = SQLPracticeRecordsRepository(database_url)
    service = RecordedPracticeService(StubPractice(), records, AdvisorDirectoryStub())
    practice_router, manager_router = create_recorded_practice_routers(service, fake_identity)
    app = FastAPI()
    app.add_exception_handler(PracticeAPIError, practice_exception_handler)
    app.include_router(practice_router, prefix="/api/v1")
    app.include_router(manager_router, prefix="/api/v1")
    manager = {"X-Test-Identity": "manager-a:manager"}
    advisor = {"X-Test-Identity": "advisor-a:advisor"}
    other = {"X-Test-Identity": "advisor-b:advisor"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/v1/practice/scenarios", headers=manager)).status_code == 200
        assert (
            await client.post(
                "/api/v1/manager/assignments",
                headers=advisor,
                json={"advisor_id": "advisor-a", "scenario_id": "SCENARIO_01_VF5_TAXI", "title": "Practice VF 5"},
            )
        ).status_code == 403
        assert (
            await client.post(
                "/api/v1/manager/assignments",
                headers=manager,
                json={"advisor_id": "missing", "scenario_id": "SCENARIO_01_VF5_TAXI", "title": "Practice VF 5"},
            )
        ).status_code == 409
        created = await client.post(
            "/api/v1/manager/assignments",
            headers=manager,
            json={"advisor_id": "advisor-a", "scenario_id": "SCENARIO_01_VF5_TAXI", "title": "Practice VF 5"},
        )
        assert created.status_code == 201, created.text
        assignment_id = created.json()["assignment_id"]
        assert created.json()["status"] == "assigned"
        assert (await client.get("/api/v1/practice/assignments", headers=other)).json() == []
        assert (await client.get("/api/v1/practice/assignments", headers=manager)).status_code == 403
        assert (
            await client.post(
                "/api/v1/practice/sessions",
                headers=other,
                json={"scenario_id": "SCENARIO_01_VF5_TAXI", "assignment_id": assignment_id},
            )
        ).status_code == 409
        assert (
            await client.post(
                "/api/v1/practice/sessions",
                headers=advisor,
                json={"scenario_id": "SCENARIO_02_VF8_FAMILY", "assignment_id": assignment_id},
            )
        ).status_code == 409
        started = await client.post(
            "/api/v1/practice/sessions",
            headers=advisor,
            json={"scenario_id": "SCENARIO_01_VF5_TAXI", "assignment_id": assignment_id},
        )
        assert started.status_code == 201, started.text
        session_id = started.json()["session_id"]
        assert (await client.get("/api/v1/practice/assignments", headers=advisor)).json()[0]["status"] == "in_progress"
        await records.complete(session_id, draft_for(session_id))
        assignment = (await client.get("/api/v1/manager/assignments", headers=manager)).json()[0]
        assert (assignment["status"], assignment["session_id"]) == ("completed", session_id)
        assert (
            await client.post(
                "/api/v1/practice/sessions",
                headers=advisor,
                json={"scenario_id": "SCENARIO_01_VF5_TAXI", "assignment_id": assignment_id},
            )
        ).status_code == 409
        before_review = (await client.get("/api/v1/manager/advisors", headers=manager)).json()
        assert before_review[0]["average_score"] is None
        assert all(item["rank"] is None for item in before_review)
        assert (
            await client.patch(
                f"/api/v1/manager/reviews/{session_id}", headers=manager, json={"change_reason": "Transcript checked."}
            )
        ).status_code == 200
        for _ in range(2):
            response = await client.post(
                "/api/v1/practice/sessions", headers=advisor, json={"scenario_id": "SCENARIO_01_VF5_TAXI"}
            )
            extra_id = response.json()["session_id"]
            await records.complete(extra_id, draft_for(extra_id))
            assert (
                await client.patch(
                    f"/api/v1/manager/reviews/{extra_id}",
                    headers=manager,
                    json={"change_reason": "Transcript checked."},
                )
            ).status_code == 200
        performance = (await client.get("/api/v1/manager/advisors", headers=manager)).json()
        assert performance[0]["advisor_id"] == "advisor-a"
        assert performance[0]["rank"] == 1
        assert performance[0]["scored_sessions"] == 3
        assert performance[0]["average_score"] == 3
        assert performance[1]["rank"] is None


@pytest.mark.asyncio
async def test_real_auth_cookie_is_used_for_practice_ownership_and_manager_access(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'vertical.db'}"
    settings = Settings(
        _env_file=None,
        database_url=database_url,
        embedding_provider="hash",
        app_env="test",
    )
    auth = AuthService(SQLAuthRepository(database_url))
    for user_id, username, role in (
        ("advisor-a", "advisor.a", UserRole.ADVISOR),
        ("advisor-b", "advisor.b", UserRole.ADVISOR),
        ("manager-a", "manager.a", UserRole.MANAGER),
    ):
        await auth.seed_user(
            user_id=user_id,
            username=username,
            display_name=user_id,
            role=role,
            password="correct horse battery staple",
        )
    records = SQLPracticeRecordsRepository(database_url)
    service = RecordedPracticeService(StubPractice(), records)
    current_user = CurrentUserDependency(auth, settings.auth_cookie_name)
    practice_router, manager_router = create_recorded_practice_routers(service, current_user)
    app = FastAPI()
    app.add_exception_handler(PracticeAPIError, practice_exception_handler)
    app.include_router(create_auth_router(auth, settings), prefix="/api/v1")
    app.include_router(practice_router, prefix="/api/v1")
    app.include_router(manager_router, prefix="/api/v1")

    transport = httpx.ASGITransport(app=app)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test") as advisor_a,
        httpx.AsyncClient(transport=transport, base_url="http://test") as advisor_b,
        httpx.AsyncClient(transport=transport, base_url="http://test") as manager,
    ):
        for client, username in (
            (advisor_a, "advisor.a"),
            (advisor_b, "advisor.b"),
            (manager, "manager.a"),
        ):
            response = await client.post(
                "/api/v1/auth/login",
                json={"username": username, "password": "correct horse battery staple"},
            )
            assert response.status_code == 200

        created = await advisor_a.post(
            "/api/v1/practice/sessions",
            json={"scenario_id": "SCENARIO_01_VF5_TAXI"},
        )
        assert created.status_code == 201
        session_id = created.json()["session_id"]
        await records.complete(session_id, draft_for(session_id))

        assert [item["session_id"] for item in (await advisor_a.get("/api/v1/practice/history")).json()] == [session_id]
        assert (await advisor_b.get("/api/v1/practice/history")).json() == []
        assert (await advisor_b.get(f"/api/v1/practice/{session_id}/attempt")).status_code == 404
        assert (await advisor_a.get("/api/v1/manager/reviews")).status_code == 403
        assert (await manager.get("/api/v1/practice/history")).status_code == 403
        assert [item["session_id"] for item in (await manager.get("/api/v1/manager/reviews")).json()] == [session_id]
        assert (await manager.get(f"/api/v1/manager/reviews/{session_id}")).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "method", "service_method", "error", "status", "code", "detail"),
    [
        (
            "message",
            "POST",
            "send_message",
            RoleplaySessionConflictError("cannot continue a finished practice session", code="session_finished"),
            409,
            "session_finished",
            "Phiên luyện tập đã kết thúc và không nhận thêm tin nhắn.",
        ),
        (
            "message",
            "POST",
            "send_message",
            RoleplaySessionConflictError(
                "customer reply is pending; retry it before sending another message", code="session_busy"
            ),
            409,
            "session_busy",
            "Khách hàng đang trả lời, vui lòng đợi giây lát.",
        ),
        (
            "retry-reply",
            "POST",
            "retry_customer_reply",
            CustomerResponseError("private customer failure"),
            503,
            "provider_unavailable",
            "Hệ thống AI tạm thời gián đoạn. Tin nhắn của bạn đã được lưu, hãy thử lại.",
        ),
        (
            "finish",
            "POST",
            "finish_session",
            PracticeEvaluationUnavailableError("private evaluation failure"),
            503,
            "evaluation_failed",
            "Chưa thể chấm điểm lúc này. Vui lòng thử lại.",
        ),
        (
            "result",
            "GET",
            "advisor_result",
            PracticeEvaluationUnavailableError("private evaluation failure"),
            503,
            "evaluation_failed",
            "Chưa thể chấm điểm lúc này. Vui lòng thử lại.",
        ),
    ],
)
async def test_recorded_practice_error_contract(endpoint, method, service_method, error, status, code, detail):
    from unittest.mock import AsyncMock, Mock

    service = Mock(spec=RecordedPracticeService)
    setattr(service, service_method, AsyncMock(side_effect=error))
    router, _ = create_recorded_practice_routers(service, fake_identity)
    app = FastAPI()
    app.add_exception_handler(PracticeAPIError, practice_exception_handler)
    app.include_router(router, prefix="/api/v1")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        kwargs = {"json": {"message": "Xin chào"}} if endpoint == "message" else {}
        response = await client.request(
            method,
            f"/api/v1/practice/session-1/{endpoint}",
            headers={"X-Test-Identity": "advisor-a:advisor"},
            **kwargs,
        )
        assert response.status_code == status
        assert response.json() == {"code": code, "detail": detail}
        assert "private" not in response.text


MANAGER = {"X-Test-Identity": "manager-a:manager"}
ADVISOR_A = {"X-Test-Identity": "advisor-a:advisor"}
ADVISOR_B = {"X-Test-Identity": "advisor-b:advisor"}
SCENARIO = "SCENARIO_01_VF5_TAXI"


def full_draft(session_id: str, scores: dict[str, int]) -> SessionEvaluationResult:
    evaluations = [
        {
            "criterion": criterion,
            "status": "assessed",
            "score": scores[criterion.value],
            "evidence": [{"message_id": "a-1", "quote": "What matters most?"}],
            "reason": "Transcript checked.",
        }
        for criterion in CriterionType
    ]
    return SessionEvaluationResult(
        session_id=session_id,
        scenario_id=SCENARIO,
        rubric_version="test-v1",
        assessed_criteria_count=5,
        overall_score=sum(scores.values()) / 5,
        evaluations=evaluations,
    )


def uniform(score: int) -> dict[str, int]:
    return {criterion.value: score for criterion in CriterionType}


async def seed_attempt(records, session_id, advisor_id, scores, days_ago, assignment_id=None):
    await records.register(session_id, SCENARIO, advisor_id, assignment_id)
    await records.complete(session_id, full_draft(session_id, scores))
    with records._engine.begin() as connection:
        connection.execute(
            update(records._attempts)
            .where(records._attempts.c.session_id == session_id)
            .values(completed_at=datetime.now(UTC) - timedelta(days=days_ago))
        )


def build_app(records, advisors=None):
    service = RecordedPracticeService(StubPractice(), records, advisors)
    practice_router, manager_router = create_recorded_practice_routers(service, fake_identity)
    app = FastAPI()
    app.add_exception_handler(PracticeAPIError, practice_exception_handler)
    app.include_router(practice_router, prefix="/api/v1")
    app.include_router(manager_router, prefix="/api/v1")
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_manager_dashboard_aggregates_matrix_trend_agreement_queue_and_assignments(tmp_path):
    records = SQLPracticeRecordsRepository(f"sqlite:///{tmp_path / 'dashboard.db'}")
    await seed_attempt(records, "s1", "advisor-a", uniform(3), days_ago=15)
    await seed_attempt(records, "s2", "advisor-a", uniform(2), days_ago=1)
    await seed_attempt(records, "s3", "advisor-a", uniform(3), days_ago=5)
    await seed_attempt(records, "s4", "advisor-b", uniform(2), days_ago=2)
    lowered = {"policy_accuracy": {"score": 1, "reason": "Policy claim was unverified."}}
    async with build_app(records, AdvisorDirectoryStub()) as client:
        for session_id, body in (
            ("s1", {"score_overrides": lowered}),
            ("s2", {}),
            ("s4", {}),
        ):
            reviewed = await client.patch(f"/api/v1/manager/reviews/{session_id}", headers=MANAGER, json=body)
            assert reviewed.status_code == 200, reviewed.text
        today = datetime.now(UTC).date()
        for advisor_id, due, linked in (
            ("advisor-a", today - timedelta(days=2), False),
            ("advisor-a", today + timedelta(days=3), False),
            ("advisor-b", None, False),
            ("advisor-b", today - timedelta(days=4), True),
        ):
            assignment = await records.create_assignment(
                "manager-a",
                CreateAssignmentInput(
                    advisor_id=advisor_id, scenario_id=SCENARIO, title=f"Task {advisor_id}", due_date=due
                ),
            )
            if linked:
                await records.register("linked", SCENARIO, advisor_id, assignment.assignment_id)

        assert (await client.get("/api/v1/manager/dashboard", headers=ADVISOR_A)).status_code == 403
        response = await client.get("/api/v1/manager/dashboard?weeks=8", headers=MANAGER)
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["advisor_count"], data["approved_attempts"], data["weeks"]) == (2, 3, 8)
    assert data["has_sample_data"] is False
    matrix = {row["advisor_id"]: row for row in data["skill_matrix"]}
    assert [row["advisor_id"] for row in data["skill_matrix"]] == ["advisor-a", "advisor-b"]
    row_a = matrix["advisor-a"]
    assert row_a["approved_sessions"] == 2
    assert row_a["overall_avg"] == 2.3
    assert row_a["criteria"]["need_discovery"] == {"avg": 2.5, "n": 2, "insufficient": False}
    assert row_a["criteria"]["policy_accuracy"] == {"avg": 1.5, "n": 2, "insufficient": False}
    assert matrix["advisor-b"]["criteria"]["need_discovery"] == {"avg": 2.0, "n": 1, "insufficient": True}
    assert set(row_a["criteria"]) == {criterion.value for criterion in CriterionType}

    trend = data["team_trend"]
    assert len(trend) == 8
    assert sum(point["attempts"] for point in trend) == 3
    assert sum(point["attempts"] > 0 for point in trend) >= 2
    assert all(point["avg_score"] is None for point in trend if point["attempts"] == 0)
    assert sum(p["attempts"] for p in data["advisor_trends"]["advisor-a"]) == 2
    assert sum(p["attempts"] for p in data["advisor_trends"]["advisor-b"]) == 1

    agreement = {item["criterion"]: item for item in data["ai_agreement"]}
    assert agreement["policy_accuracy"] == {
        "criterion": "policy_accuracy",
        "reviewed": 3,
        "changed": 1,
        "changed_rate": 0.33,
        "mean_delta": 2.0,
    }
    assert agreement["need_discovery"]["changed"] == 0
    assert agreement["need_discovery"]["mean_delta"] == 0

    assert data["queue"]["pending"] == 1
    assert data["queue"]["oldest_pending_at"] is not None
    assert data["assignments"]["open"] == 2
    overdue = data["assignments"]["overdue"]
    assert [(item["advisor_name"], item["advisor_id"]) for item in overdue] == [("Advisor A", "advisor-a")]
    assert date.fromisoformat(overdue[0]["due_date"]) < datetime.now(UTC).date()


@pytest.mark.asyncio
async def test_dashboard_lists_advisors_without_sessions_as_insufficient(tmp_path):
    records = SQLPracticeRecordsRepository(f"sqlite:///{tmp_path / 'empty.db'}")
    async with build_app(records, AdvisorDirectoryStub()) as client:
        data = (await client.get("/api/v1/manager/dashboard", headers=MANAGER)).json()
    assert [row["overall_avg"] for row in data["skill_matrix"]] == [None, None]
    assert all(cell["insufficient"] for cell in data["skill_matrix"][0]["criteria"].values())
    assert data["queue"] == {"pending": 0, "oldest_pending_at": None}


@pytest.mark.asyncio
async def test_practice_progress_returns_only_the_callers_data(tmp_path):
    records = SQLPracticeRecordsRepository(f"sqlite:///{tmp_path / 'progress.db'}")
    await seed_attempt(records, "old", "advisor-a", uniform(1), days_ago=40)
    await seed_attempt(records, "new", "advisor-a", uniform(3), days_ago=1)
    await seed_attempt(records, "pending", "advisor-a", uniform(2), days_ago=0)
    await seed_attempt(records, "other", "advisor-b", uniform(2), days_ago=1)
    async with build_app(records) as client:
        for session_id in ("old", "new", "other"):
            assert (
                await client.patch(f"/api/v1/manager/reviews/{session_id}", headers=MANAGER, json={})
            ).status_code == 200
        assert (await client.get("/api/v1/practice/progress", headers=MANAGER)).status_code == 403
        mine = (await client.get("/api/v1/practice/progress", headers=ADVISOR_A)).json()
        theirs = (await client.get("/api/v1/practice/progress", headers=ADVISOR_B)).json()
    assert mine["approved_sessions"] == 2
    assert mine["overall_avg"] == 2.0
    assert len(mine["trend"]) == 8
    assert mine["change_8w"] == 2.0
    assert mine["criteria"]["need_discovery"] == {"latest_avg": 3.0, "change_4w": 2.0, "n": 2}
    assert mine["scenarios"][SCENARIO]["last_session_id"] == "pending"
    assert mine["scenarios"][SCENARIO]["last_status"] == "pending_review"
    assert mine["scenarios"][SCENARIO]["last_score"] == 2.0
    assert theirs["approved_sessions"] == 1
    assert theirs["overall_avg"] == 2.0
    assert theirs["scenarios"][SCENARIO]["last_session_id"] == "other"


@pytest.mark.asyncio
async def test_manager_todos_are_scoped_per_manager(tmp_path):
    records = SQLPracticeRecordsRepository(f"sqlite:///{tmp_path / 'todos.db'}")
    other = {"X-Test-Identity": "manager-b:manager"}
    async with build_app(records) as client:
        assert (await client.get("/api/v1/manager/todos", headers=ADVISOR_A)).status_code == 403
        assert (await client.post("/api/v1/manager/todos", headers=MANAGER, json={"text": "   "})).status_code == 422
        assert (
            await client.post("/api/v1/manager/todos", headers=MANAGER, json={"text": "x" * 301})
        ).status_code == 422
        first = await client.post("/api/v1/manager/todos", headers=MANAGER, json={"text": "  Review queue  "})
        assert first.status_code == 201
        assert first.json()["text"] == "Review queue"
        assert first.json()["done"] is False
        second = await client.post("/api/v1/manager/todos", headers=MANAGER, json={"text": "Coach Vy"})
        todo_id = first.json()["todo_id"]
        assert (await client.get("/api/v1/manager/todos", headers=other)).json() == []
        assert (
            await client.patch(f"/api/v1/manager/todos/{todo_id}", headers=other, json={"done": True})
        ).status_code == 404
        assert (
            await client.patch("/api/v1/manager/todos/missing", headers=MANAGER, json={"done": True})
        ).status_code == 404
        done = await client.patch(f"/api/v1/manager/todos/{todo_id}", headers=MANAGER, json={"done": True})
        assert done.status_code == 200
        assert done.json()["done"] is True
        assert done.json()["done_at"] is not None
        listed = (await client.get("/api/v1/manager/todos", headers=MANAGER)).json()
        assert [item["todo_id"] for item in listed] == [second.json()["todo_id"], todo_id]
        undone = await client.patch(f"/api/v1/manager/todos/{todo_id}", headers=MANAGER, json={"done": False})
        assert undone.json()["done_at"] is None


@pytest.mark.asyncio
async def test_review_requires_reason_for_each_changed_score_and_stores_it(tmp_path):
    records = SQLPracticeRecordsRepository(f"sqlite:///{tmp_path / 'reasons.db'}")
    path = "/api/v1/manager/reviews/session-1"
    async with build_app(records) as client:
        created = await client.post("/api/v1/practice/sessions", headers=ADVISOR_A, json={"scenario_id": SCENARIO})
        assert created.json()["session_id"] == "session-1"
        await records.complete("session-1", full_draft("session-1", uniform(2)))
        missing = await client.patch(
            path, headers=MANAGER, json={"score_overrides": {"policy_accuracy": {"score": 1, "reason": "  "}}}
        )
        assert missing.status_code == 422
        assert "policy_accuracy" in missing.json()["detail"]
        assert (
            await client.patch(path, headers=MANAGER, json={"score_overrides": {"policy_accuracy": {"score": 1}}})
        ).status_code == 422
        approved = await client.patch(
            path,
            headers=MANAGER,
            json={
                "score_overrides": {
                    "policy_accuracy": {"score": 1, "reason": "Quoted a benefit without a source."},
                    "need_discovery": {"score": 2},
                },
                "general_comment": "Good rapport overall.",
            },
        )
        assert approved.status_code == 200, approved.text
        body = approved.json()
        assert body["general_comment"] == "Good rapport overall."
        reasons = {item["criterion"]: item["manager_reason"] for item in body["approved_result"]["evaluations"]}
        assert reasons["policy_accuracy"] == "Quoted a benefit without a source."
        assert reasons["need_discovery"] is None
        assert body["ai_draft"]["evaluations"][0]["manager_reason"] is None
        detail = (await client.get(path, headers=MANAGER)).json()
        assert detail["manager_review"]["general_comment"] == "Good rapport overall."
        own = (await client.get("/api/v1/practice/session-1/attempt", headers=ADVISOR_A)).json()
        assert own["manager_review"]["general_comment"] == "Good rapport overall."


@pytest.mark.asyncio
async def test_review_still_accepts_legacy_body_and_mixed_overrides(tmp_path):
    records = SQLPracticeRecordsRepository(f"sqlite:///{tmp_path / 'legacy.db'}")
    await seed_attempt(records, "s1", "advisor-a", uniform(2), days_ago=1)
    async with build_app(records) as client:
        legacy = await client.patch(
            "/api/v1/manager/reviews/s1",
            headers=MANAGER,
            json={"score_overrides": {"policy_accuracy": 1}, "change_reason": "Unsupported claim."},
        )
        assert legacy.status_code == 200, legacy.text
        body = legacy.json()
        assert body["change_reason"] == "Unsupported claim."
        reasons = {item["criterion"]: item["manager_reason"] for item in body["approved_result"]["evaluations"]}
        assert reasons["policy_accuracy"] == "Unsupported claim."
        assert body["approved_result"]["overall_score"] == 1.8
        await seed_attempt(records, "s2", "advisor-a", uniform(2), days_ago=1)
        assert (
            await client.patch(
                "/api/v1/manager/reviews/s2", headers=MANAGER, json={"score_overrides": {"policy_accuracy": 1}}
            )
        ).status_code == 422
        unchanged = await client.patch(
            "/api/v1/manager/reviews/s2",
            headers=MANAGER,
            json={"score_overrides": {"policy_accuracy": {"score": 2}}},
        )
        assert unchanged.status_code == 200
        assert unchanged.json()["general_comment"] is None
        assert unchanged.json()["approved_result"]["overall_score"] == 2
