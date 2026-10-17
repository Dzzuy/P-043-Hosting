"""Deterministic UI QA fixture. Isolated SQLite, loopback only, no provider/real customer data."""

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["APP_ENV"] = "test"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from src.api.sales_copilot import get_current_user, router
from src.integrations.sales_copilot_repository import SQLSalesCopilotRepository
from src.models.auth import AuthenticatedUser
from src.models.sales_copilot import CustomerFact, CustomerProfileSnapshot, LeadStatus, SalesPreferences
from src.services.sales_conversation_service import SalesConversationService

app = FastAPI()
identity = AuthenticatedUser(user_id="ui-fixture", username="fixture", display_name="Sales QA", role="advisor")


async def current():
    return identity


app.dependency_overrides[get_current_user] = current
app.state.current_user = lambda request: current()
engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
repo = SQLSalesCopilotRepository("sqlite://", engine=engine)
repo.ensure_schema()
service = SalesConversationService(repo)
app.state.sales_conversation_service = service
app.state.sales_copilot_repository = repo
customer = repo.create_customer(name="Khách kiểm thử nguồn", advisor_id=identity.user_id)
conv = repo.get_or_create_conversation(customer)
messages = [
    repo.add_message(conv, "customer" if n % 2 == 0 else "sales", f"Tin nguồn kiểm thử {n + 1}") for n in range(80)
]
fact = CustomerFact(
    field="usage_purpose", value="Đi làm", verification_status="inferred", source_message_ids=[messages[0].id]
)
repo.save_facts_and_snapshot(
    customer, [fact], CustomerProfileSnapshot(interested_models=["VF 3"], usage_purpose="Đi làm", facts=[fact])
)
repo.save_memory(
    conv,
    "Khách cần tư vấn đi làm, đang cân nhắc VF 3.",
    "",
    [{"title": "Nhu cầu ban đầu", "description": "Khách muốn xe đi làm", "source_message_id": messages[0].id}],
    [],
    [],
    analyzed_through_seq=75,
)
repo.save_lead_score(LeadStatus(customer_id=customer, stage="considering"))
repo.update_preferences(SalesPreferences(advisor_id=identity.user_id, draft_enabled=True))
repo.save_recommendation_or_draft(
    conv,
    "draft",
    {
        "text": "Bản nháp QA đã kiểm tra.",
        "based_on_message_seq": 80,
        "generated_at": datetime.now(UTC).isoformat(),
        "draft_id": "draft-qa",
        "sources": [],
    },
)
service.create_followup_task(
    conv, identity.user_id, title="Gọi lại đúng hẹn", priority="high", due_at=datetime(2020, 1, 1, tzinfo=UTC)
)
app.include_router(router, prefix="/api/v1")


@app.get("/api/v1/auth/me")
async def me():
    return identity


@app.get("/api/v1/practice/scenarios")
async def scenarios():
    return []


@app.get("/qa/state")
async def qa_state():
    return {
        "conversation_id": conv,
        "customer_id": customer,
        "source_id": messages[0].id,
        "count": len(repo.list_messages(conv)),
    }


class FixtureAnalyzer:
    async def analyze_conversation(self, conversation_id, advisor_id):
        repo.save_memory(
            conv,
            "Tóm tắt QA cập nhật đến tin mới nhất.",
            "",
            [],
            [],
            [],
            analyzed_through_seq=max(m.seq for m in repo.list_messages(conv)),
        )
        return {"status": "success"}


app.state.sales_copilot_analyzer = FixtureAnalyzer()
app.mount("/", StaticFiles(directory=str(Path(__file__).resolve().parents[2] / "frontend/dist"), html=True), name="ui")
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8002, log_level="warning")
