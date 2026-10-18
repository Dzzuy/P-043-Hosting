"""Apply additive intelligence tables and audited legacy stage repair."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import get_settings
from src.integrations.sales_copilot_repository import SQLSalesCopilotRepository


def migrate():
    repository = SQLSalesCopilotRepository(get_settings().database_url)
    sql_path = Path(__file__).parent / "migrations" / "005_customer_intelligence_v2.sql"
    try:
        if repository.engine.dialect.name == "postgresql" and sql_path.exists():
            sql = sql_path.read_text(encoding="utf-8")
            with repository.engine.begin() as conn:
                conn.exec_driver_sql(sql)
        repository.ensure_schema()
    finally:
        repository.engine.dispose()


if __name__ == "__main__":
    migrate()
    print("Customer Intelligence schema and legacy stage migration completed.")
