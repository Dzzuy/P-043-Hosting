"""Load raw (unanalyzed) sales-customer chat conversations from local JSON into PostgreSQL.

Usage:
    .\.venv\Scripts\python.exe scripts/seed_unprocessed_conversations.py
    .\.venv\Scripts\python.exe scripts/seed_unprocessed_conversations.py --reset
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.config import get_settings
from src.integrations.sales_copilot_repository import SQLSalesCopilotRepository
from src.models.sales_copilot import SenderRole


def purge_customer_data(repo: SQLSalesCopilotRepository, customer_ids: list[str]) -> None:
    """Remove all existing records (including any AI analysis artifacts) for the given customer IDs."""
    if not customer_ids:
        return
    t = repo.intelligence_tables
    with repo.engine.begin() as conn:
        conv_ids = [
            row[0]
            for row in conn.execute(
                select(repo.conversations.c.id).where(repo.conversations.c.customer_id.in_(customer_ids))
            ).all()
        ]
        task_ids = [
            row[0]
            for row in conn.execute(
                select(repo.tasks.c.id).where(repo.tasks.c.customer_id.in_(customer_ids))
            ).all()
        ]

        if task_ids:
            conn.execute(delete(t["activity_details"]).where(t["activity_details"].c.task_id.in_(task_ids)))
        conn.execute(delete(t["milestones"]).where(t["milestones"].c.customer_id.in_(customer_ids)))
        conn.execute(delete(t["proposals"]).where(t["proposals"].c.customer_id.in_(customer_ids)))
        conn.execute(delete(t["chat"]).where(t["chat"].c.customer_id.in_(customer_ids)))
        conn.execute(delete(t["analyses"]).where(t["analyses"].c.customer_id.in_(customer_ids)))
        conn.execute(delete(t["heads"]).where(t["heads"].c.customer_id.in_(customer_ids)))

        if conv_ids:
            conn.execute(delete(repo.recommendations).where(repo.recommendations.c.conversation_id.in_(conv_ids)))
            conn.execute(delete(repo.memories).where(repo.memories.c.conversation_id.in_(conv_ids)))
            conn.execute(delete(repo.messages).where(repo.messages.c.conversation_id.in_(conv_ids)))

        conn.execute(delete(repo.tasks).where(repo.tasks.c.customer_id.in_(customer_ids)))
        conn.execute(delete(repo.snapshots).where(repo.snapshots.c.customer_id.in_(customer_ids)))
        conn.execute(delete(repo.lead_scores).where(repo.lead_scores.c.customer_id.in_(customer_ids)))
        conn.execute(delete(repo.conversations).where(repo.conversations.c.customer_id.in_(customer_ids)))
        conn.execute(delete(repo.customers).where(repo.customers.c.id.in_(customer_ids)))


def seed_unprocessed_conversations(
    json_path: Path,
    *,
    advisor_id: str | None = None,
    reset: bool = False,
) -> list[dict]:
    raw_items = json.loads(json_path.read_text(encoding="utf-8"))
    repo = SQLSalesCopilotRepository(get_settings().database_url)
    repo.ensure_schema()

    target_names = {item["customer_name"] for item in raw_items}
    with repo.engine.connect() as conn:
        existing_rows = conn.execute(
            select(repo.customers).where(repo.customers.c.name.in_(target_names))
        ).mappings().all()

    if reset and existing_rows:
        purge_customer_data(repo, [row["id"] for row in existing_rows])
        existing_by_name = {}
    else:
        existing_by_name = {row["name"]: row for row in existing_rows}

    now = datetime.now(UTC)
    results = []

    for item in raw_items:
        name = item["customer_name"]
        owner_id = advisor_id or item.get("advisor_id") or "advisor-demo"
        if name in existing_by_name:
            results.append({
                "customer_name": name,
                "customer_id": existing_by_name[name]["id"],
                "status": "skipped_existing",
            })
            continue

        hours_ago = float(item.get("hours_ago", 12))
        base_time = now - timedelta(hours=hours_ago)

        customer_id = repo.create_customer(
            name=name,
            advisor_id=owner_id,
            phone=item.get("phone"),
            location=item.get("location"),
        )
        conv_id = repo.get_or_create_conversation(customer_id)

        messages_payload = []
        msg_time = base_time
        for msg in item.get("messages", []):
            msg_time += timedelta(minutes=3)
            role = SenderRole.SALES if msg["sender_role"] == "sales" else SenderRole.CUSTOMER
            messages_payload.append({
                "sender_role": role,
                "content": msg["content"].strip(),
                "sent_at": msg_time,
            })

        if messages_payload:
            repo.add_messages_batch(conv_id, messages_payload)

        results.append({
            "customer_name": name,
            "customer_id": customer_id,
            "conversation_id": conv_id,
            "message_count": len(messages_payload),
            "status": "created_unanalyzed",
        })

    repo.engine.dispose()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load unanalyzed sales-customer conversations from JSON into PostgreSQL."
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=ROOT_DIR / "data" / "unprocessed_sales_conversations.json",
        help="Path to the local JSON conversation dataset.",
    )
    parser.add_argument(
        "--advisor-id",
        type=str,
        default=None,
        help="Override advisor_id (defaults to advisor_id in JSON or 'advisor-demo').",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset/recreate these conversations in unanalyzed state even if they already exist.",
    )
    args = parser.parse_args()

    results = seed_unprocessed_conversations(
        args.file,
        advisor_id=args.advisor_id,
        reset=args.reset,
    )
    created = [r for r in results if r["status"] == "created_unanalyzed"]
    skipped = [r for r in results if r["status"] == "skipped_existing"]
    print(f"Done! Created: {len(created)}, Skipped existing: {len(skipped)}")
    for item in results:
        print(f"  - {item['customer_name']}: {item['status']} ({item.get('message_count', 0)} messages)")


if __name__ == "__main__":
    main()
