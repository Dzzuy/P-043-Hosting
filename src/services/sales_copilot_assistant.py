"""Explicitly requested, private drafts. Sales reviews before use."""

import re
from uuid import uuid4

from src.config import get_settings
from src.integrations.customer_intelligence_store import IntelligenceStore
from src.knowledge.retrieval_service import get_retrieval_service
from src.models.customer_intelligence import DraftAnswer
from src.models.sales_copilot import MessageDraftResponse
from src.observability import private_customer_context
from src.services.customer_pii import CustomerPII

DRAFT_PROMPT = """Bạn là Trợ lý AI hỗ trợ Tư vấn viên (Sales) ô tô điện VinFast soạn tin nhắn trả lời khách hàng.

NHIỆM VỤ:
Đọc 6 tin nhắn gần nhất (`messages`), kết hợp với:
1. Hồ sơ & bối cảnh riêng của khách hàng (`customer_context`),
2. Phong cách xưng hô & giọng văn của chính Sales (`sales_style`),
3. Tài liệu sản phẩm/chính sách VinFast (`knowledge`),
để soạn một tin nhắn trả lời hoàn chỉnh cho tin nhắn mới nhất của khách hàng.

QUY TẮC CÁ NHÂN HÓA & BẮT CHƯỚC VĂN PHONG (BẮT BUỘC):
1. Bắt chước cách xưng hô & giọng điệu của Sales (`sales_style`):
   - Sử dụng ĐÚNG cặp đại từ xưng hô trong `sales_style.self_pronoun` (VD: "em") và `sales_style.customer_address` (VD: "anh Khoa", "anh", "chị Lan").
   - Giữ đúng thói quen mở đầu câu và từ đệm cuối câu của Sales trong `sales_style.tone_markers` và `sales_style.sample_messages` (VD: "Dạ anh Khoa ơi,", "Dạ...", "...ạ", "...nhé").
   - Độ dài câu và cách ngắt nhịp tương đồng với `sales_style.sample_messages` để khách đọc thấy tự nhiên như chính Sales đang nhắn.
2. Cá nhân hóa theo bối cảnh khách hàng (`customer_context`):
   - Trả lời thẳng vào câu hỏi/ý kiến mới nhất của khách trong `messages`.
   - Khéo léo gắn câu trả lời với nhu cầu thực tế của khách trong `customer_context` (dòng xe quan tâm, hình thức mua trả thẳng/trả góp, mục đích sử dụng, điều kiện sạc, thời điểm mua hoặc lịch hẹn đã thống nhất) khi phù hợp, tránh trả lời chung chung như văn mẫu.
3. Chính xác theo tài liệu (`knowledge`):
   - Chỉ sử dụng số liệu giá bán, thông số kỹ thuật, chính sách bảo hành/trả góp có trong `knowledge` hoặc đã xác nhận trong `messages`.
   - Nếu khách hỏi thông tin thực tế tại đại lý (tồn kho màu xe, số VIN sẵn, lịch bấm biển...) hoặc chi tiết chưa có trong `knowledge`, hãy hẹn kiểm tra ngay với bộ phận liên quan và báo lại khách sớm nhất, tuyệt đối không tự bịa số liệu.
4. Trường `evidence`: nếu trích dẫn từ `messages` thì dẫn đúng `message_id` và `quote` nguyên văn (hoặc để mảng rỗng `[]` nếu chỉ dùng `knowledge`)."""


def _doc_label(doc) -> str:
    direct = getattr(doc, "source", None)
    if direct:
        return str(direct)
    meta = getattr(doc, "metadata", None)
    if isinstance(meta, dict):
        return str(meta.get("title") or meta.get("source") or "Tài liệu sản phẩm")
    if meta is not None:
        title = getattr(meta, "title", None)
        source = getattr(meta, "source", None)
        if title and source and title != source:
            return f"{title} ({source})"
        if title or source:
            return str(title or source)
    return "Tài liệu sản phẩm"


def _extract_sales_style(all_messages, customer_name: str, pii: CustomerPII) -> dict:
    """Analyze how the Sales advisor addresses the customer and writes messages."""
    sales_msgs = [pii.mask(m.content.strip()) for m in all_messages if m.sender_role == "sales" and m.content.strip()]
    joined = " ".join(sales_msgs)
    lower_joined = joined.lower()

    # 1. Self pronoun used by Sales
    self_pronoun = "em"
    if re.search(r"\bmình\b", lower_joined) and not re.search(r"\bem\b", lower_joined):
        self_pronoun = "mình"

    # 2. How Sales addresses the customer (honorific + short name)
    name_clean = (customer_name or "").strip()
    parts = name_clean.split()
    honorific = ""
    short_name = parts[-1] if parts else ""
    if parts and parts[0].lower() in ("anh", "chị", "bác", "cô", "chú", "bạn"):
        honorific = parts[0].lower()
        short_name = parts[-1] if len(parts) > 1 else ""

    if not honorific:
        for cand in ("anh", "chị", "bác", "cô", "chú", "bạn"):
            if re.search(rf"\b{cand}\b", lower_joined):
                honorific = cand
                break
    if not honorific:
        honorific = "anh/chị"

    customer_address = f"{honorific} {short_name}".strip() if short_name and honorific in ("anh", "chị", "bác", "cô", "chú", "bạn") else honorific

    # 3. Tone markers / particles used by Sales
    markers = []
    for particle in ("Dạ", "Vâng", "ạ", "nhé", "nha"):
        if re.search(rf"(?i)\b{particle}\b", joined):
            markers.append(particle)
    if not markers:
        markers = ["Dạ", "ạ", "nhé"]

    return {
        "self_pronoun": self_pronoun,
        "customer_address": customer_address,
        "customer_full_name": name_clean,
        "tone_markers": markers,
        "sample_messages": sales_msgs[-3:],
    }


def _build_customer_context(detail, confirmed: dict) -> dict:
    """Build structured customer personalization context from profile and memory."""
    profile = detail.profile or {}
    memory = detail.memory or {}
    payment_map = {"cash": "Trả thẳng", "installment": "Trả góp", "mixed": "Kết hợp trả thẳng / trả góp"}
    raw_payment = profile.get("payment_method")
    open_points = [
        kp.get("question") or kp.get("topic")
        for kp in (memory.get("key_points") or [])
        if isinstance(kp, dict) and kp.get("status") == "open" and (kp.get("question") or kp.get("topic"))
    ]
    return {
        "customer_name": detail.customer_name or "",
        "location": detail.customer_location or profile.get("living_area") or "",
        "lead_stage": (detail.lead_status or {}).get("stage") or "",
        "interested_models": profile.get("interested_models") or [],
        "competitor_models": profile.get("competitor_models") or [],
        "payment_method": payment_map.get(raw_payment, raw_payment or ""),
        "budget_vnd": profile.get("budget_vnd"),
        "budget_notes": profile.get("budget_notes") or "",
        "down_payment_vnd": profile.get("down_payment_vnd"),
        "usage_purpose": profile.get("usage_purpose") or "",
        "charging_condition": profile.get("charging_condition") or "",
        "purchase_timeline": profile.get("purchase_timeline") or "",
        "objections_and_concerns": profile.get("objections_and_concerns") or [],
        "open_questions": open_points or (profile.get("unresolved_questions") or []),
        "recap": memory.get("recap") or memory.get("quick_summary") or memory.get("detailed_summary") or "",
        "confirmed_facts": confirmed,
    }


class SalesCopilotAssistant:
    def __init__(self, repository):
        self.repository = repository

    async def generate_message_draft(self, conversation_id, advisor_id, *, force=False):
        if not get_settings().sales_intelligence_v2_enabled:
            raise ValueError("Customer Intelligence mới chưa được bật.")
        repo = self.repository
        customer_id = repo.owned_conversation(conversation_id, advisor_id)["customer_id"]
        store = IntelligenceStore(repo)
        store.authorize(customer_id, advisor_id)
        head = store.head(customer_id)
        pii = CustomerPII(head["pii_mapping"], customer_id=customer_id)
        from src.services.sales_conversation_service import SalesConversationService

        detail = SalesConversationService(repo).get_conversation_details(conversation_id)
        confirmed = {
            f["field"]: f["value"]
            for f in detail.profile.get("facts", [])
            if f.get("verification_status") == "confirmed"
        }
        all_messages = repo.list_messages(conversation_id, limit=12)
        if not all_messages:
            raise ValueError("Chưa có tin để soạn nháp.")
        messages = all_messages[-6:]
        customer_context = _build_customer_context(detail, confirmed)
        sales_style = _extract_sales_style(all_messages, detail.customer_name or "", pii)
        models = customer_context["interested_models"]

        latest_customer_text = next(
            (m.content for m in reversed(messages) if m.sender_role == "customer"),
            messages[-1].content,
        )
        query = pii.mask(latest_customer_text)
        rag_query = query
        if models and not any(str(m).lower() in rag_query.lower() for m in models if m):
            rag_query = f"{', '.join(str(m) for m in models if m)}: {rag_query}"
        # Retrieval may call an embedding model; it receives masked text too.
        with private_customer_context():
            docs = get_retrieval_service().retrieve(rag_query, top_k=5)
        sources = [{"id": str(i), "title": _doc_label(d), "content": d.content} for i, d in enumerate(docs)]
        draft = await pii.ask(
            DRAFT_PROMPT,
            {
                "profile": confirmed,
                "customer_context": customer_context,
                "sales_style": sales_style,
                "messages": [m.model_dump(mode="json") for m in messages],
                "knowledge": sources,
            },
            DraftAnswer,
        )
        from src.services.intelligence_engine import checked_evidence

        masked = {m.id: {"content": pii.mask(m.content)} for m in messages}
        valid_evidence = [
            e for e in (draft.evidence or [])
            if e.message_id in masked and e.quote and e.quote in masked[e.message_id]["content"]
        ]
        if valid_evidence:
            checked_evidence([{"evidence": [e.model_dump() for e in valid_evidence]}], masked)
        unique_sources = list(dict.fromkeys(_doc_label(d) for d in docs))
        response = MessageDraftResponse(
            conversation_id=conversation_id,
            draft_id=uuid4().hex,
            text=pii.restore(draft.text),
            context_trigger=pii.restore(query),
            sources=unique_sources,
            based_on_message_seq=max(m.seq for m in messages),
        )
        # Persist any new identifiers with optimistic concurrency before saving the draft.
        store.save_mapping(customer_id, pii, head)
        repo.save_recommendation_or_draft(conversation_id, "draft", response.model_dump(mode="json"))
        return response
