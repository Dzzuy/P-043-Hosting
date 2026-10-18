"""Isolated customer lookup/session regressions: no real DB or LLM calls."""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from pydantic import SecretStr
from sqlalchemy import create_engine, select, update
from sqlalchemy.exc import OperationalError
from starlette.requests import Request

from src.agents.copilot.runtime import CopilotAdmission, RuntimeBudget
from src.agents.copilot.state import Citation, CopilotResponse
from src.api.copilot import router as standalone_router
from src.api.sales_copilot import router
from src.config import get_settings
from src.integrations.copilot_sessions import SQLCopilotSessionsRepository
from src.integrations.sales_copilot_repository import SQLSalesCopilotRepository
from src.models.copilot import CopilotQueryRequest
from src.models.sales_copilot import CustomerProfileSnapshot
from src.services import copilot_query
from src.services.customer_lookup_context import build_customer_context


def final_response():
    return CopilotResponse(
        status="partial", answer="VF 5 có thông tin đã xác minh [C1]. " * 25,
        citations=[Citation(citation_id="C1", document_id="vf5", chunk_id="vf5_4", title="VF 5",
                            excerpt="Nguồn đã đối chiếu", effective_from="2026-01-01")],
        missing_information=["Nguồn chưa nêu chuẩn NEDC"], reason_code="insufficient_evidence",
        talking_points=["Có thể trao đổi theo nhu cầu khách"], suggested_next_question="Thế còn VF 6?",
    )


@pytest.fixture
def lookup(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "sales_pii_key", SecretStr(Fernet.generate_key().decode()))
    engine = create_engine(f"sqlite:///{tmp_path / 'lookup.db'}", connect_args={"check_same_thread": False})
    sales = SQLSalesCopilotRepository("sqlite://", engine=engine)
    sales.ensure_schema()
    sessions = SQLCopilotSessionsRepository("sqlite://", engine=engine)
    sessions._ensure_schema()
    ids = []
    for number, owner in enumerate(["sales-a", "sales-a", "sales-b"]):
        customer = sales.create_customer(name=f"Khách {number}", advisor_id=owner)
        conversation = sales.get_or_create_conversation(customer)
        ids.append(conversation)
        sales.save_facts_and_snapshot(customer, [], CustomerProfileSnapshot(
            interested_models=["VF 5 Plus"], charging_condition="Có chỗ sạc tại nhà", budget_vnd=500000000,
        ))
        for index in range(12):
            sales.add_message(conversation, "customer" if index % 2 == 0 else "sales", f"Tin {index}: VF 5 Plus")
    app = FastAPI()
    identity = SimpleNamespace(user_id="sales-a", role="advisor")

    async def current_user(request):
        if identity.user_id is None:
            raise HTTPException(status_code=401)
        return identity

    app.state.current_user = current_user
    app.state.sales_copilot_repository = sales
    app.state.copilot_sessions = sessions
    app.state.copilot_admission = CopilotAdmission(get_settings())
    app.state.copilot_readiness = lambda: None
    app.include_router(router, prefix="/api/v1")
    app.include_router(standalone_router, prefix="/api/v1")
    seen = []

    async def graph(state, **kwargs):
        seen.append(state)
        if state.get("progress_queue") is not None:
            state["progress_queue"].put_nowait({"step": "checking", "text": "Đang kiểm chứng nguồn"})
        return {"final_response": final_response()}

    monkeypatch.setattr(copilot_query.copilot_agent, "ainvoke", graph)
    monkeypatch.setattr(copilot_query, "maybe_trigger_background_summarization", lambda **kwargs: None)
    yield SimpleNamespace(app=app, sales=sales, sessions=sessions, ids=ids, identity=identity, seen=seen, engine=engine)
    engine.dispose()


def endpoint(lookup, number=0):
    return f"/api/v1/sales-copilot/conversations/{lookup.ids[number]}/copilot-chat"


@pytest.mark.asyncio
async def test_listed_customer_can_receive_message_and_use_same_advisor_lookup(lookup):
    from src.services.sales_conversation_service import SalesConversationService

    lookup.app.state.sales_conversation_service = SalesConversationService(lookup.sales)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=lookup.app), base_url="http://test") as client:
        cards = (await client.get("/api/v1/sales-copilot/conversations")).json()
        assert {card["conversation_id"] for card in cards} == set(lookup.ids[:2])
        conversation = cards[0]["conversation_id"]
        base = f"/api/v1/sales-copilot/conversations/{conversation}"
        sent = await client.post(base + "/messages", json={"sender_role": "sales", "content": "Tin từ sales đã đăng nhập"})
        assert sent.status_code == 200
        detail = (await client.get(base)).json()
        assert detail["messages"][-1]["id"] == sent.json()["id"]
        assert (await client.get(base + "/copilot-chat")).status_code == 200
        answer = await client.post(base + "/copilot-chat/stream", json={"query": "Giá VF 5 Plus?"})
        assert answer.status_code == 200 and "event: final" in answer.text
        assert len(lookup.seen) == 1 and lookup.seen[0]["history"] == []
        assert "Tin từ sales đã đăng nhập" in lookup.seen[0]["customer_context"]
        lookup.identity.user_id = "unassigned-advisor"
        assert (await client.get("/api/v1/sales-copilot/conversations")).json() == []
        assert (await client.get(base)).status_code == 404
        assert (await client.get(base + "/copilot-chat")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_first_lookup_without_customer_messages_or_ai_history(lookup, stream):
    customer_id = lookup.sales.create_customer(name="Khách chưa nhắn tin", advisor_id="sales-a")
    conversation_id = lookup.sales.get_or_create_conversation(customer_id)
    path = f"/api/v1/sales-copilot/conversations/{conversation_id}/copilot-chat"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=lookup.app), base_url="http://test") as client:
        history = await client.get(path)
        assert history.status_code == 200
        assert history.json() == {"session_id": None, "messages": [], "next_before_seq": None}
        assert lookup.sessions.customer_session("sales-a", conversation_id) is None
        response = await client.post(path + ("/stream" if stream else ""), json={"query": "VF 5 Plus giá bao nhiêu?"})
        assert response.status_code == 200
        if stream:
            assert "event: final" in response.text
        assert len(lookup.seen) == 1 and lookup.seen[0]["history"] == []
        saved = (await client.get(path)).json()
        assert saved["session_id"]
        assert [message["role"] for message in saved["messages"]] == ["user", "assistant"]
        assert saved["messages"][1]["response_data"]["citations"][0]["chunk_id"] == "vf5_4"
        assert lookup.sales.list_messages(conversation_id) == []


@pytest.mark.asyncio
async def test_shared_graph_and_customer_context_are_separate_from_ai_history(lookup, monkeypatch):
    async def no_cache(**kwargs):
        raise AssertionError("Customer lookup must not use the standalone exact cache")
    monkeypatch.setattr(copilot_query.semantic_cache, "get", no_cache)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=lookup.app), base_url="http://test") as client:
        first = await client.post(endpoint(lookup), json={"query": "VF 5 Plus giá thế nào?"})
        assert first.status_code == 200
        data = first.json()
        assert len(data["answer"]) > 500 and data["request_id"] and data["session_id"]
        assert data["query"] == "VF 5 Plus giá thế nào?" and data["answered_at"]
        assert data["citations"][0]["content"] == "Nguồn đã đối chiếu"
        context = lookup.seen[0]["customer_context"]
        assert "Có chỗ sạc tại nhà" in context and "charging_condition" in context
        assert "Tin 3:" not in context and "Tin 4:" in context and "Tin 11:" in context
        assert "Khách hàng" in context and "Tư vấn viên" in context
        assert lookup.seen[0]["history"] == []
        lookup.sales.add_message(lookup.ids[0], "customer", "Tôi chuyển sang VF 6 và không còn chỗ sạc tại nhà.")
        second = await client.post(endpoint(lookup) + "/stream", json={"query": "Thế còn bản Plus?"})
        assert "event: status" in second.text and "Đang kiểm chứng nguồn" in second.text
        assert "event: final" in second.text and "event: done" in second.text
        assert len(lookup.seen) == 2 and len(lookup.seen[1]["history"]) == 2
        assert lookup.seen[1]["history"][0]["content"] == data["query"]
        assert lookup.seen[1]["domain"] == "all" and lookup.seen[1]["target_date"] is None
        assert "Tôi chuyển sang VF 6 và không còn chỗ sạc tại nhà." in lookup.seen[1]["customer_context"]
        # The independent API executes exactly the same graph using the same prepared input.
        standalone = await client.post("/api/v1/copilot/query", json={
            "query": data["query"], "customer_context": context,
        })
        assert standalone.status_code == 200 and len(lookup.seen) == 3
        for field in ("query", "customer_context", "history", "domain", "target_date"):
            assert lookup.seen[0][field] == lookup.seen[2][field]


@pytest.mark.asyncio
async def test_durable_history_metadata_restart_and_legacy_scope(lookup):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=lookup.app), base_url="http://test") as client:
        response = (await client.post(endpoint(lookup), json={"query": "VF 5 Plus?"})).json()
        sid = response["session_id"]
        with lookup.engine.begin() as connection:
            for table in (lookup.sessions.sessions, lookup.sessions.conversations):
                connection.execute(update(table).values(expires_at=datetime.now(UTC) - timedelta(hours=9)))
        # Standalone cleanup cannot purge a durable session, and standalone APIs cannot open it.
        assert (await client.post("/api/v1/copilot/query", json={"query": "VF 6?", "customer_context": "Gara"})).status_code == 200
        assert (await client.get(f"/api/v1/copilot/sessions/{sid}")).status_code == 404
        assert (await client.delete(f"/api/v1/copilot/sessions/{sid}")).status_code == 404
        assert (await client.post("/api/v1/copilot/query", json={"query": "VF 5?", "session_id": sid})).status_code == 404
        assert sid not in [item["session_id"] for item in (await client.get("/api/v1/copilot/sessions")).json()]
        lookup.app.state.copilot_sessions = SQLCopilotSessionsRepository("sqlite://", engine=lookup.engine)
        history = (await client.get(endpoint(lookup))).json()
        assert len(history["messages"]) == 2
        saved = history["messages"][-1]["response_data"]
        for key in ("answer", "status", "reason_code", "missing_information", "talking_points", "request_id", "session_id"):
            assert saved[key] == response[key]
        assert saved["citations"][0]["chunk_id"] == "vf5_4"
        follow = await client.post(endpoint(lookup), json={"query": "Thế còn VF 6?"})
        assert follow.status_code == 200 and follow.json()["session_id"] == sid
        assert len(lookup.seen[-1]["history"]) == 2
        assert (await client.get(endpoint(lookup, 1))).json()["messages"] == []


@pytest.mark.asyncio
async def test_auth_ownership_and_query_validation_before_graph(lookup):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=lookup.app), base_url="http://test") as client:
        for path in (endpoint(lookup, 2), endpoint(lookup, 2) + "/stream"):
            assert (await client.post(path, json={"query": "VF 5?"})).status_code == 404
        assert (await client.get(endpoint(lookup, 2))).status_code == 404
        for query in (" ", "x", "x" * 4001):
            assert (await client.post(endpoint(lookup), json={"query": query})).status_code == 422
        assert not lookup.seen
        lookup.identity.user_id = None
        assert (await client.get(endpoint(lookup))).status_code == 401
        assert (await client.post(endpoint(lookup) + "/stream", json={"query": "VF 5?"})).status_code == 401
        lookup.identity.user_id, lookup.identity.role = "sales-a", "manager"
        assert (await client.post(endpoint(lookup), json={"query": "VF 5?"})).status_code == 403


def test_pagination_has_stable_sequences_and_keeps_all_rich_metadata(lookup):
    assert lookup.sessions.customer_history("sales-a", lookup.ids[0])["session_id"] is None
    sid = lookup.sessions.customer_session("sales-a", lookup.ids[0], create=True)
    assert lookup.sessions.customer_session("sales-a", lookup.ids[0], create=True) == sid
    for number in range(12):
        stored = lookup.sessions.load(sid, "sales-a", customer_conversation_id=lookup.ids[0])
        lookup.sessions.save(sid, "sales-a", [], "", stored["revision"], customer_conversation_id=lookup.ids[0], rich_turn={
            "request_id": f"{number:032x}", "user_query": f"Query {number}", "response_data": final_response().model_dump(),
        })
    newest = lookup.sessions.customer_history("sales-a", lookup.ids[0])
    older = lookup.sessions.customer_history("sales-a", lookup.ids[0], before_seq=newest["next_before_seq"])
    assert len(newest["messages"]) == 20 and len(older["messages"]) == 4
    assert [item["seq"] for item in older["messages"] + newest["messages"]] == list(range(1, 25))
    assert older["next_before_seq"] is None


@pytest.mark.asyncio
async def test_provider_and_save_failure_never_emit_or_persist_a_success(lookup, monkeypatch):
    async def broken(state, **kwargs):
        raise copilot_query.CopilotDependencyError("private provider detail")
    monkeypatch.setattr(copilot_query.copilot_agent, "ainvoke", broken)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=lookup.app), base_url="http://test") as client:
        stream = await client.post(endpoint(lookup) + "/stream", json={"query": "VF 5?"})
        assert "event: error" in stream.text and "event: final" not in stream.text and "event: delta" not in stream.text
        assert "private provider detail" not in stream.text
        assert (await client.get(endpoint(lookup))).json()["messages"] == []
        async def graph(state, **kwargs):
            return {"final_response": final_response()}
        monkeypatch.setattr(copilot_query.copilot_agent, "ainvoke", graph)
        def save_failure(*args, **kwargs):
            raise OperationalError(None, None, RuntimeError("private database detail"))
        monkeypatch.setattr(lookup.sessions, "save", save_failure)
        stream = await client.post(endpoint(lookup) + "/stream", json={"query": "VF 5?"})
        assert "event: error" in stream.text and "event: final" not in stream.text
        assert "private database detail" not in stream.text
        assert (await client.get(endpoint(lookup))).json()["messages"] == []
    assert lookup.app.state.copilot_admission.active == {}


@pytest.mark.asyncio
async def test_concurrent_questions_do_not_overwrite_or_duplicate_session(lookup, monkeypatch):
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
            client.post(endpoint(lookup), json={"query": f"VF 5 câu {number}?"}) for number in range(2)
        ])
        assert sorted(response.status_code for response in responses) == [200, 409]
        assert len((await client.get(endpoint(lookup))).json()["messages"]) == 2
    with lookup.engine.connect() as connection:
        assert len(connection.execute(select(lookup.sessions.lookup_sessions)).all()) == 1
    assert lookup.app.state.copilot_admission.active == {}


@pytest.mark.asyncio
async def test_disconnect_and_deadline_cancel_worker_and_release_admission(lookup, monkeypatch):
    started, cancelled = asyncio.Event(), asyncio.Event()
    async def slow(state, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    monkeypatch.setattr(copilot_query.copilot_agent, "ainvoke", slow)
    request = Request({"type": "http", "app": lookup.app, "headers": [], "state": {}})
    response = await copilot_query.run_copilot_request(
        CopilotQueryRequest(query="VF 5?"), request, lookup.identity, stream=True,
        customer_conversation_id=lookup.ids[0],
    )
    await anext(response.body_iterator)
    await asyncio.wait_for(started.wait(), 2)
    await response.body_iterator.aclose()
    assert cancelled.is_set() and lookup.app.state.copilot_admission.active == {}
    assert lookup.sessions.customer_history("sales-a", lookup.ids[0])["messages"] == []
    monkeypatch.setattr(copilot_query.RuntimeBudget, "create", lambda settings: RuntimeBudget(time.monotonic() + .2))
    response = await copilot_query.run_copilot_request(CopilotQueryRequest(query="VF 5?"), request, lookup.identity, stream=True)
    body = "".join([item async for item in response.body_iterator])
    assert "event: error" in body and "event: final" not in body
    assert lookup.app.state.copilot_admission.active == {}


def test_large_context_is_bounded_and_keeps_latest_customer_update(lookup):
    lookup.sales.add_message(lookup.ids[0], "customer", "X" * 8000 + " Tôi đã có gara và muốn chuyển sang VF 6.")
    context = build_customer_context(lookup.sales, lookup.ids[0], "sales-a")
    assert len(context) <= 6000 and "rút gọn" in context
    assert "Tôi đã có gara và muốn chuyển sang VF 6." in context


def test_summary_reads_durable_messages_by_real_sequence(lookup):
    sid = lookup.sessions.customer_session("sales-a", lookup.ids[0], create=True)
    for number in range(5):
        lookup.sessions.save(sid, "sales-a", [], "", number, customer_conversation_id=lookup.ids[0], rich_turn={
            "user_query": str(number), "response_data": final_response().model_dump(),
        })
    batch = lookup.sessions.summary_batch(sid, after_seq=2, through_seq=6)
    assert [row["seq"] for row in batch] == [3, 4, 5, 6]


@pytest.mark.asyncio
async def test_database_failure_before_streaming_is_503_and_releases_admission(lookup, monkeypatch):
    def unavailable(*args, **kwargs):
        raise OperationalError(None, None, RuntimeError("private database detail"))
    monkeypatch.setattr(lookup.sales, "owned_conversation", unavailable)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=lookup.app), base_url="http://test") as client:
        for path in (endpoint(lookup), endpoint(lookup) + "/stream"):
            response = await client.post(path, json={"query": "VF 5?"})
            assert response.status_code == 503 and "private database detail" not in response.text
        assert (await client.get(endpoint(lookup))).status_code == 503
    assert not lookup.seen and lookup.app.state.copilot_admission.active == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_on", ["http.response.start", "http.response.body"])
async def test_socket_failure_before_or_during_body_releases_admission(lookup, fail_on):
    scope = {"type": "http", "method": "POST", "path": "/", "app": lookup.app,
             "headers": [], "state": {}, "asgi": {"spec_version": "2.4"}}
    response = await copilot_query.run_copilot_request(
        CopilotQueryRequest(query="VF 5?"), Request(scope), lookup.identity,
        stream=True, customer_conversation_id=lookup.ids[0],
    )
    async def send(message):
        if message["type"] == fail_on:
            raise OSError("socket closed")
    async def receive():
        await asyncio.Event().wait()
    from starlette.requests import ClientDisconnect
    with pytest.raises(ClientDisconnect):
        await response(scope, receive, send)
    assert lookup.app.state.copilot_admission.active == {}
    assert lookup.sessions.customer_history("sales-a", lookup.ids[0])["messages"] == []
