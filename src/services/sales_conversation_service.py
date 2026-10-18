"""Service for managing sales conversations and seeding real dataset from docx."""

from __future__ import annotations

import logging
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from src.integrations.sales_copilot_repository import SQLSalesCopilotRepository
from src.models.sales_copilot import (
    ChatMessageResponse,
    ConversationResponse,
    FollowupTask,
    LeadStage,
    SenderRole,
)

logger = logging.getLogger(__name__)


def extract_paragraphs_from_docx(docx_path: str) -> list[str]:
    """Extract all text paragraphs from a .docx file using Python standard library."""
    if not os.path.exists(docx_path):
        raise FileNotFoundError(f"File not found: {docx_path}")

    with zipfile.ZipFile(docx_path, "r") as z:
        xml_content = z.read("word/document.xml")

    tree = ET.fromstring(xml_content)
    paragraphs = []
    for p in tree.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
        texts = [
            node.text
            for node in p.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
            if node.text
        ]
        if texts:
            combined = "".join(texts).strip()
            if combined:
                paragraphs.append(combined)
    return paragraphs


class SalesConversationService:
    def __init__(self, repository: SQLSalesCopilotRepository):
        self.repository = repository

    def seed_real_conversations_from_docx(
        self,
        docx_path: str = "data/message_sales.docx",
        default_advisor_id: str = "advisor-demo",
    ) -> list[dict[str, Any]]:
        """Parse message_sales.docx and seed the 3 rich VinFast sales conversations into PostgreSQL."""
        self.repository.ensure_schema()
        paragraphs = extract_paragraphs_from_docx(docx_path)

        # Detect conversation boundaries
        splits: list[tuple[int, str]] = []
        for idx, p in enumerate(paragraphs):
            if "hội thoại" in p.lower():
                splits.append((idx, p))

        seeded_conversations = []
        base_time = datetime.now(UTC) - timedelta(days=2)

        meta_configs = [
            {
                "customer_name": "Anh Minh Tuấn",
                "phone": "0912 345 678",
                "location": "Long Biên, Hà Nội",
                "default_model": "VF 6 Eco",
            },
            {
                "customer_name": "Anh Quang Huy",
                "phone": "0988 765 432",
                "location": "Hà Đông, Hà Nội",
                "default_model": "VF 8",
            },
            {
                "customer_name": "Anh Đức Trọng",
                "phone": "0904 112 233",
                "location": "Nam Từ Liêm, Hà Nội",
                "default_model": "VF 3",
            },
        ]

        for i in range(len(splits)):
            start_idx = splits[i][0] + 1
            end_idx = splits[i + 1][0] if i + 1 < len(splits) else len(paragraphs)
            conv_paragraphs = paragraphs[start_idx:end_idx]

            cfg = meta_configs[i] if i < len(meta_configs) else {
                "customer_name": f"Khách hàng {i+1}",
                "phone": f"0900 000 00{i+1}",
                "location": "Hà Nội",
                "default_model": "VinFast",
            }

            # Check if customer already seeded by name and advisor
            existing_customers = self.repository.list_customers_for_advisor(default_advisor_id)
            target_customer = next((c for c in existing_customers if c.name == cfg["customer_name"]), None)

            if target_customer:
                customer_id = target_customer.id
                conv_id = self.repository.get_or_create_conversation(customer_id)
                seeded_conversations.append({
                    "customer_id": customer_id,
                    "conversation_id": conv_id,
                    "name": cfg["customer_name"],
                    "status": "already_exists",
                })
                continue

            # Create customer
            customer_id = self.repository.create_customer(
                name=cfg["customer_name"],
                advisor_id=default_advisor_id,
                phone=cfg["phone"],
                location=cfg["location"],
            )
            conv_id = self.repository.get_or_create_conversation(customer_id)

            # Ingest messages in batch
            msg_time = base_time + timedelta(hours=i * 6)
            batch_data = []
            for p_text in conv_paragraphs:
                p_text = p_text.strip()
                if not p_text:
                    continue

                if p_text.lower().startswith("sales:") or p_text.lower().startswith("sales :"):
                    role = SenderRole.SALES
                    content = re.sub(r"^sales\s*:\s*", "", p_text, flags=re.I).strip()
                elif p_text.lower().startswith("khách hàng:") or p_text.lower().startswith("khách hàng :"):
                    role = SenderRole.CUSTOMER
                    content = re.sub(r"^khách hàng\s*:\s*", "", p_text, flags=re.I).strip()
                else:
                    role = SenderRole.SALES if "em" in p_text.lower() else SenderRole.CUSTOMER
                    content = p_text

                msg_time += timedelta(minutes=3)
                batch_data.append({
                    "sender_role": role,
                    "content": content,
                    "sent_at": msg_time,
                })

            if batch_data:
                self.repository.add_messages_batch(conv_id, batch_data)

            seeded_conversations.append({
                "customer_id": customer_id,
                "conversation_id": conv_id,
                "name": cfg["customer_name"],
                "status": "created",
                "message_count": len(conv_paragraphs),
            })

        return seeded_conversations

    def get_conversation_details(self, conversation_id: str, message_limit: int | None = None) -> ConversationResponse | None:
        """Fetch full conversation with message history, customer snapshot, memory, tasks, and lead status."""
        self.repository.ensure_schema()
        with self.repository.engine.connect() as conn:
            metadata = self.repository.get_conversation_metadata(conversation_id, connection=conn)
            if metadata is None:
                return None
            # One request owns this connection; nested reads borrow it without closing it.
            row = metadata["record"]
            customer_id = row["customer_id"]
            customer = metadata["customer"]
            messages = self.repository.list_messages(conversation_id, limit=message_limit, connection=conn)
            tasks = self.repository.list_tasks_for_customer(customer_id, connection=conn)
            from src.integrations.customer_intelligence_store import IntelligenceStore, active_milestones
            milestones = active_milestones(IntelligenceStore(self.repository).milestone_history(customer_id, conn))
            if metadata["memory"].get("stage"):
                metadata["memory"]["timeline"] = [{"id": m["id"], "title": m["action"], "description": m["action"],
                    "event_type": m["event_type"], "occurred_at": m.get("occurred_at") or m["created_at"],
                    "source_message_id": (m.get("evidence") or [{}])[0].get("message_id") or next(iter(m.get("source_message_ids", [])), None)} for m in milestones]
        lead_status = metadata["lead"]
        if metadata["memory"].get("stage"):
            lead_status = {**lead_status, **metadata["memory"]["stage"]}
        override = metadata["override"]
        lead_status = {
            **lead_status,
            "ai_stage": lead_status.get("ai_stage", lead_status.get("stage")),
            "stage_source": lead_status.get("stage_source", "ai" if lead_status else "unknown"),
        }
        if override.get("stage") in LeadStage._value2member_map_:
            lead_status.update(stage=override["stage"], stage_source="sales", override=override)
        elif lead_status.get("stage_source") == "sales":
            lead_status.update(stage=lead_status.get("ai_stage"), stage_source="rules")
            lead_status.pop("override", None)

        profile = dict(metadata["profile"])
        for field, override_fact in metadata.get("profile_overrides", {}).items():
            profile[field] = override_fact["value"]
            if field == "budget_vnd":
                profile["budget_notes"] = None
            facts = [fact for fact in profile.get("facts", []) if fact.get("field") != field]
            original = next((fact for fact in profile.get("facts", []) if fact.get("field") == field), {})
            facts.append({**original, "field": field, "value": override_fact["value"], "verification_status": "confirmed", "note": "Sales xác nhận", "source_message_ids": original.get("source_message_ids", []) if original.get("value") == override_fact["value"] else []})
            profile["facts"] = facts
        return ConversationResponse(
            id=conversation_id,
            customer_id=customer_id,
            customer_name=customer["name"] if customer else "Khách hàng",
            customer_location=customer.get("location") if customer else None,
            last_analyzed_at=row["last_analyzed_at"],
            analysis_version=row["analysis_version"],
            messages=messages,
            message_total=metadata["message_total"],
            last_message_seq=metadata["last_message_seq"],
            next_before_seq=messages[0].seq if message_limit and messages and messages[0].seq > 1 else None,
            profile=profile,
            memory=metadata["memory"],
            tasks=tasks,
            milestones=milestones,
            lead_status=lead_status,
        )

    def add_sales_message(self, conversation_id: str, content: str) -> ChatMessageResponse:
        """Sales appends a manual message to the conversation."""
        return self.repository.add_message(
            conversation_id=conversation_id,
            sender_role=SenderRole.SALES,
            content=content.strip(),
            sent_at=datetime.now(UTC),
        )

    def update_lead_stage(
        self, conversation_id: str, advisor_id: str, stage: LeadStage | None, reason: str = "",
    ) -> dict[str, Any]:
        """Keep the sales rep's stage separate from the latest AI assessment."""
        from sqlalchemy import select

        repo = self.repository
        repo.owned_conversation(conversation_id, advisor_id)
        if stage in (LeadStage.WON, LeadStage.LOST) and not reason.strip():
            raise ValueError("Cần lý do và xác nhận hợp đồng đã ký / đóng cơ hội.")
        repo.ensure_schema()
        with repo.engine.connect() as conn:
            exists = conn.execute(select(repo.conversations.c.id)
                                  .where(repo.conversations.c.id == conversation_id)).scalar_one_or_none()
        if not exists:
            raise LookupError(conversation_id)
        payload = {
            "stage": stage.value if stage else None, "reason": reason.strip(),
            "advisor_id": advisor_id, "updated_at": datetime.now(UTC).isoformat(),
        }
        repo.save_recommendation_or_draft(conversation_id, "lead_stage_override", payload)
        return self.get_conversation_details(conversation_id).lead_status

    def create_followup_task(
        self,
        conversation_id: str,
        advisor_id: str,
        *,
        title: str,
        priority: str = "medium",
        due_at: datetime | None = None,
    ) -> dict[str, Any]:
        from sqlalchemy import select

        self.repository.ensure_schema()
        with self.repository.engine.connect() as conn:
            customer_id = conn.execute(
                select(self.repository.conversations.c.customer_id)
                .where(self.repository.conversations.c.id == conversation_id)
            ).scalar_one_or_none()
        if not customer_id:
            raise LookupError(conversation_id)
        task = FollowupTask(
            id=uuid4().hex,
            customer_id=customer_id,
            conversation_id=conversation_id,
            owner_sales_id=advisor_id,
            task_type="manual_follow_up",
            title=title,
            description="",
            due_at=due_at,
            priority=priority,
            created_at=datetime.now(UTC),
        )
        self.repository.save_tasks([task])
        return task.model_dump(mode="json")

    def list_advisor_conversations(self, advisor_id: str) -> list[dict[str, Any]]:
        """Read list-card data in batches, independent of the number of customers."""
        import json

        from sqlalchemy import case, func, select

        repo = self.repository
        repo.ensure_schema()
        with repo.engine.connect() as conn:
            customers = conn.execute(
                select(repo.customers).where(repo.customers.c.advisor_id == advisor_id)
            ).mappings().all()
            if not customers:
                return []
            ids = [customer["id"] for customer in customers]
            scores = {row["customer_id"]: row for row in conn.execute(
                select(repo.lead_scores).where(repo.lead_scores.c.customer_id.in_(ids))
            ).mappings()}
            snapshots = {}
            for row in conn.execute(
                select(repo.snapshots).where(repo.snapshots.c.customer_id.in_(ids))
            ).mappings():
                try:
                    snapshots[row["customer_id"]] = json.loads(row["snapshot_json"])
                except (ValueError, TypeError):
                    snapshots[row["customer_id"]] = {}
            task_stats = {row[0]: (row[1], row[2]) for row in conn.execute(
                select(repo.tasks.c.customer_id, func.count(), func.sum(case((
                    (repo.tasks.c.priority.in_(["high", "urgent"])) & (repo.tasks.c.ends_at <= datetime.now(UTC)) & (repo.tasks.c.status.in_(["pending", "in_progress"])), 1,
                ), else_=0)))
                .where(repo.tasks.c.customer_id.in_(ids), repo.tasks.c.status.not_in(["completed", "cancelled"]))
                .group_by(repo.tasks.c.customer_id)
            ).all()}
            last_message = repo.messages.alias("last_message")
            last_id = (
                select(repo.messages.c.id)
                .where(repo.messages.c.conversation_id == repo.conversations.c.id)
                .order_by(repo.messages.c.seq.desc())
                .limit(1)
                .correlate(repo.conversations)
                .scalar_subquery()
            )
            conversations = {}
            stage_override = (
                select(repo.recommendations.c.payload_json)
                .where(repo.customer_override_scope(),
                       repo.recommendations.c.type == "lead_stage_override")
                .order_by(repo.recommendations.c.created_at.desc(), repo.recommendations.c.id.desc())
                .limit(1).correlate(repo.conversations).scalar_subquery()
            )
            profile_override = (
                select(repo.recommendations.c.payload_json)
                .where(repo.customer_override_scope(),
                       repo.recommendations.c.type == "profile_overrides")
                .order_by(repo.recommendations.c.created_at.desc(), repo.recommendations.c.id.desc())
                .limit(1).correlate(repo.conversations).scalar_subquery()
            )
            analysis_context = (
                select(repo.recommendations.c.payload_json)
                .where(repo.recommendations.c.conversation_id == repo.conversations.c.id,
                       repo.recommendations.c.type == "analysis_context")
                .order_by(repo.recommendations.c.created_at.desc(), repo.recommendations.c.id.desc())
                .limit(1).correlate(repo.conversations).scalar_subquery()
            )
            message_total = (
                select(func.count())
                .where(repo.messages.c.conversation_id == repo.conversations.c.id)
                .correlate(repo.conversations).scalar_subquery()
            )
            unprocessed_after_analysis = (
                select(func.count())
                .where(
                    repo.messages.c.conversation_id == repo.conversations.c.id,
                    repo.messages.c.sent_at > repo.conversations.c.last_analyzed_at,
                )
                .correlate(repo.conversations).scalar_subquery()
            )
            for row in conn.execute(
                select(
                    repo.conversations.c.id,
                    repo.conversations.c.customer_id,
                    repo.conversations.c.analysis_version,
                    repo.conversations.c.last_analyzed_at,
                    stage_override.label("stage_override"),
                    profile_override.label("profile_override"),
                    analysis_context.label("analysis_context"),
                    message_total.label("message_total"),
                    unprocessed_after_analysis.label("unprocessed_after_analysis"),
                    last_message.c.seq.label("last_message_seq"),
                    last_message.c.content,
                    last_message.c.sent_at,
                    last_message.c.sender_role,
                )
                .select_from(repo.conversations)
                .outerjoin(last_message, last_message.c.id == last_id)
                .where(repo.conversations.c.customer_id.in_(ids))
                .order_by(repo.conversations.c.updated_at.desc(), repo.conversations.c.id)
            ).mappings():
                conversations.setdefault(row["customer_id"], row)

        result = []
        for customer in customers:
            cid = customer["id"]
            conversation = conversations.get(cid)
            conv_id = conversation["id"] if conversation else repo.get_or_create_conversation(cid)
            score = scores.get(cid) or {}
            snapshot = snapshots.get(cid) or {}
            confirmed = json.loads(conversation["profile_override"] or "{}") if conversation else {}
            for field, fact in confirmed.items():
                snapshot[field] = fact["value"]
                if field == "budget_vnd":
                    snapshot["budget_notes"] = None
            last_content = conversation["content"] if conversation else ""
            last_content = last_content or ""
            sent_at = conversation["sent_at"] if conversation else None
            override = json.loads(conversation["stage_override"] or "{}") if conversation else {}
            analysis_version = (conversation["analysis_version"] or 0) if conversation else 0
            last_analyzed_at = conversation["last_analyzed_at"] if conversation else None
            msg_total = int(conversation["message_total"] or 0) if conversation else 0
            last_seq = int(conversation["last_message_seq"] or 0) if conversation else 0
            ctx = json.loads(conversation["analysis_context"] or "{}") if conversation else {}
            through_seq = ctx.get("through_seq") if ctx.get("version") == analysis_version else None
            pending_analysis_count = (
                max(0, last_seq - through_seq)
                if isinstance(through_seq, int)
                else (
                    msg_total
                    if analysis_version == 0 or not last_analyzed_at
                    else int(conversation["unprocessed_after_analysis"] or 0)
                )
            )
            result.append({
                "conversation_id": conv_id,
                "customer_id": cid,
                "customer_name": customer["name"],
                "phone": customer["phone"],
                "location": customer["location"],
                "lead_stage": (override.get("stage") or score.get("stage", "new")) if (override.get("stage") or score.get("stage", "new")) in LeadStage._value2member_map_ else None,
                "analysis_version": analysis_version,
                "last_analyzed_at": last_analyzed_at.isoformat() if last_analyzed_at else None,
                "message_total": msg_total,
                "last_message_seq": last_seq,
                "pending_analysis_count": pending_analysis_count,
                "pending_tasks_count": task_stats.get(cid, (0, 0))[0],
                "important_overdue_count": task_stats.get(cid, (0, 0))[1],
                "last_sender_role": conversation["sender_role"] if conversation else None,
                "interested_models": snapshot.get("interested_models", []),
                "budget_vnd": snapshot.get("budget_vnd"),
                "budget_notes": snapshot.get("budget_notes"),
                "last_message": last_content[:90] + ("..." if len(last_content) > 90 else ""),
                "last_message_at": (sent_at or customer["created_at"]).isoformat(),
            })
        return sorted(result, key=lambda item: item["last_message_at"], reverse=True)
