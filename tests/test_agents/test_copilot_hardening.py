"""Regression checks for failure reporting, citations and source validity."""

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.agents.copilot import nodes
from src.agents.copilot.nodes import CopilotDependencyError
from src.agents.copilot.nodes import retrieval as retrieval_nodes
from src.agents.copilot.state import SearchRequest
from src.api.copilot import CopilotQueryRequest, query_copilot, router
from src.knowledge.schemas import ChunkMetadata
from src.knowledge.validity import is_document_retrievable
from tests.test_agents.test_copilot_agentic import draft_state, scripted

EVIDENCE = {
    "chunk_id": "price-1",
    "document_id": "price-list",
    "content": "Giá VF 8 trong bảng giá.",
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
    "native_score": 5.0,
    "rank": 1,
    "dense_score": None,
    "bm25_score": 5.0,
    "rrf_score": 0.016,
}


@pytest.mark.asyncio
async def test_retrieval_failure_is_not_an_empty_knowledge_result(monkeypatch):
    class BrokenSearch:
        def search(self, **kwargs):
            raise TimeoutError("provider unavailable")

    monkeypatch.setattr(retrieval_nodes, "get_dense_search_engine", lambda: BrokenSearch())
    monkeypatch.setattr(retrieval_nodes, "get_bm25_search_engine", lambda: BrokenSearch())
    monkeypatch.setattr(retrieval_nodes, "get_settings", lambda: SimpleNamespace(retrieval_timeout_seconds=5))
    with pytest.raises(CopilotDependencyError, match="retrieval dependencies unavailable"):
        await nodes._search(SearchRequest(query="Giá VF 8"), {})


@pytest.mark.asyncio
async def test_generation_failure_is_not_abstention(monkeypatch):
    scripted(monkeypatch, [ConnectionError("offline"), ConnectionError("offline")])
    with pytest.raises(CopilotDependencyError, match="generate_answer unavailable"):
        await nodes.generate_node(draft_state())


@pytest.mark.asyncio
async def test_retry_does_not_attach_citation_to_unsupported_claim(monkeypatch):
    scripted(monkeypatch, [{"answer": "Giảm giá 50%.", "citation_ids": ["C1"]}])
    result = await nodes.generate_node(draft_state())
    assert result["draft_answer"] is None
    assert result["generation_count"] == 2


@pytest.mark.asyncio
async def test_api_reports_dependency_failure_for_retry(monkeypatch):
    async def broken_graph(state, **kwargs):
        raise CopilotDependencyError("generation unavailable")

    monkeypatch.setattr("src.api.copilot.copilot_agent.ainvoke", broken_graph)
    with pytest.raises(HTTPException) as exc:
        await query_copilot(CopilotQueryRequest(query="Giá VF 8"))
    assert exc.value.status_code == 503


def test_current_lookup_excludes_expired_or_out_of_date_documents():
    metadata = ChunkMetadata(
        chunk_id="c1",
        document_id="p1",
        title="Chính sách",
        document_type="policy",
        product_model="VF 8",
        effective_date=date(2025, 1, 1),
        expiry_date=date(2025, 12, 31),
        status="active",
        source="https://example.com",
        version="1",
    )
    assert not is_document_retrievable(metadata, date(2026, 1, 1))
    metadata.status = "expired"
    assert not is_document_retrievable(metadata)
    assert is_document_retrievable(metadata, date(2025, 6, 1))


def test_public_ingest_endpoint_is_not_registered():
    assert not any(getattr(route, "path", "") == "/copilot/ingest" for route in router.routes)


@pytest.mark.asyncio
async def test_context_does_not_let_one_document_crowd_out_a_price_list():
    product_hits = [{**EVIDENCE, "chunk_id": f"product-{index}", "document_id": "product-vf8"} for index in range(1, 6)]
    price_hit = {**EVIDENCE, "chunk_id": "price-1", "document_id": "price-list"}

    _, selected = nodes._merge_evidence({}, [*product_hits, price_hit])
    assert len(selected) <= 8
    assert "price-list" in {item["document_id"] for item in selected}
    assert selected[0]["chunk_id"] == product_hits[0]["chunk_id"]


@pytest.mark.asyncio
async def test_context_keeps_sparse_price_evidence():
    product_hits = [{**EVIDENCE, "chunk_id": f"product-{index}", "document_id": "product-vf8"} for index in range(1, 8)]
    price_hit = {
        **EVIDENCE,
        "chunk_id": "price-1",
        "document_id": "price-list",
        "dense_score": None,
        "bm25_score": 2.48,
    }

    _, selected = nodes._merge_evidence({}, [*product_hits, price_hit])
    assert "price-list" in {item["document_id"] for item in selected}
