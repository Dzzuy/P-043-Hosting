"""Insert labeled Dashboard demo data into the configured DB, without replacing any rows.

Dry run: python scripts/seed_dashboard_demo.py --owner advisor-demo
Apply:   python scripts/seed_dashboard_demo.py --owner advisor-demo --apply
Stable IDs make repeated runs a no-op; dates are anchored to Vietnam time at first insertion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, insert, select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import get_settings
from src.integrations.auth_repository import SQLAuthRepository
from src.integrations.practice_persistence import normalize_database_url
from src.integrations.sales_copilot_repository import SQLSalesCopilotRepository
from src.models.sales_copilot import CustomerProfileSnapshot, FollowupTask
from src.services.sales_agenda_service import SalesAgendaService

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
LABEL = "[Mẫu]"
NAMES = ["Minh Anh", "Hoàng Nam", "Thu Hà", "Đức Long", "Ngọc Mai", "Quang Dũng",
         "Thanh Trúc", "Hải Đăng", "Bảo Ngân", "Trung Kiên", "Khánh Linh", "Tuấn Phong"]
STAGES = ["new", "discovery", "qualified", "considering", "considering", "negotiating",
          "appointment", "appointment", "deposit_process", "won", "lost", "qualified"]
MODELS = [["VF 3"], ["VF 5", "VF 6"], ["VF 6"], ["VF 7", "VF 8"], ["VF 5"], ["VF 8"],
          ["VF 6", "VF 7"], ["VF 9"], ["VF 8", "VF 9"], ["VF 3"], ["VF 5"], ["VF 7"]]
ISSUES = [[], ["Chưa rõ phương án sạc tại chung cư"], ["Cần bảng dự toán lăn bánh"],
          ["Cần so sánh không gian hàng ghế sau", "Chưa thống nhất phương án trả góp"],
          ["Cần so sánh chi phí sử dụng hằng tháng"], ["Chưa xác nhận màu xe sẵn có"],
          ["Cần xác nhận địa điểm lái thử"], ["Cần kiểm tra chỗ đỗ xe tại nhà"],
          ["Chưa xác nhận thời điểm giao xe"], [], [], ["Cần tư vấn phụ kiện phù hợp"]]


def build_rows(repo, owner, now):
    now = now.astimezone(TZ).replace(second=0, microsecond=0)
    today = now.replace(hour=0, minute=0)
    prefix = "dashdemo1_" + hashlib.sha256(owner.encode()).hexdigest()[:10] + "_"
    ident = lambda kind, value: f"{prefix}{kind}_{value}"
    utc = lambda value: value.astimezone(UTC)
    dump = lambda value: json.dumps(value, ensure_ascii=False)
    rows = {name: [] for name in ("customers", "conversations", "messages", "snapshots", "memories", "lead_scores", "recommendations", "tasks")}
    for index, name in enumerate(NAMES):
        cid, vid = ident("customer", index), ident("conversation", index)
        messages = []
        for days_ago in range(29, 0, -1):
            # Vary activity by day/customer; keep some quiet days.
            if (days_ago + index) % 4 == 0 or (days_ago * 3 + index) % 5 == 0:
                continue
            at = today - timedelta(days=days_ago) + timedelta(hours=9 + index % 7, minutes=(index * 7) % 40)
            topic = ["nhu cầu sử dụng", "phương án sạc", "không gian nội thất", "lịch lái thử", "chi phí sử dụng"][(days_ago + index) % 5]
            messages.extend([(at, "customer", f"Em muốn hỏi thêm về {topic} của {MODELS[index][0]}."),
                             (at + timedelta(minutes=8 + index), "sales", f"Em đã ghi nhận câu hỏi về {topic}. Mình cùng xem thông tin chi tiết nhé.")])
        waiting = index in (0, 1, 3, 5, 7)
        last = now - timedelta(minutes=12 + index * 19)
        messages.append((last - timedelta(minutes=8), "sales", "Mình muốn trao đổi tiếp phần nào để em chuẩn bị tư vấn?"))
        question = ISSUES[index][0] if ISSUES[index] else f"Em muốn tìm hiểu thêm về {MODELS[index][0]}."
        messages.append((last, "customer", question))
        if not waiting:
            messages.append((last + timedelta(minutes=5), "sales", "Em đã ghi nhận và sẽ chuẩn bị nội dung cho lần trao đổi tiếp theo."))
        messages.sort(key=lambda value: value[0])
        for seq, (at, role, content) in enumerate(messages, 1):
            rows["messages"].append({"id": ident("message", f"{index}_{seq}"), "conversation_id": vid,
                "sender_role": role, "content": f"{LABEL} {content}", "seq": seq, "sent_at": utc(at)})
        last_message = rows["messages"][-1]
        source_id = ident("message", f"{index}_{len(messages) - (0 if waiting else 1)}")
        created = utc(today - timedelta(days=35 - index))
        rows["customers"].append({"id": cid, "name": f"{LABEL} {name}", "phone": None, "email": None,
            "location": ["Hà Nội", "TP. Hồ Chí Minh", "Đà Nẵng"][index % 3], "advisor_id": owner,
            "created_at": created, "updated_at": utc(now)})
        rows["conversations"].append({"id": vid, "customer_id": cid,
            "channel": ["zalo_oa", "website", "phone"][index % 3], "created_at": created,
            "updated_at": last_message["sent_at"], "last_analyzed_at": last_message["sent_at"], "analysis_version": 1})
        profile = CustomerProfileSnapshot(interested_models=MODELS[index], budget_vnd=[350, 550, 750, 1100, 600, 1300, 900, 1700, 1500, 350, 550, 900][index] * 1000000,
            payment_method="installment" if index % 2 else "cash", usage_purpose="Đi làm và đi chơi cùng gia đình",
            passenger_count=4 + index % 3, daily_distance_km=f"{20 + index * 5} km/ngày",
            purchase_timeline="Trong 1–2 tháng tới", charging_condition="public_charger" if index % 2 else "home_ground",
            unresolved_questions=ISSUES[index])
        rows["snapshots"].append({"customer_id": cid, "snapshot_json": profile.model_dump_json(), "updated_at": utc(now)})
        rows["memories"].append({"conversation_id": vid,
            "quick_summary": f"{LABEL} Kịch bản mô phỏng: khách quan tâm {', '.join(MODELS[index])}, ưu tiên nhu cầu gia đình.",
            "detailed_summary": f"{LABEL} Dữ liệu giả phục vụ Dashboard. Đã trao đổi nhu cầu, điều kiện sạc và kế hoạch mua xe; chỉ các mục có giờ xác nhận mới được đưa lên lịch.",
            "timeline_json": dump([{"title": "Trao đổi nhu cầu sử dụng", "description": f"{LABEL} Ghi nhận mục đích sử dụng và dòng xe quan tâm.",
                "event_type": "consulted", "occurred_at": last_message["sent_at"].isoformat(), "source_message_id": source_id}]),
            "pending_items_json": dump(ISSUES[index]), "key_promises_json": dump([]), "version": 1, "updated_at": utc(now)})
        rows["lead_scores"].append({"customer_id": cid, "stage": STAGES[index], "score": min(95, 25 + index * 6),
            "action_priority": "high" if waiting else "medium", "rationale": f"{LABEL} Phân loại trong kịch bản mô phỏng.",
            "breakdown_json": "[]", "updated_at": utc(now)})
        for kind, payload in [("analysis_context", {"version": 1, "through_seq": len(messages)}),
            ("lead_stage_override", {"stage": STAGES[index], "advisor_id": owner, "reason": f"{LABEL} Giai đoạn xác nhận trong kịch bản mô phỏng."})]:
            rows["recommendations"].append({"id": ident(kind, index), "conversation_id": vid, "type": kind,
                "payload_json": dump(payload), "status": "confirmed" if kind == "lead_stage_override" else "generated", "created_at": utc(now)})

    def add_task(index, title, start, end, *, customer=None, status="pending", kind="task", priority="medium"):
        cid = ident("customer", customer) if customer is not None else None
        vid = ident("conversation", customer) if customer is not None else None
        source = []
        if vid:
            source = [next(row["id"] for row in reversed(rows["messages"]) if row["conversation_id"] == vid and row["sender_role"] == "customer")]
        item = FollowupTask(id=ident("task", index), customer_id=cid, conversation_id=vid, owner_sales_id=owner,
            task_type="follow_up" if status == "needs_review" else "manual_follow_up", title=f"{LABEL} {title}",
            description="Dữ liệu mô phỏng Dashboard; không phải lịch hẹn với khách thật.", starts_at=utc(start) if start else None,
            ends_at=utc(end) if end else None, item_type=kind, priority=priority, status=status,
            source_message_ids=source, dedupe_key=ident("task", index), created_at=utc(now - timedelta(days=2)),
            completed_at=utc(end) if status == "completed" else None).model_dump(mode="python")
        item["source_message_ids_json"] = dump(item.pop("source_message_ids"))
        rows["tasks"].append(item)

    add_task(0, "Gọi xác nhận nhu cầu VF 5", today + timedelta(hours=9), today + timedelta(hours=9, minutes=30), customer=1, priority="high")
    add_task(1, "Tư vấn phương án sạc tại nhà", now - timedelta(minutes=15), now + timedelta(minutes=30), customer=3, status="in_progress", priority="high")
    add_task(2, "Hẹn tư vấn VF 8", now + timedelta(minutes=45), now + timedelta(minutes=105), customer=5, kind="appointment", priority="high")
    add_task(3, "Họp chuẩn bị nội dung tư vấn", now + timedelta(minutes=75), now + timedelta(minutes=120), kind="appointment")
    add_task(4, "Rà soát hồ sơ cuối ngày", today + timedelta(hours=23, minutes=30), today + timedelta(days=1, minutes=45))
    add_task(5, "Tổng hợp tài liệu chuyển ca", today - timedelta(minutes=30), today + timedelta(minutes=45), priority="low")
    for index in range(14):
        start = today + timedelta(days=1 + index % 6, hours=9 + (index // 6) * 3)
        customer = index % 9
        title = ["Hẹn lái thử", "Chuẩn bị phương án tư vấn", "Gọi chăm sóc", "Trao đổi kế hoạch mua xe"][index % 4]
        add_task(6 + index, f"{title} {MODELS[customer][0]}", start, start + timedelta(minutes=45 + index % 2 * 15),
            customer=customer, kind="appointment" if index % 2 == 0 else "task", priority=["low", "medium", "high"][index % 3])
    sunday = today + timedelta(days=6 - today.weekday(), hours=23, minutes=30)
    add_task(20, "Tổng hợp hoạt động giao hai tuần", sunday, sunday + timedelta(hours=1))
    add_task(21, "Hẹn xem xe tuần sau", today + timedelta(days=8, hours=10), today + timedelta(days=8, hours=11), customer=7, kind="appointment")
    for index, days_ago in enumerate((0, 1, 4)):
        start = today - timedelta(days=days_ago) + timedelta(hours=10)
        if start + timedelta(minutes=30) > now:
            start = now - timedelta(hours=2)
        add_task(22 + index, "Đã gửi nội dung tư vấn", start, start + timedelta(minutes=30), customer=2 + index, status="completed")
    add_task(25, "Lịch hẹn đã hủy", today + timedelta(days=1, hours=15), today + timedelta(days=1, hours=16), customer=4, status="cancelled", kind="appointment")
    for index in range(3):
        add_task(26 + index, f"Đề xuất chăm sóc {MODELS[index + 2][0]}", None, None, customer=index + 2, status="needs_review")
    return prefix, rows


def seed(engine, owner, *, apply=False, now=None):
    repo = SQLSalesCopilotRepository("", engine=engine)
    auth = SQLAuthRepository("", engine=engine)
    prefix, rows = build_rows(repo, owner, now or datetime.now(UTC))
    counts = {name: len(values) for name, values in rows.items()}
    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            conn.execute(text("SET LOCAL lock_timeout = '5s'"))
            conn.execute(text("SET LOCAL statement_timeout = '30s'"))
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": prefix})
        account = conn.execute(select(auth._users.c.user_id).where(auth._users.c.user_id == owner,
            auth._users.c.active.is_(True), auth._users.c.role == "advisor")).scalar_one_or_none()
        if not account:
            raise ValueError("Owner must be an existing active advisor account.")
        marker = conn.execute(select(repo.customers.c.id).where(repo.customers.c.id == rows["customers"][0]["id"])).first()
        if marker:
            return {"applied": False, "already_seeded": True, "owner": owner, "batch": prefix}
        if apply:
            for name, values in rows.items():
                if values:
                    conn.execute(insert(getattr(repo, name)), values)
    return {"applied": apply, "already_seeded": False, "owner": owner, "batch": prefix, "rows": counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if settings.app_env == "production":
        raise RuntimeError("Demo seeding is restricted to development/test.")
    engine = create_engine(normalize_database_url(settings.database_url), pool_pre_ping=True,
                           connect_args={"connect_timeout": 10})
    try:
        result = seed(engine, args.owner, apply=args.apply)
        if args.apply:
            agenda = SalesAgendaService(SQLSalesCopilotRepository("", engine=engine))
            dashboard = agenda.dashboard(args.owner, activity_days=30)
            calendar = agenda.calendar(args.owner, datetime.now(TZ).date())
            result["dashboard"] = {"kpis": dashboard["kpis"], "unscheduled": dashboard["unscheduled"]["total"],
                "chart_days": len(dashboard["message_activity"]), "messages_30_days": sum(row["customer"] + row["sales"] for row in dashboard["message_activity"]),
                "calendar_events_this_week": len(calendar["items"])}
        print(json.dumps(result))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
