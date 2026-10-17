import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from src.agents.roleplay.customer_agent import CustomerResponseError
from src.agents.roleplay.graph import (
    RoleplayScenarioNotFoundError,
    RoleplaySessionNotFoundError,
)
from src.agents.roleplay.scenario_loader import ScenarioRepository
from src.api.practice import create_practice_router
from src.api.practice_errors import PracticeAPIError, practice_exception_handler
from src.services.practice import (
    PracticeEvaluationUnavailableError,
    PracticeResultView,
    PracticeSessionView,
)


def session_view(session_id="session-1"):
    return PracticeSessionView(
        session_id=session_id,
        scenario_id="SCENARIO_01_VF5_TAXI",
        difficulty="Medium",
        sales_channel="Fanpage",
        training_objective="Practice discovery",
        conversation_stage="opening",
        turn_count=0,
        visible_context="A customer asks about switching cars.",
        termination_status="active",
        messages=[],
    )


class StubPracticeService:
    def __init__(self):
        self.scenarios = ScenarioRepository().list_public()
        self.start_error = None
        self.message_error = None
        self.finish_error = None
        self.start_calls = []
        self.turn_limit_calls = []
        self.message_calls = []
        self.finish_calls = []

    def list_scenarios(self):
        return self.scenarios

    async def start_session(self, scenario_id, max_turns=None):
        self.start_calls.append(scenario_id)
        self.turn_limit_calls.append(max_turns)
        if self.start_error:
            raise self.start_error
        return session_view().model_copy(update={"max_turns": max_turns or 10})

    async def send_message(self, session_id, message):
        self.message_calls.append((session_id, message))
        if self.message_error:
            raise self.message_error
        return session_view(session_id)

    async def finish_session(self, session_id):
        self.finish_calls.append(session_id)
        if self.finish_error:
            raise self.finish_error
        return PracticeResultView(session_id=session_id, evaluation_status="pending")

    async def get_result(self, session_id):
        if self.finish_error:
            raise self.finish_error
        return PracticeResultView(session_id=session_id, evaluation_status="failed")

    async def get_session(self, session_id):
        if session_id == "missing":
            raise RoleplaySessionNotFoundError("internal detail")
        return session_view(session_id)


@pytest.fixture
def service():
    return StubPracticeService()


@pytest_asyncio.fixture
async def client(service):
    app = FastAPI()
    app.add_exception_handler(PracticeAPIError, practice_exception_handler)
    app.include_router(create_practice_router(service), prefix="/api/v1")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client


@pytest.mark.asyncio
async def test_list_scenarios_does_not_expose_private_fields(client):
    response = await client.get("/api/v1/practice/scenarios")

    assert response.status_code == 200
    assert len(response.json()) == 4
    assert "hidden_facts" not in response.json()[0]


@pytest.mark.asyncio
async def test_start_session_returns_created_session(client, service):
    response = await client.post(
        "/api/v1/practice/sessions",
        json={"scenario_id": "SCENARIO_01_VF5_TAXI"},
    )

    assert response.status_code == 201
    assert response.json()["session_id"] == "session-1"
    assert service.start_calls == ["SCENARIO_01_VF5_TAXI"]


@pytest.mark.asyncio
async def test_start_session_accepts_only_eight_to_fifteen_turns(client, service):
    for invalid in (7, 16):
        response = await client.post(
            "/api/v1/practice/sessions",
            json={"scenario_id": "SCENARIO_01_VF5_TAXI", "max_turns": invalid},
        )
        assert response.status_code == 422
    assert service.start_calls == []

    response = await client.post(
        "/api/v1/practice/sessions",
        json={"scenario_id": "SCENARIO_01_VF5_TAXI", "max_turns": 15},
    )
    assert response.status_code == 201
    assert response.json()["max_turns"] == 15
    assert service.turn_limit_calls == [15]


@pytest.mark.asyncio
async def test_start_unknown_scenario_returns_404(client, service):
    service.start_error = RoleplayScenarioNotFoundError("private internal detail")

    response = await client.post(
        "/api/v1/practice/sessions",
        json={"scenario_id": "missing"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Không tìm thấy phiên luyện tập.", "code": "session_not_found"}


@pytest.mark.asyncio
async def test_blank_message_is_rejected_before_service_call(client, service):
    response = await client.post(
        "/api/v1/practice/session-1/message",
        json={"message": "   "},
    )

    assert response.status_code == 422
    assert service.message_calls == []


@pytest.mark.asyncio
async def test_missing_session_returns_404(client, service):
    service.message_error = RoleplaySessionNotFoundError("private internal detail")

    response = await client.post(
        "/api/v1/practice/missing/message",
        json={"message": "Xin chào"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Không tìm thấy phiên luyện tập.", "code": "session_not_found"}


@pytest.mark.asyncio
async def test_invalid_ai_output_returns_retryable_503_without_internal_detail(
    client,
    service,
):
    service.message_error = CustomerResponseError("model returned secret detail")

    response = await client.post(
        "/api/v1/practice/session-1/message",
        json={"message": "Xin chào"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "code": "provider_unavailable",
        "detail": "Hệ thống AI tạm thời gián đoạn. Tin nhắn của bạn đã được lưu, hãy thử lại.",
    }
    assert "secret detail" not in response.text


@pytest.mark.asyncio
async def test_finish_and_result_expose_evaluation_status(client, service):
    finish = await client.post("/api/v1/practice/session-1/finish")
    result = await client.get("/api/v1/practice/session-1/result")

    assert finish.status_code == 200
    assert finish.json() == {
        "session_id": "session-1",
        "evaluation_status": "pending",
        "result": None,
    }
    assert result.status_code == 200
    assert result.json()["evaluation_status"] == "failed"
    assert service.finish_calls == ["session-1"]


@pytest.mark.asyncio
async def test_finish_provider_failure_is_retryable_without_internal_detail(client, service):
    service.finish_error = PracticeEvaluationUnavailableError("secret provider response")

    response = await client.post("/api/v1/practice/session-1/finish")

    assert response.status_code == 503
    assert response.json() == {
        "code": "evaluation_failed",
        "detail": "Chưa thể chấm điểm lúc này. Vui lòng thử lại.",
    }
    assert "secret provider response" not in response.text


@pytest.mark.asyncio
async def test_get_session_returns_only_advisor_safe_context(client):
    response = await client.get("/api/v1/practice/session-1")

    assert response.status_code == 200
    assert response.json()["session_id"] == "session-1"
    assert "hidden_facts" not in response.json()
    assert "evaluation_result" not in response.json()


@pytest.mark.asyncio
async def test_get_missing_session_returns_404(client):
    response = await client.get("/api/v1/practice/missing")

    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reason", "code", "detail"),
    [
        (
            "cannot continue a finished practice session",
            "session_finished",
            "Phiên luyện tập đã kết thúc và không nhận thêm tin nhắn.",
        ),
        (
            "customer reply is pending; retry it before sending another message",
            "session_busy",
            "Khách hàng đang trả lời, vui lòng đợi giây lát.",
        ),
    ],
)
async def test_message_conflicts_have_distinct_localized_codes(client, service, reason, code, detail):
    from src.agents.roleplay.graph import RoleplaySessionConflictError

    service.message_error = RoleplaySessionConflictError(reason, code=code)
    response = await client.post("/api/v1/practice/session-1/message", json={"message": "Xin chào"})
    assert response.status_code == 409
    assert response.json() == {"code": code, "detail": detail}


@pytest.mark.asyncio
async def test_result_evaluation_failure_is_localized(client, service):
    service.finish_error = PracticeEvaluationUnavailableError("private evaluation details")
    response = await client.get("/api/v1/practice/session-1/result")
    assert response.status_code == 503
    assert response.json() == {
        "code": "evaluation_failed",
        "detail": "Chưa thể chấm điểm lúc này. Vui lòng thử lại.",
    }
