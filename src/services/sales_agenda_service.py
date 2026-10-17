"""Personal sales agenda and read-only dashboard; no analysis or chat history loading."""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func, or_, select, update

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
        return select(self.tasks, self.repo.customers.c.name.label("customer_name")).outerjoin(
            self.repo.customers, self.repo.customers.c.id == self.tasks.c.customer_id,
        ).where(self._scope(advisor_id))

    def create(self, advisor_id, values, *, conversation_id=None):
        values = dict(values)
        validate_interval(values.get("starts_at"), values.get("ends_at"), required=True)
        for key in ("starts_at", "ends_at"):
            values[key] = values[key].astimezone(UTC)
        customer_id = values.pop("customer_id", None)
        if conversation_id:
            conversation = self.repo.owned_conversation(conversation_id, advisor_id)
            customer_id = conversation["customer_id"]
        elif customer_id:
            customer = self.repo.get_customer(customer_id)
            if not customer or customer["advisor_id"] != advisor_id:
                raise LookupError(customer_id)
            conversation_id = self.repo.get_or_create_conversation(customer_id)
        task = FollowupTask(id=uuid4().hex, owner_sales_id=advisor_id,
                            customer_id=customer_id, conversation_id=conversation_id,
                            task_type="manual_follow_up", created_at=datetime.now(UTC),
                            **values)
        self.repo.save_tasks([task])
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
            approving = row["status"] == "needs_review" and changes.get("status") in (*ACTIVE, "completed")
            validate_interval(start, end, required=approving or bool(row["starts_at"]))
            for key in ("starts_at", "ends_at"):
                if key in changes and changes[key]:
                    changes[key] = changes[key].astimezone(UTC)
            if "title" in changes:
                changes["title"] = changes["title"].strip()
            if "status" in changes:
                changes["completed_at"] = datetime.now(UTC) if changes["status"] == "completed" else None
            conn.execute(update(self.tasks).where(t.id == task_id).values(**changes))
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
        with self.repo.engine.connect() as conn:
            rows = conn.execute(self._task_query(advisor_id).where(
                t.starts_at < end, t.ends_at > start, t.status.in_((*ACTIVE, "completed")),
            ).order_by(t.starts_at, t.id)).mappings()
            items = [task_payload(row) for row in rows]
        return {"week_start": monday.isoformat(), "timezone": TIMEZONE,
                "generated_at": datetime.now(UTC).isoformat(), "items": items}

    def _customers(self, conn, advisor_id):
        r = self.repo
        c, v, m = r.customers.c, r.conversations.c, r.messages.c
        ranked = select(v.id, v.customer_id, func.row_number().over(
            partition_by=v.customer_id, order_by=(v.updated_at.desc(), v.id.desc()),
        ).label("position")).subquery()
        last = select(m.sender_role).where(m.conversation_id == ranked.c.id,
            m.sender_role.in_(("sales", "customer"))).order_by(m.seq.desc()).limit(1).correlate(ranked).scalar_subquery()
        sales_seq = select(func.max(m.seq)).where(m.conversation_id == ranked.c.id,
            m.sender_role == "sales").correlate(ranked).scalar_subquery()
        waiting = select(func.min(m.sent_at)).where(m.conversation_id == ranked.c.id,
            m.sender_role == "customer", m.seq > func.coalesce(sales_seq, 0)).correlate(ranked).scalar_subquery()

        def override(kind):
            rec = r.recommendations.c
            return select(rec.payload_json).where(rec.conversation_id == ranked.c.id, rec.type == kind).order_by(
                rec.created_at.desc(), rec.id.desc()).limit(1).correlate(ranked).scalar_subquery()

        query = select(c.id, c.name, ranked.c.id.label("conversation_id"), r.lead_scores.c.stage,
            r.snapshots.c.snapshot_json, r.memories.c.pending_items_json,
            r.memories.c.updated_at.label("analyzed_at"), last.label("last_sender"), waiting.label("waiting_since"),
            override("lead_stage_override").label("stage_override"), override("profile_overrides").label("profile_override"),
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
        # Six bounded queries: customer context, counters, page, upcoming, unscheduled, daily counts.
        with self.repo.engine.connect() as conn:
            customers = self._customers(conn, advisor_id)
            counts = conn.execute(select(
                func.count().label("total_tasks"),
                func.coalesce(func.sum(case((today_match, 1), else_=0)), 0).label("today_events"),
                func.coalesce(func.sum(case((upcoming, 1), else_=0)), 0).label("upcoming_events"),
                func.coalesce(func.sum(case((unscheduled, 1), else_=0)), 0).label("unscheduled"),
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
        stages, models = Counter(), Counter()
        waiting, intelligence, choices = [], [], []
        for customer in customers:
            profile = decoded(customer["snapshot_json"], {})
            for field, fact in decoded(customer["profile_override"], {}).items():
                if isinstance(fact, dict) and "value" in fact:
                    profile[field] = fact["value"]
            stage = decoded(customer["stage_override"], {}).get("stage") or customer["stage"] or "new"
            stages[stage] += 1
            model_values = profile.get("interested_models") or []
            normalized_models = set()
            for value in model_values:
                name = " ".join(str(value).upper().split())
                family = re.search(r"\bVF\s*([3-9])\b", name)
                if name:
                    normalized_models.add(f"VF {family.group(1)}" if family else name)
            for name in normalized_models:
                models[name] += 1
            choice = {"customer_id": customer["id"], "customer_name": customer["name"], "conversation_id": customer["conversation_id"]}
            choices.append(choice)
            if customer["last_sender"] == "customer":
                since = aware(customer["waiting_since"])
                waiting.append(choice | {"waiting_since": since.isoformat() if since else None})
            issues, seen = [], set()
            for issue in [*decoded(customer["pending_items_json"], []), *(profile.get("unresolved_questions") or [])]:
                if not isinstance(issue, str):
                    continue
                key = " ".join(issue.casefold().split())
                if key and key not in seen:
                    seen.add(key)
                    issues.append(issue.strip())
            if issues:
                analyzed = aware(customer["analyzed_at"])
                intelligence.append(choice | {"issues": issues, "analyzed_at": analyzed.isoformat() if analyzed else None})
        waiting.sort(key=lambda item: item["waiting_since"] or "9999")
        intelligence.sort(key=lambda item: (-len(item["issues"]), item["customer_name"]))
        series = { (today - timedelta(days=i)).isoformat(): {"customer": 0, "sales": 0} for i in range(activity_days - 1, -1, -1)}
        for row in activity:
            key = str(row["day"])
            if key in series:
                series[key][row["sender_role"]] = row["count"]
        return {"generated_at": now.isoformat(), "timezone": TIMEZONE, "customers": choices,
            "kpis": {"active_customers": sum(v for k, v in stages.items() if k not in ("won", "lost")),
                     "waiting_customers": len(waiting), "today_events": counts["today_events"],
                     "upcoming_events": counts["upcoming_events"], "total_tasks": counts["total_tasks"]},
            "work_items": {"items": work, "total": counts["filtered"], "page": work_page, "page_size": 10, "filter": work_filter},
            "upcoming_events": upcoming_items, "unscheduled": {"total": counts["unscheduled"], "items": unscheduled_items},
            "waiting_customers": waiting, "customer_intelligence": intelligence[:5],
            "stage_distribution": [{"stage": key, "count": value} for key, value in stages.items()],
            "model_interest": [{"model": key, "count": value} for key, value in sorted(models.items(), key=lambda pair: (-pair[1], pair[0]))],
            "message_activity": [{"date": key, **value} for key, value in series.items()]}
