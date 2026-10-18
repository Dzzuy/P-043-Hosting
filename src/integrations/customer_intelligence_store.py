"""Versioned customer snapshots and encrypted PII maps, shared by all customer views."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, Integer, String, Table, Text, delete, insert, select, update


def encoded(value):
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


def profile_confirmations(confirmations):
    result = {}
    for c in confirmations:
        if c["type"] != "profile_overrides":
            continue
        for field, fact in c["payload"].items():
            if (
                isinstance(fact, dict)
                and "value" in fact
                and fact.get("updated_at", "") >= result.get(field, {}).get("updated_at", "")
            ):
                result[field] = fact
    return result


def active_milestones(history):
    latest = {}
    for item in history:
        key = item.get("activity_id") or item.get("event_id") or item["id"]
        latest[key] = item
    return [item for item in latest.values() if not item.get("revoked")]


def define_tables(metadata):
    return {
        "heads": Table(
            "copilot_intelligence_heads",
            metadata,
            Column("customer_id", String(64), primary_key=True),
            Column("analysis_id", String(64)),
            Column("revision", Integer, nullable=False, default=0),
            Column("pii_mapping", Text, nullable=False),
        ),
        "analyses": Table(
            "copilot_intelligence_analyses",
            metadata,
            Column("id", String(64), primary_key=True),
            Column("customer_id", String(64), index=True),
            Column("previous_id", String(64)),
            Column("requested_at", DateTime(timezone=True)),
            Column("published_at", DateTime(timezone=True)),
            Column("payload_json", Text, nullable=False),
        ),
        "chat": Table(
            "copilot_intelligence_chat",
            metadata,
            Column("id", String(64), primary_key=True),
            Column("customer_id", String(64), index=True),
            Column("analysis_id", String(64), index=True),
            Column("advisor_id", String(120)),
            Column("created_at", DateTime(timezone=True)),
            Column("payload_json", Text, nullable=False),
        ),
        "proposals": Table(
            "copilot_activity_proposals",
            metadata,
            Column("id", String(64), primary_key=True),
            Column("customer_id", String(64), index=True),
            Column("analysis_id", String(64)),
            Column("fingerprint", String(64), unique=True),
            Column("status", String(24), nullable=False),
            Column("payload_json", Text, nullable=False),
            Column("created_at", DateTime(timezone=True)),
        ),
        "milestones": Table(
            "copilot_milestone_history",
            metadata,
            Column("id", String(64), primary_key=True),
            Column("customer_id", String(64), index=True),
            Column("activity_id", String(64), index=True),
            Column("actor_id", String(120)),
            Column("created_at", DateTime(timezone=True)),
            Column("payload_json", Text, nullable=False),
        ),
        "activity_details": Table(
            "copilot_activity_details",
            metadata,
            Column("task_id", String(64), primary_key=True),
            Column("location", Text, nullable=False),
        ),
    }


class IntelligenceStore:
    def __init__(self, repository):
        self.repo = repository
        repository.ensure_schema()
        self.tables = repository.intelligence_tables

    def authorize(self, customer_id, advisor_id):
        c = self.repo.get_customer(customer_id)
        if not c or c["advisor_id"] != advisor_id:
            raise LookupError("Không tìm thấy khách hàng.")
        return c

    def head(self, customer_id, conn=None):
        if conn is None:
            with self.repo.engine.connect() as connection:
                return self.head(customer_id, connection)
        row = (
            conn.execute(select(self.tables["heads"]).where(self.tables["heads"].c.customer_id == customer_id))
            .mappings()
            .first()
        )
        return dict(row) if row else {"analysis_id": None, "revision": 0, "pii_mapping": None}

    def all_messages(self, customer_id, conn=None):
        if conn is None:
            with self.repo.engine.connect() as connection:
                return self.all_messages(customer_id, connection)
        r = self.repo
        rows = conn.execute(
            select(r.messages)
            .join(r.conversations, r.conversations.c.id == r.messages.c.conversation_id)
            .where(r.conversations.c.customer_id == customer_id)
            .order_by(r.messages.c.sent_at, r.messages.c.conversation_id, r.messages.c.seq)
        ).mappings()
        return [{**dict(row), "sent_at": row["sent_at"].isoformat()} for row in rows]

    def analysis(self, customer_id, analysis_id=None, conn=None):
        if conn is None:
            with self.repo.engine.connect() as connection:
                return self.analysis(customer_id, analysis_id, connection)
        analysis_id = analysis_id or self.head(customer_id, conn)["analysis_id"]
        if not analysis_id:
            return None
        t = self.tables["analyses"]
        row = conn.execute(select(t).where(t.c.id == analysis_id, t.c.customer_id == customer_id)).mappings().first()
        if not row:
            raise LookupError("Không tìm thấy phiên phân tích.")
        return {
            "analysis_id": row["id"],
            "published_at": row["published_at"].isoformat(),
            "requested_at": row["requested_at"].isoformat(),
            **json.loads(row["payload_json"]),
        }

    def confirmations(self, customer_id, conn):
        r = self.repo
        rows = (
            conn.execute(
                select(r.recommendations)
                .join(r.conversations, r.conversations.c.id == r.recommendations.c.conversation_id)
                .where(
                    r.conversations.c.customer_id == customer_id,
                    r.recommendations.c.type.in_(("profile_overrides", "lead_stage_override")),
                )
                .order_by(r.recommendations.c.created_at, r.recommendations.c.id)
            )
            .mappings()
            .all()
        )
        return [{"id": x["id"], "type": x["type"], "payload": json.loads(x["payload_json"])} for x in rows]

    def capture(self, customer_id):
        with self.repo.engine.begin() as conn:
            conn.execute(
                select(self.repo.customers.c.id).where(self.repo.customers.c.id == customer_id).with_for_update()
            ).first()
            head = self.head(customer_id, conn)
            return {
                "head": head,
                "previous": self.analysis(customer_id, head["analysis_id"], conn),
                "messages": self.all_messages(customer_id, conn),
                "confirmations": self.confirmations(customer_id, conn),
                "requested_at": datetime.now(UTC),
            }

    def status(self, customer_id):
        current = self.analysis(customer_id)
        signatures = current.get("message_hashes", {}) if current else {}
        r = self.repo
        with r.engine.connect() as conn:
            # Counting arrivals must not read their message bodies.
            identifiers = set(
                conn.execute(
                    select(r.messages.c.id)
                    .join(r.conversations, r.conversations.c.id == r.messages.c.conversation_id)
                    .where(r.conversations.c.customer_id == customer_id)
                ).scalars()
            )
            old_rows = (
                conn.execute(select(r.messages).where(r.messages.c.id.in_(list(signatures)))).mappings().all()
                if signatures
                else []
            )
        changed_old = sum(
            signatures[row["id"]] != message_hash({**row, "sent_at": row["sent_at"].isoformat()}) for row in old_rows
        )
        changed = len(identifiers - set(signatures)) + changed_old
        return {
            "analysis_id": current["analysis_id"] if current else None,
            "published_at": current["published_at"] if current else None,
            "pending_message_count": changed,
            "requires_reanalysis": bool(set(signatures) - identifiers) or bool(changed_old),
            "intelligence": {k: v for k, v in current.items() if k not in ("messages", "message_hashes")}
            if current
            else None,
        }

    def stage_history(self, customer_id):
        with self.repo.engine.connect() as conn:
            t = self.tables["analyses"]
            records = [
                {
                    "at": row["published_at"].isoformat(),
                    "analysis_id": row["id"],
                    "stage": json.loads(row["payload_json"])["stage"],
                }
                for row in conn.execute(select(t).where(t.c.customer_id == customer_id)).mappings()
            ]
            for c in self.confirmations(customer_id, conn):
                if c["type"] == "lead_stage_override":
                    records.append({"at": c["payload"].get("updated_at", ""), "stage": c["payload"], "source": "sales"})
        return sorted(records, key=lambda r: r["at"])

    def save_chat(self, customer_id, advisor_id, analysis_id, query, result, pii, head, model_context=None):
        with self.repo.engine.begin() as conn:
            if pii.has_new_tokens:
                t = self.tables["heads"]
                if not head["revision"]:
                    conn.execute(insert(t).values(customer_id=customer_id, revision=1, pii_mapping=pii.encrypt()))
                else:
                    updated = conn.execute(
                        update(t)
                        .where(t.c.customer_id == customer_id, t.c.revision == head["revision"])
                        .values(pii_mapping=pii.encrypt(), revision=head["revision"] + 1)
                    )
                    if not updated.rowcount:
                        raise ValueError("Phiên đã thay đổi, vui lòng thử lại.")
            conn.execute(
                insert(self.tables["chat"]).values(
                    id=uuid4().hex,
                    customer_id=customer_id,
                    analysis_id=analysis_id,
                    advisor_id=advisor_id,
                    created_at=datetime.now(UTC),
                    payload_json=encoded({"query": query, **result, "_model_context": model_context}),
                )
            )

    def save_mapping(self, customer_id, pii, head):
        if not pii.has_new_tokens:
            return
        with self.repo.engine.begin() as conn:
            t = self.tables["heads"]
            if not head["revision"]:
                conn.execute(insert(t).values(customer_id=customer_id, revision=1, pii_mapping=pii.encrypt()))
            else:
                updated = conn.execute(
                    update(t)
                    .where(t.c.customer_id == customer_id, t.c.revision == head["revision"])
                    .values(pii_mapping=pii.encrypt(), revision=head["revision"] + 1)
                )
                if not updated.rowcount:
                    raise ValueError("Dữ liệu đã thay đổi. Hãy thử lại.")

    def chats(self, customer_id):
        t = self.tables["chat"]
        with self.repo.engine.connect() as conn:
            return [
                {
                    "created_at": row["created_at"].isoformat(),
                    **{k: v for k, v in json.loads(row["payload_json"]).items() if k != "_model_context"},
                }
                for row in conn.execute(
                    select(t).where(t.c.customer_id == customer_id).order_by(t.c.created_at)
                ).mappings()
            ]

    def model_chats(self, customer_id, analysis_id):
        t = self.tables["chat"]
        with self.repo.engine.connect() as conn:
            rows = (
                conn.execute(
                    select(t.c.payload_json)
                    .where(t.c.customer_id == customer_id, t.c.analysis_id == analysis_id)
                    .order_by(t.c.created_at.desc())
                    .limit(6)
                )
                .scalars()
                .all()
            )
        return [item["_model_context"] for row in reversed(rows) if (item := json.loads(row)).get("_model_context")]

    def review(self, customer_id, advisor_id, proposal_id, approve, edits):
        """Approve/reject atomically with the official activity mutation."""
        from src.services.sales_agenda_service import aware, validate_interval

        self.authorize(customer_id, advisor_id)
        r, t = self.repo, self.tables["proposals"]
        with r.engine.begin() as conn:
            conn.execute(select(r.customers.c.id).where(r.customers.c.id == customer_id).with_for_update()).first()
            row = (
                conn.execute(select(t).where(t.c.id == proposal_id, t.c.customer_id == customer_id).with_for_update())
                .mappings()
                .first()
            )
            if not row:
                raise LookupError("Không tìm thấy đề xuất.")
            if row["status"] != "pending":
                raise ValueError("Đề xuất đã được xử lý.")
            p = json.loads(row["payload_json"])
            if approve:
                snapshot = self.analysis(customer_id, row["analysis_id"], conn)
                signatures = snapshot["message_hashes"]
                for evidence in p["evidence"]:
                    message = (
                        conn.execute(select(r.messages).where(r.messages.c.id == evidence["message_id"]))
                        .mappings()
                        .first()
                    )
                    if not message or signatures.get(message["id"]) != message_hash(
                        {**message, "sent_at": message["sent_at"].isoformat()}
                    ):
                        raise ValueError("Tin nguồn đã thay đổi. Cần phân tích lại trước khi duyệt.")
                op = p["operation"]
                now = datetime.now(UTC)
                allowed = {
                    k: v
                    for k, v in edits.items()
                    if k in ("title", "starts_at", "ends_at", "location", "description", "item_type", "priority")
                }
                if "location" in allowed:
                    allowed["location"] = allowed["location"].strip()

                def date_value(value):
                    return datetime.fromisoformat(value) if isinstance(value, str) else value

                if op in ("update", "cancel"):
                    task = (
                        conn.execute(
                            select(r.tasks)
                            .where(r.tasks.c.id == p["target_task_id"], r.tasks.c.customer_id == customer_id)
                            .with_for_update()
                        )
                        .mappings()
                        .first()
                    )
                    if not task:
                        raise LookupError("Không tìm thấy công việc đích.")
                    tid = task["id"]
                    changes = {"status": "cancelled"} if op == "cancel" else allowed.copy()
                    location = changes.pop("location", None)
                    start = date_value(changes.get("starts_at", aware(task["starts_at"])))
                    end = date_value(changes.get("ends_at", aware(task["ends_at"])))
                    kind = changes.get("item_type", task["item_type"])
                    validate_interval(start, end, required=kind == "appointment" and op != "cancel")
                    if op != "cancel":
                        changes.update(starts_at=start, ends_at=end)
                    conn.execute(update(r.tasks).where(r.tasks.c.id == tid).values(**changes))
                else:
                    kind = allowed.get("item_type", "appointment" if p["event_type"] == "appointment" else "task")
                    start, end = (
                        date_value(allowed.get("starts_at", p["starts_at"])),
                        date_value(allowed.get("ends_at", p["ends_at"])),
                    )
                    location = allowed.get("location", p["location"])
                    validate_interval(start, end, required=kind == "appointment")
                    if kind == "appointment" and not location.strip():
                        raise ValueError("Lịch hẹn cần địa điểm.")
                    tid = uuid4().hex
                    mid = p["evidence"][0]["message_id"]
                    cid = conn.execute(select(r.messages.c.conversation_id).where(r.messages.c.id == mid)).scalar_one()
                    conn.execute(
                        insert(r.tasks).values(
                            id=tid,
                            customer_id=customer_id,
                            conversation_id=cid,
                            owner_sales_id=advisor_id,
                            task_type=p.get("activity_kind", p["event_type"]),
                            title=allowed.get("title", p["action"]),
                            description=allowed.get("description", ""),
                            starts_at=start,
                            ends_at=end,
                            item_type=kind,
                            priority=allowed.get("priority", "medium"),
                            status="pending",
                            source_message_ids_json=encoded([e["message_id"] for e in p["evidence"]]),
                            created_at=now,
                        )
                    )
                if op == "update" and kind == "appointment":
                    d = self.tables["activity_details"]
                    saved_location = conn.execute(select(d.c.location).where(d.c.task_id == tid)).scalar()
                    if not (location if location is not None else saved_location):
                        raise ValueError("Lịch hẹn cần địa điểm.")
                if location is not None:
                    d = self.tables["activity_details"]
                    conn.execute(delete(d).where(d.c.task_id == tid))
                    conn.execute(insert(d).values(task_id=tid, location=location))
                p["approved_task_id"] = tid
                p["approved_edits"] = allowed
            conn.execute(
                update(t)
                .where(t.c.id == proposal_id)
                .values(status="approved" if approve else "rejected", payload_json=encoded(p))
            )
        return self.proposals(customer_id)

    def confirm_milestone(self, customer_id, advisor_id, event_id, revoke=False):
        self.authorize(customer_id, advisor_id)
        analysis = self.analysis(customer_id)
        event = next((e for e in (analysis or {}).get("events", []) if e["id"] == event_id), None)
        kinds = {
            "contacted",
            "needs_understood",
            "quote_sent",
            "test_drive_completed",
            "deposit_received",
            "contract_signed",
            "delivered",
        }
        if not event or event["event_type"] not in kinds or event["conditional"]:
            raise ValueError("Sự kiện không thể xác nhận thành milestone.")
        with self.repo.engine.begin() as conn:
            conn.execute(
                select(self.repo.customers.c.id).where(self.repo.customers.c.id == customer_id).with_for_update()
            ).first()
            t = self.tables["milestones"]
            activity_id = event.get("target_task_id")
            if (
                activity_id
                and not conn.execute(
                    select(self.repo.tasks.c.id).where(
                        self.repo.tasks.c.id == activity_id, self.repo.tasks.c.customer_id == customer_id
                    )
                ).first()
            ):
                raise ValueError("Công việc không thuộc khách hàng.")
            latest = (
                conn.execute(select(t.c.payload_json).where(t.c.customer_id == customer_id).order_by(t.c.created_at))
                .scalars()
                .all()
            )
            matching = [item for p in latest if (item := json.loads(p)).get("event_id") == event_id]
            linked = (
                conn.execute(
                    select(t)
                    .where(t.c.customer_id == customer_id, t.c.activity_id == activity_id)
                    .order_by(t.c.created_at.desc())
                )
                .mappings()
                .first()
                if activity_id
                else None
            )
            duplicate = linked and json.loads(linked["payload_json"]).get("revoked", False) == revoke
            duplicate = duplicate or (matching and matching[-1].get("revoked", False) == revoke)
            if not duplicate:
                conn.execute(
                    insert(t).values(
                        id=uuid4().hex,
                        customer_id=customer_id,
                        actor_id=advisor_id,
                        activity_id=activity_id,
                        created_at=datetime.now(UTC),
                        payload_json=encoded(
                            {**event, "event_id": event_id, "revoked": revoke, "confirmed_by": "sales"}
                        ),
                    )
                )
        return self.milestone_history(customer_id)

    def publish(self, customer_id, capture, payload, encrypted_mapping, proposals):
        r, t = self.repo, self.tables
        now, aid = datetime.now(UTC), uuid4().hex
        with r.engine.begin() as conn:
            # All customer mutations serialize on the customer, including profile/stage edits.
            conn.execute(select(r.customers.c.id).where(r.customers.c.id == customer_id).with_for_update()).first()
            head = self.head(customer_id, conn)
            if (
                head["revision"] != capture["head"]["revision"]
                or self.confirmations(customer_id, conn) != capture["confirmations"]
            ):
                raise ValueError("Dữ liệu đã thay đổi. Hãy phân tích lại.")
            current = {m["id"]: m for m in self.all_messages(customer_id, conn)}
            if any(
                m["id"] not in current or message_hash(m) != message_hash(current[m["id"]]) for m in capture["messages"]
            ):
                raise ValueError("Tin nhắn đã được sửa hoặc xóa. Hãy phân tích lại.")
            conn.execute(
                insert(t["analyses"]).values(
                    id=aid,
                    customer_id=customer_id,
                    previous_id=head["analysis_id"],
                    requested_at=capture["requested_at"],
                    published_at=now,
                    payload_json=encoded(payload),
                )
            )
            if head["revision"]:
                updated = conn.execute(
                    update(t["heads"])
                    .where(t["heads"].c.customer_id == customer_id, t["heads"].c.revision == head["revision"])
                    .values(analysis_id=aid, revision=head["revision"] + 1, pii_mapping=encrypted_mapping)
                )
                if not updated.rowcount:
                    raise ValueError("Phiên đã thay đổi. Hãy phân tích lại.")
            else:
                conn.execute(
                    insert(t["heads"]).values(
                        customer_id=customer_id, analysis_id=aid, revision=1, pii_mapping=encrypted_mapping
                    )
                )
            # Compatibility read projections are committed together with the authoritative snapshot.
            conn.execute(delete(r.snapshots).where(r.snapshots.c.customer_id == customer_id))
            conn.execute(
                insert(r.snapshots).values(
                    customer_id=customer_id, snapshot_json=encoded(payload["profile"]), updated_at=now
                )
            )
            projected_stage = (
                payload["stage"].get("ai_stage", payload["stage"]["stage"])
                if payload["stage"].get("stage_source") == "sales"
                else payload["stage"]["stage"]
            )
            stage_values = {
                "stage": projected_stage or "unknown",
                "rationale": payload["stage"]["rationale"],
                "updated_at": now,
            }
            existing_stage = conn.execute(
                select(r.lead_scores.c.customer_id).where(r.lead_scores.c.customer_id == customer_id)
            ).first()
            if existing_stage:
                # Keep obsolete score columns for migration/audit; never expose or recompute them.
                conn.execute(
                    update(r.lead_scores).where(r.lead_scores.c.customer_id == customer_id).values(**stage_values)
                )
            else:
                conn.execute(
                    insert(r.lead_scores).values(
                        customer_id=customer_id, score=0, action_priority="medium", breakdown_json="[]", **stage_values
                    )
                )
            for cid, seq in payload["watermarks"].items():
                memory = {
                    "quick_summary": payload["recap"],
                    "detailed_summary": "",
                    # Official timelines are projected from the milestone audit.
                    # Extracted (unconfirmed) events remain only in the analysis.
                    "timeline_json": "[]",
                    "pending_items_json": encoded(
                        [p["question"] or p["topic"] for p in payload["topics"] if p["status"] == "open"]
                    ),
                    "key_promises_json": "[]",
                    "version": head["revision"] + 1,
                    "updated_at": now,
                }
                conn.execute(delete(r.memories).where(r.memories.c.conversation_id == cid))
                conn.execute(insert(r.memories).values(conversation_id=cid, **memory))
                conn.execute(
                    update(r.conversations)
                    .where(r.conversations.c.id == cid)
                    .values(last_analyzed_at=now, analysis_version=head["revision"] + 1)
                )
                ci = {
                    "key_points": [
                        {**p, "source_message_ids": [e["message_id"] for e in p["evidence"]]} for p in payload["topics"]
                    ],
                    "outcomes": [],
                    "commitments": [],
                }
                conn.execute(
                    insert(r.recommendations).values(
                        id=uuid4().hex,
                        conversation_id=cid,
                        type="analysis_context",
                        payload_json=encoded(
                            {
                                "version": head["revision"] + 1,
                                "through_seq": seq,
                                "stage": payload["stage"],
                                "customer_intelligence": ci,
                            }
                        ),
                        status="generated",
                        created_at=now,
                    )
                )
            for p in proposals:
                identity = {
                    "event_type": p["event_type"],
                    "activity_kind": p.get("activity_kind"),
                    "operation": p["operation"],
                    "target_task_id": p.get("target_task_id"),
                    "evidence": sorted(e["message_id"] for e in p["evidence"]),
                }
                fingerprint = hashlib.sha256(encoded([customer_id, identity]).encode()).hexdigest()
                if not conn.execute(
                    select(t["proposals"].c.id).where(t["proposals"].c.fingerprint == fingerprint)
                ).first():
                    conn.execute(
                        insert(t["proposals"]).values(
                            id=uuid4().hex,
                            customer_id=customer_id,
                            analysis_id=aid,
                            fingerprint=fingerprint,
                            status="pending",
                            payload_json=encoded(p),
                            created_at=now,
                        )
                    )
        return self.analysis(customer_id, aid)

    def proposals(self, customer_id):
        t = self.tables["proposals"]
        with self.repo.engine.connect() as conn:
            return [
                {
                    **(payload := json.loads(row["payload_json"])),
                    "event_id": payload.get("id"),
                    "id": row["id"],
                    "analysis_id": row["analysis_id"],
                    "status": row["status"],
                }
                for row in conn.execute(
                    select(t).where(t.c.customer_id == customer_id).order_by(t.c.created_at)
                ).mappings()
            ]

    def milestone_history(self, customer_id, conn=None):
        t = self.tables["milestones"]
        if conn is None:
            with self.repo.engine.connect() as connection:
                return self.milestone_history(customer_id, connection)
        return [
            {
                **json.loads(x["payload_json"]),
                "id": x["id"],
                "activity_id": x["activity_id"],
                "actor_id": x["actor_id"],
                "created_at": x["created_at"].isoformat(),
            }
            for x in conn.execute(select(t).where(t.c.customer_id == customer_id).order_by(t.c.created_at)).mappings()
        ]


def message_hash(message):
    return hashlib.sha256(
        encoded({k: message[k] for k in ("id", "content", "sent_at", "sender_role", "conversation_id", "seq")}).encode()
    ).hexdigest()
