"""Response compatibility across structured generation and grounded Markdown publication."""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.copilot.nodes.answer import finalize_response, generate_answer
from src.agents.copilot.nodes.verification import check_grounding
from src.agents.copilot.state import Citation, CopilotResponse, GeneratedAnswer, Requirement
from src.agents.copilot.tools import build_evidence_context


def sample_hit():
    return {
        "chunk_id": "doc-vf8#chunk-1",
        "document_id": "PRICE_VF8",
        "content": "VF 8 Thế hệ mới có giá niêm yết 899 triệu đồng.",
        "title": "Bảng giá VF 8",
        "section": "Giá niêm yết",
        "page": 1,
        "source_uri": "https://vinfast.vn/price.pdf",
        "effective_from": "2026-10-01",
        "effective_to": None,
        "status": "active",
        "version": "2026.10",
        "product_model": "VF 8",
        "document_type": "price_list",
        "policy_type": None,
        "competitor_model": None,
        "retrieval_method": "dense",
        "native_score": 0.95,
        "rank": 1,
        "citation_id": "C1",
    }


def test_citation_excerpt():
    _, citations = build_evidence_context([sample_hit()])
    assert len(citations) == 1
    assert citations[0].citation_id == "C1"
    assert citations[0].excerpt == "VF 8 Thế hệ mới có giá niêm yết 899 triệu đồng."
    assert citations[0].title == "Bảng giá VF 8"


@pytest.mark.asyncio
async def test_generate_answer_renders_structured_citations():
    hit = sample_hit()
    _, citations = build_evidence_context([hit])
    state = {
        "query": "Giá VF 8 bao nhiêu?",
        "answer_context": f"[C1] {hit['content']}",
        "resolved_date": "2026-10-13",
        "selected_evidence": [hit],
        "generation_count": 0,
    }

    state["requirements"] = [Requirement(requirement_id="R1", description="Giá VF 8")]
    mock_text = "VF 8 Thế hệ mới có giá niêm yết từ 899 triệu đồng. [C1]"
    generated = GeneratedAnswer(
        claims=[
            {
                "text": mock_text.removesuffix(" [C1]"),
                "requirement_ids": ["R1"],
                "citation_ids": ["C1"],
            }
        ]
    )
    with patch("src.agents.copilot.nodes.answer._invoke_json", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = (generated, {"input_tokens": 100, "output_tokens": 50})
        res = await generate_answer(state)
        assert res["draft_answer"] == mock_text
        assert res["generation_count"] == 1
        assert res["route"] == "check_grounding"


@pytest.mark.asyncio
async def test_finalize_response_attaches_citations_and_excerpt():
    hit = sample_hit()
    state = {
        "query": "Giá VF 8 bao nhiêu?",
        "product_models": ["VF 8"],
        "draft_answer": "VF 8 có giá 899 triệu đồng theo bảng giá. [C1]",
        "draft_citations": ["C1"],
        "selected_evidence": [hit],
        "request_id": "a" * 32,
    }

    from src.agents.copilot.state import StructuredGroundingReview
    from src.agents.copilot.validation.structured import render_answer
    from tests.test_agents.test_copilot_agentic import checked

    state["requirements"] = [Requirement(requirement_id="R1", description="Giá VF 8")]
    state["generated_answer"] = GeneratedAnswer(
        claims=[
            {
                "text": "VF 8 có giá 899 triệu đồng theo bảng giá.",
                "requirement_ids": ["R1"],
                "citation_ids": ["C1"],
            }
        ]
    )
    state["draft_answer"] = render_answer(state["generated_answer"])
    state["resolved_date"] = "2026-10-13"
    with patch("src.agents.copilot.nodes.verification._invoke_json", new_callable=AsyncMock) as invoke:
        invoke.return_value = (StructuredGroundingReview(**checked(scope="VF 8")), {})
        state.update(await check_grounding(state))
    res = await finalize_response(state)
    assert res["route"] == "end"
    final: CopilotResponse = res["final_response"]
    assert final.status == "answered"
    assert len(final.citations) == 1
    assert final.citations[0].citation_id == "C1"
    assert final.citations[0].excerpt == "VF 8 Thế hệ mới có giá niêm yết 899 triệu đồng."
    # A price already stated in the answer is not a complementary product highlight.
    assert final.product_insights == []


def test_build_product_insights_strictly_from_snapshot_citations():
    from src.agents.copilot.insights import build_product_insights

    # Empty citations returns empty insights
    assert build_product_insights({"product_models": ["VF 3"]}, "text", []) == []

    citations = [
        Citation(
            citation_id="C1",
            chunk_id="CHUNK_1",
            document_id="DOC_1",
            title="Bảng giá VF 3",
            section="Giá bán lẻ",
            effective_from="2026-01-01",
            product_model="VF 3",
            document_type="price_list",
            excerpt="VF 3 Plus có giá 296 triệu đồng.",
        ),
        Citation(
            citation_id="C2",
            chunk_id="CHUNK_2",
            document_id="DOC_2",
            title="Chính sách ưu đãi sạc",
            section="Ưu đãi trạm V-GREEN",
            effective_from="2026-01-01",
            product_model="ALL",
            document_type="policy",
            excerpt="Miễn phí sạc pin tại trạm V-GREEN trong 1 năm đầu.",
        ),
    ]

    insights = build_product_insights(
        {"query": "VF 3 giá bao nhiêu?", "product_models": ["VF 3"]},
        "VF 3 Plus có giá 296 triệu đồng. [C1]",
        existing_citations=citations,
    )
    assert len(insights) == 2
    by_source = {insight.citation.citation_id: insight for insight in insights}
    assert by_source["C1"].category == "policy"
    assert by_source["C1"].product_model == "VF 3"
    assert "296 triệu" in by_source["C1"].summary
    assert by_source["C2"].category == "policy"
    assert by_source["C2"].product_model == "ALL"
    assert "Miễn phí sạc" in by_source["C2"].summary
    assert all(i.citation is not None for i in insights)
