"""Tests for Copilot SSE Streaming endpoint."""

from types import SimpleNamespace

import pytest

from src.agents.copilot.runtime import CopilotAdmission
from src.agents.copilot.state import Citation, CopilotResponse
from src.api.copilot import current_copilot_user
from src.config import get_settings
from src.integrations.copilot_sessions import SQLCopilotSessionsRepository
from src.knowledge.index_readiness import load_snapshot
from src.main import app


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    repository = SQLCopilotSessionsRepository(f"sqlite:///{tmp_path / 'stream_test.db'}")
    monkeypatch.setattr(app.state, "copilot_sessions", repository)
    monkeypatch.setattr(app.state, "copilot_readiness", load_snapshot)
    monkeypatch.setattr(app.state, "copilot_admission", CopilotAdmission(get_settings()))
    yield repository
    repository.engine.dispose()


@pytest.fixture
def owner():
    identity = SimpleNamespace(user_id="sales-stream-tester")

    async def authenticated():
        return identity

    app.dependency_overrides[current_copilot_user] = authenticated
    yield identity
    app.dependency_overrides.pop(current_copilot_user, None)


@pytest.mark.asyncio
async def test_stream_requires_authentication(client):
    response = await client.post("/api/v1/copilot/query/stream", json={"query": "VF 5?"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_stream_returns_sse_events(client, sessions, owner, monkeypatch):
    async def mock_graph(state, **kwargs):
        return {
            "final_response": CopilotResponse(
                status="answered",
                answer="Giá VF 5 Plus là 496 triệu đồng [C1].",
                citations=[
                    Citation(
                        citation_id="C1",
                        document_id="vf5_specs",
                        chunk_id="chunk-1",
                        title="Bảng giá VF 5 Plus",
                        excerpt="Giá 496 triệu",
                    )
                ],
            )
        }

    monkeypatch.setattr("src.api.copilot.copilot_agent.ainvoke", mock_graph)

    resp = await client.post(
        "/api/v1/copilot/query/stream",
        json={"query": "VF 5 Plus giá bao nhiêu?", "domain": "specs"},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    body = resp.text
    assert "event: status" in body
    assert "event: delta" in body
    assert "event: final" in body
    assert "event: done" in body
    assert "496 triệu đồng" in body


@pytest.mark.asyncio
async def test_stream_logs_dependency_stage_without_private_provider_details(client, sessions, owner, monkeypatch, caplog):
    from src.agents.copilot.runtime import CopilotDependencyError

    async def unavailable(state, **kwargs):
        state["runtime"].events.append({
            "node": "analyze_and_route", "failure_stage": "analyze_and_route",
            "error_type": "TimeoutError", "failure_kind": "provider", "provider_status": None,
        })
        raise CopilotDependencyError("analyze_and_route unavailable") from TimeoutError("private provider detail")

    monkeypatch.setattr("src.api.copilot.copilot_agent.ainvoke", unavailable)
    response = await client.post("/api/v1/copilot/query/stream", json={"query": "VF 5 Plus?"})
    assert response.status_code == 200  # The stream has started before the worker fails.
    assert "event: error" in response.text and "event: final" not in response.text
    failure = next(record.telemetry for record in caplog.records if hasattr(record, "telemetry"))
    assert failure["failure_stage"] == "analyze_and_route"
    assert failure["cause_type"] == "TimeoutError"
    assert len(failure["request_id"]) == 32
    assert "private provider detail" not in caplog.text + response.text
