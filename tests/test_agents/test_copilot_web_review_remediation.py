"""Tests for the Copilot workflow and complementary web review remediation (October 14, 2026)."""

import pytest

from src.agents.copilot.insights import (
    _clean_model,
    _clean_summary,
    build_complementary_insights,
    build_product_insights,
)
from src.agents.copilot.nodes import answer as answer_nodes
from src.agents.copilot.nodes import guard as guard_nodes
from src.agents.copilot.state import (
    Citation,
    CopilotResponse,
    GeneratedAnswer,
    IntakeDecision,
    Requirement,
    SelfCheckVerdict,
    VerifiedAnswerSnapshot,
)


def test_clean_summary_preserves_essential_conditions_and_warnings():
    """Verify P1: _clean_summary does NOT strip (*) Lưu ý or warnings regarding features/delivery."""
    raw = "Tính năng X thông minh. (*) Lưu ý: Một số tính năng sẽ chưa có sẵn tại thời điểm giao xe."
    cleaned = _clean_summary(raw, title="Chi tiết tính năng")
    assert "(*) Lưu ý" in cleaned
    assert "Một số tính năng sẽ chưa có sẵn tại thời điểm giao xe" in cleaned


def test_clean_model_preserves_scope_all():
    """Verify P1: _clean_model preserves scope ALL instead of coercing to the first model in state."""
    model = _clean_model("ALL", ["VF 5", "VF 6"])
    assert model == "ALL"

    model_lower = _clean_model("all", ["VF 5"])
    assert model_lower == "ALL"

    model_specific = _clean_model("VF 7", ["VF 5"])
    assert model_specific == "VF 7"


def test_atomic_requirements_preserves_qualifiers_and_avoids_synthetic_assumptions():
    """Verify P2: atomic_requirements retains date and customer qualifiers without adding false pin/VAT assumptions."""
    req = Requirement(
        requirement_id="R1",
        description="Giá niêm yết và quãng đường của VF 5 áp dụng tháng 10/2026 cho khách dịch vụ.",
        kind="fact",
    )
    decision = IntakeDecision(
        guard_decision={"decision": "allow", "reason": "none"},
        route="complex",
        requirements=[req],
    )
    atomized = guard_nodes.atomic_requirements(decision)
    descriptions = [r.description for r in atomized.requirements]
    assert len(descriptions) >= 2
    # Verify date and customer qualifiers were preserved
    assert any("tháng 10/2026" in d or "khách dịch vụ" in d for d in descriptions)
    # Verify we didn't inject synthetic "kèm pin/VAT và cấu hình áp dụng" when not mentioned
    assert not any("kèm pin/VAT và cấu hình áp dụng" in d for d in descriptions)


@pytest.mark.asyncio
async def test_pure_greeting_routes_to_terminal_reply():
    """Verify Phase B: pure greetings (hi, xin chào, cảm ơn) return terminal response without LLM / search."""
    for greeting in ["hi", "xin chào!", "Hello", "Cảm ơn bạn.", "Bạn là ai?"]:
        state = {"query": greeting, "history": []}
        result = await guard_nodes.analyze_and_route(state)
        assert result["route"] == "end"
        final: CopilotResponse = result["final_response"]
        assert final.status == "answered"
        assert final.answer_kind == "coaching"
        assert len(final.citations) == 0
        assert len(final.missing_information) == 0
        assert len(final.answer) > 10


@pytest.mark.asyncio
async def test_mixed_greeting_does_not_short_circuit():
    """Verify Phase B: 'Hi, giá VF 5 bao nhiêu?' is a task and does not short-circuit as pure greeting."""
    query = "Hi, giá VF 5 bao nhiêu?"
    # _check_pure_greeting must return None
    assert guard_nodes._check_pure_greeting(query) is None


def test_complementary_insights_filters_duplicate_facts_from_answer():
    """Verify Phase D: complementary insights excludes cards whose core facts are already in the answer."""
    citations = [
        Citation(
            citation_id="C1",
            chunk_id="price-1",
            document_id="doc-price",
            title="Giá VF 5 Plus",
            excerpt="VF 5 Plus có giá niêm yết 496 triệu đồng.",
            product_model="VF 5",
            document_type="price_list",
        ),
        Citation(
            citation_id="C2",
            chunk_id="warranty-1",
            document_id="doc-warranty",
            title="Bảo hành VF 5",
            excerpt="VF 5 được bảo hành chính hãng 7 năm hoặc 160.000 km.",
            product_model="VF 5",
            document_type="highlight",
        ),
    ]

    # If answer already explains the price of 496 triệu:
    answer_text = "Giá niêm yết của xe VF 5 Plus là 496 triệu đồng đã gồm VAT [C1]."
    insights = build_complementary_insights(
        {"product_models": ["VF 5"]},
        answer_text=answer_text,
        existing_citations=citations,
    )

    # Price card should be omitted due to semantic duplication; warranty card should be retained!
    assert len(insights) == 1
    assert insights[0].title == "Bảo hành VF 5"
    assert "7 năm" in insights[0].summary
    assert insights[0].product_model == "VF 5"


@pytest.mark.asyncio
async def test_snapshot_strictly_owns_published_suggestions():
    """Verify P1: if snapshot has suggestions=None, subsequent drafts cannot leak suggestions into publication."""
    citation = Citation(
        citation_id="C1",
        chunk_id="chunk-1",
        document_id="doc-1",
        title="Bảng giá",
    )
    snapshot = VerifiedAnswerSnapshot(
        answer="VF 5 giá 468 triệu [C1]",
        draft_hash="hash1",
        context_hash="ctx1",
        requirements_hash="req1",
        resolved_date="2026-10-14",
        citations=[citation],
        answered_requirement_ids=["R1"],
        status="answered",
        suggested_message=None,  # Snapshot specifically had NO suggested message
        suggested_next_question=None,
    )

    # State has subsequent suggestions that should not leak if snapshot does not have them
    state = {
        "verified_snapshot": snapshot,
        "resolved_date": "2026-10-14",
        "suggested_message": "Leak suggestion that should never be published!",
        "suggested_next_question": "Leak question?",
        "self_check": SelfCheckVerdict(grounded=False, suggestions_safe=True),
    }

    result = await answer_nodes.finalize_response(state)
    final: CopilotResponse = result["final_response"]
    assert final.suggested_message is None
    assert final.suggested_next_question is None
