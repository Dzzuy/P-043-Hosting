"""Loopback-only shared Copilot UI fixture: real API/storage, synthetic data and LLM response."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.qa.customer_workspace_fixture import app, engine, identity, repo  # noqa: E402
from src.agents.copilot.runtime import CopilotAdmission  # noqa: E402
from src.agents.copilot.state import Citation, CopilotResponse  # noqa: E402
from src.api.copilot import router  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.integrations.copilot_sessions import SQLCopilotSessionsRepository  # noqa: E402
from src.services import copilot_query  # noqa: E402

# Register the real knowledge API ahead of the existing static frontend mount.
ui = app.router.routes.pop()
app.include_router(router, prefix="/api/v1")
app.state.copilot_sessions = SQLCopilotSessionsRepository("sqlite://", engine=engine)
app.state.copilot_admission = CopilotAdmission(get_settings())
app.state.copilot_readiness = lambda: None
seen = []

customer = repo.create_customer(name="Khách thứ hai VF 6", advisor_id=identity.user_id)
conversation = repo.get_or_create_conversation(customer)
repo.add_message(conversation, "customer", "Tôi quan tâm VF 6, ngân sách riêng của khách thứ hai.")


async def graph(state, **kwargs):
    seen.append({"query": state["query"], "customer_context": state["customer_context"], "history": state["history"]})
    await asyncio.sleep(2)
    return {"final_response": CopilotResponse(
        status="answered", answer="Thông tin kiểm thử kiến thức xe đã xác minh [C1].",
        citations=[Citation(citation_id="C1", document_id="qa", chunk_id="qa_1", title="Tài liệu QA",
                            excerpt="Nguồn tổng quát cho sales; dữ liệu kiểm thử.")],
    )}


copilot_query.copilot_agent.ainvoke = graph
copilot_query.maybe_trigger_background_summarization = lambda **kwargs: None


@app.get("/qa/copilot-state")
async def copilot_state():
    return {"seen": seen, "session_id": app.state.copilot_sessions.advisor_session(identity.user_id)}


app.router.routes.append(ui)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8003, log_level="warning")
