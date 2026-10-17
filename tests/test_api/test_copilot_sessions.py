"""Real HTTP ownership, dialogue persistence and failure semantics."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import update

from src.agents.copilot.runtime import CopilotAdmission
from src.agents.copilot.state import CopilotResponse
from src.api.copilot import current_copilot_user
from src.config import get_settings
from src.integrations.copilot_sessions import (
    CopilotSessionConflictError,
    CopilotSessionNotFoundError,
    SQLCopilotSessionsRepository,
)
from src.knowledge.index_readiness import load_snapshot
from src.main import app


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    repository = SQLCopilotSessionsRepository(f"sqlite:///{tmp_path / 'sessions.db'}")
    monkeypatch.setattr(app.state, "copilot_sessions", repository)
    monkeypatch.setattr(app.state, "copilot_readiness", load_snapshot)
    monkeypatch.setattr(app.state, "copilot_admission", CopilotAdmission(get_settings()))
    yield repository
    repository.engine.dispose()


@pytest.fixture
def owner():
    identity = SimpleNamespace(user_id="sales-a")

    async def authenticated():
        return identity

    app.dependency_overrides[current_copilot_user] = authenticated
    yield identity
    app.dependency_overrides.pop(current_copilot_user, None)


@pytest.mark.asyncio
async def test_http_requires_authentication(client):
    response = await client.post("/api/v1/copilot/query", json={"query": "VF 5?"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_follow_up_passes_owned_history_and_context(client, sessions, owner, monkeypatch):
    seen = []

    async def graph(state, **kwargs):
        seen.append(state)
        question = "Bạn đang tư vấn mẫu xe nào?"
        return {
            "final_response": CopilotResponse(
                status="needs_clarification", answer=question, clarification_question=question
            )
        }

    monkeypatch.setattr("src.api.copilot.copilot_agent.ainvoke", graph)
    first = await client.post(
        "/api/v1/copilot/query", json={"query": "Chuẩn bị cuộc gọi", "customer_context": "Khách có gara"}
    )
    assert first.status_code == 200
    session_id = first.json()["session_id"]
    second = await client.post("/api/v1/copilot/query", json={"query": "VF 5", "session_id": session_id})
    assert second.status_code == 200
    assert seen[1]["history"][0]["content"] == "Chuẩn bị cuộc gọi"
    assert seen[1]["customer_context"] == "Khách có gara"
    assert second.json()["is_clarification"] is True
    assert len(sessions.load(session_id, owner.user_id)["history"]) == 4
    owner.user_id = "sales-b"
    foreign = await client.post("/api/v1/copilot/query", json={"query": "VF 6?", "session_id": session_id})
    assert foreign.status_code == 404
    assert len(seen) == 2
    assert (await client.delete(f"/api/v1/copilot/sessions/{session_id}")).status_code == 404
    owner.user_id = "sales-a"
    assert (await client.delete(f"/api/v1/copilot/sessions/{session_id}")).status_code == 204


@pytest.mark.asyncio
async def test_provider_failure_is_503_and_does_not_save_dialogue(client, sessions, owner, monkeypatch):
    from src.agents.copilot.nodes import CopilotDependencyError

    session_id = "a" * 32
    sessions.save(session_id, owner.user_id, [], "", None)

    async def broken(state, **kwargs):
        raise CopilotDependencyError("generation unavailable")

    monkeypatch.setattr("src.api.copilot.copilot_agent.ainvoke", broken)
    result = await client.post("/api/v1/copilot/query", json={"query": "VF 5?", "session_id": session_id})
    assert result.status_code == 503
    assert sessions.load(session_id, owner.user_id)["history"] == []


def test_session_expiry_and_optimistic_concurrency(sessions):
    session_id = "a" * 32
    sessions.save(session_id, "sales-a", [], "", None)
    sessions.save(session_id, "sales-a", [{"role": "user", "content": "VF 5?"}], "", 1)
    with pytest.raises(CopilotSessionConflictError):
        sessions.save(session_id, "sales-a", [], "", 1)
    with sessions.engine.begin() as connection:
        connection.execute(update(sessions.sessions).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    with pytest.raises(CopilotSessionNotFoundError):
        sessions.load(session_id, "sales-a")


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["load", "save"])
async def test_sql_dependency_failure_is_503(client, sessions, owner, monkeypatch, operation):
    from sqlalchemy.exc import OperationalError

    session_id = "a" * 32
    sessions.save(session_id, owner.user_id, [], "", None)

    def unavailable(*args, **kwargs):
        raise OperationalError(None, None, ConnectionError("database unavailable"))

    async def graph(state, **kwargs):
        question = "Bạn cần tư vấn mẫu xe nào?"
        return {
            "final_response": CopilotResponse(
                status="needs_clarification", answer=question, clarification_question=question
            )
        }

    monkeypatch.setattr(sessions, operation, unavailable)
    monkeypatch.setattr("src.api.copilot.copilot_agent.ainvoke", graph)
    result = await client.post("/api/v1/copilot/query", json={"query": "VF 5?", "session_id": session_id})
    assert result.status_code == 503
    assert app.state.copilot_admission.active == {}


@pytest.mark.asyncio
async def test_conflicting_http_turn_does_not_overwrite_newer_history(client, sessions, owner, monkeypatch):
    session_id = "a" * 32
    sessions.save(session_id, owner.user_id, [], "", None)

    async def concurrent_graph(state, **kwargs):
        sessions.save(session_id, owner.user_id, [{"role": "user", "content": "newer turn"}], "", 1)
        return {
            "final_response": CopilotResponse(
                status="abstained", answer="Tôi không thể xác minh thông tin này từ nguồn tài liệu hiện có."
            )
        }

    monkeypatch.setattr("src.api.copilot.copilot_agent.ainvoke", concurrent_graph)
    response = await client.post("/api/v1/copilot/query", json={"query": "VF 5?", "session_id": session_id})
    assert response.status_code == 409
    assert sessions.load(session_id, owner.user_id)["history"][0]["content"] == "newer turn"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"query": "  "},
        {"query": "VF 5?", "session_id": "foreign"},
        {"query": "VF 5?", "target_date": "2026-10-09T00:00:00"},
        {"query": "VF 5?", "customer_context": "x" * 6001},
        {"query": "VF 5?", "domain": "unknown"},
    ],
)
async def test_invalid_input_is_rejected_before_graph_execution(client, owner, payload, monkeypatch):
    async def forbidden(state, **kwargs):
        raise AssertionError("graph must not run")

    monkeypatch.setattr("src.api.copilot.copilot_agent.ainvoke", forbidden)
    assert (await client.post("/api/v1/copilot/query", json=payload)).status_code == 422


@pytest.mark.asyncio
async def test_blocked_turn_never_saves_query_or_customer_context(client, sessions, owner, monkeypatch):
    from src.agents.copilot.state import FALLBACK_ANSWERS

    async def blocked(state, **kwargs):
        return {
            "final_response": CopilotResponse(
                status="abstained", reason_code="input_blocked", answer=FALLBACK_ANSWERS["input_blocked"]
            )
        }

    monkeypatch.setattr("src.api.copilot.copilot_agent.ainvoke", blocked)
    result = await client.post(
        "/api/v1/copilot/query", json={"query": "injected", "customer_context": "secret context"}
    )
    assert result.status_code == 200 and result.json()["session_id"] is None
    assert len(result.json()["request_id"]) == 32
    session_id = "b" * 32
    sessions.save(session_id, owner.user_id, [], "old context", None)
    result = await client.post(
        "/api/v1/copilot/query", json={"query": "injected", "session_id": session_id, "customer_context": "new context"}
    )
    stored = sessions.load(session_id, owner.user_id)
    assert stored["history"] == [] and stored["customer_context"] == "old context"
    assert result.json()["session_id"] == session_id


@pytest.mark.asyncio
async def test_readiness_failure_is_503_before_retrieval(client, sessions, owner, monkeypatch):
    from src.knowledge.index_readiness import IndexNotReadyError

    def broken():
        raise IndexNotReadyError("changed checksum")

    from tests.test_agents.test_copilot_agentic import intake, scripted

    scripted(monkeypatch, [intake()])
    monkeypatch.setattr(app.state, "copilot_readiness", broken)
    result = await client.post("/api/v1/copilot/query", json={"query": "VF 5?"})
    assert result.status_code == 503
    assert (await client.get("/ready")).status_code == 503
    assert (await client.get("/health")).status_code == 200


@pytest.mark.asyncio
async def test_sources_require_authentication(client):
    assert (await client.get("/api/v1/copilot/sources/SPECS_VF5_PLUS_2026")).status_code == 401


@pytest.mark.asyncio
async def test_http_rate_limit_has_retry_after(client, sessions, owner, monkeypatch):
    limits = CopilotAdmission(get_settings())
    limits.rate = 1
    limits.acquire(owner.user_id)
    limits.release(owner.user_id)
    monkeypatch.setattr(app.state, "copilot_admission", limits)
    result = await client.post("/api/v1/copilot/query", json={"query": "VF 5?"})
    assert result.status_code == 429 and int(result.headers["Retry-After"]) > 0


@pytest.mark.asyncio
async def test_backend_limit_returns_503_and_releases_capacity(client, sessions, owner, monkeypatch):
    limits = CopilotAdmission(get_settings())
    limits.max_active = 1
    limits.acquire("another-user")
    monkeypatch.setattr(app.state, "copilot_admission", limits)
    result = await client.post("/api/v1/copilot/query", json={"query": "VF 5?"})
    assert result.status_code == 503
    assert limits.active == {"another-user": 1}
