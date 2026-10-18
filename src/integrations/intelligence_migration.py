"""Additive, repeatable legacy stage repair. Original rows stay in the audit trail."""

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import insert, select, update


def migrate_appointment_stages(repo):
    with repo.engine.begin() as conn:
        for row in (
            conn.execute(select(repo.lead_scores).where(repo.lead_scores.c.stage == "appointment")).mappings().all()
        ):
            # A sales override is trustworthy history; old activity guesses are not.
            records = (
                conn.execute(
                    select(repo.recommendations)
                    .join(repo.conversations, repo.conversations.c.id == repo.recommendations.c.conversation_id)
                    .where(
                        repo.conversations.c.customer_id == row["customer_id"],
                        repo.recommendations.c.type == "lead_stage_override",
                    )
                    .order_by(repo.recommendations.c.created_at.desc(), repo.recommendations.c.id.desc())
                )
                .mappings()
                .all()
            )
            valid = {"new", "discovery", "qualified", "considering", "negotiating", "deposit_process", "won", "lost"}
            stage = next(
                (
                    json.loads(r["payload_json"]).get("stage")
                    for r in records
                    if json.loads(r["payload_json"]).get("stage") in valid
                ),
                "unknown",
            )
            cid = conn.execute(
                select(repo.conversations.c.id).where(repo.conversations.c.customer_id == row["customer_id"]).limit(1)
            ).scalar()
            if cid:
                conn.execute(
                    insert(repo.recommendations).values(
                        id=uuid4().hex,
                        conversation_id=cid,
                        type="pipeline_migration",
                        payload_json=json.dumps({"legacy": dict(row), "restored_stage": stage}, default=str),
                        status="migrated",
                        created_at=datetime.now(UTC),
                    )
                )
            conn.execute(
                update(repo.lead_scores)
                .where(repo.lead_scores.c.customer_id == row["customer_id"])
                .values(
                    stage=stage,
                    rationale="Khôi phục giai đoạn sales đã xác nhận."
                    if stage != "unknown"
                    else "Cần xác nhận giai đoạn.",
                )
            )
