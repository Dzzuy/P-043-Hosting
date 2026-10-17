"""Unit tests for Sales Copilot docx extraction and PostgreSQL repository."""

import pytest
from src.config import get_settings
from src.integrations.sales_copilot_repository import SQLSalesCopilotRepository
from src.services.sales_conversation_service import SalesConversationService, extract_paragraphs_from_docx


def test_docx_paragraph_extraction():
    paragraphs = extract_paragraphs_from_docx("data/message_sales.docx")
    assert len(paragraphs) >= 150
    assert any("Hội thoại 1" in p for p in paragraphs)
    assert any("Hội thoại 2" in p for p in paragraphs)
    assert any("Hội thoại 3" in p for p in paragraphs)


def test_repository_and_seed():
    settings = get_settings()
    repo = SQLSalesCopilotRepository(settings.database_url)
    repo.ensure_schema()
    service = SalesConversationService(repo)

    # Seed
    seeded = service.seed_real_conversations_from_docx("data/message_sales.docx", "test_advisor")
    assert len(seeded) == 3

    # Check customers
    customers = repo.list_customers_for_advisor("test_advisor")
    assert len(customers) >= 3
    customer_names = [c.name for c in customers]
    assert "Anh Minh Tuấn" in customer_names
    assert "Anh Quang Huy" in customer_names
    assert "Anh Đức Trọng" in customer_names

    # Check messages in conversation 1
    c1 = next(c for c in customers if c.name == "Anh Minh Tuấn")
    conv1_id = repo.get_or_create_conversation(c1.id)
    msgs1 = repo.list_messages(conv1_id)
    assert len(msgs1) > 20
    assert any("VF 6" in m.content for m in msgs1)
