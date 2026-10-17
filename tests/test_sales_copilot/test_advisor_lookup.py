"""Shared sales knowledge: real HTTP/session persistence, isolated DB and stubbed LLM."""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, update

from src.integrations.copilot_sessions import SQLCopilotSessionsRepository
from src.services import copilot_query
from tests.test_sales_copilot import test_customer_lookup as customer_lookup

final_response = customer_lookup.final_response


@pytest.fixture
def lookup(tmp_path, monkeypatch):
    yield from customer_lookup.lookup.__wrapped__(tmp_path, monkeypatch)

PATH = "/api/v1/copilot/knowledge"


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_shared_lookup_needs_no_customer_and_never_reads_customer_context(lookup, monkeypatch, stream):
    def unexpected_customer_read(*args, **kwargs):
        raise AssertionError("Shared knowledge must never read CRM customer data")

    monkeypatch.setattr(copilot_query, "build_customer_context", unexpected_customer_read)
    monkeypatch.setattr(copilot_query, "authorize_customer", unexpected_customer_read)
    del lookup.app.state.sales_copilot_repository
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=lookup.app), base_url="http://test") as client:
        assert (await client.get(PATH)).json() == {"session_id": None, "messages": [], "next_before_seq": None}
        assert lookup.sessions.advisor_session("sales-a") is None
        response = await client.post(PATH + ("/stream" if stream else ""), json={"query": "Giá VF 5?"})
        assert response.status_code == 200
        if stream:
            assert "event: final" in response.text and "event: done" in response.text
        assert lookup.seen[-1]["customer_context"] == ""
        assert lookup.seen[-1]["history"] == []
        first = (await client.get(PATH)).json()
        assert len(first["messages"]) == 2
        assert first["messages"][-1]["response_data"]["citations"][0]["chunk_id"] == "vf5_4"
        # A later question uses only sales Q&A history, regardless of the CRM selection.
        follow = await client.post(PATH, json={"query": "Thế còn VF 3?"})
        assert follow.json()["session_id"] == first["session_id"]
        assert len(lookup.seen[-1]["history"]) == 2
        assert lookup.seen[-1]["history"][0]["content"] == "Giá VF 5?"
        assert lookup.seen[-1]["customer_context"] == ""


@pytest.mark.asyncio
async def test_account_isolation_auth_and_reject_client_customer_or_session_scope(lookup):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=lookup.app), base_url="http://test") as client:
        for extra in ({"customer_context": "Khách bí mật"}, {"session_id": "a" * 32}, {"conversation_id": lookup.ids[0]}):
            assert (await client.post(PATH, json={"query": "VF 5?", **extra})).status_code == 422
        for query in (" ", "x", "x" * 4001):
            assert (await client.post(PATH + "/stream", json={"query": query})).status_code == 422
        first = (await client.post(PATH, json={"query": "VF 5?"})).json()
        lookup.identity.user_id = "sales-with-no-customers"
        assert (await client.get(PATH)).json()["messages"] == []
        second = (await client.post(PATH, json={"query": "VF 3?"})).json()
        assert second["session_id"] != first["session_id"]
        assert lookup.seen[-1]["history"] == []
        lookup.identity.user_id = "sales-a"
        assert len((await client.get(PATH)).json()["messages"]) == 2
        lookup.identity.user_id = None
        for path in (PATH, PATH + "/stream"):
            assert (await client.post(path, json={"query": "VF 5?"})).status_code == 401
        assert (await client.get(PATH)).status_code == 401
        lookup.identity.user_id, lookup.identity.role = "sales-a", "manager"
        assert (await client.get(PATH)).status_code == 403
        assert (await client.post(PATH, json={"query": "VF 5?"})).status_code == 403


@pytest.mark.asyncio
async def test_shared_history_durable_and_separate_from_customer_and_legacy_sessions(lookup):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=lookup.app), base_url="http://test") as client:
        old = f"/api/v1/sales-copilot/conversations/{lookup.ids[0]}/copilot-chat"
        customer = (await client.post(old, json={"query": "Khách cần VF 5?"})).json()
        shared = (await client.post(PATH, json={"query": "Bảo hành VF 3?"})).json()
        sid = shared["session_id"]
        assert sid != customer["session_id"]
        assert lookup.seen[-1]["history"] == [] and lookup.seen[-1]["customer_context"] == ""
        with lookup.engine.begin() as connection:
            for table in (lookup.sessions.sessions, lookup.sessions.conversations):
                connection.execute(update(table).values(expires_at=datetime.now(UTC) - timedelta(days=5)))
        # Standalone cleanup must preserve both durable scopes, and cannot load the shared session.
        assert (await client.post("/api/v1/copilot/query", json={"query": "VF 6?", "customer_context": "Thông tin thủ công"})).status_code == 200
        assert (await client.get(f"/api/v1/copilot/sessions/{sid}")).status_code == 404
        assert (await client.delete(f"/api/v1/copilot/sessions/{sid}")).status_code == 404
        assert (await client.post("/api/v1/copilot/query", json={"query": "VF 5?", "session_id": sid})).status_code == 404
        lookup.app.state.copilot_sessions = SQLCopilotSessionsRepository("sqlite://", engine=lookup.engine)
        page = (await client.get(PATH)).json()
        assert page["session_id"] == sid and len(page["messages"]) == 2
        assert (await client.get(old)).json()["session_id"] == customer["session_id"]
        follow = await client.post(PATH, json={"query": "Thế còn VF 5?"})
        assert follow.status_code == 200 and follow.json()["session_id"] == sid


def test_shared_history_pagination_has_no_customer_messages(lookup):
    sid = lookup.sessions.advisor_session("sales-a", create=True)
    for number in range(12):
        stored = lookup.sessions.load(sid, "sales-a", advisor=True)
        lookup.sessions.save(sid, "sales-a", [], "", stored["revision"], advisor=True, rich_turn={
            "request_id": f"{number:032x}", "user_query": f"Query {number}", "response_data": final_response().model_dump(),
        })
    newest = lookup.sessions.advisor_history("sales-a")
    older = lookup.sessions.advisor_history("sales-a", before_seq=newest["next_before_seq"])
    assert [message["seq"] for message in older["messages"] + newest["messages"]] == list(range(1, 25))
    assert older["next_before_seq"] is None
    assert lookup.sessions.advisor_history("sales-b")["messages"] == []


@pytest.mark.asyncio
async def test_concurrent_shared_questions_conflict_without_overwriting(lookup, monkeypatch):
    ready, arrived = asyncio.Event(), 0

    async def graph(state, **kwargs):
        nonlocal arrived
        arrived += 1
        if arrived == 2:
            ready.set()
        await ready.wait()
        return {"final_response": final_response()}

    monkeypatch.setattr(copilot_query.copilot_agent, "ainvoke", graph)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=lookup.app), base_url="http://test") as client:
        responses = await asyncio.gather(*[
            client.post(PATH, json={"query": f"VF 5 câu {number}?"}) for number in range(2)
        ])
        assert sorted(response.status_code for response in responses) == [200, 409]
        assert len((await client.get(PATH)).json()["messages"]) == 2
    with lookup.engine.connect() as connection:
        assert len(connection.execute(select(lookup.sessions.advisor_sessions)).all()) == 1
    assert lookup.app.state.copilot_admission.active == {}
