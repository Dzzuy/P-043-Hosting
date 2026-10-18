"""Tests for Conversation Memory & History REST endpoints and repository."""

from types import SimpleNamespace

import pytest

from src.agents.copilot.runtime import CopilotAdmission
from src.agents.copilot.state import Citation, CopilotResponse, ProductInsight
from src.api.copilot import current_copilot_user
from src.config import get_settings
from src.integrations.copilot_sessions import (
    SQLCopilotSessionsRepository,
)
from src.knowledge.index_readiness import load_snapshot
from src.main import app


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    repository = SQLCopilotSessionsRepository(f"sqlite:///{tmp_path / 'memory_test.db'}")
    monkeypatch.setattr(app.state, "copilot_sessions", repository)
    monkeypatch.setattr(app.state, "copilot_readiness", load_snapshot)
    monkeypatch.setattr(app.state, "copilot_admission", CopilotAdmission(get_settings()))
    yield repository
    repository.engine.dispose()


@pytest.fixture
def owner():
    identity = SimpleNamespace(user_id="sales-test-user")

    async def authenticated():
        return identity

    app.dependency_overrides[current_copilot_user] = authenticated
    yield identity
    app.dependency_overrides.pop(current_copilot_user, None)


@pytest.mark.asyncio
async def test_sessions_list_empty_and_created(client, sessions, owner, monkeypatch):
    # 1. Empty list initially
    resp = await client.get("/api/v1/copilot/sessions")
    assert resp.status_code == 200
    assert resp.json() == []

    # Mock copilot graph
    async def mock_graph(state, **kwargs):
        return {
            "final_response": CopilotResponse(
                status="answered",
                answer="Giá VF 5 Plus là 540 triệu đồng [C1].",
                citations=[
                    Citation(
                        citation_id="C1",
                        document_id="vf5_specs",
                        chunk_id="chunk-1",
                        title="Bảng giá VF 5 Plus",
                        excerpt="Giá kèm pin 540 triệu",
                    )
                ],
                product_insights=[
                    ProductInsight(
                        category="highlight",
                        product_model="VF 5",
                        title="Ưu điểm pin",
                        summary="Pin LFP 37.23 kWh bền bỉ",
                    )
                ],
            )
        }

    monkeypatch.setattr("src.api.copilot.copilot_agent.ainvoke", mock_graph)

    # 2. Query 1
    post_resp = await client.post(
        "/api/v1/copilot/query",
        json={"query": "VF 5 giá bao nhiêu?", "customer_context": "Khách mua xe lần đầu"},
    )
    assert post_resp.status_code == 200
    sess_id = post_resp.json()["session_id"]
    assert sess_id is not None

    # 3. List sessions contains the new conversation
    list_resp = await client.get("/api/v1/copilot/sessions")
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert len(data) == 1
    assert data[0]["session_id"] == sess_id
    assert "VF 5 giá bao nhiêu" in data[0]["title"]
    assert data[0]["message_count"] == 2

    # 4. Detail endpoint returns rich messages with citations and product_insights
    detail_resp = await client.get(f"/api/v1/copilot/sessions/{sess_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["session_id"] == sess_id
    assert len(detail["messages"]) == 2

    # User message
    user_msg = detail["messages"][0]
    assert user_msg["role"] == "user"
    assert user_msg["content"] == "VF 5 giá bao nhiêu?"

    # Assistant message
    asst_msg = detail["messages"][1]
    assert asst_msg["role"] == "assistant"
    assert "540 triệu" in asst_msg["content"]
    assert len(asst_msg["citations"]) == 1
    assert asst_msg["citations"][0]["citation_id"] == "C1"
    assert len(asst_msg["product_insights"]) == 1
    assert asst_msg["product_insights"][0]["title"] == "Ưu điểm pin"

    # 5. Delete session
    del_resp = await client.delete(f"/api/v1/copilot/sessions/{sess_id}")
    assert del_resp.status_code == 204

    # 6. Verify detail now returns 404 and list is empty
    assert (await client.get(f"/api/v1/copilot/sessions/{sess_id}")).status_code == 404
    assert (await client.get("/api/v1/copilot/sessions")).json() == []


@pytest.mark.asyncio
async def test_multi_turn_conversation_appends_messages_correctly(client, sessions, owner, monkeypatch):
    async def mock_graph_turn1(state, **kwargs):
        return {
            "final_response": CopilotResponse(
                status="answered",
                answer="VF 3 có giá 240 triệu đồng [C1].",
                citations=[
                    Citation(
                        citation_id="C1",
                        document_id="vf3_specs",
                        chunk_id="chunk-1",
                        title="Thông số VF 3",
                        excerpt="Giá 240 triệu",
                    )
                ],
            )
        }

    async def mock_graph_turn2(state, **kwargs):
        # Verify history passed to state
        assert len(state.get("history", [])) == 2
        assert state["history"][0]["content"] == "VF 3 giá bao nhiêu?"
        return {
            "final_response": CopilotResponse(
                status="answered",
                answer="Quãng đường di chuyển của VF 3 là 210 km [C2].",
                citations=[
                    Citation(
                        citation_id="C2",
                        document_id="vf3_specs",
                        chunk_id="chunk-2",
                        title="Thông số VF 3",
                        excerpt="Quãng đường 210 km",
                    )
                ],
            )
        }

    # Turn 1
    monkeypatch.setattr("src.api.copilot.copilot_agent.ainvoke", mock_graph_turn1)
    t1_resp = await client.post("/api/v1/copilot/query", json={"query": "VF 3 giá bao nhiêu?"})
    assert t1_resp.status_code == 200
    session_id = t1_resp.json()["session_id"]

    # Turn 2
    monkeypatch.setattr("src.api.copilot.copilot_agent.ainvoke", mock_graph_turn2)
    t2_resp = await client.post(
        "/api/v1/copilot/query",
        json={"query": "Quãng đường của nó là bao nhiêu?", "session_id": session_id},
    )
    assert t2_resp.status_code == 200

    # Verify session detail has all 4 messages in sequence
    detail_resp = await client.get(f"/api/v1/copilot/sessions/{session_id}")
    assert detail_resp.status_code == 200
    messages = detail_resp.json()["messages"]
    assert len(messages) == 4
    assert messages[0]["content"] == "VF 3 giá bao nhiêu?"
    assert "240 triệu" in messages[1]["content"]
    assert messages[2]["content"] == "Quãng đường của nó là bao nhiêu?"
    assert "210 km" in messages[3]["content"]


@pytest.mark.asyncio
async def test_session_isolation_between_different_users(client, sessions, owner, monkeypatch):
    async def mock_graph(state, **kwargs):
        return {
            "final_response": CopilotResponse(
                status="answered",
                answer="Mẫu xe rất tiết kiệm điện [C1].",
                citations=[
                    Citation(
                        citation_id="C1",
                        document_id="doc1",
                        chunk_id="chk1",
                        title="Tiết kiệm điện",
                    )
                ],
            )
        }

    monkeypatch.setattr("src.api.copilot.copilot_agent.ainvoke", mock_graph)

    # User 1 creates session
    owner.user_id = "user-alice"
    res1 = await client.post("/api/v1/copilot/query", json={"query": "Tư vấn VF 6"})
    s1 = res1.json()["session_id"]

    # User 2 cannot access Alice's session
    owner.user_id = "user-bob"
    bob_list = await client.get("/api/v1/copilot/sessions")
    assert bob_list.json() == []

    bob_get_s1 = await client.get(f"/api/v1/copilot/sessions/{s1}")
    assert bob_get_s1.status_code == 404
