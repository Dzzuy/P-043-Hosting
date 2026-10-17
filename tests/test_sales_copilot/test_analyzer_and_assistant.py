"""Unit tests for Sales Copilot Analyzer (F01, F02, F05, F06) and Assistant (F03, F04)."""

import pytest
from src.config import get_settings
from src.integrations.sales_copilot_repository import SQLSalesCopilotRepository
from src.models.sales_copilot import SalesPreferences
from src.services.sales_conversation_service import SalesConversationService
from src.services.sales_copilot_analyzer import SalesCopilotAnalyzer
from src.services.sales_copilot_assistant import SalesCopilotAssistant


@pytest.mark.asyncio
async def test_analyzer_on_demand():
    settings = get_settings()
    repo = SQLSalesCopilotRepository(settings.database_url)
    repo.ensure_schema()
    service = SalesConversationService(repo)
    analyzer = SalesCopilotAnalyzer(repo)

    # Ensure seeded
    service.seed_real_conversations_from_docx("data/message_sales.docx", "test_advisor")
    customers = repo.list_customers_for_advisor("test_advisor")
    c3 = next(c for c in customers if c.name == "Anh Đức Trọng")
    conv_id = repo.get_or_create_conversation(c3.id)

    # Trigger analysis
    result = await analyzer.analyze_conversation(conv_id, "test_advisor")
    assert result["status"] == "success"

    # Verify F01 Profile
    profile = result["profile"]
    assert "VF 3" in profile.get("interested_models", [])
    assert profile.get("down_payment_vnd") == 150000000 or profile.get("budget_vnd") == 285000000

    # Verify F02 Memory
    memory = result["memory"]
    assert len(memory.get("quick_summary", "")) > 10
    assert len(memory.get("timeline", [])) >= 2

    # Verify F05 Tasks
    tasks = result["tasks"]
    assert len(tasks) >= 2
    task_titles = [t["title"] for t in tasks]
    assert any("trả góp" in t.lower() or "bảng" in t.lower() for t in task_titles)

    # Verify F06 Lead Status & Score
    lead_status = result["lead_status"]
    assert lead_status["score"] >= 60
    assert lead_status["stage"] in ["considering", "negotiating", "appointment"]


@pytest.mark.asyncio
async def test_assistant_nba_and_draft_toggles():
    settings = get_settings()
    repo = SQLSalesCopilotRepository(settings.database_url)
    repo.ensure_schema()
    service = SalesConversationService(repo)
    assistant = SalesCopilotAssistant(repo)

    service.seed_real_conversations_from_docx("data/message_sales.docx", "test_advisor")
    customers = repo.list_customers_for_advisor("test_advisor")
    c2 = next(c for c in customers if c.name == "Anh Quang Huy")
    conv_id = repo.get_or_create_conversation(c2.id)

    # 1. When flags are OFF
    repo.update_preferences(SalesPreferences(advisor_id="test_advisor", nba_enabled=False, draft_enabled=False))
    nba_off = await assistant.generate_next_best_actions(conv_id, "test_advisor", force=False)
    assert len(nba_off.actions) == 0

    draft_off = await assistant.generate_message_draft(conv_id, "test_advisor", force=False)
    assert draft_off.text == ""

    # 2. When flags are ON ("Tự gợi ý khi bật")
    repo.update_preferences(SalesPreferences(advisor_id="test_advisor", nba_enabled=True, draft_enabled=True))
    nba_on = await assistant.generate_next_best_actions(conv_id, "test_advisor", force=False)
    assert len(nba_on.actions) >= 1
    assert any("VF 8" in a.product_reference or "lái thử" in a.title.lower() or "pin" in a.title.lower() for a in nba_on.actions)

    draft_on = await assistant.generate_message_draft(conv_id, "test_advisor", force=False)
    assert len(draft_on.text) > 30
    assert draft_on.status == "generated"
