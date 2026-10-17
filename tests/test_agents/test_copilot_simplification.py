"""Tests for simplified Copilot Agent: direct Markdown generation and self-check."""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.copilot.nodes.answer import finalize_response, generate_answer
from src.agents.copilot.nodes.verification import check_grounding
from src.agents.copilot.state import Citation, CopilotResponse, SelfCheckVerdict
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


def test_self_check_verdict_contract():
    verdict = SelfCheckVerdict(
        grounded=True,
        feedback="",
        unsupported_claims=[],
        missing_information=[],
    )
    assert verdict.grounded is True

    failed_verdict = SelfCheckVerdict(
        grounded=False,
        feedback="Suy diễn xe đi được 4 ngày không cần sạc",
        unsupported_claims=["Xe chạy 4 ngày không cần sạc"],
        missing_information=[],
    )
    assert failed_verdict.grounded is False
    assert len(failed_verdict.unsupported_claims) == 1


@pytest.mark.asyncio
async def test_generate_answer_parses_citations():
    hit = sample_hit()
    _, citations = build_evidence_context([hit])
    state = {
        "query": "Giá VF 8 bao nhiêu?",
        "answer_context": f"[C1] {hit['content']}",
        "resolved_date": "2026-10-13",
        "selected_evidence": [hit],
        "generation_count": 0,
    }

    mock_text = "VF 8 Thế hệ mới có giá niêm yết từ 899 triệu đồng. [C1]"
    with patch("src.agents.copilot.nodes.answer._invoke_text", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = (mock_text, {"input_tokens": 100, "output_tokens": 50})
        res = await generate_answer(state)
        assert res["draft_answer"] == mock_text
        assert res["generation_count"] == 1
        assert res["route"] == "check_grounding"


@pytest.mark.asyncio
async def test_check_grounding_passes_when_grounded():
    hit = sample_hit()
    state = {
        "query": "Giá VF 8 bao nhiêu?",
        "draft_answer": "VF 8 có giá 899 triệu. [C1]",
        "answer_context": f"[C1] {hit['content']}",
        "resolved_date": "2026-10-13",
        "generation_count": 1,
    }

    mock_verdict = SelfCheckVerdict(grounded=True)
    with patch("src.agents.copilot.nodes.verification._invoke_json", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = (mock_verdict, {"input_tokens": 80, "output_tokens": 20})
        res = await check_grounding(state)
        assert res["route"] == "finalize_response"
        assert res["self_check"].grounded is True


@pytest.mark.asyncio
async def test_check_grounding_retries_on_extrapolation():
    hit = sample_hit()
    state = {
        "query": "Giá VF 8 bao nhiêu?",
        "draft_answer": "VF 8 có giá 899 triệu và chạy 4 ngày không cần sạc. [C1]",
        "answer_context": f"[C1] {hit['content']}",
        "resolved_date": "2026-10-13",
        "generation_count": 1,
    }

    mock_verdict = SelfCheckVerdict(
        grounded=False,
        feedback="Phát biểu chạy 4 ngày là suy diễn vượt chứng cứ.",
        unsupported_claims=["chạy 4 ngày không cần sạc"],
    )
    with patch("src.agents.copilot.nodes.verification._invoke_json", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = (mock_verdict, {"input_tokens": 80, "output_tokens": 20})
        with patch("src.agents.copilot.nodes.verification.can_regenerate", return_value=True):
            res = await check_grounding(state)
            assert res["route"] == "generate_answer"
            assert "suy diễn" in res["feedback"]
            assert res["unsupported_claims"] == ["chạy 4 ngày không cần sạc"]


@pytest.mark.asyncio
async def test_check_grounding_abstains_on_second_failed_attempt():
    hit = sample_hit()
    state = {
        "query": "Giá VF 8 bao nhiêu?",
        "draft_answer": "VF 8 có giá 899 triệu và chạy 4 ngày không cần sạc. [C1]",
        "answer_context": f"[C1] {hit['content']}",
        "resolved_date": "2026-10-13",
        "generation_count": 2,
    }

    mock_verdict = SelfCheckVerdict(
        grounded=False,
        feedback="Vẫn còn suy diễn.",
        unsupported_claims=["chạy 4 ngày không cần sạc"],
    )
    with patch("src.agents.copilot.nodes.verification._invoke_json", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = (mock_verdict, {"input_tokens": 80, "output_tokens": 20})
        with patch("src.agents.copilot.nodes.verification.can_regenerate", return_value=False):
            res = await check_grounding(state)
            assert res["route"] == "fallback_response"
            assert res["fallback_reason"] == "verification_failed"


@pytest.mark.asyncio
async def test_finalize_response_attaches_citations_and_excerpt():
    hit = sample_hit()
    state = {
        "query": "Giá VF 8 bao nhiêu?",
        "product_models": ["VF 8"],
        "draft_answer": "VF 8 có giá 899 triệu đồng theo bảng giá. [C1]",
        "draft_citations": ["C1"],
        "selected_evidence": [hit],
        "self_check": SelfCheckVerdict(grounded=True),
        "request_id": "a" * 32,
    }

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


