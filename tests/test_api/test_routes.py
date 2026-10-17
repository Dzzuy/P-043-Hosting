import pytest

from src.models.auth import AuthenticatedUser, UserRole


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_chat_empty_message(client):
    response = await client.post("/api/v1/chat", json={"message": ""})
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_agent_status(client):
    response = await client.get("/api/v1/status")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_practice_scenarios_require_authentication_on_application(client):
    response = await client.get("/api/v1/practice/scenarios")

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.",
        "code": "unauthenticated",
    }


@pytest.mark.asyncio
async def test_copilot_and_source_routes_require_authentication_on_application(client):
    query = await client.post("/api/v1/copilot/query", json={"query": "Giá VF 8"})
    source = await client.get("/api/v1/copilot/sources/PRICE_LIST_VINFAST_20260921")

    assert query.status_code == 401
    assert source.status_code == 401
    assert query.json() == {"detail": "Authentication required."}
    assert source.json() == {"detail": "Authentication required."}


@pytest.mark.asyncio
async def test_manager_cannot_use_advisor_copilot_routes(client, monkeypatch):
    async def manager_identity(_request):
        return AuthenticatedUser(
            user_id="manager-test", username="manager.test", display_name="Manager", role=UserRole.MANAGER
        )

    monkeypatch.setattr("src.main.app.state.current_user", manager_identity)
    response = await client.get("/api/v1/copilot/sources/PRICE_LIST_VINFAST_20260921")

    assert response.status_code == 403
