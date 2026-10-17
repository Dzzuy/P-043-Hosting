"""Customer Intelligence UI smoke: real API/analyzer/storage, synthetic model output."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.qa.customer_workspace_fixture import app, conv, customer, messages, repo  # noqa: E402
from src.models.sales_copilot import CustomerFact, CustomerProfileSnapshot  # noqa: E402
from src.services.sales_copilot_analyzer import SalesCopilotAnalyzer  # noqa: E402

fact = CustomerFact(field="usage_purpose", value="Đi làm", verification_status="inferred",
                    source_message_ids=[messages[0].id])
profile = CustomerProfileSnapshot(interested_models=["VF 3"], budget_vnd=300000000,
                                  usage_purpose="Đi làm", purchase_timeline="Tháng sau", facts=[fact])
repo.save_facts_and_snapshot(customer, [fact], profile)
memory = {
    "quick_summary": "Khách đang cân nhắc VF 3 và đã hiểu phương án trả góp. Hai bên còn chờ chốt lịch xem xe.",
    "customer_intelligence": {
        "key_points": [
            {"topic": "Phương án trả góp", "question": "Khách hỏi mức trả hàng tháng",
             "answer": "Sales đã giải thích phương án vay phù hợp ngân sách 300 triệu.", "status": "answered",
             "source_message_ids": [messages[0].id, messages[1].id]},
            {"topic": "Lịch xem xe", "question": "Khách muốn xem xe tháng sau", "answer": "Chưa thống nhất ngày và giờ.",
             "status": "open", "source_message_ids": [messages[2].id]},
        ],
        "outcomes": [{"text": "Khách xác nhận đã hiểu phương án vay.", "source_message_ids": [messages[2].id]}],
        "commitments": [{"actor": "Sales", "action": "Gửi bảng tính trả góp", "time": "Chiều nay",
                         "source_message_ids": [messages[1].id]}],
    },
    "detailed_summary": "Sales đã tư vấn trả góp. Khách xác nhận đã hiểu phương án vay; còn chờ lịch xem xe.",
    "timeline": [
        {"title": "Tư vấn trả góp", "description": "Sales đã giải thích phương án vay", "event_type": "consulted",
         "source_message_id": messages[1].id},
        {"title": "Xác nhận phương án", "description": "Khách xác nhận đã hiểu phương án vay", "event_type": "resolved",
         "source_message_id": messages[2].id},
    ],
    "pending_items": ["Chưa chốt lịch xem xe"],
    "key_promises": ["Sales gửi bảng tính trả góp vào chiều nay"],
}
repo.save_memory(conv, **memory, analyzed_through_seq=75)


async def analysis(_):
    return {"profile": profile.model_dump(), "memory": memory}


analyzer = SalesCopilotAnalyzer(repo)
analyzer._call_llm_analysis = analysis
app.state.sales_copilot_analyzer = analyzer

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8004, log_level="warning")
