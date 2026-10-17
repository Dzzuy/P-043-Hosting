"""Repair orphaned CRM demo assignments without changing customers or private AI history.

Dry run by default. Run with --apply after reviewing the IDs printed by dry run.
Only the three known seed records can be reassigned, and only when advisor_01
does not correspond to an account and the canonical demo advisor already exists.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import and_, or_, select, update

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.integrations.auth_repository import SQLAuthRepository  # noqa: E402
from src.integrations.copilot_sessions import SQLCopilotSessionsRepository  # noqa: E402
from src.integrations.sales_copilot_repository import SQLSalesCopilotRepository  # noqa: E402

SEED_IDENTITIES = (
    ("Anh Minh Tuấn", "0912 345 678"),
    ("Anh Quang Huy", "0988 765 432"),
    ("Anh Đức Trọng", "0904 112 233"),
)
OLD_OWNER = "advisor_01"
DEMO_OWNER = "advisor-demo"


def repair(engine, *, apply=False):
    auth = SQLAuthRepository("", engine=engine)
    sales = SQLSalesCopilotRepository("", engine=engine)
    sessions = SQLCopilotSessionsRepository("", engine=engine)
    with engine.begin() as connection:
        old_account = connection.execute(select(auth._users.c.user_id).where(
            auth._users.c.user_id == OLD_OWNER,
        )).scalar_one_or_none()
        canonical = connection.execute(select(auth._users.c.user_id).where(
            auth._users.c.user_id == DEMO_OWNER, auth._users.c.username == "advisor.demo",
            auth._users.c.active.is_(True), auth._users.c.role == "advisor",
        )).scalar_one_or_none()
        if old_account or not canonical:
            raise RuntimeError("Repair requires an orphaned legacy ID and the existing canonical demo advisor")
        customers = connection.execute(select(sales.customers.c.id).where(
            sales.customers.c.advisor_id == OLD_OWNER,
            or_(*(and_(sales.customers.c.name == name, sales.customers.c.phone == phone)
                  for name, phone in SEED_IDENTITIES)),
        ).with_for_update()).scalars().all()
        conversations = connection.execute(select(sales.conversations.c.id).where(
            sales.conversations.c.customer_id.in_(customers),
        )).scalars().all()
        private_bindings = connection.execute(select(sessions.lookup_sessions.c.session_id).where(
            sessions.lookup_sessions.c.sales_conversation_id.in_(conversations),
            sessions.lookup_sessions.c.owner_id != DEMO_OWNER,
        )).scalars().all()
        if private_bindings:
            raise RuntimeError("Repair refused: a selected customer has private lookup history for another owner")
        result = {"applied": apply, "from_owner": OLD_OWNER, "to_owner": DEMO_OWNER,
                  "customer_ids": customers, "conversation_ids": conversations, "updated": 0}
        if apply and customers:
            changed = connection.execute(update(sales.customers).where(
                sales.customers.c.id.in_(customers), sales.customers.c.advisor_id == OLD_OWNER,
            ).values(advisor_id=DEMO_OWNER, updated_at=datetime.now(UTC))).rowcount
            if changed != len(customers):
                raise RuntimeError("Customer ownership changed concurrently; transaction rolled back")
            connection.execute(update(sales.tasks).where(
                sales.tasks.c.customer_id.in_(customers), sales.tasks.c.owner_sales_id == OLD_OWNER,
            ).values(owner_sales_id=DEMO_OWNER))
            result["updated"] = changed
    return result


def main():
    from sqlalchemy import create_engine

    from src.config import get_settings
    from src.integrations.practice_persistence import normalize_database_url

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if settings.app_env == "production":
        raise RuntimeError("Demo assignment repair is restricted to development/test")
    engine = create_engine(normalize_database_url(settings.database_url))
    try:
        print(json.dumps(repair(engine, apply=args.apply)), flush=True)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
