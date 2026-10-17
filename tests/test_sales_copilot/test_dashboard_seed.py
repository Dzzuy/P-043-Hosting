"""Demo data is additive, atomic, owner-scoped and repeatable without duplicates."""
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, func, insert, select

from scripts.seed_dashboard_demo import seed
from src.integrations.auth_repository import SQLAuthRepository
from src.integrations.sales_copilot_repository import SQLSalesCopilotRepository
from src.services.sales_agenda_service import SalesAgendaService

NOW = datetime(2026, 10, 16, 12, 45, tzinfo=UTC)


def test_seed_preserves_existing_rows_populates_dashboard_and_is_idempotent():
    engine = create_engine("sqlite://")
    repo = SQLSalesCopilotRepository("", engine=engine)
    repo.ensure_schema()
    auth = SQLAuthRepository("", engine=engine)
    auth._users.create(engine)
    with engine.begin() as conn:
        conn.execute(insert(auth._users).values(user_id="demo", username="demo", display_name="Demo",
            role="advisor", active=True, password_hash="unused", password_salt="unused", password_iterations=1))
    original = repo.create_customer("Khách cũ", "demo")
    dry = seed(engine, "demo", now=NOW)
    assert not dry["applied"] and dry["rows"]["customers"] == 12 and dry["rows"]["tasks"] == 29
    with engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(repo.customers)).scalar_one() == 1
    assert seed(engine, "demo", apply=True, now=NOW)["applied"]
    agenda = SalesAgendaService(repo)
    data = agenda.dashboard("demo", now=NOW, activity_days=30)
    assert data["kpis"]["total_tasks"] == 29
    assert data["kpis"]["active_customers"] == 11  # Original plus ten active demo customers.
    assert data["kpis"]["waiting_customers"] == 5
    assert data["kpis"]["today_events"] >= 6 and data["kpis"]["upcoming_events"] >= 14
    assert len(data["message_activity"]) == 30
    assert all(day["customer"] and day["sales"] for day in data["message_activity"])
    assert len(data["customer_intelligence"]) == 5
    assert agenda.dashboard("demo", now=NOW, work_filter="review")["work_items"]["total"] == 3
    assert repo.get_customer(original)["name"] == "Khách cũ"
    assert not agenda.calendar("other", NOW.date())["items"]
    with engine.connect() as conn:
        before = {table.name:conn.execute(select(func.count()).select_from(table)).scalar_one() for table in repo.metadata.tables.values()}
        assert all(row["id"].startswith("dashdemo1_") for row in conn.execute(select(repo.messages)).mappings())
        assert all(row["sent_at"] <= NOW.replace(tzinfo=None) for row in conn.execute(select(repo.messages)).mappings())
    assert seed(engine, "demo", apply=True, now=NOW)["already_seeded"]
    with engine.connect() as conn:
        after = {table.name:conn.execute(select(func.count()).select_from(table)).scalar_one() for table in repo.metadata.tables.values()}
    assert before == after
    with pytest.raises(ValueError, match="existing active advisor"):
        seed(engine, "unknown", apply=True, now=NOW)
    engine.dispose()
