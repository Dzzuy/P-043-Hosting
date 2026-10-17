"""Agenda behavior on an isolated DB: access, time zones, aggregates, migration compatibility."""
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, insert, select, update
from sqlalchemy.pool import StaticPool

from src.api.sales_copilot import get_current_user, router
from src.integrations.sales_copilot_repository import SQLSalesCopilotRepository
from src.models.auth import AuthenticatedUser
from src.models.sales_copilot import CustomerProfileSnapshot, FollowupTask, LeadStatus
from src.services.sales_agenda_service import SalesAgendaService
from src.services.sales_conversation_service import SalesConversationService

OWNER = "agenda-sales"
NOW = datetime(2026, 10, 16, 2, tzinfo=UTC)  # Friday, 09:00 Vietnam.
INTERVAL = {"starts_at": "2026-10-16T09:00:00+07:00", "ends_at": "2026-10-16T10:00:00+07:00"}


@pytest.fixture
def agenda():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    repo = SQLSalesCopilotRepository("sqlite://", engine=engine)
    repo.ensure_schema()
    app = FastAPI()
    app.state.sales_copilot_repository = repo
    app.state.sales_conversation_service = SalesConversationService(repo)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(user_id=OWNER, username=OWNER, display_name="Sales", role="advisor")
    app.include_router(router, prefix="/api/v1")
    with TestClient(app) as client:
        yield repo, SalesAgendaService(repo), client
    engine.dispose()


def task(repo, *, customer=None, conversation=None, owner=OWNER, **values):
    payload = FollowupTask(customer_id=customer, conversation_id=conversation, owner_sales_id=owner,
        task_type="manual_follow_up", title="Một việc", description="", **values)
    repo.save_tasks([payload])
    with repo.engine.connect() as conn:
        return conn.execute(select(repo.tasks.c.id).order_by(repo.tasks.c.created_at.desc()).limit(1)).scalar_one()


def test_exact_personal_scope_and_legacy_tasks_are_not_auto_scheduled(agenda):
    repo, service, _ = agenda
    customer = repo.create_customer(name="Được giao", advisor_id=OWNER)
    conversation = repo.get_or_create_conversation(customer)
    for _ in range(6):
        task(repo, customer=customer, conversation=conversation, due_at=NOW)
    for _ in range(5):
        task(repo, customer=customer, conversation=conversation, owner="another-sales", due_at=NOW)
    alien = repo.create_customer(name="Ngoài phạm vi", advisor_id="another-sales")
    task(repo, customer=alien, owner=OWNER)
    data = service.dashboard(OWNER, work_filter="unscheduled", now=NOW)
    assert data["kpis"]["total_tasks"] == 6
    assert data["unscheduled"]["total"] == 6
    assert len(data["work_items"]["items"]) == 6
    assert not service.calendar(OWNER, date(2026, 10, 16))["items"]
    with repo.engine.connect() as conn:
        assert conn.execute(select(repo.tasks.c.due_at).limit(1)).scalar() is not None


@pytest.mark.parametrize("changes", [{}, {"starts_at": INTERVAL["starts_at"]},
    {"starts_at": "2026-10-16T10:00:00+07:00", "ends_at": "2026-10-16T09:00:00+07:00"},
    {"starts_at": "2026-10-16T09:00:00", "ends_at": "2026-10-16T10:00:00"},
    {"starts_at": INTERVAL["starts_at"], "ends_at": INTERVAL["starts_at"]}])
def test_new_tasks_require_valid_aware_interval(agenda, changes):
    _, _, client = agenda
    assert client.post("/api/v1/sales-copilot/tasks", json={"title": "Việc mới", **changes}).status_code == 422


def test_personal_creation_edit_overlap_and_other_owner_are_private(agenda):
    repo, service, client = agenda
    response = client.post("/api/v1/sales-copilot/tasks", json={"title": "Họp", "item_type": "appointment", **INTERVAL})
    assert response.status_code == 201
    item = response.json()
    assert item["customer_id"] is None and item["conversation_id"] is None
    assert item["starts_at"] == "2026-10-16T02:00:00+00:00"
    assert service.dashboard(OWNER, now=NOW)["kpis"]["today_events"] == 1
    assert len(service.overlaps(OWNER, NOW, datetime(2026, 10, 16, 3, tzinfo=UTC))) == 1
    assert not service.overlaps(OWNER, NOW, datetime(2026, 10, 16, 3, tzinfo=UTC), item["id"])
    assert not service.calendar("other", date(2026, 10, 16))["items"]
    other_id = task(repo, owner="other")
    assert client.patch(f"/api/v1/sales-copilot/tasks/{other_id}", json={"status": "completed"}).status_code == 404
    assert client.patch(f"/api/v1/sales-copilot/tasks/{item['id']}", json={"ends_at": "2026-10-16T01:00:00Z"}).status_code == 422
    assert client.patch(f"/api/v1/sales-copilot/tasks/{item['id']}", json={"starts_at": None, "ends_at": None}).status_code == 422
    client.patch(f"/api/v1/sales-copilot/tasks/{item['id']}", json={"status": "completed"})
    assert service.dashboard(OWNER, now=NOW)["kpis"]["today_events"] == 0
    assert service.calendar(OWNER, date(2026, 10, 16))["items"][0]["status"] == "completed"
    client.patch(f"/api/v1/sales-copilot/tasks/{item['id']}", json={"status": "cancelled"})
    assert not service.calendar(OWNER, date(2026, 10, 16))["items"]


def test_root_creation_with_customer_checks_access_and_reuses_conversation(agenda):
    repo, _, client = agenda
    customer = repo.create_customer(name="Của tôi", advisor_id=OWNER)
    response = client.post("/api/v1/sales-copilot/tasks", json={"title": "Gặp khách", "customer_id": customer, **INTERVAL})
    assert response.status_code == 201
    item = response.json()
    assert item["conversation_id"] and item["customer_id"] == customer
    assert item["starts_at"] == "2026-10-16T02:00:00+00:00"
    assert repo.list_tasks_for_customer(customer)[0]["id"] == item["id"]
    detail = client.get(f"/api/v1/sales-copilot/conversations/{item['conversation_id']}")
    assert detail.status_code == 200
    assert detail.json()["tasks"][0]["starts_at"] == item["starts_at"]
    alien = repo.create_customer(name="Của người khác", advisor_id="another")
    assert client.post("/api/v1/sales-copilot/tasks", json={"title": "Không hợp lệ", "customer_id": alien, **INTERVAL}).status_code == 404


def test_review_approval_requires_schedule_and_does_not_publish_early(agenda):
    repo, service, client = agenda
    item_id = task(repo, status="needs_review")
    assert service.dashboard(OWNER, now=NOW, work_filter="review")["work_items"]["total"] == 1
    assert not service.calendar(OWNER, date(2026, 10, 16))["items"]
    url = f"/api/v1/sales-copilot/tasks/{item_id}"
    assert client.patch(url, json={"status": "pending"}).status_code == 422
    assert client.patch(url, json={"status": "completed"}).status_code == 422
    assert client.patch(url, json={"status": "pending", **INTERVAL}).status_code == 200
    assert len(service.calendar(OWNER, date(2026, 10, 16))["items"]) == 1


def test_calendar_monday_boundaries_and_midnight_intersection(agenda):
    _, service, client = agenda
    for start, end in [("2026-10-11T23:00:00+07:00", "2026-10-12T01:00:00+07:00"),
                       ("2026-10-18T23:00:00+07:00", "2026-10-19T01:00:00+07:00"),
                       ("2026-10-19T00:00:00+07:00", "2026-10-19T01:00:00+07:00")]:
        assert client.post("/api/v1/sales-copilot/tasks", json={"title": "Qua ngày", "starts_at": start, "ends_at": end}).status_code == 201
    result = service.calendar(OWNER, date(2026, 10, 18))
    assert result["week_start"] == "2026-10-12" and len(result["items"]) == 2
    assert len(service.calendar(OWNER, date(2026, 10, 19))["items"]) == 2


def test_dashboard_orders_today_pages_work_and_keeps_the_next_five_events(agenda):
    repo, service, _ = agenda
    def add(title, start, end):
        return service.create(OWNER, {"title": title, "starts_at": NOW + timedelta(minutes=start),
            "ends_at": NOW + timedelta(minutes=end), "item_type": "task", "description": ""})
    add("Đã qua", -120, -60)
    add("Sắp bắt đầu", 60, 120)
    add("Đang diễn ra", -30, 30)
    for index in range(12):
        add(f"Xa {index}", 8 * 1440 + index * 60, 8 * 1440 + index * 60 + 30)
    data = service.dashboard(OWNER, now=NOW)
    assert [item["title"] for item in data["work_items"]["items"]] == ["Đang diễn ra", "Sắp bắt đầu", "Đã qua"]
    assert data["kpis"]["today_events"] == 3 and data["kpis"]["upcoming_events"] == 1
    assert len(data["upcoming_events"]) == 5
    assert data["upcoming_events"][0]["title"] == "Sắp bắt đầu"
    assert data["upcoming_events"][-1]["title"] == "Xa 3"
    task(repo)
    for index in range(10):
        task(repo, priority="low")
    second_page = service.dashboard(OWNER, now=NOW, work_filter="unscheduled", work_page=2)["work_items"]
    assert second_page["total"] == 11 and second_page["page"] == 2 and len(second_page["items"]) == 1


def test_dashboard_uses_confirmations_dedupes_context_and_aggregates_messages(agenda):
    repo, service, _ = agenda
    customer = repo.create_customer(name="Khách", advisor_id=OWNER)
    conversation = repo.get_or_create_conversation(customer)
    repo.save_lead_score(LeadStatus(customer_id=customer, stage="discovery"))
    repo.save_facts_and_snapshot(customer, [], CustomerProfileSnapshot(interested_models=["VF 6"], unresolved_questions=[" Điểm sạc ", "Tài chính"]))
    repo.save_profile_override(conversation, "interested_models", ["VF 8", "vf8", "VF 8 Plus"], OWNER)
    repo.save_recommendation_or_draft(conversation, "lead_stage_override", {"stage": "appointment"})
    repo.add_message(conversation, "customer", "Một")
    repo.add_message(conversation, "sales", "Hai")
    repo.add_message(conversation, "customer", "Ba")
    repo.add_message(conversation, "system", "Không đổi trạng thái chờ")
    with repo.engine.begin() as conn:
        conn.execute(update(repo.messages).values(sent_at=NOW))
        conn.execute(insert(repo.memories).values(conversation_id=conversation, quick_summary="", detailed_summary="", timeline_json="[]", pending_items_json='["điểm sạc"]', key_promises_json="[]", version=1, updated_at=NOW))
    data = service.dashboard(OWNER, now=NOW)
    assert data["stage_distribution"] == [{"stage": "appointment", "count": 1}]
    assert data["model_interest"] == [{"model": "VF 8", "count": 1}]
    assert data["kpis"]["waiting_customers"] == 1
    assert len(data["customer_intelligence"][0]["issues"]) == 2
    assert len(data["message_activity"]) == 7
    assert data["message_activity"][-1] == {"date": "2026-10-16", "customer": 2, "sales": 1}
    assert all(row["customer"] == row["sales"] == 0 for row in data["message_activity"][:-1])


def test_dashboard_reads_are_bounded_and_never_create_conversations(agenda):
    repo, service, client = agenda
    for i in range(12):
        repo.create_customer(name=f"Chưa hội thoại {i}", advisor_id=OWNER)
    statements = []
    def capture(conn, cursor, statement, *args):
        statements.append(statement)
    event.listen(repo.engine, "before_cursor_execute", capture)
    try:
        response = client.get("/api/v1/sales-copilot/dashboard?activity_days=30&work_page=2")
    finally:
        event.remove(repo.engine, "before_cursor_execute", capture)
    assert response.status_code == 200 and len(response.json()["message_activity"]) == 30
    assert len(statements) == 6 and all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    with repo.engine.connect() as conn:
        assert not conn.execute(select(repo.conversations)).all()
    assert client.get("/api/v1/sales-copilot/dashboard?activity_days=8").status_code == 422
    assert client.get("/api/v1/sales-copilot/calendar?week_start=invalid").status_code == 422
