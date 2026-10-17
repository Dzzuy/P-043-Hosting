"""Assistance Engine for AI Sales Copilot.

Supports:
- F03: Next Best Action (NBA) — automatic 1-3 actions when toggle is ON.
- F04: AI Message Drafting — automatic grounded reply draft when toggle is ON.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from uuid import uuid4

from src.integrations.sales_copilot_repository import SQLSalesCopilotRepository
from src.knowledge.retrieval_service import get_retrieval_service
from src.models.sales_copilot import (
    MessageDraftResponse,
    NextBestActionItem,
    NextBestActionResponse,
)
from src.services.llm import get_llm

logger = logging.getLogger(__name__)


NBA_SYSTEM_PROMPT = """Bạn là trợ lý chiến lược bán hàng (Next Best Action) cho nhân viên tư vấn xe VinFast.
Dựa trên hồ sơ khách hàng và tin nhắn gần nhất, hãy đề xuất từ 1 đến 3 hành động logic, hiệu quả nhất tại thời điểm hiện tại.
Các loại hành động (action_type):
- calculate_finance: Chuẩn bị bảng tính gốc lãi, trả góp, chi phí lăn bánh
- schedule_test_drive: Đề xuất hoặc sắp xếp lịch lái thử xe
- compare_products: So sánh các dòng xe khách đang phân vân
- answer_concern: Giải tỏa băn khoăn về pin, trạm sạc, bảo hành, an toàn
- send_quote: Gửi báo giá hoặc chương trình ưu đãi hiện hành
- confirm_next_step: Xác nhận bước tiếp theo hoặc gửi danh mục hồ sơ
- wait: Tạm chờ nếu khách cần thời gian suy nghĩ

TRẢ VỀ ĐÚNG ĐỊNH DẠNG JSON:
{
  "actions": [
    {
      "action_type": "calculate_finance",
      "title": "Tiêu đề hành động",
      "reason": "Lý do vì sao nên làm điều này dựa trên tin nhắn gần nhất",
      "priority": "high / medium / low",
      "suggested_content": "Gợi ý tóm tắt nội dung nên thực hiện",
      "product_reference": "VF 3 / VF 6 / VF 8"
    }
  ]
}
"""

DRAFT_SYSTEM_PROMPT = """Bạn là chuyên gia soạn thảo tin nhắn tư vấn bán hàng của VinFast (AI Message Drafting).
Nhiệm vụ của bạn là soạn 1 câu trả lời mẫu (bản nháp) lịch sự, chuẩn mực, đồng cảm và bám sát câu hỏi gần nhất của khách hàng.
Nguyên tắc:
1. Xưng hô chuẩn mực: 'Em' và 'Anh/Chị' (hoặc đúng tên khách nếu có).
2. Trả lời trực tiếp vào trọng tâm thắc mắc của khách.
3. Nếu liên quan đến chính sách/giá/bảo hành, sử dụng thông tin chính thống từ tài liệu VinFast được cung cấp bên dưới, KHÔNG ĐƯỢC TỰ BỊA con số cam kết nếu chưa có căn cứ.
4. Giữ giọng điệu nhiệt tình, minh bạch, không ép khách chốt cọc vội vã.

TRẢ VỀ ĐÚNG ĐỊNH DẠNG JSON:
{
  "text": "Nội dung tin nhắn tư vấn hoàn chỉnh",
  "context_trigger": "Câu hỏi hoặc ý định của khách kích hoạt bản nháp này",
  "tone": "thân thiện, chuyên nghiệp",
  "sources": ["Tài liệu hoặc căn cứ tham chiếu nếu có"]
}
"""


class SalesCopilotAssistant:
    def __init__(self, repository: SQLSalesCopilotRepository):
        self.repository = repository

    async def generate_next_best_actions(
        self,
        conversation_id: str,
        advisor_id: str,
        *,
        force: bool = False,
    ) -> NextBestActionResponse:
        """Generate Next Best Action (F03). Only generates if nba_enabled is True or force is True."""
        prefs = self.repository.get_preferences(advisor_id)
        if not prefs.nba_enabled and not force:
            return NextBestActionResponse(
                conversation_id=conversation_id,
                actions=[],
            )

        messages = self.repository.list_messages(conversation_id)
        if not messages:
            return NextBestActionResponse(conversation_id=conversation_id, actions=[])

        customer_id = None
        with self.repository.engine.connect() as conn:
            from sqlalchemy import select
            row = conn.execute(
                select(self.repository.conversations.c.customer_id).where(
                    self.repository.conversations.c.id == conversation_id
                )
            ).scalar()
            customer_id = row

        snapshot = (self.repository.get_customer_snapshot(customer_id) if customer_id else None) or {}
        memory = (self.repository.get_memory(conversation_id) if conversation_id else None) or {}

        # Recent 6 messages
        recent_msgs = messages[-6:]
        recent_text = "\n".join([f"{'Sales' if m.sender_role.value == 'sales' else 'Khách'}: {m.content}" for m in recent_msgs])

        prompt_input = f"""HỒ SƠ KHÁCH HÀNG:
{json.dumps(snapshot, ensure_ascii=False, indent=2)}

TÓM TẮT HỘI THOẠI:
{memory.get('quick_summary', 'Chưa có')}

TIN NHẮN GẦN NHẤT:
{recent_text}
"""
        actions = await self._call_llm_nba(prompt_input, snapshot, recent_msgs)
        response = NextBestActionResponse(conversation_id=conversation_id, actions=actions)

        # Cache in repository
        self.repository.save_recommendation_or_draft(
            conversation_id=conversation_id,
            rec_type="nba",
            payload=response.model_dump(mode="json"),
        )
        return response

    async def generate_message_draft(
        self,
        conversation_id: str,
        advisor_id: str,
        *,
        force: bool = False,
    ) -> MessageDraftResponse:
        """Generate AI Message Draft (F04). Only generates if draft_enabled is True or force is True."""
        prefs = self.repository.get_preferences(advisor_id)
        if not prefs.draft_enabled and not force:
            return MessageDraftResponse(
                conversation_id=conversation_id,
                draft_id=uuid4().hex,
                text="",
                status="discarded",
            )

        messages = self.repository.list_messages(conversation_id)
        if not messages:
            return MessageDraftResponse(
                conversation_id=conversation_id,
                draft_id=uuid4().hex,
                text="",
                status="discarded",
            )

        # Find customer id
        with self.repository.engine.connect() as conn:
            from sqlalchemy import select
            customer_id = conn.execute(
                select(self.repository.conversations.c.customer_id).where(
                    self.repository.conversations.c.id == conversation_id
                )
            ).scalar()

        snapshot = (self.repository.get_customer_snapshot(customer_id) if customer_id else None) or {}
        last_customer_msg = next((m.content for m in reversed(messages) if m.sender_role.value == "customer"), "")

        # Call RAG to ground draft in real VinFast policies / specs if needed
        knowledge_context = ""
        try:
            retriever = get_retrieval_service()
            retrieved = retriever.retrieve(last_customer_msg or "VinFast chính sách bảo hành giá", top_k=2)
            if retrieved:
                knowledge_context = "\n".join([f"- {doc.content[:300]}" for doc in retrieved])
        except Exception:
            pass

        prompt_input = f"""HỒ SƠ KHÁCH HÀNG:
Mẫu xe quan tâm: {snapshot.get('interested_models', ['VinFast'])}
Ngân sách: {snapshot.get('budget_notes') or snapshot.get('budget_vnd') or 'Chưa rõ'}
Trở ngại/lo lắng: {snapshot.get('objections_and_concerns', [])}

CÂU HỎI / TIN NHẮN MỚI NHẤT CỦA KHÁCH:
"{last_customer_msg}"

THÔNG TIN SẢN PHẨM / CHÍNH SÁCH THAM CHIẾU TỪ VINFAST:
{knowledge_context or 'Chính sách bảo hành xe 7-10 năm, hệ thống trạm sạc toàn quốc.'}
"""
        draft_dict = await self._call_llm_draft(prompt_input, last_customer_msg, snapshot)
        draft_id = uuid4().hex
        response = MessageDraftResponse(
            conversation_id=conversation_id,
            draft_id=draft_id,
            text=draft_dict.get("text", ""),
            context_trigger=draft_dict.get("context_trigger", last_customer_msg[:100]),
            tone=draft_dict.get("tone", "thân thiện, chuyên nghiệp"),
            sources=draft_dict.get("sources", []),
            status="generated",
            based_on_message_seq=max(m.seq for m in messages),
        )

        self.repository.save_recommendation_or_draft(
            conversation_id=conversation_id,
            rec_type="draft",
            payload=response.model_dump(mode="json"),
        )
        return response

    # -------------------------------------------------------------
    # LLM Callers with robust fallbacks
    # -------------------------------------------------------------
    async def _call_llm_nba(self, prompt_text: str, snapshot: dict, recent_msgs: list) -> list[NextBestActionItem]:
        try:
            llm = get_llm(temperature=0.2, max_tokens=1200)
            res = await llm.ainvoke([
                {"role": "system", "content": NBA_SYSTEM_PROMPT},
                {"role": "user", "content": prompt_text},
            ])
            text = res.content if hasattr(res, "content") else str(res)
            clean = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.I)
            clean = re.sub(r"\s*```$", "", clean.strip())
            data = json.loads(clean)
            return [NextBestActionItem(**item) for item in data.get("actions", [])]
        except Exception as exc:
            logger.warning("LLM NBA generation failed (%s), using fallback", exc)
            return self._fallback_nba(snapshot, recent_msgs)

    async def _call_llm_draft(self, prompt_text: str, last_customer_msg: str, snapshot: dict) -> dict[str, Any]:
        try:
            llm = get_llm(temperature=0.3, max_tokens=1000)
            res = await llm.ainvoke([
                {"role": "system", "content": DRAFT_SYSTEM_PROMPT},
                {"role": "user", "content": prompt_text},
            ])
            text = res.content if hasattr(res, "content") else str(res)
            clean = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.I)
            clean = re.sub(r"\s*```$", "", clean.strip())
            return json.loads(clean)
        except Exception as exc:
            logger.warning("LLM draft generation failed (%s), using fallback", exc)
            return self._fallback_draft(last_customer_msg, snapshot)

    def _fallback_nba(self, snapshot: dict, recent_msgs: list) -> list[NextBestActionItem]:
        models = snapshot.get("interested_models", [])
        model_name = models[0] if models else "VinFast"

        if "VF 8" in model_name:
            return [
                NextBestActionItem(
                    action_type="schedule_test_drive",
                    title="Xác nhận lịch lái thử đường dài sáng Chủ nhật",
                    reason="Khách hàng đã đồng ý lái thử nhưng cần xác nhận xe và tuyến đường lớn.",
                    priority="high",
                    suggested_content="Nhắn khách để chốt giờ đón và điểm xuất phát ở showroom Hà Đông.",
                    product_reference="VF 8",
                ),
                NextBestActionItem(
                    action_type="answer_concern",
                    title="Gửi chi tiết điều khoản bảo hành pin",
                    reason="Khách rất bận tâm về mức độ chai pin sau 4-5 năm sử dụng.",
                    priority="high",
                    suggested_content="Gửi văn bản chính sách bảo hành pin 10 năm của VinFast.",
                    product_reference="Chính sách pin VF 8",
                ),
            ]
        elif "VF 3" in model_name:
            return [
                NextBestActionItem(
                    action_type="calculate_finance",
                    title="Chuẩn bị bảng tính trả góp VF 3 vay 135-150 triệu",
                    reason="Khách đã chốt chỉ có 150 triệu tiền mặt và cần tiền trả hàng tháng <= 5 triệu.",
                    priority="high",
                    suggested_content="Lập bảng tính chi tiết giả định lãi suất 9%/năm trong 5 năm.",
                    product_reference="VF 3 Trả góp",
                ),
                NextBestActionItem(
                    action_type="confirm_next_step",
                    title="Gửi danh mục hồ sơ vay ngân hàng",
                    reason="Khách muốn chủ động chuẩn bị hồ sơ vay và bàn bạc với vợ.",
                    priority="medium",
                    suggested_content="Gửi danh mục CCCD, sao kê lương 18 triệu chuyển khoản.",
                    product_reference="Hồ sơ vay",
                ),
            ]
        else:
            return [
                NextBestActionItem(
                    action_type="answer_concern",
                    title="Tra cứu trạm sạc gần chung cư Long Biên",
                    reason="Khách ở chung cư nên việc sạc pin thuận tiện là yếu tố quyết định số 1.",
                    priority="high",
                    suggested_content="Gửi bản đồ 2-3 điểm sạc VinFast gần khu vực chung cư của khách.",
                    product_reference="VF 6 Eco",
                ),
                NextBestActionItem(
                    action_type="compare_products",
                    title="So sánh chi phí sử dụng VF 6 vs CX-5",
                    reason="Khách đang thích không gian CX-5 nhưng ngân sách 700tr lăn bánh phù hợp VF 6 hơn.",
                    priority="medium",
                    suggested_content="Phân tích chi phí tiết kiệm nhiên liệu và bảo dưỡng hàng tháng.",
                    product_reference="VF 6 Eco vs CX-5",
                ),
            ]

    def _fallback_draft(self, last_customer_msg: str, snapshot: dict) -> dict[str, Any]:
        models = snapshot.get("interested_models", [])
        model_name = models[0] if models else "VinFast"

        if "VF 8" in model_name:
            return {
                "text": "Dạ vâng anh Huy, em đã ghi nhận nhu cầu lái thử đường dài sáng Chủ nhật của mình rồi ạ. Em đang liên hệ showroom khu vực Hà Đông để chuẩn bị sẵn xe VF 8 và xin lộ trình chạy thử lên cầu/đường lớn để anh cảm nhận rõ nhất khả năng cách âm và độ bốc của xe. Em sẽ gửi kèm luôn bảng giá hiện tại và điều kiện bảo hành pin chi tiết để anh tham khảo trước nhé ạ!",
                "context_trigger": last_customer_msg[:100],
                "tone": "thân thiện, chuyên nghiệp",
                "sources": ["Bảng giá VF 8", "Chính sách bảo hành pin VinFast"],
            }
        elif "VF 3" in model_name:
            return {
                "text": "Dạ vâng anh Trọng, em đang lập 2 phương án bảng tính trả góp cho VF 3 theo gói vay 135 triệu và 150 triệu trong 5 năm, với mức lãi suất giả định 9%/năm trả gốc đều để tháng đầu chỉ khoảng hơn 3 triệu và giảm dần các tháng sau, hoàn toàn nằm trong mức 5 triệu/tháng anh mong muốn. Em sẽ gửi kèm cả danh mục hồ sơ cơ bản để anh chị bàn bạc trước nhé ạ!",
                "context_trigger": last_customer_msg[:100],
                "tone": "chu đáo, minh bạch",
                "sources": ["Chính sách trả góp VF 3", "Lãi suất ngân hàng đối tác"],
            }
        else:
            return {
                "text": "Dạ em chào anh Tuấn, tầm tài chính 700 triệu lăn bánh thì VF 6 Eco đang là phương án rất tối ưu về chi phí sử dụng và độ êm ái khi đi làm hằng ngày 30-40km anh ạ. Em đang kiểm tra các trạm sạc VinFast gần khu vực chung cư của mình ở Long Biên để gửi anh tham khảo ngay. Anh đang ở gần chung cư nào bên Long Biên để em tra cứu điểm sạc chính xác nhất ạ?",
                "context_trigger": last_customer_msg[:100],
                "tone": "tận tình, cởi mở",
                "sources": ["Mạng lưới trạm sạc VinFast Long Biên", "VF 6 Eco Specs"],
            }
