"""Verify migration in a rollback-only isolated PostgreSQL schema, then optionally apply.

Usage: python scripts/migrate_sales_agenda.py [--apply]
Uses the existing configured database; never prints connection credentials or customer content.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from src.config import get_settings
from src.integrations.practice_persistence import normalize_database_url


def migrate(apply=False):
    engine = create_engine(normalize_database_url(get_settings().database_url),
                           connect_args={"connect_timeout": 10})
    sql = (Path(__file__).parent / "migrations/004_sales_copilot_agenda.sql").read_text(encoding="utf-8")
    schema = "qa_agenda_" + uuid4().hex
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            source = conn.exec_driver_sql("SELECT current_schema()").scalar_one()
            quoted_source = conn.dialect.identifier_preparer.quote(source)
            conn.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
            conn.exec_driver_sql("SET LOCAL statement_timeout = '30s'")
            conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            conn.exec_driver_sql(f'CREATE TABLE "{schema}".copilot_followup_tasks (LIKE {quoted_source}.copilot_followup_tasks INCLUDING ALL)')
            conn.exec_driver_sql(f'INSERT INTO "{schema}".copilot_followup_tasks SELECT * FROM {quoted_source}.copilot_followup_tasks')
            conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            count = conn.exec_driver_sql("SELECT count(*) FROM copilot_followup_tasks").scalar_one()
            conn.exec_driver_sql(sql)
            conn.exec_driver_sql(sql)  # An interrupted/repeated deployment must be safe.
            assert conn.exec_driver_sql("SELECT count(*) FROM copilot_followup_tasks").scalar_one() == count
            missing = conn.exec_driver_sql(f'''SELECT count(*) FROM (
                SELECT id, due_at, due_window FROM {quoted_source}.copilot_followup_tasks
                EXCEPT SELECT id, due_at, due_window FROM copilot_followup_tasks
            ) AS missing''').scalar_one()
            assert missing == 0
            conn.exec_driver_sql("""INSERT INTO copilot_followup_tasks
                (id, owner_sales_id, task_type, title, description, priority, status,
                 source_message_ids_json, created_at, starts_at, ends_at, item_type)
                VALUES ('qa-personal', 'qa-sales', 'manual_follow_up', 'QA', '', 'medium', 'pending',
                        '[]', now(), now(), now() + interval '1 hour', 'appointment')""")
            savepoint = conn.begin_nested()
            rejected = False
            try:
                conn.exec_driver_sql("UPDATE copilot_followup_tasks SET ends_at = starts_at WHERE id = 'qa-personal'")
            except Exception:
                rejected = True
            finally:
                savepoint.rollback()
            assert rejected, "Invalid intervals must be rejected by PostgreSQL"
            print(json.dumps({"isolated_schema_verified": True, "preserved_tasks": count,
                              "legacy_values_preserved": True, "idempotent": True,
                              "personal_event_verified": True, "invalid_interval_rejected": True}))
        finally:
            transaction.rollback()  # Removes only the temporary schema and its copied rows.
        if apply:
            with conn.begin():
                conn.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
                conn.exec_driver_sql("SET LOCAL statement_timeout = '30s'")
                before = conn.exec_driver_sql("SELECT count(*) FROM copilot_followup_tasks").scalar_one()
                conn.exec_driver_sql(sql)
                after = conn.exec_driver_sql("SELECT count(*) FROM copilot_followup_tasks").scalar_one()
                assert before == after
            print(json.dumps({"migration_applied": True, "preserved_tasks": after}))
    engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    migrate(parser.parse_args().apply)
