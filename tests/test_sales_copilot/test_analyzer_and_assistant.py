"""Draft requests use confirmed facts and fail closed without demo replies."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from src.config import get_settings
from src.integrations.sales_copilot_repository import SQLSalesCopilotRepository
from src.models.customer_intelligence import DraftAnswer
from src.services.customer_pii import CustomerPII
from src.services.sales_copilot_assistant import SalesCopilotAssistant


@pytest.fixture
def conversation(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "sales_pii_key", SecretStr(Fernet.generate_key().decode()))
    monkeypatch.setattr(get_settings(), "sales_intelligence_v2_enabled", True)
    repo = SQLSalesCopilotRepository(f"sqlite:///{tmp_path / 'draft.db'}")
    customer = repo.create_customer(name="Draft test", advisor_id="sales")
    conv = repo.get_or_create_conversation(customer)
    repo.add_message(conv, "customer", "Tôi muốn tư vấn VF 6. SĐT: 0912345678")
    yield repo, customer, conv
    repo.engine.dispose()


@pytest.mark.asyncio
async def test_request_draft_uses_confirmed_profile_and_original_cursor(conversation, monkeypatch):
    repo, customer, conv = conversation
    repo.save_profile_override(conv, "budget_vnd", 500000000, "sales")
    retrieval = SimpleNamespace(retrieve=lambda query, **_: [])
    monkeypatch.setattr("src.services.sales_copilot_assistant.get_retrieval_service", lambda: retrieval)
    seen = []

    async def ask(self, system, payload, schema):
        assert schema is DraftAnswer
        seen.append(payload)
        assert payload["profile"] == {"budget_vnd": 500000000}
        repo.add_message(conv, "customer", "Tin mới trong lúc tạo nháp")
        return DraftAnswer(text="Em sẽ kiểm tra thông tin để tư vấn anh/chị.")

    monkeypatch.setattr(CustomerPII, "ask", ask)
    response = await SalesCopilotAssistant(repo).generate_message_draft(conv, "sales")
    assert len(seen) == 1
    assert response.based_on_message_seq == 1
    assert response.status == "generated"
    assert repo.get_latest_recommendation(conv, "draft")["text"] == response.text
    assert len(repo.list_messages(conv)) == 2  # Draft was not sent.


@pytest.mark.asyncio
async def test_draft_retrieval_receives_masked_query_and_failure_saves_nothing(conversation, monkeypatch):
    repo, _, conv = conversation
    queries = []

    def retrieve(query, **kwargs):
        queries.append(query)
        raise RuntimeError("Unavailable")

    monkeypatch.setattr(
        "src.services.sales_copilot_assistant.get_retrieval_service", lambda: SimpleNamespace(retrieve=retrieve)
    )
    model = AsyncMock()
    monkeypatch.setattr(CustomerPII, "ask", model)
    with pytest.raises(RuntimeError):
        await SalesCopilotAssistant(repo).generate_message_draft(conv, "sales")
    assert queries and "0912345678" not in queries[0]
    assert "[SDT_1]" in queries[0]
    model.assert_not_called()
    assert repo.get_latest_recommendation(conv, "draft") is None


@pytest.mark.asyncio
async def test_draft_authorization_before_any_model_call(conversation, monkeypatch):
    repo, _, conv = conversation
    model = AsyncMock()
    monkeypatch.setattr(CustomerPII, "ask", model)
    with pytest.raises(LookupError):
        await SalesCopilotAssistant(repo).generate_message_draft(conv, "other")
    model.assert_not_called()
