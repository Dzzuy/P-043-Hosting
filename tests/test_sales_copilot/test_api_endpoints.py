"""Integration tests for Sales Copilot FastAPI endpoints."""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.api.sales_copilot import router
from src.integrations.sales_copilot_repository import SQLSalesCopilotRepository
from src.models.auth import AuthenticatedUser
from src.services.sales_conversation_service import SalesConversationService
from src.services.sales_copilot_analyzer import SalesCopilotAnalyzer


@pytest.fixture
def client(tmp_path, monkeypatch):
    repository = SQLSalesCopilotRepository(f"sqlite:///{tmp_path / 'api.db'}")
    for number in range(1, 4):
        customer = repository.create_customer(name=f"Khách QA {number}", advisor_id="endpoint-test")
        conversation_id = repository.get_or_create_conversation(customer)
        for index in range(12):
            repository.add_message(conversation_id, "customer", f"Câu hỏi kiểm thử {index}")
    analyzer = SalesCopilotAnalyzer(repository)
    monkeypatch.setattr(analyzer, "analyze_conversation", AsyncMock(return_value={
        "status": "success", "profile": {}, "memory": {}, "tasks": [], "lead_status": {},
    }))
    isolated_app = FastAPI()

    async def authenticated(request):
        return AuthenticatedUser(user_id="endpoint-test", username="test", display_name="Test", role="advisor")

    isolated_app.state.current_user = authenticated
    isolated_app.state.sales_copilot_repository = repository
    isolated_app.state.sales_conversation_service = SalesConversationService(repository)
    isolated_app.state.sales_copilot_analyzer = analyzer
    isolated_app.include_router(router, prefix="/api/v1")
    with TestClient(isolated_app) as test_client:
        yield test_client
    repository.engine.dispose()


def test_list_conversations_endpoint(client):
    res = client.get("/api/v1/sales-copilot/conversations")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 3
    names = [c["customer_name"] for c in data]
    assert set(names) == {"Khách QA 1", "Khách QA 2", "Khách QA 3"}


def test_conversation_details_and_analyze_endpoint(client):
    conv_list = client.get("/api/v1/sales-copilot/conversations").json()
    conv_id = conv_list[0]["conversation_id"]

    # Get details
    res = client.get(f"/api/v1/sales-copilot/conversations/{conv_id}")
    assert res.status_code == 200
    details = res.json()
    assert details["id"] == conv_id
    assert len(details["messages"]) > 10

    # Sales triggers analysis: "⚡ Phân tích hội thoại"
    analyze_res = client.post(f"/api/v1/sales-copilot/conversations/{conv_id}/analyze")
    assert analyze_res.status_code == 200
    result = analyze_res.json()
    assert result["status"] == "success"
    assert "profile" in result
    assert "memory" in result
    assert "tasks" in result
    assert "lead_status" in result


def test_preferences_endpoint(client):
    # GET
    res = client.get("/api/v1/sales-copilot/preferences")
    assert res.status_code == 200
    assert "draft_enabled" in res.json()

    # PATCH
    patch_res = client.patch(
        "/api/v1/sales-copilot/preferences",
        json={"advisor_id": "advisor_01", "nba_enabled": True, "draft_enabled": True},
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["advisor_id"] == "endpoint-test"
    assert "nba_enabled" not in updated
    assert updated["draft_enabled"] is True


def test_send_sales_message_endpoint(client):
    conv_list = client.get("/api/v1/sales-copilot/conversations").json()
    conv_id = conv_list[0]["conversation_id"]

    res = client.post(
        f"/api/v1/sales-copilot/conversations/{conv_id}/messages",
        json={"content": "Tin nhắn thử nghiệm kiểm tra endpoint", "sender_role": "sales"},
    )
    assert res.status_code == 200
    msg = res.json()
    assert msg["sender_role"] == "sales"
    assert "Tin nhắn thử nghiệm" in msg["content"]

    repo = client.app.state.sales_copilot_repository
    saved = repo.list_messages(conv_id)[-1]
    assert saved.id == msg["id"]
    assert saved.content == msg["content"]


def test_endpoints_reject_anonymous_requests(client):
    async def anonymous(request):
        raise HTTPException(status_code=401, detail="Authentication required.")

    client.app.state.current_user = anonymous
    assert client.get("/api/v1/sales-copilot/conversations").status_code == 401
    assert client.get("/api/v1/sales-copilot/preferences").status_code == 401


def test_endpoints_do_not_expose_another_advisors_conversation(client):
    repo = client.app.state.sales_copilot_repository
    customer = repo.create_customer(name="Other owner", advisor_id="other-advisor")
    conversation_id = repo.get_or_create_conversation(customer)
    repo.add_message(conversation_id, "customer", "Private message")
    prefix = f"/api/v1/sales-copilot/conversations/{conversation_id}"
    assert client.get(prefix).status_code == 404
    assert client.post(prefix + "/messages", json={"content": "Unauthorized", "sender_role": "sales"}).status_code == 404
    assert len(repo.list_messages(conversation_id)) == 1


def test_copilot_contextual_chat_endpoint(tmp_path, monkeypatch, request):
    from cryptography.fernet import Fernet
    from pydantic import SecretStr

    from src.config import get_settings
    monkeypatch.setattr(get_settings(), "sales_pii_key", SecretStr(Fernet.generate_key().decode()))
    from fastapi import FastAPI

    from src.agents.copilot.runtime import CopilotAdmission
    from src.agents.copilot.state import Citation
    from src.api.copilot import CopilotQueryResponse
    from src.api.sales_copilot import router
    from src.config import get_settings
    from src.integrations.copilot_sessions import SQLCopilotSessionsRepository
    from src.integrations.sales_copilot_repository import SQLSalesCopilotRepository
    from src.models.auth import AuthenticatedUser

    async def mock_query_copilot(req, **kwargs):
        assert "VF 3" in req.query
        return CopilotQueryResponse(
            status="answered", request_id="a" * 32,
            answer="Xe VF 3 có quãng đường di chuyển 215 km [C1].",
            citations=[
                Citation(
                    citation_id="C1",
                    chunk_id="chunk_vf3_01",
                    document_id="doc_vf3_specs",
                    title="Thông số kỹ thuật VF 3",
                    product_model="VF 3",
                    version="1.0",
                    excerpt="Quãng đường di chuyển 215 km theo chuẩn NEDC.",
                )
            ],
            suggested_message="Anh có thể cân nhắc VF 3 phù hợp đi làm 20km/ngày.",
        )

    monkeypatch.setattr("src.services.copilot_query.query_copilot", mock_query_copilot)
    url = f"sqlite:///{tmp_path / 'endpoint.db'}"
    repo, sessions = SQLSalesCopilotRepository(url), SQLCopilotSessionsRepository(url)
    customer_id = repo.create_customer(name="Khách kiểm thử", advisor_id="lookup-test")
    conv_id = repo.get_or_create_conversation(customer_id)
    isolated_app = FastAPI()
    async def authenticated(request):
        return AuthenticatedUser(user_id="lookup-test", username="test", display_name="Test", role="advisor")
    isolated_app.state.current_user = authenticated
    isolated_app.state.sales_copilot_repository = repo
    isolated_app.state.copilot_sessions = sessions
    isolated_app.state.copilot_admission = CopilotAdmission(get_settings())
    isolated_app.state.copilot_readiness = lambda: None
    isolated_app.include_router(router, prefix="/api/v1")
    client = TestClient(isolated_app)
    request.addfinalizer(lambda: (client.close(), repo.engine.dispose(), sessions.engine.dispose()))

    res = client.post(
        f"/api/v1/sales-copilot/conversations/{conv_id}/copilot-chat",
        json={"query": "Tư vấn pin và quãng đường xe VF 3 cho khách này"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "answered"
    assert "215 km [C1]" in data["answer"]
    assert len(data["citations"]) == 1
    assert data["citations"][0]["citation_id"] == "C1"
    assert data["citations"][0]["chunk_id"] == "chunk_vf3_01"
    assert data["citations"][0]["title"] == "Thông số kỹ thuật VF 3"


