"""The repair only adopts known orphaned demo data, never another advisor's records."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, insert, select, update

from scripts.repair_sales_demo_assignments import DEMO_OWNER, OLD_OWNER, SEED_IDENTITIES, repair
from src.integrations.auth_repository import SQLAuthRepository
from src.integrations.copilot_sessions import SQLCopilotSessionsRepository
from src.integrations.sales_copilot_repository import SQLSalesCopilotRepository
from src.services.sales_conversation_service import SalesConversationService


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'repair.db'}")
    auth = SQLAuthRepository("", engine=engine)
    auth._ensure_schema()
    sales = SQLSalesCopilotRepository("", engine=engine)
    sales.ensure_schema()
    sessions = SQLCopilotSessionsRepository("", engine=engine)
    sessions._ensure_schema()
    with engine.begin() as connection:
        connection.execute(insert(auth._users).values(
            user_id=DEMO_OWNER, username="advisor.demo", display_name="Demo", role="advisor",
            password_hash="unused", password_salt="unused", password_iterations=1, active=True,
        ))
    ids = []
    for name, phone in SEED_IDENTITIES:
        customer = sales.create_customer(name=name, phone=phone, advisor_id=OLD_OWNER)
        conversation = sales.get_or_create_conversation(customer)
        sales.add_message(conversation, "customer", "Tin gốc phải được giữ")
        ids.append((customer, conversation))
    yield engine, auth, sales, sessions, ids
    engine.dispose()


def test_repair_is_dry_run_by_default_and_preserves_conversations(seeded):
    engine, _, sales, _, ids = seeded
    outsider = sales.create_customer(name="Khách khác", advisor_id=OLD_OWNER)
    real_owner = sales.create_customer(name=SEED_IDENTITIES[0][0], phone=SEED_IDENTITIES[0][1], advisor_id="real-sales")
    before = {conversation: sales.list_messages(conversation) for _, conversation in ids}
    preview = repair(engine)
    assert preview["updated"] == 0
    assert sales.get_customer(ids[0][0])["advisor_id"] == OLD_OWNER
    applied = repair(engine, apply=True)
    assert applied["updated"] == 3
    assert set(applied["customer_ids"]) == {customer for customer, _ in ids}
    assert sales.get_customer(outsider)["advisor_id"] == OLD_OWNER
    assert sales.get_customer(real_owner)["advisor_id"] == "real-sales"
    for customer, conversation in ids:
        assert sales.owned_conversation(conversation, DEMO_OWNER)["customer_id"] == customer
        assert sales.list_messages(conversation) == before[conversation]
    assert len(SalesConversationService(sales).list_advisor_conversations(DEMO_OWNER)) == 3
    assert repair(engine, apply=True)["updated"] == 0


@pytest.mark.parametrize("guard", ["legacy_account", "inactive_demo", "private_history"])
def test_repair_refuses_ambiguous_or_private_ownership(seeded, guard):
    engine, auth, sales, sessions, ids = seeded
    with engine.begin() as connection:
        if guard == "legacy_account":
            connection.execute(insert(auth._users).values(
                user_id=OLD_OWNER, username="legacy", display_name="Actual sales", role="advisor",
                password_hash="unused", password_salt="unused", password_iterations=1, active=True,
            ))
        elif guard == "inactive_demo":
            connection.execute(update(auth._users).where(auth._users.c.user_id == DEMO_OWNER).values(active=False))
        else:
            connection.execute(insert(sessions.lookup_sessions).values(
                owner_id="someone-else", sales_conversation_id=ids[0][1], session_id="private-session",
                created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
            ))
    with pytest.raises(RuntimeError):
        repair(engine, apply=True)
    with engine.connect() as connection:
        assert set(connection.execute(select(sales.customers.c.advisor_id)).scalars()) == {OLD_OWNER}
