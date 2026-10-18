"""Unit tests for ExactCacheService (remediated semantic cache)."""

from datetime import date
from unittest.mock import patch

import pytest

from src.agents.copilot.state import Citation, CopilotResponse
from src.knowledge.index_readiness import load_snapshot
from src.services.semantic_cache import (
    ExactCacheService,
    normalize_query_text,
)


def test_normalize_query_text():
    # Preserves casing and punctuation, collapses multiple whitespaces, strips leading/trailing
    assert (
        normalize_query_text("   VF 5 Plus   giá bao nhiêu???  ")
        == "VF 5 Plus giá bao nhiêu???"
    )


@pytest.mark.asyncio
async def test_exact_hash_cache_hit():
    snapshot = load_snapshot()
    # Pick a real active chunk from snapshot
    real_chunk = next(c for c in snapshot.chunks.values() if getattr(c.metadata, "status", "") == "active")
    cache = ExactCacheService()

    cit = Citation(
        citation_id="C1",
        chunk_id=real_chunk.chunk_id,
        document_id=real_chunk.document_id,
        title=real_chunk.metadata.title,
        version="1.0",
        effective_from="2026-01-01",
    )
    sample_response = CopilotResponse(
        status="answered",
        answer="VF 5 Plus có giá 496 triệu đồng [C1].",
        citations=[cit],
        product_insights=[],
        talking_points=[],
        sales_actions=[],
    )

    query = "VF 5 Plus giá bao nhiêu?"
    cache.put(query, sample_response, domain="specs")

    # Exact match hit
    hit = await cache.get(query, domain="specs")
    assert hit is not None
    assert "496 triệu" in hit["answer"]
    assert len(hit["citations"]) == 1

    # Miss when query has different casing or domain or date
    miss_case = await cache.get("vf 5 plus giá bao nhiêu?", domain="specs")
    assert miss_case is None

    miss_domain = await cache.get(query, domain="policy")
    assert miss_domain is None

    miss_date = await cache.get(query, domain="specs", target_date=date(2025, 1, 1))
    assert miss_date is None


@pytest.mark.asyncio
async def test_context_dependent_pronoun_bypasses_cache():
    cache = ExactCacheService()
    snapshot = load_snapshot()
    real_chunk = next(iter(snapshot.chunks.values()))
    cit = Citation(
        citation_id="C1",
        chunk_id=real_chunk.chunk_id,
        document_id=real_chunk.document_id,
        title="Thông số",
    )
    sample_response = CopilotResponse(
        status="answered",
        answer="VF 5 Plus đi được 326.4 km [C1].",
        citations=[cit],
    )
    cache.put("Quãng đường của nó là bao nhiêu?", sample_response)

    # Context-dependent pronoun "nó" must bypass cache
    assert cache.should_bypass("Quãng đường của nó là bao nhiêu?") is True
    hit = await cache.get("Quãng đường của nó là bao nhiêu?")
    assert hit is None


@pytest.mark.asyncio
async def test_unanswered_status_not_cached():
    cache = ExactCacheService()
    unanswered_response = {
        "status": "abstained",
        "answer": "Không tìm thấy thông tin.",
        "citations": [],
    }
    cache.put("Giá bảo hiểm bao nhiêu?", unanswered_response)
    hit = await cache.get("Giá bảo hiểm bao nhiêu?")
    assert hit is None


@pytest.mark.asyncio
async def test_disabled_cache_flag_bypasses():
    cache = ExactCacheService()
    snapshot = load_snapshot()
    real_chunk = next(iter(snapshot.chunks.values()))
    cit = Citation(
        citation_id="C1",
        chunk_id=real_chunk.chunk_id,
        document_id=real_chunk.document_id,
        title="Bảng giá",
    )
    sample_response = CopilotResponse(
        status="answered",
        answer="VF 5 giá 496 triệu [C1].",
        citations=[cit],
    )
    query = "VF 5 giá bao nhiêu?"
    cache.put(query, sample_response)

    with patch("src.services.semantic_cache.get_settings") as mock_settings:
        from types import SimpleNamespace
        mock_settings.return_value = SimpleNamespace(copilot_exact_cache_enabled=False)
        assert cache.should_bypass(query) is True
        hit = await cache.get(query)
        assert hit is None
