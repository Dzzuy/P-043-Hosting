"""Server-owned customer context, separate from private sales/AI dialogue."""

import json


def authorize_customer(repository, conversation_id, owner_id):
    return repository.owned_conversation(conversation_id, owner_id)


def build_customer_context(repository, conversation_id, owner_id):
    owned = authorize_customer(repository, conversation_id, owner_id)
    snapshot = repository.get_customer_snapshot(owned["customer_id"]) or {}
    confirmed = repository.get_latest_recommendation(conversation_id, "profile_overrides") or {}
    for field, fact in confirmed.items():
        snapshot[field] = fact["value"]
        if field == "budget_vnd":
            snapshot.pop("budget_notes", None)
    memory = repository.get_memory(conversation_id) or {}
    messages = repository.list_messages(conversation_id, limit=8)
    header = (
        "Ngữ cảnh khách hàng, không phải nguồn xác minh giá/thông số/chính sách. "
        "Tin mới có thể cập nhật hồ sơ/tóm tắt cũ. Lời tư vấn viên không phải câu trả lời trước của AI.\n"
        "Hội thoại khách–sales gần nhất (có người nói và thứ tự):\n"
    )
    remaining = 6000 - len(header)
    recent = []
    for message in reversed(messages):
        role = getattr(message.sender_role, "value", message.sender_role)
        label = "Khách hàng" if role == "customer" else "Tư vấn viên"
        prefix = f"[{message.seq} · {message.sent_at.isoformat()} · {label}] "
        line = prefix + message.content
        if len(line) + 1 > remaining:
            marker = "[Nội dung đã rút gọn] "
            available = remaining - len(prefix) - len(marker) - 1
            if available > 0:
                recent.insert(0, prefix + marker + message.content[-available:])
                remaining = 0
            break
        recent.insert(0, line)
        remaining -= len(line) + 1
    context = header + "\n".join(recent)
    fields = (
        "interested_models", "budget_notes", "budget_vnd", "down_payment_vnd", "monthly_income_vnd",
        "daily_distance_km", "charging_condition", "living_area", "objections_and_concerns", "customer_segment",
        "competitor_models", "payment_method", "max_monthly_payment_vnd", "loan_term_years",
        "usage_purpose", "passenger_count", "purchase_timeline", "buying_signals", "unresolved_questions",
    )
    profile = {key: snapshot[key] for key in fields if snapshot.get(key) is not None}
    if confirmed:
        profile["sales_confirmed_fields"] = {key: {"value": fact["value"], "confirmed_at": fact["updated_at"]} for key, fact in confirmed.items()}
    older = "\nHồ sơ đã lưu (có thể cũ): " + json.dumps(profile, ensure_ascii=False)
    if memory.get("quick_summary"):
        older += "\nTóm tắt hội thoại khách–sales đã lưu (có thể cũ): " + memory["quick_summary"]
    space = 6000 - len(context)
    if len(older) <= space:
        context += older
    elif space >= len("\n[Hồ sơ/tóm tắt đã rút gọn]"):
        marker = "\n[Hồ sơ/tóm tắt đã rút gọn]"
        context += older[:space - len(marker)] + marker
    return context
