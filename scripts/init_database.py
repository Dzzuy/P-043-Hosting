"""Utility script to verify connection and initialize Copilot tables on Supabase/PostgreSQL.

Usage:
    python scripts/init_database.py
"""

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from sqlalchemy import inspect, text

from src.config import get_settings
from src.integrations.copilot_sessions import SQLCopilotSessionsRepository
from src.knowledge.pgvector_store import PgVectorStore


def main():
    settings = get_settings()
    db_url = settings.database_url

    # Mask password for display
    masked_url = db_url
    if "@" in db_url:
        prefix, host_part = db_url.split("@", 1)
        scheme, creds = prefix.split("://", 1)
        user = creds.split(":", 1)[0] if ":" in creds else creds
        masked_url = f"{scheme}://{user}:****@{host_part}"

    print("==================================================")
    print("  VINFAST SALES COPILOT - DATABASE INITIALIZER   ")
    print("==================================================")
    print(f"Connecting to database: {masked_url}")

    # 1. Initialize Copilot session & memory tables
    print("\n[Step 1] Ensuring Copilot dialogue and memory schema...")
    copilot_repo = SQLCopilotSessionsRepository(db_url)
    copilot_repo._ensure_schema()
    print("  ✓ Copilot tables synchronized successfully!")

    # 2. Initialize pgvector extension & knowledge vectors table
    print("\n[Step 2] Ensuring pgvector extension and knowledge_vectors table...")
    if settings.vector_store_type == "pgvector" or db_url.startswith(("postgres://", "postgresql://")):
        try:
            PgVectorStore(db_url, settings.chroma_collection_name)
            print("  ✓ pgvector extension and knowledge_vectors table synchronized!")
        except Exception as exc:
            print(f"  ⚠ pgvector notice: {exc}")

    # 3. Inspect Copilot tables
    print("\n[Step 3] Inspecting Copilot tables in PostgreSQL database:")
    inspector = inspect(copilot_repo.engine)
    copilot_tables = [
        "conversations",
        "copilot_messages",
        "conversation_memories",
        "copilot_sessions",
        "knowledge_vectors",
    ]

    for table_name in copilot_tables:
        if inspector.has_table(table_name):
            columns = inspector.get_columns(table_name)
            col_names = [col["name"] for col in columns]
            print(f"  [OK] Table '{table_name}' ({len(columns)} cols): {', '.join(col_names)}")
        else:
            print(f"  [MISSING] Table '{table_name}' was not found!")

    # 4. Test database connection ping
    print("\n[Step 4] Testing database health query...")
    with copilot_repo.engine.connect() as conn:
        res = conn.execute(text("SELECT version();")).scalar()
        print(f"  Database Engine: {res}")

    print("\n Copilot database initialization complete and verified!")
    print("==================================================")


if __name__ == "__main__":
    main()
