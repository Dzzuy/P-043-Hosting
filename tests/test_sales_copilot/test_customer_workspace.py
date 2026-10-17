"""Isolated regression checks for the database-backed customer workspace."""

import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from src.api.sales_copilot import get_current_user, router
from src.integrations.sales_copilot_repository import SQLSalesCopilotRepository
from src.models.auth import AuthenticatedUser
from src.models.sales_copilot import CustomerProfileSnapshot, LeadStatus, SalesPreferences
from src.services.sales_conversation_service import SalesConversationService


@pytest.fixture
def workspace():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    repository = SQLSalesCopilotRepository("sqlite://", engine=engine)
    repository.ensure_schema()
    service = SalesConversationService(repository)
    app = FastAPI()
    app.state.sales_conversation_service = service
    app.state.sales_copilot_repository = repository

    async def user():
        return AuthenticatedUser(user_id="workspace_advisor", username="workspace", display_name="Workspace", role="advisor")

    app.dependency_overrides[get_current_user] = user
    app.include_router(router, prefix="/api/v1")
    with TestClient(app) as client:
        yield repository, service, client
    engine.dispose()


def make_conversation(repo, number=1):
    customer_id = repo.create_customer(name=f"Khách {number}", advisor_id="workspace_advisor")
    conversation_id = repo.get_or_create_conversation(customer_id)
    repo.add_message(conversation_id, "customer", f"Cần tư vấn VF {number}")
    return customer_id, conversation_id


def test_sales_stage_survives_ai_reanalysis_and_can_be_reset(workspace):
    repo, service, client = workspace
    customer_id, conversation_id = make_conversation(repo)
    _, other_id = make_conversation(repo, 2)
    repo.save_lead_score(LeadStatus(customer_id=customer_id, stage="considering", score=65, rationale="Cần so sánh xe"))
    result = client.patch(f"/api/v1/sales-copilot/conversations/{conversation_id}/lead-stage",
                          json={"stage": "appointment", "reason": "Khách đã hẹn xem xe"})
    assert result.status_code == 200
    assert result.json()["stage_source"] == "sales"
    assert result.json()["score"] == 65
    repo.save_lead_score(LeadStatus(customer_id=customer_id, stage="negotiating", score=75))
    lead = service.get_conversation_details(conversation_id).lead_status
    assert lead["stage"] == "appointment"
    assert lead["ai_stage"] == "negotiating"
    assert lead["score"] == 75
    assert service.get_conversation_details(other_id).lead_status.get("stage") is None
    listed = {item["conversation_id"]: item for item in service.list_advisor_conversations("workspace_advisor")}
    assert listed[conversation_id]["lead_stage"] == "appointment"
    reset = client.patch(f"/api/v1/sales-copilot/conversations/{conversation_id}/lead-stage", json={"stage": None})
    assert reset.json()["stage"] == "negotiating"
    assert reset.json()["stage_source"] == "ai"
    assert service.list_advisor_conversations("workspace_advisor")[0]["lead_stage"] in {"new", "negotiating"}


def test_stage_update_validates_input_and_missing_conversation(workspace):
    repo, _, client = workspace
    _, conversation_id = make_conversation(repo)
    assert client.patch(f"/api/v1/sales-copilot/conversations/{conversation_id}/lead-stage", json={"stage": "unknown"}).status_code == 422
    assert client.patch("/api/v1/sales-copilot/conversations/missing/lead-stage", json={"stage": "appointment"}).status_code == 404


def test_memory_tracks_messages_actually_analyzed_not_generation_finish_time(workspace, monkeypatch):
    from src.services.sales_copilot_analyzer import SalesCopilotAnalyzer

    repo, service, _ = workspace
    _, conversation_id = make_conversation(repo)
    analyzer = SalesCopilotAnalyzer(repo)

    async def analyze(_):
        repo.add_message(conversation_id, "customer", "Tin mới trong lúc AI đang chạy")
        original_id = repo.list_messages(conversation_id)[0].id
        return {"profile": {"usage_purpose": "Đi làm", "facts": [
            {"field": "usage_purpose", "value": "Đi làm", "source_message_ids": [original_id, "other-conversation"]},
        ]}, "memory": {"quick_summary": "Nhu cầu cũ", "timeline": [
            {"title": "Nhu cầu", "description": "Đi làm", "source_message_id": original_id},
            {"title": "Sai nguồn", "description": "Khác", "source_message_id": "other-conversation"},
        ]}}

    monkeypatch.setattr(analyzer, "_call_llm_analysis", analyze)
    asyncio.run(analyzer.analyze_conversation(conversation_id, "workspace_advisor"))
    detail = service.get_conversation_details(conversation_id)
    assert detail.memory["analyzed_through_seq"] == 1
    assert detail.messages[-1].seq == 2
    assert detail.profile["facts"][0]["source_message_ids"] == [detail.messages[0].id]
    assert detail.memory["timeline"][1]["source_message_id"] is None
    # A legacy memory write must not inherit a cursor from a different version.
    repo.save_memory(conversation_id, "Cũ", "", [], [], [])
    assert repo.get_memory(conversation_id)["analyzed_through_seq"] is None


def test_customer_intelligence_uses_one_analysis_and_resolution_needs_customer_source(workspace, monkeypatch):
    from src.services.sales_copilot_analyzer import SalesCopilotAnalyzer

    repo, service, _ = workspace
    _, conversation_id = make_conversation(repo)
    sales = repo.add_message(conversation_id, "sales", "Đã giải thích phương án vay")
    customer = repo.add_message(conversation_id, "customer", "Tôi đã hiểu phương án vay")
    analyzer = SalesCopilotAnalyzer(repo)
    calls = []

    async def analyze(transcript):
        calls.append(transcript)
        return {"profile": {"budget_vnd": 300000000}, "memory": {
            "quick_summary": "Khách mua xe với ngân sách 300 triệu.",
            "detailed_summary": "Đã tư vấn phương án vay, khách xác nhận đã hiểu.",
            "timeline": [
                {"title": "Tư vấn vay", "description": "Đã tư vấn", "event_type": "consulted", "source_message_id": sales.id},
                {"title": "Khách xác nhận", "description": "Đã giải quyết", "event_type": "resolved", "source_message_id": customer.id},
                {"title": "Sales trả lời", "description": "Chưa có xác nhận", "event_type": "resolved", "source_message_id": sales.id},
            ], "pending_items": ["Chờ hồ sơ vay"], "key_promises": ["Sales gửi bảng tính"],
        }}

    monkeypatch.setattr(analyzer, "_call_llm_analysis", analyze)
    result = asyncio.run(analyzer.analyze_conversation(conversation_id, "workspace_advisor"))
    assert len(calls) == 1
    detail = service.get_conversation_details(conversation_id)
    assert detail.profile["budget_vnd"] == 300000000
    assert detail.memory["detailed_summary"] == result["memory"]["detailed_summary"]
    assert [event["event_type"] for event in detail.memory["timeline"]] == ["consulted", "resolved", "general"]
    assert result["memory"]["timeline"] == detail.memory["timeline"]
    assert detail.memory["pending_items"] == ["Chờ hồ sơ vay"]


def test_concise_intelligence_round_trips_with_evidence_and_legacy_dashboard_data(workspace, monkeypatch):
    from src.services.sales_copilot_analyzer import SalesCopilotAnalyzer

    repo, service, _ = workspace
    _, conversation_id = make_conversation(repo)
    sales = repo.add_message(conversation_id, "sales", "Tôi gửi bảng tính chiều nay")
    customer = repo.add_message(conversation_id, "customer", "Tôi chọn VF 6, còn điểm sạc thế nào?")
    analyzer = SalesCopilotAnalyzer(repo)

    async def analyze(_):
        return {"profile": {"interested_models": ["VF 6"]}, "memory": {
            "quick_summary": "Khách chọn VF 6, đang tìm hiểu điểm sạc.",
            "pending_items": ["Kiểm tra điểm sạc"], "customer_intelligence": {
                "key_points": [
                    {"topic": "Sạc", "answer": "Cũ", "status": "answered", "source_message_ids": [sales.id]},
                    {"topic": "SẠC.", "question": "Điểm sạc thế nào?", "status": "open", "source_message_ids": [customer.id, "outside"]},
                ],
                "outcomes": [
                    {"text": "Khách chọn VF 6", "source_message_ids": [customer.id]},
                    {"text": "Khách chọn VF 6.", "source_message_ids": [customer.id]},
                    {"text": "Sales đề xuất đã chốt", "source_message_ids": [sales.id]},
                ],
                "commitments": [
                    {"actor": "Sales", "action": "Gửi bảng tính", "time": "Chiều nay", "source_message_ids": [sales.id]},
                    {"action": "Hứa không có nguồn", "source_message_ids": ["outside"]},
                ],
            },
        }}

    monkeypatch.setattr(analyzer, "_call_llm_analysis", analyze)
    result = asyncio.run(analyzer.analyze_conversation(conversation_id, "workspace_advisor"))
    memory = service.get_conversation_details(conversation_id).memory
    intelligence = memory["customer_intelligence"]
    assert intelligence == result["memory"]["customer_intelligence"]
    assert len(intelligence["key_points"]) == 1
    assert intelligence["key_points"][0]["source_message_ids"] == [customer.id]
    assert len(intelligence["outcomes"]) == 1
    assert len(intelligence["commitments"]) == 1
    assert memory["pending_items"] == ["Kiểm tra điểm sạc", "Điểm sạc thế nào?"]
    assert memory["key_promises"] == ["Sales — Gửi bảng tính — Chiều nay"]
    assert service.get_conversation_details(conversation_id).tasks == []
    repo.save_memory(conversation_id, "Bản cũ", "", [], [], [])
    assert repo.get_memory(conversation_id)["customer_intelligence"] is None


def test_generated_draft_keeps_original_message_cursor(workspace, monkeypatch):
    from src.services.sales_copilot_assistant import SalesCopilotAssistant

    repo, _, _ = workspace
    _, conversation_id = make_conversation(repo)
    repo.update_preferences(SalesPreferences(advisor_id="workspace_advisor", draft_enabled=True))
    assistant = SalesCopilotAssistant(repo)

    def no_retrieval():
        raise RuntimeError("No external retrieval in this test")

    async def draft(*_):
        repo.add_message(conversation_id, "customer", "Thêm câu hỏi khi bản nháp đang được tạo")
        return {"text": "Cần kiểm tra thêm thông tin", "sources": []}

    monkeypatch.setattr("src.services.sales_copilot_assistant.get_retrieval_service", no_retrieval)
    monkeypatch.setattr(assistant, "_call_llm_draft", draft)
    response = asyncio.run(assistant.generate_message_draft(conversation_id, "workspace_advisor"))
    assert response.based_on_message_seq == 1
    assert response.generated_at.tzinfo is not None
    assert repo.get_latest_recommendation(conversation_id, "draft")["based_on_message_seq"] == 1


@pytest.mark.parametrize("customer_count", [3, 20])
def test_list_query_count_does_not_grow_with_customers(workspace, customer_count):
    repo, service, _ = workspace
    for number in range(customer_count):
        make_conversation(repo, number)
    selects = []

    def count(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(repo.engine, "before_cursor_execute", count)
    try:
        result = service.list_advisor_conversations("workspace_advisor")
    finally:
        event.remove(repo.engine, "before_cursor_execute", count)
    assert len(result) == customer_count
    assert len(selects) == 5


def test_list_uses_stored_snapshot_and_latest_sequence(workspace):
    repo, _, client = workspace
    customer_id, conversation_id = make_conversation(repo)
    repo.save_facts_and_snapshot(customer_id, [], CustomerProfileSnapshot(interested_models=["VF 6"], budget_vnd=700_000_000))
    repo.add_message(conversation_id, "sales", "Tin tư vấn mới nhất", sent_at=datetime(2020, 1, 1, tzinfo=UTC))
    response = client.get("/api/v1/sales-copilot/conversations")
    assert response.status_code == 200
    row = response.json()[0]
    assert row["conversation_id"] == conversation_id
    assert row["interested_models"] == ["VF 6"]
    assert row["budget_vnd"] == 700_000_000
    assert row["last_message"] == "Tin tư vấn mới nhất"


def test_detail_reuses_one_connection_and_preserves_all_sections(workspace):
    repo, service, _ = workspace
    customer_id, conversation_id = make_conversation(repo)
    repo.save_facts_and_snapshot(customer_id, [], CustomerProfileSnapshot(interested_models=["VF 6"], budget_vnd=700_000_000))
    repo.save_memory(conversation_id, "Tóm tắt", "Chi tiết", [], ["Hỏi giá"], ["Gửi báo giá"])
    repo.save_lead_score(LeadStatus(customer_id=customer_id, stage="considering", score=65))
    repo.save_recommendation_or_draft(conversation_id, "lead_stage_override", {"stage": "appointment"})
    task = service.create_followup_task(conversation_id, "workspace_advisor", title="Gửi báo giá")
    expected_messages = repo.list_messages(conversation_id)
    expected_memory = repo.get_memory(conversation_id)
    checkouts, checkins, statements = [], [], []

    def checkout(*args):
        checkouts.append(True)

    def checkin(*args):
        checkins.append(True)

    def count(conn, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(repo.engine.pool, "checkout", checkout)
    event.listen(repo.engine.pool, "checkin", checkin)
    event.listen(repo.engine, "before_cursor_execute", count)
    try:
        detail = service.get_conversation_details(conversation_id)
    finally:
        event.remove(repo.engine.pool, "checkout", checkout)
        event.remove(repo.engine.pool, "checkin", checkin)
        event.remove(repo.engine, "before_cursor_execute", count)
    assert len(checkouts) == len(checkins) == 1
    assert len(statements) == 3 and all(sql.lstrip().upper().startswith("SELECT") for sql in statements)
    assert detail.messages == expected_messages
    assert detail.profile["budget_vnd"] == 700_000_000
    assert detail.memory == expected_memory
    assert detail.tasks[0]["id"] == task["id"]
    assert detail.lead_status["stage"] == "appointment"
    assert detail.lead_status["ai_stage"] == "considering"


def test_detail_releases_borrowed_connection_after_a_query_failure(workspace):
    repo, service, _ = workspace
    _, conversation_id = make_conversation(repo)
    returned = []

    def fail(conn, cursor, statement, parameters, context, many):
        if "FROM copilot_chat_messages" in statement:
            raise RuntimeError("Database read failed")

    def checkin(*args):
        returned.append(True)

    event.listen(repo.engine, "before_cursor_execute", fail)
    event.listen(repo.engine.pool, "checkin", checkin)
    try:
        with pytest.raises(RuntimeError, match="Database read failed"):
            service.get_conversation_details(conversation_id)
        assert len(returned) == 1
    finally:
        event.remove(repo.engine, "before_cursor_execute", fail)
        event.remove(repo.engine.pool, "checkin", checkin)
    assert service.get_conversation_details(conversation_id).messages
    assert service.get_conversation_details("missing") is None


def test_empty_database_does_not_create_synthetic_customers(workspace, monkeypatch):
    _, service, client = workspace

    def no_seed(*args, **kwargs):
        pytest.fail("Reading customers must not seed synthetic conversations")

    monkeypatch.setattr(service, "seed_real_conversations_from_docx", no_seed)
    assert client.get("/api/v1/sales-copilot/conversations").json() == []


def test_manual_task_is_persisted_to_the_selected_customer(workspace):
    repo, _, client = workspace
    customer_id, conversation_id = make_conversation(repo)
    _, other_id = make_conversation(repo, 2)
    response = client.post(f"/api/v1/sales-copilot/conversations/{conversation_id}/tasks", json={"title": "  Gửi phương án trả góp  ", "priority": "high", "starts_at": "2026-10-16T08:00:00+07:00", "ends_at": "2026-10-16T09:00:00+07:00"})
    assert response.status_code == 201
    task = response.json()
    assert task["customer_id"] == customer_id
    assert task["owner_sales_id"] == "workspace_advisor"
    assert task["title"] == "Gửi phương án trả góp"
    assert task["due_at"] is None
    details = client.get(f"/api/v1/sales-copilot/conversations/{conversation_id}").json()
    assert details["tasks"][0]["id"] == task["id"]
    assert client.get(f"/api/v1/sales-copilot/conversations/{other_id}").json()["tasks"] == []
    assert client.patch(f"/api/v1/sales-copilot/tasks/{task['id']}", json={"status": "completed"}).status_code == 200
    assert repo.list_tasks_for_customer(customer_id)[0]["status"] == "completed"


@pytest.mark.parametrize("payload", [{"title": "   "}, {"title": "Tư vấn", "priority": "invalid"}])
def test_invalid_tasks_are_rejected(workspace, payload):
    repo, _, client = workspace
    customer_id, conversation_id = make_conversation(repo)
    assert client.post(f"/api/v1/sales-copilot/conversations/{conversation_id}/tasks", json=payload).status_code == 422
    assert repo.list_tasks_for_customer(customer_id) == []


def test_task_unknown_conversation_is_404(workspace):
    _, _, client = workspace
    assert client.post("/api/v1/sales-copilot/conversations/missing/tasks", json={"title": "Tư vấn"}).status_code == 404


def test_saved_draft_is_a_read_without_an_assistant(workspace):
    repo, _, client = workspace
    _, conversation_id = make_conversation(repo)
    url = f"/api/v1/sales-copilot/conversations/{conversation_id}/draft"
    assert client.get(url).json() is None
    repo.save_recommendation_or_draft(conversation_id, "draft", {"text": "Bản nháp đã lưu", "conversation_id": conversation_id})
    assert client.get(url).json()["text"] == "Bản nháp đã lưu"


def test_send_message_is_persisted_without_reloading_other_customers(workspace):
    repo, _, client = workspace
    _, conversation_id = make_conversation(repo)
    _, other_id = make_conversation(repo, 2)
    response = client.post(f"/api/v1/sales-copilot/conversations/{conversation_id}/messages", json={"content": "Tin đã lưu trong DB", "sender_role": "sales"})
    assert response.status_code == 200
    message = response.json()
    assert repo.list_messages(conversation_id)[-1].id == message["id"]
    assert len(repo.list_messages(other_id)) == 1


def test_unassigned_advisor_does_not_see_another_advisors_customers(workspace):
    repo, service, client = workspace
    customer = repo.create_customer(name="Khách của sales khác", advisor_id="someone-else")
    repo.get_or_create_conversation(customer)
    assert service.list_advisor_conversations("workspace_advisor") == []
    assert repo.list_customers_for_advisor("workspace_advisor") == []
    assert client.get("/api/v1/sales-copilot/conversations").json() == []


def test_customer_reads_and_mutations_cannot_cross_advisors(workspace):
    repo, service, client = workspace
    customer = repo.create_customer(name="Khách riêng", advisor_id="someone-else")
    conversation = repo.get_or_create_conversation(customer)
    task = service.create_followup_task(conversation, "someone-else", title="Việc riêng")
    base = f"/api/v1/sales-copilot/conversations/{conversation}"
    calls = [
        ("GET", base, None), ("GET", base + "/draft", None),
        ("POST", base + "/messages", {"sender_role": "sales", "content": "Không được ghi"}),
        ("POST", base + "/tasks", {"title": "Không được tạo"}),
        ("POST", base + "/analyze", None), ("POST", base + "/draft", None),
        ("POST", base + "/recommendations", None),
        ("PATCH", base + "/lead-stage", {"stage": "appointment"}),
        ("PATCH", f"/api/v1/sales-copilot/tasks/{task['id']}", {"status": "completed"}),
    ]
    for method, path, payload in calls:
        assert client.request(method, path, json=payload).status_code == 404
    assert repo.list_messages(conversation) == []
    assert repo.list_tasks_for_customer(customer)[0]["status"] == "pending"


def test_crm_has_no_demo_identity_fallback(workspace):
    from fastapi import HTTPException

    _, _, client = workspace
    app = client.app
    app.dependency_overrides.pop(get_current_user)

    async def expired(request):
        raise HTTPException(status_code=401, detail="Authentication required.")

    app.state.current_user = expired
    assert client.get("/api/v1/sales-copilot/conversations").status_code == 401

    async def manager(request):
        return AuthenticatedUser(user_id="manager", username="manager", display_name="Manager", role="manager")

    app.state.current_user = manager
    assert client.get("/api/v1/sales-copilot/conversations").status_code == 403


def test_list_database_work_runs_outside_event_loop(workspace, monkeypatch):
    _, service, client = workspace

    def list_in_worker(advisor_id):
        with pytest.raises(RuntimeError, match="no running event loop"):
            asyncio.get_running_loop()
        return []

    monkeypatch.setattr(service, "list_advisor_conversations", list_in_worker)
    assert client.get("/api/v1/sales-copilot/conversations").status_code == 200


def test_bounded_message_pages_and_old_sources_remain_scoped_to_conversation(workspace):
    repo, service, client = workspace
    _, conversation = make_conversation(repo)
    _, other = make_conversation(repo, 2)
    for number in range(79):
        repo.add_message(conversation, "sales", f"Tin {number}")
    base = f"/api/v1/sales-copilot/conversations/{conversation}"
    detail = client.get(base + "?message_limit=30").json()
    assert len(detail["messages"]) == 30
    assert detail["message_total"] == detail["last_message_seq"] == 80
    assert detail["next_before_seq"] == 51
    page = client.get(base + "/messages?before_seq=51").json()
    assert [message["seq"] for message in page["messages"]] == list(range(21, 51))
    source = repo.list_messages(conversation)[0]
    assert client.get(base + f"/messages?source_message_id={source.id}").json()["messages"][0]["id"] == source.id
    foreign_source = repo.list_messages(other)[0]
    assert client.get(base + f"/messages?source_message_id={foreign_source.id}").status_code == 404
    assert client.get(base + "/messages?limit=101").status_code == 422
    assert client.get(base + "/messages?before_seq=0").status_code == 422
    assert len(service.get_conversation_details(conversation).messages) == 80  # legacy API still supports full reads


def test_profile_confirmation_survives_analysis_and_reaches_list_and_lookup(workspace):
    from src.services.customer_lookup_context import build_customer_context

    repo, service, client = workspace
    customer, conversation = make_conversation(repo)
    base = f"/api/v1/sales-copilot/conversations/{conversation}"
    repo.save_facts_and_snapshot(customer, [], CustomerProfileSnapshot(budget_vnd=400, budget_notes="Ngân sách cũ"))
    response = client.patch(base + "/profile-fact", json={"field": "budget_vnd", "value": 700_000_000})
    assert response.status_code == 200
    assert response.json()["budget_vnd"] == 700_000_000
    assert response.json()["budget_notes"] is None
    client.patch(base + "/profile-fact", json={"field": "charging_condition", "value": "Sạc tại nhà"})
    repo.save_facts_and_snapshot(customer, [], CustomerProfileSnapshot(budget_vnd=300, charging_condition="Chưa rõ"))
    profile = service.get_conversation_details(conversation).profile
    assert profile["budget_vnd"] == 700_000_000
    assert profile["charging_condition"] == "Sạc tại nhà"
    assert all(fact["verification_status"] == "confirmed" for fact in profile["facts"])
    assert service.list_advisor_conversations("workspace_advisor")[0]["budget_vnd"] == 700_000_000
    context = build_customer_context(repo, conversation, "workspace_advisor")
    assert "700000000" in context and "Sạc tại nhà" in context and "sales_confirmed_fields" in context
    assert client.patch(base + "/profile-fact", json={"field": "budget_vnd", "value": -1}).status_code == 422
    assert client.patch(base + "/profile-fact", json={"field": "advisor_id", "value": "other"}).status_code == 422


def test_task_edit_and_operational_attention(workspace):
    repo, service, client = workspace
    customer, conversation = make_conversation(repo)
    task = service.create_followup_task(conversation, "workspace_advisor", title="Gọi lại", priority="low")
    service.add_sales_message(conversation, "Đã trả lời")
    assert service.list_advisor_conversations("workspace_advisor")[0]["important_overdue_count"] == 0
    response = client.patch(f"/api/v1/sales-copilot/tasks/{task['id']}", json={
        "title": "Gọi lại đúng hẹn", "priority": "high", "starts_at": "2020-01-01T00:00:00Z", "ends_at": "2020-01-01T01:00:00Z",
    })
    assert response.status_code == 200
    assert repo.list_tasks_for_customer(customer)[0]["title"] == "Gọi lại đúng hẹn"
    assert service.list_advisor_conversations("workspace_advisor")[0]["important_overdue_count"] == 1
    client.patch(f"/api/v1/sales-copilot/tasks/{task['id']}", json={"status": "completed"})
    assert service.list_advisor_conversations("workspace_advisor")[0]["pending_tasks_count"] == 0
    client.patch(f"/api/v1/sales-copilot/tasks/{task['id']}", json={"status": "pending", "starts_at": "2090-01-01T00:00:00Z", "ends_at": "2090-01-01T01:00:00Z"})
    assert service.list_advisor_conversations("workspace_advisor")[0]["important_overdue_count"] == 0
    assert client.patch(f"/api/v1/sales-copilot/tasks/{task['id']}", json={"title": " "}).status_code == 422
    assert client.patch(f"/api/v1/sales-copilot/tasks/{task['id']}", json={}).status_code == 422


def test_new_endpoints_cannot_cross_advisor_ownership(workspace):
    repo, _, client = workspace
    customer = repo.create_customer(name="Riêng tư", advisor_id="other")
    conversation = repo.get_or_create_conversation(customer)
    base = f"/api/v1/sales-copilot/conversations/{conversation}"
    assert client.get(base + "/messages").status_code == 404
    assert client.patch(base + "/profile-fact", json={"field": "usage_purpose", "value": "Không được sửa"}).status_code == 404


def test_ai_tasks_require_enabled_rule_evidence_and_review_without_invented_deadlines(workspace, monkeypatch):
    from types import SimpleNamespace

    from src.services import sales_copilot_analyzer as module

    repo, _, _ = workspace
    customer, conversation = make_conversation(repo)
    message_id = repo.list_messages(conversation)[0].id
    analyzer = module.SalesCopilotAnalyzer(repo)
    enabled = SimpleNamespace(sales_ai_task_rules="")
    monkeypatch.setattr(module, "get_settings", lambda: enabled)

    async def analysis(_):
        return {"profile": {"usage_purpose": "Đi làm"}, "memory": {}, "tasks": [
            {"task_type": "send_quote", "title": "Gửi báo giá đã hẹn", "source_message_ids": [message_id]},
            {"task_type": "send_quote", "title": "Không có bằng chứng", "source_message_ids": ["foreign"]},
            {"task_type": "answer_question", "title": "Câu hỏi cần trả lời ngay", "source_message_ids": [message_id]},
        ]}

    monkeypatch.setattr(analyzer, "_call_llm_analysis", analysis)
    asyncio.run(analyzer.analyze_conversation(conversation, "workspace_advisor"))
    assert repo.list_tasks_for_customer(customer) == []
    enabled.sales_ai_task_rules = "send_quote,answer_question"
    asyncio.run(analyzer.analyze_conversation(conversation, "workspace_advisor"))
    asyncio.run(analyzer.analyze_conversation(conversation, "workspace_advisor"))
    tasks = repo.list_tasks_for_customer(customer)
    assert len(tasks) == 1
    assert tasks[0]["status"] == "needs_review" and tasks[0]["due_at"] is None
    assert tasks[0]["source_message_ids"] == [message_id]
