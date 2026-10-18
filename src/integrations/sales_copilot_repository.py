"""PostgreSQL-backed persistence adapter for AI Sales Copilot.

Stores customers, conversations, 2-sided chat messages, customer profile facts,
rolling conversation memories, smart follow-up tasks, lead scores, and sales preferences.
"""

from __future__ import annotations

import json
import logging
from contextlib import nullcontext
from datetime import UTC, datetime
from threading import Lock
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    desc,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Connection, Engine

from src.integrations.practice_persistence import normalize_database_url
from src.models.sales_copilot import (
    ChatMessageResponse,
    CustomerFact,
    CustomerProfileSnapshot,
    CustomerResponse,
    FollowupTask,
    LeadStage,
    LeadStatus,
    SalesPreferences,
    SenderRole,
    TaskStatus,
)

logger = logging.getLogger(__name__)


class SQLSalesCopilotRepository:
    def __init__(self, database_url: str, *, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(normalize_database_url(database_url), pool_pre_ping=True)
        self.metadata = MetaData()

        self.customers = Table(
            "copilot_customers",
            self.metadata,
            Column("id", String(64), primary_key=True),
            Column("name", String(120), nullable=False),
            Column("phone", String(30), nullable=True),
            Column("email", String(120), nullable=True),
            Column("location", String(120), nullable=True),
            Column("advisor_id", String(120), nullable=False, index=True),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=True),
        )

        self.conversations = Table(
            "copilot_conversations",
            self.metadata,
            Column("id", String(64), primary_key=True),
            Column("customer_id", String(64), ForeignKey("copilot_customers.id"), nullable=False, index=True),
            Column("last_analyzed_at", DateTime(timezone=True), nullable=True),
            Column("analysis_version", Integer, default=0, nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
        )

        self.messages = Table(
            "copilot_chat_messages",
            self.metadata,
            Column("id", String(64), primary_key=True),
            Column("conversation_id", String(64), ForeignKey("copilot_conversations.id"), nullable=False, index=True),
            Column("sender_role", String(20), nullable=False),
            Column("content", Text, nullable=False),
            Column("seq", Integer, nullable=False),
            Column("sent_at", DateTime(timezone=True), nullable=False),
        )

        self.snapshots = Table(
            "copilot_customer_snapshots",
            self.metadata,
            Column("customer_id", String(64), primary_key=True),
            Column("snapshot_json", Text, nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
        )

        self.memories = Table(
            "copilot_memories",
            self.metadata,
            Column("conversation_id", String(64), primary_key=True),
            Column("quick_summary", Text, default="", nullable=False),
            Column("detailed_summary", Text, default="", nullable=False),
            Column("timeline_json", Text, default="[]", nullable=False),
            Column("pending_items_json", Text, default="[]", nullable=False),
            Column("key_promises_json", Text, default="[]", nullable=False),
            Column("version", Integer, default=1, nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
        )

        self.tasks = Table(
            "copilot_followup_tasks",
            self.metadata,
            Column("id", String(64), primary_key=True),
            Column("customer_id", String(64), nullable=True, index=True),
            Column("conversation_id", String(64), nullable=True, index=True),
            Column("owner_sales_id", String(120), nullable=False, index=True),
            Column("task_type", String(50), nullable=False),
            Column("title", String(255), nullable=False),
            Column("description", Text, nullable=False),
            Column("due_at", DateTime(timezone=True), nullable=True),
            Column("due_window", String(100), nullable=True),
            Column("starts_at", DateTime(timezone=True), nullable=True),
            Column("ends_at", DateTime(timezone=True), nullable=True),
            Column("item_type", String(20), nullable=False, server_default="task"),
            Column("priority", String(20), default="medium", nullable=False),
            Column("status", String(30), default="pending", nullable=False),
            Column("source_message_ids_json", Text, default="[]", nullable=False),
            Column("dedupe_key", String(120), nullable=True, index=True),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("completed_at", DateTime(timezone=True), nullable=True),
            CheckConstraint("(starts_at IS NULL AND ends_at IS NULL) OR (starts_at IS NOT NULL AND ends_at IS NOT NULL AND ends_at > starts_at)", name="ck_copilot_task_interval"),
            CheckConstraint("item_type IN ('task', 'appointment')", name="ck_copilot_task_item_type"),
            Index("ix_copilot_tasks_owner_schedule", "owner_sales_id", "starts_at", "ends_at"),
        )

        self.lead_scores = Table(
            "copilot_lead_scores",
            self.metadata,
            Column("customer_id", String(64), primary_key=True),
            Column("stage", String(40), default="discovery", nullable=False),
            Column("score", Integer, default=0, nullable=False),
            Column("action_priority", String(20), default="medium", nullable=False),
            Column("rationale", Text, default="", nullable=False),
            Column("breakdown_json", Text, default="[]", nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
        )

        self.preferences = Table(
            "copilot_sales_preferences",
            self.metadata,
            Column("advisor_id", String(120), primary_key=True),
            Column("nba_enabled", Boolean, default=False, nullable=False),
            Column("draft_enabled", Boolean, default=False, nullable=False),
            Column("notifications_enabled", Boolean, default=True, nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
        )

        self.recommendations = Table(
            "copilot_recommendations_and_drafts",
            self.metadata,
            Column("id", String(64), primary_key=True),
            Column("conversation_id", String(64), nullable=False, index=True),
            Column("type", String(30), nullable=False),
            Column("payload_json", Text, nullable=False),
            Column("status", String(30), default="generated", nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False),
        )

        from src.integrations.customer_intelligence_store import define_tables
        self.intelligence_tables = define_tables(self.metadata)
        self._ready = False
        self._lock = Lock()

    def ensure_schema(self) -> None:
        if not self._ready:
            with self._lock:
                if not self._ready:
                    self.metadata.create_all(self.engine)
                    from src.integrations.intelligence_migration import migrate_appointment_stages
                    migrate_appointment_stages(self)
                    self._ready = True

    # -------------------------------------------------------------
    # Customer Operations
    # -------------------------------------------------------------
    def create_customer(
        self,
        name: str,
        advisor_id: str,
        *,
        customer_id: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        location: str | None = None,
    ) -> str:
        self.ensure_schema()
        cid = customer_id or uuid4().hex
        now = datetime.now(UTC)
        with self.engine.begin() as conn:
            conn.execute(
                insert(self.customers).values(
                    id=cid,
                    name=name,
                    phone=phone,
                    email=email,
                    location=location,
                    advisor_id=advisor_id,
                    created_at=now,
                    updated_at=now,
                )
            )
        return cid

    def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        self.ensure_schema()
        with self.engine.connect() as conn:
            row = conn.execute(
                select(self.customers).where(self.customers.c.id == customer_id)
            ).mappings().first()
        return dict(row) if row else None

    def list_customers_for_advisor(self, advisor_id: str) -> list[CustomerResponse]:
        self.ensure_schema()
        with self.engine.connect() as conn:
            query = select(self.customers).where(self.customers.c.advisor_id == advisor_id)
            rows = conn.execute(query).mappings().all()
            results = []
            for r in rows:
                cid = r["id"]
                # get score
                score_row = conn.execute(
                    select(self.lead_scores).where(self.lead_scores.c.customer_id == cid)
                ).mappings().first()
                lead_stage = (LeadStage(score_row["stage"]) if score_row["stage"] in LeadStage._value2member_map_ else None) if score_row else LeadStage.NEW

                # get pending tasks count
                pending_count = conn.execute(
                    select(self.tasks).where(
                        self.tasks.c.customer_id == cid,
                        self.tasks.c.status == TaskStatus.PENDING,
                    )
                ).fetchall()

                # get snapshot models
                snap_row = conn.execute(
                    select(self.snapshots).where(self.snapshots.c.customer_id == cid)
                ).mappings().first()
                interested = []
                if snap_row:
                    try:
                        snap_data = json.loads(snap_row["snapshot_json"])
                        interested = snap_data.get("interested_models", [])
                    except Exception:
                        pass

                results.append(
                    CustomerResponse(
                        id=cid,
                        name=r["name"],
                        phone=r["phone"],
                        email=r["email"],
                        location=r["location"],
                        advisor_id=r["advisor_id"],
                        created_at=r["created_at"],
                        updated_at=r["updated_at"],
                        lead_stage=lead_stage,
                        pending_tasks_count=len(pending_count),
                        interested_models=interested,
                    )
                )
            return results

    # -------------------------------------------------------------
    # Conversation & Message Operations
    # -------------------------------------------------------------
    def get_or_create_conversation(self, customer_id: str) -> str:
        self.ensure_schema()
        with self.engine.begin() as conn:
            existing = conn.execute(
                select(self.conversations.c.id).where(self.conversations.c.customer_id == customer_id)
            ).scalar()
            if existing:
                return existing

            conv_id = uuid4().hex
            now = datetime.now(UTC)
            conn.execute(
                insert(self.conversations).values(
                    id=conv_id,
                    customer_id=customer_id,
                    analysis_version=0,
                    created_at=now,
                    updated_at=now,
                )
            )
            return conv_id

    def add_message(
        self,
        conversation_id: str,
        sender_role: SenderRole | str,
        content: str,
        sent_at: datetime | None = None,
        message_id: str | None = None,
    ) -> ChatMessageResponse:
        self.ensure_schema()
        now = sent_at or datetime.now(UTC)
        mid = message_id or uuid4().hex
        role_str = sender_role.value if isinstance(sender_role, SenderRole) else str(sender_role)

        with self.engine.begin() as conn:
            # find max seq
            last_seq = conn.execute(
                select(self.messages.c.seq)
                .where(self.messages.c.conversation_id == conversation_id)
                .order_by(desc(self.messages.c.seq))
                .limit(1)
            ).scalar()
            next_seq = (last_seq or 0) + 1

            conn.execute(
                insert(self.messages).values(
                    id=mid,
                    conversation_id=conversation_id,
                    sender_role=role_str,
                    content=content,
                    seq=next_seq,
                    sent_at=now,
                )
            )
            conn.execute(
                update(self.conversations)
                .where(self.conversations.c.id == conversation_id)
                .values(updated_at=now)
            )

        return ChatMessageResponse(
            id=mid,
            conversation_id=conversation_id,
            sender_role=SenderRole(role_str),
            content=content,
            seq=next_seq,
            sent_at=now,
        )

    def add_messages_batch(
        self,
        conversation_id: str,
        messages_data: list[dict[str, Any]],
    ) -> list[ChatMessageResponse]:
        self.ensure_schema()
        if not messages_data:
            return []

        now = datetime.now(UTC)
        insert_rows = []
        response_items = []

        with self.engine.begin() as conn:
            last_seq = conn.execute(
                select(self.messages.c.seq)
                .where(self.messages.c.conversation_id == conversation_id)
                .order_by(desc(self.messages.c.seq))
                .limit(1)
            ).scalar() or 0

            for idx, item in enumerate(messages_data, start=1):
                mid = item.get("id") or uuid4().hex
                role = item["sender_role"]
                role_str = role.value if isinstance(role, SenderRole) else str(role)
                content = item["content"]
                sent_at = item.get("sent_at") or now
                seq = last_seq + idx

                insert_rows.append({
                    "id": mid,
                    "conversation_id": conversation_id,
                    "sender_role": role_str,
                    "content": content,
                    "seq": seq,
                    "sent_at": sent_at,
                })
                response_items.append(
                    ChatMessageResponse(
                        id=mid,
                        conversation_id=conversation_id,
                        sender_role=SenderRole(role_str),
                        content=content,
                        seq=seq,
                        sent_at=sent_at,
                    )
                )

            conn.execute(insert(self.messages), insert_rows)
            conn.execute(
                update(self.conversations)
                .where(self.conversations.c.id == conversation_id)
                .values(updated_at=now)
            )

        return response_items

    def customer_override_scope(self, outer=None):
        outer = outer if outer is not None else self.conversations
        scope = self.conversations.alias("override_customer_conversations")
        return self.recommendations.c.conversation_id.in_(select(scope.c.id).where(
            scope.c.customer_id == outer.c.customer_id).correlate(outer))

    def get_conversation_metadata(self, conversation_id: str, *, connection: Connection) -> dict[str, Any] | None:
        """Read one-to-one sections together, without multiplying messages or tasks."""
        self.ensure_schema()
        def latest_payload(kind, *, break_ties=False):
            order = [self.recommendations.c.created_at.desc()]
            if break_ties:
                order.append(self.recommendations.c.id.desc())
            return (
                select(self.recommendations.c.payload_json)
                .where(self.customer_override_scope() if kind in ("profile_overrides", "lead_stage_override") else self.recommendations.c.conversation_id == self.conversations.c.id,
                       self.recommendations.c.type == kind)
                .order_by(*order).limit(1).correlate(self.conversations).scalar_subquery()
            )

        query = (
            select(
                self.conversations,
                self.customers.c.name.label("customer_name"), self.customers.c.location.label("customer_location"),
                self.snapshots.c.snapshot_json,
                *(column.label(f"memory_{column.name}") for column in self.memories.c),
                *(column.label(f"lead_{column.name}") for column in self.lead_scores.c),
                latest_payload("analysis_context", break_ties=True).label("analysis_context"),
                latest_payload("lead_stage_override").label("stage_override"),
                latest_payload("profile_overrides", break_ties=True).label("profile_overrides"),
                select(func.count()).where(self.messages.c.conversation_id == self.conversations.c.id)
                .correlate(self.conversations).scalar_subquery().label("message_total"),
                select(func.max(self.messages.c.seq)).where(self.messages.c.conversation_id == self.conversations.c.id)
                .correlate(self.conversations).scalar_subquery().label("last_message_seq"),
            ).select_from(
                self.conversations
                .outerjoin(self.customers, self.customers.c.id == self.conversations.c.customer_id)
                .outerjoin(self.snapshots, self.snapshots.c.customer_id == self.conversations.c.customer_id)
                .outerjoin(self.memories, self.memories.c.conversation_id == self.conversations.c.id)
                .outerjoin(self.lead_scores, self.lead_scores.c.customer_id == self.conversations.c.customer_id)
            ).where(self.conversations.c.id == conversation_id)
        )
        row = connection.execute(query).mappings().first()
        if row is None:
            return None
        memory = {column.name: row[f"memory_{column.name}"] for column in self.memories.c}
        memory["analysis_context"] = row["analysis_context"]
        lead = {column.name: row[f"lead_{column.name}"] for column in self.lead_scores.c}
        return {
            "record": {column.name: row[column.name] for column in self.conversations.c},
            "customer": {"name": row["customer_name"], "location": row["customer_location"]} if row["customer_name"] is not None else None,
            "profile": json.loads(row["snapshot_json"]) if row["snapshot_json"] else {},
            "memory": self._memory_data(memory) if memory["conversation_id"] is not None else {},
            "lead": self._lead_data(lead) if lead["customer_id"] is not None else {},
            "override": json.loads(row["stage_override"] or "{}"),
            "profile_overrides": json.loads(row["profile_overrides"] or "{}"),
            "message_total": row["message_total"],
            "last_message_seq": row["last_message_seq"] or 0,
        }

    def owned_conversation(self, conversation_id: str, owner_id: str):
        self.ensure_schema()
        with self.engine.connect() as connection:
            row = connection.execute(
                select(self.conversations.c.customer_id).join(
                    self.customers, self.customers.c.id == self.conversations.c.customer_id,
                ).where(self.conversations.c.id == conversation_id, self.customers.c.advisor_id == owner_id)
            ).mappings().first()
        if row is None:
            raise LookupError(conversation_id)
        return dict(row)

    def list_messages(self, conversation_id: str, *, limit: int | None = None, before_seq: int | None = None,
                      source_message_id: str | None = None, connection: Connection | None = None) -> list[ChatMessageResponse]:
        self.ensure_schema()
        with nullcontext(connection) if connection is not None else self.engine.connect() as conn:
            query = select(self.messages).where(self.messages.c.conversation_id == conversation_id)
            if before_seq is not None:
                query = query.where(self.messages.c.seq < before_seq)
            if source_message_id:
                source_seq = conn.execute(select(self.messages.c.seq).where(
                    self.messages.c.conversation_id == conversation_id, self.messages.c.id == source_message_id,
                )).scalar_one_or_none()
                if source_seq is None:
                    raise LookupError(source_message_id)
                query = query.where(self.messages.c.seq <= source_seq)
            query = query.order_by(self.messages.c.seq.desc() if limit else self.messages.c.seq.asc())
            if limit:
                query = query.limit(limit)
            rows = conn.execute(query).mappings().all()
            if limit:
                rows.reverse()

        return [
            ChatMessageResponse(
                id=r["id"],
                conversation_id=r["conversation_id"],
                sender_role=SenderRole(r["sender_role"]),
                content=r["content"],
                seq=r["seq"],
                sent_at=r["sent_at"],
            )
            for r in rows
        ]

    # -------------------------------------------------------------
    # Facts & Snapshot (F01)
    # -------------------------------------------------------------
    def save_facts_and_snapshot(
        self,
        customer_id: str,
        facts: list[CustomerFact],
        snapshot: CustomerProfileSnapshot,
    ) -> None:
        self.ensure_schema()
        now = datetime.now(UTC)
        if facts and not snapshot.facts:
            snapshot = snapshot.model_copy(update={"facts": list(facts)})
        with self.engine.begin() as conn:
            conn.execute(delete(self.snapshots).where(self.snapshots.c.customer_id == customer_id))
            conn.execute(
                insert(self.snapshots).values(
                    customer_id=customer_id,
                    snapshot_json=snapshot.model_dump_json(),
                    updated_at=now,
                )
            )

    def get_customer_snapshot(self, customer_id: str) -> dict[str, Any] | None:
        self.ensure_schema()
        with self.engine.connect() as conn:
            row = conn.execute(
                select(self.snapshots).where(self.snapshots.c.customer_id == customer_id)
            ).mappings().first()
            if row:
                return json.loads(row["snapshot_json"])
        return None

    # -------------------------------------------------------------
    # Memory (F02)
    # -------------------------------------------------------------
    def save_memory(
        self,
        conversation_id: str,
        quick_summary: str,
        detailed_summary: str,
        timeline: list[dict[str, Any]],
        pending_items: list[str],
        key_promises: list[str],
        analyzed_through_seq: int | None = None,
        customer_intelligence: dict[str, Any] | None = None,
    ) -> None:
        self.ensure_schema()
        now = datetime.now(UTC)
        with self.engine.begin() as conn:
            row = conn.execute(
                select(self.memories.c.version).where(self.memories.c.conversation_id == conversation_id)
            ).scalar()
            new_version = (row or 0) + 1

            conn.execute(delete(self.memories).where(self.memories.c.conversation_id == conversation_id))
            conn.execute(
                insert(self.memories).values(
                    conversation_id=conversation_id,
                    quick_summary=quick_summary,
                    detailed_summary=detailed_summary,
                    timeline_json=json.dumps(timeline, ensure_ascii=False),
                    pending_items_json=json.dumps(pending_items, ensure_ascii=False),
                    key_promises_json=json.dumps(key_promises, ensure_ascii=False),
                    version=new_version,
                    updated_at=now,
                )
            )
            # update conversation last analyzed time
            conn.execute(
                update(self.conversations)
                .where(self.conversations.c.id == conversation_id)
                .values(last_analyzed_at=now, analysis_version=new_version)
            )
            if analyzed_through_seq is not None or customer_intelligence is not None:
                conn.execute(insert(self.recommendations).values(
                    id=uuid4().hex,
                    conversation_id=conversation_id,
                    type="analysis_context",
                    # The versioned analysis payload is stored atomically with memory.
                    payload_json=json.dumps({"version": new_version, "through_seq": analyzed_through_seq,
                                             "customer_intelligence": customer_intelligence}, ensure_ascii=False),
                    status="generated",
                    created_at=now,
                ))

    def get_memory(self, conversation_id: str) -> dict[str, Any] | None:
        self.ensure_schema()
        context = (
            select(self.recommendations.c.payload_json)
            .where(self.recommendations.c.conversation_id == conversation_id,
                   self.recommendations.c.type == "analysis_context")
            .order_by(self.recommendations.c.created_at.desc(), self.recommendations.c.id.desc())
            .limit(1).scalar_subquery()
        )
        with self.engine.connect() as conn:
            row = conn.execute(
                select(self.memories, context.label("analysis_context"))
                .where(self.memories.c.conversation_id == conversation_id)
            ).mappings().first()
            if row:
                return self._memory_data(row)
        return None

    @staticmethod
    def _memory_data(row) -> dict[str, Any]:
        metadata = json.loads(row["analysis_context"] or "{}")
        return {
            "customer_intelligence": metadata.get("customer_intelligence") if metadata.get("version") == row["version"] else None,
            "analyzed_through_seq": metadata.get("through_seq") if metadata.get("version") == row["version"] else None,
            "stage": metadata.get("stage") if metadata.get("version") == row["version"] else None,
            "quick_summary": row["quick_summary"], "detailed_summary": row["detailed_summary"],
            "timeline": json.loads(row["timeline_json"]), "pending_items": json.loads(row["pending_items_json"]),
            "key_promises": json.loads(row["key_promises_json"]), "version": row["version"],
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }

    # -------------------------------------------------------------
    # Smart Follow-up Tasks (F05)
    # -------------------------------------------------------------
    def save_tasks(self, tasks: list[FollowupTask]) -> None:
        self.ensure_schema()
        now = datetime.now(UTC)
        with self.engine.begin() as conn:
            # Serialize dedupe checks across concurrent analysis requests on PostgreSQL.
            for conversation_id in sorted({task.conversation_id for task in tasks if task.conversation_id}):
                conn.execute(select(self.conversations.c.id).where(
                    self.conversations.c.id == conversation_id,
                ).with_for_update())
            for t in tasks:
                # check dedupe_key
                if t.dedupe_key:
                    existing = conn.execute(
                        select(self.tasks.c.id).where(self.tasks.c.dedupe_key == t.dedupe_key)
                    ).scalar()
                    if existing:
                        continue  # avoid duplicate task creation

                tid = t.id or uuid4().hex
                conn.execute(
                    insert(self.tasks).values(
                        id=tid,
                        customer_id=t.customer_id,
                        conversation_id=t.conversation_id,
                        owner_sales_id=t.owner_sales_id,
                        task_type=t.task_type,
                        title=t.title,
                        description=t.description,
                        due_at=t.due_at,
                        due_window=t.due_window,
                        starts_at=t.starts_at,
                        ends_at=t.ends_at,
                        item_type=t.item_type,
                        priority=t.priority.value if hasattr(t.priority, "value") else str(t.priority),
                        status=t.status.value if hasattr(t.status, "value") else str(t.status),
                        source_message_ids_json=json.dumps(t.source_message_ids),
                        dedupe_key=t.dedupe_key,
                        created_at=now,
                    )
                )

    def list_tasks_for_customer(self, customer_id: str, *, connection: Connection | None = None) -> list[dict[str, Any]]:
        self.ensure_schema()
        with nullcontext(connection) if connection is not None else self.engine.connect() as conn:
            details = self.intelligence_tables["activity_details"]
            rows = conn.execute(
                select(self.tasks, details.c.location).outerjoin(details, details.c.task_id == self.tasks.c.id)
                .where(self.tasks.c.customer_id == customer_id)
                .order_by(self.tasks.c.created_at.desc())
            ).mappings().all()

        return [
            {
                "id": r["id"],
                "customer_id": r["customer_id"],
                "conversation_id": r["conversation_id"],
                "owner_sales_id": r["owner_sales_id"],
                "task_type": r["task_type"],
                "title": r["title"],
                "description": r["description"],
                "due_at": r["due_at"].isoformat() if r["due_at"] else None,
                "due_window": r["due_window"],
                "starts_at": (r["starts_at"].replace(tzinfo=UTC) if r["starts_at"].tzinfo is None else r["starts_at"]).isoformat() if r["starts_at"] else None,
                "ends_at": (r["ends_at"].replace(tzinfo=UTC) if r["ends_at"].tzinfo is None else r["ends_at"]).isoformat() if r["ends_at"] else None,
                "item_type": r["item_type"],
                "location": r["location"] or "",
                "priority": r["priority"],
                "status": r["status"],
                "source_message_ids": json.loads(r["source_message_ids_json"]),
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]

    def owns_task(self, task_id: str, advisor_id: str) -> bool:
        self.ensure_schema()
        with self.engine.connect() as connection:
            return connection.execute(
                select(self.tasks.c.id).outerjoin(
                    self.customers, self.customers.c.id == self.tasks.c.customer_id,
                ).where(self.tasks.c.id == task_id, (
                    (self.customers.c.advisor_id == advisor_id) |
                    ((self.tasks.c.customer_id.is_(None)) & (self.tasks.c.owner_sales_id == advisor_id))
                ))
            ).scalar_one_or_none() is not None

    def update_task_status(self, task_id: str, status: TaskStatus | str) -> bool:
        self.ensure_schema()
        status_str = status.value if isinstance(status, TaskStatus) else str(status)
        now = datetime.now(UTC)
        completed_at = now if status_str == "completed" else None
        with self.engine.begin() as conn:
            res = conn.execute(
                update(self.tasks)
                .where(self.tasks.c.id == task_id)
                .values(status=status_str, completed_at=completed_at)
            )
            return res.rowcount > 0

    def edit_task(self, task_id: str, changes: dict[str, Any]) -> bool:
        self.ensure_schema()
        with self.engine.begin() as conn:
            return conn.execute(update(self.tasks).where(self.tasks.c.id == task_id).values(**changes)).rowcount > 0

    def save_profile_override(self, conversation_id: str, field: str, value: Any, advisor_id: str) -> None:
        """Serialize field edits and preserve confirmations across future AI analyses."""
        self.ensure_schema()
        customer_id = self.owned_conversation(conversation_id, advisor_id)["customer_id"]
        with self.engine.begin() as conn:
            conn.execute(select(self.customers.c.id).where(self.customers.c.id == select(
                self.conversations.c.customer_id).where(self.conversations.c.id == conversation_id).scalar_subquery()).with_for_update()).first()
            previous = conn.execute(select(self.recommendations.c.payload_json).where(
                self.recommendations.c.conversation_id.in_(select(self.conversations.c.id).where(self.conversations.c.customer_id == customer_id)),
                self.recommendations.c.type == "profile_overrides",
            ).order_by(self.recommendations.c.created_at.desc(), self.recommendations.c.id.desc()).limit(1)).scalar_one_or_none()
            overrides = json.loads(previous or "{}")
            overrides[field] = {"value": value, "advisor_id": advisor_id, "updated_at": datetime.now(UTC).isoformat()}
            conn.execute(insert(self.recommendations).values(
                id=uuid4().hex, conversation_id=conversation_id, type="profile_overrides",
                payload_json=json.dumps(overrides, ensure_ascii=False), status="confirmed", created_at=datetime.now(UTC),
            ))

    # -------------------------------------------------------------
    # Lead Classification & Scoring (F06)
    # -------------------------------------------------------------
    def save_lead_score(self, status: LeadStatus) -> None:
        self.ensure_schema()
        now = datetime.now(UTC)
        with self.engine.begin() as conn:
            conn.execute(delete(self.lead_scores).where(self.lead_scores.c.customer_id == status.customer_id))
            conn.execute(
                insert(self.lead_scores).values(
                    customer_id=status.customer_id,
                    stage=status.stage.value if hasattr(status.stage, "value") else str(status.stage),
                    score=0,
                    action_priority="medium",
                    rationale=status.rationale,
                    breakdown_json="[]",
                    updated_at=now,
                )
            )

    def get_lead_score(self, customer_id: str) -> dict[str, Any] | None:
        self.ensure_schema()
        with self.engine.connect() as conn:
            row = conn.execute(
                select(self.lead_scores).where(self.lead_scores.c.customer_id == customer_id)
            ).mappings().first()
            if row:
                return self._lead_data(row)
        return None

    @staticmethod
    def _lead_data(row) -> dict[str, Any]:
        return {
            "customer_id": row["customer_id"], "stage": row["stage"] if row["stage"] in LeadStage._value2member_map_ else None,
            "rationale": row["rationale"],
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }

    # -------------------------------------------------------------
    # Sales Preferences (Feature Flags F03 & F04)
    # -------------------------------------------------------------
    def get_preferences(self, advisor_id: str) -> SalesPreferences:
        self.ensure_schema()
        with self.engine.connect() as conn:
            row = conn.execute(
                select(self.preferences).where(self.preferences.c.advisor_id == advisor_id)
            ).mappings().first()
            if row:
                return SalesPreferences(
                    advisor_id=row["advisor_id"],
                    draft_enabled=row["draft_enabled"],
                    notifications_enabled=row["notifications_enabled"],
                )
        return SalesPreferences(advisor_id=advisor_id, draft_enabled=False, notifications_enabled=True)

    def update_preferences(self, prefs: SalesPreferences) -> SalesPreferences:
        self.ensure_schema()
        now = datetime.now(UTC)
        with self.engine.begin() as conn:
            conn.execute(delete(self.preferences).where(self.preferences.c.advisor_id == prefs.advisor_id))
            conn.execute(
                insert(self.preferences).values(
                    advisor_id=prefs.advisor_id,
                    nba_enabled=False,
                    draft_enabled=prefs.draft_enabled,
                    notifications_enabled=prefs.notifications_enabled,
                    updated_at=now,
                )
            )
        return prefs

    # -------------------------------------------------------------
    # Recommendations & Drafts Cache
    # -------------------------------------------------------------
    def save_recommendation_or_draft(
        self,
        conversation_id: str,
        rec_type: str,
        payload: dict[str, Any],
    ) -> str:
        self.ensure_schema()
        now = datetime.now(UTC)
        rid = uuid4().hex
        with self.engine.begin() as conn:
            if rec_type == "lead_stage_override":
                conn.execute(select(self.customers.c.id).where(self.customers.c.id == select(
                    self.conversations.c.customer_id).where(self.conversations.c.id == conversation_id).scalar_subquery()).with_for_update()).first()
            conn.execute(
                insert(self.recommendations).values(
                    id=rid,
                    conversation_id=conversation_id,
                    type=rec_type,
                    payload_json=json.dumps(payload, ensure_ascii=False, default=str),
                    status="generated",
                    created_at=now,
                )
            )
        return rid

    def get_latest_recommendation(self, conversation_id: str, rec_type: str) -> dict[str, Any] | None:
        self.ensure_schema()
        with self.engine.connect() as conn:
            row = conn.execute(
                select(self.recommendations)
                .where(
                    self.recommendations.c.conversation_id == conversation_id,
                    self.recommendations.c.type == rec_type,
                )
                .order_by(self.recommendations.c.created_at.desc())
                .limit(1)
            ).mappings().first()
            if row:
                return json.loads(row["payload_json"])
        return None
