"""Personal sales agenda and read-only dashboard; no analysis or chat history loading."""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, delete, func, insert, or_, select, update

from src.models.sales_copilot import FollowupTask

TIMEZONE = "Asia/Ho_Chi_Minh"
TZ = ZoneInfo(TIMEZONE)
ACTIVE = ("pending", "in_progress")


def aware(value: datetime | None) -> datetime | None:
    # Legacy SQLite / historical timestamps represent UTC when no offset is present.
    return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


def validate_interval(start, end, *, required=False):
    if not start and not end and not required:
        return
    if not start or not end:
        raise ValueError("Cần nhập cả giờ bắt đầu và kết thúc.")
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("Thời gian phải có múi giờ.")
    if end <= start:
        raise ValueError("Giờ kết thúc phải sau giờ bắt đầu.")


def decoded(value, default):
    try:
        result = json.loads(value or "null")
        return result if isinstance(result, type(default)) else default
    except (ValueError, TypeError):
        return default


def task_payload(row):
    data = dict(row)
    data["source_message_ids"] = decoded(data.pop("source_message_ids_json", None), [])
    for key in ("starts_at", "ends_at", "due_at", "created_at", "completed_at"):
        if isinstance(data.get(key), datetime):
            data[key] = aware(data[key]).astimezone(UTC).isoformat()
    return data


class SalesAgendaService:
    def __init__(self, repository):
        self.repo = repository
        self.repo.ensure_schema()
        self.tasks = repository.tasks

    def _scope(self, advisor_id):
        t, c = self.tasks.c, self.repo.customers.c
        return and_(t.owner_sales_id == advisor_id,
                    or_(t.customer_id.is_(None), c.advisor_id == advisor_id))

    def _task_query(self, advisor_id):
        details = self.repo.intelligence_tables["activity_details"]
        return select(self.tasks, self.repo.customers.c.name.label("customer_name"), details.c.location).outerjoin(
            self.repo.customers, self.repo.customers.c.id == self.tasks.c.customer_id,
        ).outerjoin(details, details.c.task_id == self.tasks.c.id).where(self._scope(advisor_id))

    def create(self, advisor_id, values, *, conversation_id=None):
        values = dict(values)
        values.setdefault("description", "")
        appointment = values.get("item_type") == "appointment"
        location = values.pop("location", "").strip()
        validate_interval(values.get("starts_at"), values.get("ends_at"), required=appointment)
        if appointment and not location:
            raise ValueError("Lịch hẹn cần địa điểm.")
        for key in ("starts_at", "ends_at"):
            values[key] = values[key].astimezone(UTC) if values.get(key) else None
        customer_id = values.pop("customer_id", None)
        if conversation_id:
            conversation = self.repo.owned_conversation(conversation_id, advisor_id)
            customer_id = conversation["customer_id"]
        elif customer_id:
            customer = self.repo.get_customer(customer_id)
            if not customer or customer["advisor_id"] != advisor_id:
                raise LookupError(customer_id)
            conversation_id = self.repo.get_or_create_conversation(customer_id)
        source_ids = values.pop("source_message_ids", None) or []
        task_type = "ai_follow_up" if source_ids else "manual_follow_up"
        task = FollowupTask(id=uuid4().hex, owner_sales_id=advisor_id,
                            customer_id=customer_id, conversation_id=conversation_id,
                            task_type=task_type, source_message_ids=source_ids,
                            created_at=datetime.now(UTC), **values)
        self.repo.save_tasks([task])
        with self.repo.engine.begin() as conn:
            conn.execute(insert(self.repo.intelligence_tables["activity_details"]).values(task_id=task.id, location=location))
        return self.get(advisor_id, task.id)

    def get(self, advisor_id, task_id):
        with self.repo.engine.connect() as conn:
            row = conn.execute(self._task_query(advisor_id).where(self.tasks.c.id == task_id)).mappings().first()
        if not row:
            raise LookupError(task_id)
        return task_payload(row)

    def edit(self, advisor_id, task_id, changes):
        """Keep existing customer-workspace permissions; personal entries require their owner."""
        t, c = self.tasks.c, self.repo.customers.c
        permitted = or_(c.advisor_id == advisor_id, and_(t.customer_id.is_(None), t.owner_sales_id == advisor_id))
        with self.repo.engine.begin() as conn:
            # Lock only the task; PostgreSQL cannot lock the nullable side of an outer join.
            row = conn.execute(select(self.tasks).where(t.id == task_id).with_for_update()).mappings().first()
            allowed = conn.execute(select(t.id).outerjoin(self.repo.customers, c.id == t.customer_id)
                                   .where(t.id == task_id, permitted)).first() if row else None
            if not allowed:
                raise LookupError(task_id)
            start = changes.get("starts_at", aware(row["starts_at"]))
            end = changes.get("ends_at", aware(row["ends_at"]))
            appointment = changes.get("item_type", row["item_type"]) == "appointment" and changes.get("status", row["status"]) != "cancelled"
            validate_interval(start, end, required=appointment)
            details = self.repo.intelligence_tables["activity_details"]
            location = changes.pop("location", None)
            if location is not None:
                location = location.strip()
            old_location = conn.execute(select(details.c.location).where(details.c.task_id == task_id)).scalar()
            if appointment and not (location if location is not None else old_location):
                raise ValueError("Lịch hẹn cần địa điểm.")
            if location is not None:
                conn.execute(delete(details).where(details.c.task_id == task_id))
                conn.execute(insert(details).values(task_id=task_id, location=location))
            for key in ("starts_at", "ends_at"):
                if key in changes and changes[key]:
                    changes[key] = changes[key].astimezone(UTC)
            if "title" in changes:
                changes["title"] = changes["title"].strip()
            if "status" in changes:
                changes["completed_at"] = datetime.now(UTC) if changes["status"] == "completed" else None
            conn.execute(update(self.tasks).where(t.id == task_id).values(**changes))
            if changes.get("status") == "completed" and row["status"] != "completed" and row["customer_id"]:
                # A completion is a sales attestation, never inferred from elapsed time.
                milestones = self.repo.intelligence_tables["milestones"]
                conn.execute(insert(milestones).values(id=uuid4().hex, customer_id=row["customer_id"], activity_id=task_id,
                    actor_id=advisor_id, created_at=datetime.now(UTC), payload_json=json.dumps({
                        "event_type": {"test_drive": "test_drive_completed", "custom_quote": "quote_sent"}.get(row["task_type"], "activity_completed"), "action": row["title"], "confirmed_by": "sales",
                        "source_message_ids": decoded(row["source_message_ids_json"], []), "revoked": False})))
            elif changes.get("status") in ("pending", "in_progress", "cancelled") and row["status"] == "completed" and row["customer_id"]:
                conn.execute(insert(self.repo.intelligence_tables["milestones"]).values(id=uuid4().hex,
                    customer_id=row["customer_id"], activity_id=task_id, actor_id=advisor_id, created_at=datetime.now(UTC),
                    payload_json=json.dumps({"event_type": "activity_completed", "action": row["title"], "revoked": True, "confirmed_by": "sales"})))
            result = dict(row) | changes
        return task_payload(result)

    def overlaps(self, advisor_id, starts_at, ends_at, exclude_id=None):
        validate_interval(starts_at, ends_at, required=True)
        starts_at, ends_at = starts_at.astimezone(UTC), ends_at.astimezone(UTC)
        t = self.tasks.c
        query = self._task_query(advisor_id).where(t.status.in_(ACTIVE), t.starts_at < ends_at,
                                                 t.ends_at > starts_at)
        if exclude_id:
            query = query.where(t.id != exclude_id)
        with self.repo.engine.connect() as conn:
            return [task_payload(row) for row in conn.execute(query.order_by(t.starts_at).limit(10)).mappings()]

    def calendar(self, advisor_id, week_start: date):
        monday = week_start - timedelta(days=week_start.weekday())
        start = datetime.combine(monday, time.min, TZ).astimezone(UTC)
        end = start + timedelta(days=7)
        t = self.tasks.c
        c = self.repo.customers.c
        priorities = case(
            (t.priority == "urgent", 0),
            (t.priority == "high", 1),
            (t.priority == "medium", 2),
            else_=3,
        )
        with self.repo.engine.connect() as conn:
            rows = conn.execute(self._task_query(advisor_id).where(
                t.starts_at < end, t.ends_at > start, t.status.in_((*ACTIVE, "completed")),
            ).order_by(t.starts_at, t.id)).mappings()
            items = [task_payload(row) for row in rows]
            unscheduled_rows = conn.execute(self._task_query(advisor_id).where(
                t.starts_at.is_(None), t.status.in_(ACTIVE),
            ).order_by(priorities, t.created_at.desc(), t.id).limit(8)).mappings()
            unscheduled_items = [task_payload(row) for row in unscheduled_rows]
            recent_rows = conn.execute(self._task_query(advisor_id).where(
                t.starts_at.is_not(None), t.status.in_((*ACTIVE, "completed")),
            ).order_by(t.starts_at.desc(), t.id).limit(8)).mappings()
            scheduled_recent = [task_payload(row) for row in recent_rows]
            customer_rows = conn.execute(
                select(c.id, c.name).where(c.advisor_id == advisor_id).order_by(c.name, c.id)
            ).mappings()
            customers = [
                {"customer_id": row["id"], "customer_name": row["name"], "conversation_id": None}
                for row in customer_rows
            ]
        return {
            "week_start": monday.isoformat(),
            "timezone": TIMEZONE,
            "generated_at": datetime.now(UTC).isoformat(),
            "items": items,
            "unscheduled_items": unscheduled_items,
            "scheduled_recent": scheduled_recent,
            "customers": customers,
        }

    def _customers(self, conn, advisor_id):
        r = self.repo
        c, v, m = r.customers.c, r.conversations.c, r.messages.c
        prop = r.intelligence_tables["proposals"].c
        ranked = select(v.id, v.customer_id, v.last_analyzed_at, func.row_number().over(
            partition_by=v.customer_id, order_by=(v.updated_at.desc(), v.id.desc()),
        ).label("position")).subquery()
        last = select(m.sender_role).where(m.conversation_id == ranked.c.id,
            m.sender_role.in_(("sales", "customer"))).order_by(m.seq.desc()).limit(1).correlate(ranked).scalar_subquery()
        last_msg = select(m.content).where(m.conversation_id == ranked.c.id,
            m.sender_role.in_(("sales", "customer"))).order_by(m.seq.desc()).limit(1).correlate(ranked).scalar_subquery()
        sales_seq = select(func.max(m.seq)).where(m.conversation_id == ranked.c.id,
            m.sender_role == "sales").correlate(ranked).scalar_subquery()
        waiting = select(func.min(m.sent_at)).where(m.conversation_id == ranked.c.id,
            m.sender_role == "customer", m.seq > func.coalesce(sales_seq, 0)).correlate(ranked).scalar_subquery()
        unanalyzed = select(func.count(m.id)).where(
            m.conversation_id == ranked.c.id,
            or_(ranked.c.last_analyzed_at.is_(None), m.sent_at > ranked.c.last_analyzed_at),
        ).correlate(ranked).scalar_subquery()
        pending_props = select(func.count(prop.id)).where(
            prop.customer_id == c.id, prop.status == "pending",
        ).correlate(r.customers).scalar_subquery()

        def override(kind):
            rec = r.recommendations.c
            scope = r.conversations.alias("dashboard_override_conversations")
            return select(rec.payload_json).where(rec.conversation_id.in_(select(scope.c.id).where(scope.c.customer_id == c.id).correlate(r.customers)), rec.type == kind).order_by(
                rec.created_at.desc(), rec.id.desc()).limit(1).correlate(r.customers).scalar_subquery()

        query = select(
            c.id, c.name, c.phone, c.location, ranked.c.id.label("conversation_id"),
            r.lead_scores.c.stage, r.lead_scores.c.score, r.lead_scores.c.action_priority, r.lead_scores.c.rationale,
            r.snapshots.c.snapshot_json, r.memories.c.quick_summary,
            r.memories.c.pending_items_json, r.memories.c.key_promises_json,
            r.memories.c.updated_at.label("analyzed_at"),
            last.label("last_sender"), last_msg.label("last_message"),
            waiting.label("waiting_since"), unanalyzed.label("unanalyzed_count"),
            pending_props.label("pending_proposals"),
            override("lead_stage_override").label("stage_override"),
            override("profile_overrides").label("profile_override"),
        ).select_from(r.customers).outerjoin(ranked, and_(ranked.c.customer_id == c.id, ranked.c.position == 1)
        ).outerjoin(r.lead_scores, r.lead_scores.c.customer_id == c.id
        ).outerjoin(r.snapshots, r.snapshots.c.customer_id == c.id
        ).outerjoin(r.memories, r.memories.c.conversation_id == ranked.c.id).where(c.advisor_id == advisor_id).order_by(c.name, c.id)
        return list(conn.execute(query).mappings())

    def dashboard(self, advisor_id, *, activity_days=7, work_filter="today", work_page=1, now=None):
        now = aware(now or datetime.now(UTC)).astimezone(UTC)
        today = now.astimezone(TZ).date()
        midnight = datetime.combine(today, time.min, TZ).astimezone(UTC)
        tomorrow = midnight + timedelta(days=1)
        until = now + timedelta(days=7)
        t = self.tasks.c
        active = t.status.in_(ACTIVE)
        today_match = and_(active, t.starts_at < tomorrow, t.ends_at > midnight)
        upcoming = and_(active, t.starts_at >= now, t.starts_at < until)
        unscheduled = and_(active, or_(t.starts_at.is_(None), t.ends_at.is_(None)))
        filters = {"today": today_match, "upcoming": upcoming,
                   "stale": and_(active, t.ends_at <= now), "unscheduled": unscheduled,
                   "review": t.status == "needs_review", "completed": t.status == "completed"}
        selected = filters[work_filter]
        base = self._task_query(advisor_id)
        # Seven bounded queries: customer context, counters, page, upcoming, unscheduled, daily counts, milestones.
        with self.repo.engine.connect() as conn:
            customers = self._customers(conn, advisor_id)
            counts = conn.execute(select(
                func.count().label("total_tasks"),
                func.coalesce(func.sum(case((today_match, 1), else_=0)), 0).label("today_events"),
                func.coalesce(func.sum(case((upcoming, 1), else_=0)), 0).label("upcoming_events"),
                func.coalesce(func.sum(case((unscheduled, 1), else_=0)), 0).label("unscheduled"),
                func.coalesce(func.sum(case((filters["stale"], 1), else_=0)), 0).label("stale_tasks"),
                func.coalesce(func.sum(case((filters["review"], 1), else_=0)), 0).label("review_tasks"),
                func.coalesce(func.sum(case((filters["completed"], 1), else_=0)), 0).label("completed_tasks"),
                func.coalesce(func.sum(case((and_(active, t.item_type == "appointment"), 1), else_=0)), 0).label("active_appointments"),
                func.coalesce(func.sum(case((and_(active, t.priority.in_(("high", "urgent"))), 1), else_=0)), 0).label("high_priority_tasks"),
                func.coalesce(func.sum(case((selected, 1), else_=0)), 0).label("filtered"),
            ).select_from(self.tasks).outerjoin(self.repo.customers, self.repo.customers.c.id == t.customer_id
            ).where(self._scope(advisor_id))).mappings().one()
            page_count = max(1, (counts["filtered"] + 9) // 10)
            work_page = min(work_page, page_count)
            order = case((and_(t.starts_at <= now, t.ends_at > now), 0), (t.starts_at > now, 1), else_=2)
            priorities = case((t.priority == "urgent", 0), (t.priority == "high", 1), (t.priority == "medium", 2), else_=3)
            work = [task_payload(row) for row in conn.execute(base.where(selected).order_by(
                order, t.starts_at, priorities, t.created_at, t.id).offset((work_page - 1) * 10).limit(10)).mappings()]
            upcoming_items = [task_payload(row) for row in conn.execute(base.where(active, t.starts_at >= now).order_by(t.starts_at, t.id).limit(5)).mappings()]
            unscheduled_items = [task_payload(row) for row in conn.execute(base.where(unscheduled).order_by(priorities, t.created_at, t.id).limit(5)).mappings()]
            m = self.repo.messages.c
            local_day = (func.date(func.timezone(TIMEZONE, m.sent_at)) if conn.dialect.name == "postgresql"
                         else func.date(m.sent_at, "+7 hours"))
            days_start = midnight - timedelta(days=activity_days - 1)
            activity = conn.execute(select(local_day.label("day"), m.sender_role, func.count().label("count"))
                .select_from(self.repo.messages).join(self.repo.conversations, self.repo.conversations.c.id == m.conversation_id)
                .join(self.repo.customers, self.repo.customers.c.id == self.repo.conversations.c.customer_id)
                .where(self.repo.customers.c.advisor_id == advisor_id, m.sent_at >= days_start,
                       m.sent_at < tomorrow, m.sender_role.in_(("customer", "sales")))
                .group_by(local_day, m.sender_role)).mappings().all()
            milestone_table = self.repo.intelligence_tables["milestones"]
            milestone_rows = conn.execute(select(milestone_table).join(self.repo.customers,
                self.repo.customers.c.id == milestone_table.c.customer_id).where(self.repo.customers.c.advisor_id == advisor_id)
                .order_by(milestone_table.c.created_at)).mappings().all()
            from src.integrations.customer_intelligence_store import active_milestones
            milestones = active_milestones([{**json.loads(row["payload_json"]), "id": row["id"],
                "customer_id": row["customer_id"], "activity_id": row["activity_id"], "created_at": row["created_at"].isoformat()} for row in milestone_rows])
        stages, models = Counter(), Counter()
        payments, chargings, budget_tiers = Counter(), Counter(), Counter()
        waiting, intelligence, choices, priority_pool = [], [], [], []
        customer_map = {}
        pipeline_budget = 0
        score_sum, score_count = 0, 0
        unanalyzed_customers = 0
        pending_proposals_total = 0
        completeness = {"total_active": 0, "with_model": 0, "with_budget": 0, "with_payment": 0, "with_charging": 0, "with_timeline": 0}
        stage_rank = {"deposit_process": 6, "negotiating": 5, "considering": 4, "qualified": 3, "needs_confirmation": 2, "discovery": 1, "new": 0}

        for customer in customers:
            profile = decoded(customer["snapshot_json"], {})
            for field, fact in decoded(customer["profile_override"], {}).items():
                if isinstance(fact, dict) and "value" in fact:
                    profile[field] = fact["value"]
            stage_override_payload = decoded(customer["stage_override"], {})
            stage = stage_override_payload.get("stage") or customer["stage"] or "new"
            if stage in ("appointment", "unknown"):
                stage = "needs_confirmation"
            stages[stage] += 1
            model_values = profile.get("interested_models") or []
            normalized_models = set()
            for value in model_values:
                name = " ".join(str(value).upper().split())
                family = re.search(r"\bVF\s*([3-9])\b", name)
                if name:
                    normalized_models.add(f"VF {family.group(1)}" if family else name)
            customer_models = sorted(normalized_models)
            for name in customer_models:
                models[name] += 1
            choice = {
                "customer_id": customer["id"],
                "customer_name": customer["name"],
                "conversation_id": customer["conversation_id"],
            }
            customer_map[customer["id"]] = choice

            budget_raw = profile.get("budget_vnd")
            budget_vnd = int(budget_raw) if isinstance(budget_raw, (int, float)) and budget_raw > 0 else None
            down_raw = profile.get("down_payment_vnd")
            down_payment_vnd = int(down_raw) if isinstance(down_raw, (int, float)) and down_raw > 0 else None
            payment_method = str(profile.get("payment_method") or "").strip() or None
            charging_condition = str(profile.get("charging_condition") or "").strip() or None
            purchase_timeline = str(profile.get("purchase_timeline") or "").strip() or None
            usage_purpose = str(profile.get("usage_purpose") or "").strip() or None
            competitor_models = [str(m).strip() for m in (profile.get("competitor_models") or []) if str(m).strip()]
            buying_signals = [str(s).strip() for s in (profile.get("buying_signals") or []) if str(s).strip()]
            objections = [str(o).strip() for o in (profile.get("objections_and_concerns") or []) if str(o).strip()]
            rationale = str(stage_override_payload.get("reason") or customer["rationale"] or "").strip() or None
            phone = str(customer["phone"] or "").strip() or None
            score = int(customer["score"] or 0)
            priority = customer["action_priority"] or "medium"
            quick_summary = str(customer["quick_summary"] or "").strip()
            last_message = str(customer["last_message"] or "").strip()
            unanalyzed_count = int(customer["unanalyzed_count"] or 0)
            pending_props_count = int(customer["pending_proposals"] or 0)
            if unanalyzed_count > 0:
                unanalyzed_customers += 1
            pending_proposals_total += pending_props_count

            issues, seen = [], set()
            for issue in [*decoded(customer["pending_items_json"], []), *(profile.get("unresolved_questions") or []), *objections]:
                if not isinstance(issue, str):
                    continue
                key = " ".join(issue.casefold().split())
                if key and key not in seen:
                    seen.add(key)
                    issues.append(issue.strip())
            promises = [p.strip() for p in decoded(customer["key_promises_json"], []) if isinstance(p, str) and p.strip()]
            since = aware(customer["waiting_since"]) if customer["last_sender"] == "customer" else None

            choices.append(choice | {
                "stage": stage,
                "score": score,
                "models": customer_models,
                "competitor_models": competitor_models[:2],
                "budget_vnd": budget_vnd,
                "waiting_since": since.isoformat() if since else None,
                "last_message": last_message[:180] if last_message else None,
                "buying_signals": buying_signals[:2],
                "issues": issues[:2],
                "promises": promises[:2],
                "quick_summary": quick_summary,
            })

            if customer["last_sender"] == "customer":
                waiting.append(choice | {
                    "waiting_since": since.isoformat() if since else None,
                    "stage": stage,
                    "score": score,
                    "priority": priority,
                    "models": customer_models,
                    "competitor_models": competitor_models[:2],
                    "budget_vnd": budget_vnd,
                    "down_payment_vnd": down_payment_vnd,
                    "payment_method": payment_method,
                    "purchase_timeline": purchase_timeline,
                    "phone": phone,
                    "location": customer["location"],
                    "last_message": last_message[:180] if last_message else None,
                    "buying_signals": buying_signals[:2],
                    "issues": issues[:2],
                    "promises": promises[:2],
                    "unanalyzed_count": unanalyzed_count,
                })
            if issues:
                analyzed = aware(customer["analyzed_at"])
                intelligence.append(choice | {
                    "issues": issues,
                    "promises": promises[:3],
                    "buying_signals": buying_signals[:2],
                    "competitor_models": competitor_models[:2],
                    "analyzed_at": analyzed.isoformat() if analyzed else None,
                    "stage": stage,
                    "score": score,
                    "models": customer_models,
                    "budget_vnd": budget_vnd,
                    "payment_method": payment_method,
                    "phone": phone,
                    "location": customer["location"],
                    "quick_summary": quick_summary,
                    "purchase_timeline": purchase_timeline,
                    "unanalyzed_count": unanalyzed_count,
                })

            if stage not in ("won", "lost"):
                completeness["total_active"] += 1
                if customer_models:
                    completeness["with_model"] += 1
                if budget_vnd:
                    completeness["with_budget"] += 1
                    pipeline_budget += budget_vnd
                    if budget_vnd < 600_000_000:
                        budget_tiers["under_600m"] += 1
                    elif budget_vnd <= 1_000_000_000:
                        budget_tiers["600m_to_1b"] += 1
                    else:
                        budget_tiers["over_1b"] += 1
                else:
                    budget_tiers["unknown"] += 1
                if payment_method:
                    completeness["with_payment"] += 1
                    pm_lower = payment_method.casefold()
                    if "installment" in pm_lower or "góp" in pm_lower or "vay" in pm_lower:
                        payments["installment"] += 1
                    elif "cash" in pm_lower or "thẳng" in pm_lower or "100%" in pm_lower:
                        payments["cash"] += 1
                    else:
                        payments["other"] += 1
                else:
                    payments["unknown"] += 1
                if charging_condition:
                    completeness["with_charging"] += 1
                    cc_lower = charging_condition.casefold()
                    if "home" in cc_lower or "nhà" in cc_lower or "riêng" in cc_lower:
                        chargings["home"] += 1
                    else:
                        chargings["public"] += 1
                else:
                    chargings["unknown"] += 1
                if purchase_timeline:
                    completeness["with_timeline"] += 1
                if score > 0:
                    score_sum += score
                    score_count += 1
                priority_pool.append(choice | {
                    "stage": stage,
                    "score": score,
                    "priority": priority,
                    "models": customer_models,
                    "competitor_models": competitor_models[:2],
                    "budget_vnd": budget_vnd,
                    "down_payment_vnd": down_payment_vnd,
                    "payment_method": payment_method,
                    "charging_condition": charging_condition,
                    "purchase_timeline": purchase_timeline,
                    "usage_purpose": usage_purpose,
                    "phone": phone,
                    "location": customer["location"],
                    "rationale": rationale,
                    "quick_summary": quick_summary,
                    "last_message": last_message[:140] if last_message else None,
                    "waiting_since": since.isoformat() if since else None,
                    "is_waiting": customer["last_sender"] == "customer",
                    "unanalyzed_count": unanalyzed_count,
                    "pending_proposals": pending_props_count,
                    "buying_signals": buying_signals[:2],
                    "issues": issues[:2],
                    "promises": promises[:2],
                    "issues_count": len(issues),
                })

        for ms in milestones:
            linked = customer_map.get(ms.get("customer_id"))
            if linked:
                ms.setdefault("customer_name", linked["customer_name"])
                ms.setdefault("conversation_id", linked["conversation_id"])

        waiting.sort(key=lambda item: item["waiting_since"] or "9999")
        intelligence.sort(key=lambda item: (-len(item["issues"]), item["customer_name"]))
        priority_pool.sort(key=lambda item: (
            -stage_rank.get(item["stage"], 0),
            -item["score"],
            -(item["budget_vnd"] or 0),
            item["customer_name"],
        ))
        hot_leads = sum(1 for item in priority_pool if item["stage"] in ("considering", "negotiating", "deposit_process") or item["score"] >= 70)
        closing_leads = sum(1 for item in priority_pool if item["stage"] in ("negotiating", "deposit_process"))
        series = {(today - timedelta(days=i)).isoformat(): {"customer": 0, "sales": 0} for i in range(activity_days - 1, -1, -1)}
        for row in activity:
            key = str(row["day"])
            if key in series:
                series[key][row["sender_role"]] = row["count"]
        return {
            "generated_at": now.isoformat(),
            "timezone": TIMEZONE,
            "customers": choices,
            "milestones": milestones,
            "kpis": {
                "active_customers": sum(v for k, v in stages.items() if k not in ("won", "lost")),
                "waiting_customers": len(waiting),
                "today_events": counts["today_events"],
                "upcoming_events": counts["upcoming_events"],
                "total_tasks": counts["total_tasks"],
                "hot_leads": hot_leads,
                "closing_leads": closing_leads,
                "unanalyzed_customers": unanalyzed_customers,
                "stale_tasks": counts["stale_tasks"],
                "review_tasks": counts["review_tasks"],
                "completed_tasks": counts["completed_tasks"],
                "active_appointments": counts["active_appointments"],
                "high_priority_tasks": counts["high_priority_tasks"],
                "pending_proposals": pending_proposals_total,
                "pipeline_budget_vnd": pipeline_budget,
                "avg_lead_score": round(score_sum / score_count) if score_count else 0,
            },
            "work_items": {"items": work, "total": counts["filtered"], "page": work_page, "page_size": 10, "filter": work_filter},
            "upcoming_events": upcoming_items,
            "unscheduled": {"total": counts["unscheduled"], "items": unscheduled_items},
            "waiting_customers": waiting,
            "customer_intelligence": intelligence[:5],
            "priority_customers": priority_pool[:8],
            "portfolio_insights": {
                "work_counts": {
                    "today": counts["today_events"],
                    "upcoming": counts["upcoming_events"],
                    "stale": counts["stale_tasks"],
                    "unscheduled": counts["unscheduled"],
                    "review": counts["review_tasks"],
                    "completed": counts["completed_tasks"],
                },
                "payment_breakdown": [
                    {"key": "installment", "label": "Trả góp / Vay NH", "count": payments["installment"]},
                    {"key": "cash", "label": "Trả thẳng 100%", "count": payments["cash"]},
                    {"key": "unknown", "label": "Chưa xác định", "count": payments["unknown"] + payments["other"]},
                ],
                "charging_breakdown": [
                    {"key": "home", "label": "Sạc tại nhà riêng", "count": chargings["home"]},
                    {"key": "public", "label": "Trạm V-GREEN / Chung cư", "count": chargings["public"]},
                    {"key": "unknown", "label": "Chưa khảo sát", "count": chargings["unknown"]},
                ],
                "budget_segments": [
                    {"key": "under_600m", "label": "Dưới 600 triệu (VF 3, VF 5)", "count": budget_tiers["under_600m"]},
                    {"key": "600m_to_1b", "label": "600 triệu - 1 tỷ (VF 6, VF 7)", "count": budget_tiers["600m_to_1b"]},
                    {"key": "over_1b", "label": "Trên 1 tỷ (VF 8, VF 9)", "count": budget_tiers["over_1b"]},
                    {"key": "unknown", "label": "Chưa rõ ngân sách", "count": budget_tiers["unknown"]},
                ],
                "profile_completeness": completeness,
            },
            "stage_distribution": [{"stage": key, "count": value} for key, value in stages.items()],
            "model_interest": [{"model": key, "count": value} for key, value in sorted(models.items(), key=lambda pair: (-pair[1], pair[0]))],
            "message_activity": [{"date": key, **value} for key, value in series.items()],
        }
