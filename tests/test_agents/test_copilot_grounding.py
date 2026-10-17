"""Regression checks after integrating the baseline Copilot graph."""

import pytest

from src.agents.copilot.graph import copilot_agent
from src.agents.copilot.nodes import _merge_evidence
from src.agents.copilot.state import GeneratedAnswer
from tests.test_agents.test_copilot_agentic import draft_state, generated


def _hit(document_id: str, chunk_id: str, score: float) -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "content": "VF 8 có trong bảng giá.",
        "title": "Bảng giá",
        "section": None,
        "page": None,
        "source_uri": "https://example.com/price.pdf",
        "effective_from": "2026-01-01",
        "effective_to": None,
        "status": "active",
        "version": "1",
        "product_model": "VF 8",
        "retrieval_method": "bm25",
        "native_score": score,
        "rank": 1,
        "dense_score": None,
        "bm25_score": score,
        "rrf_score": 0.016,
    }


def test_integrated_graph_uses_hybrid_retrieval():
    names = set(copilot_agent.get_graph().nodes)
    assert {
        "analyze_and_route",
        "select_evidence",
        "retrieve_documents",
        "check_grounding",
        "finalize_response",
    } <= names


@pytest.mark.asyncio
async def test_price_evidence_can_be_used_without_dense_match():
    _, selected = _merge_evidence({}, [_hit("PRICE_LIST", "price-1", 3.0)])
    assert [item["document_id"] for item in selected] == ["PRICE_LIST"]


@pytest.mark.asyncio
async def test_citation_from_other_document_is_rejected():
    from src.agents.copilot.validation.claims import validate_claims

    state = draft_state()
    assert validate_claims(GeneratedAnswer(**generated(cid="C999")), state) == {0: "citation"}
