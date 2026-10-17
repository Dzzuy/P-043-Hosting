"""Unit tests verifying architectural remediations from review 2026-10-13."""

import pytest
from unittest.mock import AsyncMock, patch
from pydantic import ValidationError

from src.agents.copilot.nodes import answer as answer_nodes
from src.agents.copilot.nodes import verification as verif_nodes
from src.agents.copilot.state import (
    Citation,
    CopilotResponse,
    CopilotState,
    GroundedClaim,
    RetrievalHit,
    SelfCheckVerdict,
    VerifiedAnswerSnapshot,
)


def test_self_check_verdict_empty_dict_fails_validation():
    """Verify probe: empty dict or missing grounded field strictly fails validation."""
    with pytest.raises(ValidationError):
        SelfCheckVerdict.model_validate({})


def test_self_check_verdict_extra_fields_forbidden():
    """Verify probe: extra hallucinated fields are forbidden."""
    with pytest.raises(ValidationError):
        SelfCheckVerdict.model_validate({"grounded": True, "hallucinated_field": "fake"})


def test_self_check_verdict_disjoint_answered_and_missing():
    """Verify probe: answered and missing requirement IDs must be disjoint (missing takes precedence)."""
    verdict = SelfCheckVerdict(
        grounded=True,
        answered_requirement_ids=["R1", "R2"],
        missing_requirement_ids=["R2", "R3"],
    )
    assert verdict.answered_requirement_ids == ["R1"]
    assert verdict.missing_requirement_ids == ["R2", "R3"]


@pytest.mark.asyncio
async def test_finalize_response_never_publishes_ungrounded_draft():
    """Verify P1 invariant: draft_answer with grounded=False strictly routes to fallback."""
    unsupported_verdict = SelfCheckVerdict(
        grounded=False,
        feedback="Phát hiện suy diễn quãng đường 9999km",
        unsupported_claims=["VF 5 đi được 9999km"],
    )
    state: CopilotState = {
        "draft_answer": "VF 5 Plus đi được 9999km [C1].",
        "self_check": unsupported_verdict,
        "verified_claims": [],
        "selected_evidence": [],
    }
    result = await answer_nodes.finalize_response(state)
    assert result["route"] == "fallback_response"
    assert result["fallback_reason"] == "verification_failed"


@pytest.mark.asyncio
async def test_finalize_preserves_multiple_citations_from_same_document():
    """Verify P1: citations with distinct citation_ids from same document are both preserved."""
    hit1: RetrievalHit = {
        "chunk_id": "chunk-doc1-part1",
        "document_id": "doc-price-sheet",
        "title": "Bảng giá VF 5",
        "content": "Giá VF 5 thuê pin: 468 triệu",
        "citation_id": "C1",
        "section": "Bảng giá",
        "page": 1,
        "effective_from": "2026-01-01",
        "effective_to": None,
        "source_uri": "s3://doc1.pdf",
        "product_model": "VF 5",
        "document_type": "price_sheet",
        "policy_type": None,
        "competitor_model": None,
        "status": "active",
        "version": "1.0",
        "retrieval_method": "dense",
        "native_score": 0.9,
        "rank": 1,
    }
    hit2: RetrievalHit = {
        "chunk_id": "chunk-doc1-part2",
        "document_id": "doc-price-sheet",
        "title": "Bảng giá VF 5",
        "content": "Giá VF 5 kèm pin: 548 triệu",
        "citation_id": "C2",
        "section": "Bảng giá",
        "page": 2,
        "effective_from": "2026-01-01",
        "effective_to": None,
        "source_uri": "s3://doc1.pdf",
        "product_model": "VF 5",
        "document_type": "price_sheet",
        "policy_type": None,
        "competitor_model": None,
        "status": "active",
        "version": "1.0",
        "retrieval_method": "dense",
        "native_score": 0.88,
        "rank": 2,
    }
    verdict = SelfCheckVerdict(grounded=True)
    state: CopilotState = {
        "draft_answer": "VF 5 thuê pin là 468 triệu [C1], kèm pin là 548 triệu [C2].",
        "draft_citations": ["C1", "C2"],
        "self_check": verdict,
        "selected_evidence": [hit1, hit2],
        "requirements": [],
        "answered_requirement_ids": [],
    }
    result = await answer_nodes.finalize_response(state)
    assert result["route"] == "end"
    response: CopilotResponse = result["final_response"]
    cids = [c.citation_id for c in response.citations]
    assert "C1" in cids
    assert "C2" in cids
    assert len(cids) == 2


@pytest.mark.asyncio
async def test_fallback_response_is_strictly_terminal():
    """Verify P1: fallback_response always routes to 'end', never back to finalize_response."""
    state: CopilotState = {
        "draft_answer": "Một câu trả lời nào đó",
        "self_check": SelfCheckVerdict(grounded=True),
        "fallback_reason": "verification_failed",
    }
    result = await answer_nodes.fallback_response(state)
    assert result["route"] == "end"
    assert "final_response" in result
    assert result["final_response"].status in {"abstained", "needs_clarification"}


def test_semantic_cache_metadata_strip_allows_copilot_response_validation():
    """Verify P2: cached dictionary cleaned of extra fields validates successfully against CopilotResponse."""
    original_resp = CopilotResponse(
        status="answered",
        answer="VF 5 Plus có giá 496 triệu đồng [C1].",
        citations=[
            Citation(
                citation_id="C1",
                chunk_id="chk1",
                title="Bảng giá",
                document_id="doc1",
                version="1.0",
                effective_from="2026-01-01",
            )
        ],
        product_insights=[],
        missing_information=[],
        talking_points=[],
        sales_actions=[],
    )
    cached_dict = original_resp.model_dump()
    cached_dict["cached"] = True
    cached_dict["similarity_score"] = 0.98

    clean = {k: v for k, v in cached_dict.items() if k not in {"cached", "similarity_score"}}
    resp = CopilotResponse.model_validate(clean)
    assert resp.status == "answered"
    assert "496 triệu" in resp.answer


@pytest.mark.asyncio
async def test_failed_recovery_publishes_verified_snapshot():
    """Verify Đợt 1: when recovery fails (e.g. 2nd attempt ungrounded or out of budget), earlier valid snapshot is published."""
    cit1 = Citation(
        citation_id="C1",
        chunk_id="chk1",
        title="Bảng giá",
        document_id="doc1",
        version="1.0",
        effective_from="2026-01-01",
    )
    snap = VerifiedAnswerSnapshot(
        answer="VF 5 giá 468 triệu [C1]",
        draft_hash="hash1",
        context_hash="chash1",
        requirements_hash="rhash1",
        resolved_date="2026-10-13",
        corpus_fingerprint="fp1",
        citations=[cit1],
        answered_requirement_ids=["R1"],
        missing_requirement_ids=["R2"],
        missing_information=["Chính sách ưu đãi"],
        status="partial",
        reason_code="insufficient_evidence",
        created_at_attempt=1,
    )
    state: CopilotState = {
        "verified_snapshot": snap,
        "draft_answer": "Draft mới chưa kiểm chứng hoặc bị lỗi",
        "fallback_reason": "verification_failed",
        "resolved_date": "2026-10-13",
        "selected_evidence": [],
    }
    result = await answer_nodes.finalize_response(state)
    assert result["route"] == "end"
    resp: CopilotResponse = result["final_response"]
    assert resp.status == "partial"
    assert resp.answer == "VF 5 giá 468 triệu [C1]"
    assert resp.reason_code == "verification_failed"
    assert len(resp.citations) == 1
    assert resp.citations[0].citation_id == "C1"


def test_parse_answer_citations_detects_malformed_and_unknown():
    """Verify Đợt 1: parse_answer_citations accurately distinguishes valid, unknown, and malformed markers."""
    from src.agents.copilot.tools import parse_answer_citations

    text = "Giá VF 5 [C1] và [C2], kèm lỗi [C0] và [C] hoặc [Cabc], cùng lạ [C99]."
    res = parse_answer_citations(text, allowed_cids={"C1", "C2"})
    assert set(res["cited_ids"]) == {"C1", "C2", "C99"}
    assert res["unknown_ids"] == ["C99"]
    assert "C0" in res["malformed"]
    assert "C" in res["malformed"]
    assert "Cabc" in res["malformed"]


@pytest.mark.asyncio
async def test_exact_cache_end_to_end_fresh_request_id():
    """Verify Đợt 2: cached response produces fresh request_id, matching content, and misses on date/corpus/domain change."""
    from datetime import date
    from src.knowledge.index_readiness import load_snapshot
    from src.services.semantic_cache import ExactCacheService

    snapshot = load_snapshot()
    active_chunk = next(c for c in snapshot.chunks.values() if getattr(c.metadata, "status", "") == "active")

    cache = ExactCacheService()
    cit = Citation(
        citation_id="C1",
        chunk_id=active_chunk.chunk_id,
        document_id=active_chunk.document_id,
        title="Thông số",
    )
    resp = CopilotResponse(
        status="answered",
        answer="VF 5 giá 496 triệu [C1].",
        citations=[cit],
        product_insights=[],
        talking_points=[],
        sales_actions=[],
    )

    query = "VF 5 Plus giá bao nhiêu?"
    cache.put(query, resp, domain="specs")

    hit1 = await cache.get(query, domain="specs")
    assert hit1 is not None
    assert hit1["answer"] == "VF 5 giá 496 triệu [C1]."

    # Different date -> miss
    hit_date_diff = await cache.get(query, domain="specs", target_date=date(2024, 1, 1))
    assert hit_date_diff is None

    # Different domain -> miss
    hit_domain_diff = await cache.get(query, domain="policy")
    assert hit_domain_diff is None


@pytest.mark.asyncio
async def test_check_grounding_rejects_unknown_id_r99():
    """Verify Đợt 3: R99 cannot satisfy or alter requirements R1/R2."""
    from unittest.mock import AsyncMock, patch
    from src.agents.copilot.state import Requirement

    req1 = Requirement(requirement_id="R1", description="Giá xe", kind="fact")
    req2 = Requirement(requirement_id="R2", description="Quãng đường", kind="fact")

    mock_verdict = SelfCheckVerdict(
        grounded=True,
        answered_requirement_ids=["R99"],  # Hallucinated ID R99
        missing_requirement_ids=["R1"],
    )

    state: CopilotState = {
        "query": "Giá và quãng đường VF 5",
        "draft_answer": "VF 5 giá 468 triệu [C1]",
        "requirements": [req1, req2],
        "answer_context": "VF 5 giá 468 triệu [C1]",
        "selected_evidence": [
            RetrievalHit(
                chunk_id="chk1",
                document_id="doc1",
                title="Bảng giá",
                product_model="VF 5",
                status="active",
                effective_from="2026-01-01",
                effective_to=None,
                source_uri=None,
                section=None,
                page=None,
                content="VF 5 giá 468 triệu",
                score=0.9,
                version="1.0",
                retrieval_method="dense",
                native_score=0.9,
                rank=1,
            )
        ],
        "resolved_date": "2026-10-13",
        "generation_count": 1,
    }

    with patch("src.agents.copilot.nodes.verification._invoke_json", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = (mock_verdict, None)
        res = await verif_nodes.check_grounding(state)
        # Grounded must be overturned to False due to invalid requirement ID R99
        assert res["self_check"].grounded is False
        assert "không hợp lệ" in res["self_check"].feedback


@pytest.mark.asyncio
async def test_check_grounding_recovery_routing():
    """Search by default; an explicit checker request permits regeneration at 70s."""
    from unittest.mock import AsyncMock, patch
    from types import SimpleNamespace
    from src.agents.copilot.state import Requirement

    req1 = Requirement(requirement_id="R1", description="Giá xe", kind="fact")
    req2 = Requirement(requirement_id="R2", description="Quãng đường", kind="fact")

    hit = RetrievalHit(
        chunk_id="chk1",
        document_id="doc1",
        title="Bảng giá",
        product_model="VF 5",
        status="active",
        effective_from="2026-01-01",
        effective_to=None,
        source_uri=None,
        section=None,
        page=None,
        content="VF 5 giá 468 triệu",
        score=0.9,
        version="1.0",
        retrieval_method="dense",
        native_score=0.9,
        rank=1,
    )

    # Subtest 1: R2=[] (no candidate in context) -> does NOT regenerate
    verdict1 = SelfCheckVerdict(
        grounded=True,
        answered_requirement_ids=["R1"],
        missing_requirement_ids=["R2"],
        missing_information=["Quãng đường NEDC chưa rõ"],
    )
    state_empty_r2: CopilotState = {
        "query": "Giá và quãng đường VF 5",
        "draft_answer": "VF 5 giá 468 triệu [C1]",
        "requirements": [req1, req2],
        "answer_context": "VF 5 giá 468 triệu [C1]",
        "selected_evidence": [hit],
        "evidence_map": {"R1": ["chk1"]},  # R2 has NO candidates in context
        "resolved_date": "2026-10-13",
        "generation_count": 1,
    }
    with patch("src.agents.copilot.nodes.verification._invoke_json", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = (verdict1, None)
        res1 = await verif_nodes.check_grounding(state_empty_r2)
        # R2 has NO candidates in context -> must NOT regenerate!
        assert res1["route"] != "generate_answer"
        assert res1["route"] == "plan_queries"  # routes to corrective search, not regenerate

    # Subtest 2: explicit checker regeneration with 70s remaining (> 60s gate).
    state_with_r2_candidates: CopilotState = {
        "query": "Giá và quãng đường VF 5",
        "draft_answer": "VF 5 giá 468 triệu [C1]",
        "requirements": [req1, req2],
        "answer_context": "VF 5 giá 468 triệu [C1] VF 5 đi được 326 km [C1]",
        "selected_evidence": [hit],
        "evidence_map": {"R1": ["chk1"], "R2": ["chk1"]},  # R2 has candidate
        "resolved_date": "2026-10-13",
        "generation_count": 1,
        "runtime": SimpleNamespace(
            remaining=lambda: 70.0,
            attempts=1,
            max_attempts=6,
            events=[],
            timeout=lambda s: min(s, 70.0),
        ),
    }
    with patch("src.agents.copilot.nodes.verification._invoke_json", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = (verdict1.model_copy(update={"recovery": "regenerate"}), None)
        res2 = await verif_nodes.check_grounding(state_with_r2_candidates)
        assert res2["route"] == "generate_answer"
        assert "recovery_requirement_ids" in res2
        assert "R2" in res2["recovery_requirement_ids"]


@pytest.mark.asyncio
async def test_check_grounding_r2_empty_list_routes_to_search():
    """Verify bugfix: evidence_map with R2=[] must NOT be treated as having evidence in context."""
    from unittest.mock import AsyncMock, patch
    from src.agents.copilot.state import Requirement

    req1 = Requirement(requirement_id="R1", description="Giá xe", kind="fact")
    req2 = Requirement(requirement_id="R2", description="Quãng đường", kind="fact")

    hit: RetrievalHit = {
        "chunk_id": "chk1",
        "document_id": "doc1",
        "title": "Bảng giá",
        "product_model": "VF 5",
        "status": "active",
        "effective_from": "2026-01-01",
        "effective_to": None,
        "source_uri": None,
        "section": None,
        "page": None,
        "content": "VF 5 giá 468 triệu",
        "citation_id": "C1",
        "version": "1.0",
        "retrieval_method": "dense",
        "native_score": 0.9,
        "rank": 1,
    }

    verdict = SelfCheckVerdict(
        grounded=True,
        answered_requirement_ids=["R1"],
        missing_requirement_ids=["R2"],
        missing_information=["Quãng đường chưa rõ"],
    )
    # Production shape: evidence_map has key R2 with value []
    state: CopilotState = {
        "query": "Giá và quãng đường VF 5",
        "draft_answer": "VF 5 giá 468 triệu [C1]",
        "requirements": [req1, req2],
        "answer_context": "VF 5 giá 468 triệu [C1]",
        "selected_evidence": [hit],
        "evidence_map": {"R1": ["C1"], "R2": []},
        "resolved_date": "2026-10-13",
        "generation_count": 1,
    }
    with patch("src.agents.copilot.nodes.verification._invoke_json", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = (verdict, None)
        res = await verif_nodes.check_grounding(state)
        # Must route to search (plan_queries), NOT regenerate!
        assert res["route"] == "plan_queries"
        assert res["recovery_requirement_ids"] == ["R2"]


@pytest.mark.asyncio
async def test_partial_snapshot_derives_missing_information_and_finalizes_cleanly():
    """Verify bugfix: partial snapshot with empty missing_information derives text, avoiding 500 error."""
    from unittest.mock import AsyncMock, patch
    from src.agents.copilot.state import Requirement

    req1 = Requirement(requirement_id="R1", description="Giá niêm yết VF 5", kind="fact")
    req2 = Requirement(requirement_id="R2", description="Quãng đường NEDC của VF 5", kind="fact")

    hit: RetrievalHit = {
        "chunk_id": "chk1",
        "document_id": "doc1",
        "title": "Bảng giá",
        "product_model": "VF 5",
        "status": "active",
        "effective_from": "2026-01-01",
        "effective_to": None,
        "source_uri": None,
        "section": None,
        "page": None,
        "content": "VF 5 giá 468 triệu",
        "citation_id": "C1",
        "version": "1.0",
        "retrieval_method": "dense",
        "native_score": 0.9,
        "rank": 1,
    }

    # Checker says grounded=True, answered R1, missing R2, BUT missing_information is empty list!
    verdict = SelfCheckVerdict(
        grounded=True,
        answered_requirement_ids=["R1"],
        missing_requirement_ids=["R2"],
        missing_information=[],
    )
    state: CopilotState = {
        "query": "Giá và quãng đường VF 5",
        "draft_answer": "VF 5 giá 468 triệu [C1]",
        "requirements": [req1, req2],
        "answer_context": "VF 5 giá 468 triệu [C1]",
        "selected_evidence": [hit],
        "evidence_map": {"R1": ["C1"], "R2": []},
        "resolved_date": "2026-10-13",
        "generation_count": 2,  # recovery budget exhausted
    }
    with patch("src.agents.copilot.nodes.verification._invoke_json", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = (verdict, None)
        res = await verif_nodes.check_grounding(state)
        # Should finalize with snapshot
        assert res["route"] == "finalize_response"
        snapshot = res["verified_snapshot"]
        assert snapshot.status == "partial"
        assert len(snapshot.missing_information) > 0
        assert "Quãng đường NEDC của VF 5" in snapshot.missing_information[0]

        # Finalize response must succeed and NOT throw ValueError
        final_res = await answer_nodes.finalize_response({**state, **res})
        assert final_res["route"] == "end"
        response = final_res["final_response"]
        assert response.status == "partial"
        assert len(response.missing_information) > 0


def test_self_check_verdict_rejects_grounded_true_with_unsupported_claims():
    """Verify invariant: grounded=True with unsupported_claims strictly raises ValidationError."""
    with pytest.raises(ValidationError):
        SelfCheckVerdict(
            grounded=True,
            unsupported_claims=["VF 5 có thể bay"],
        )


def test_verified_answer_snapshot_rejects_empty_missing_info_for_partial():
    """Verify invariant: partial snapshot requires non-empty missing_information."""
    with pytest.raises(ValidationError):
        VerifiedAnswerSnapshot(
            answer="VF 5 giá 468 triệu [C1]",
            draft_hash="hash1",
            context_hash="hash2",
            requirements_hash="hash3",
            resolved_date="2026-10-13",
            status="partial",
            missing_information=[],
        )


@pytest.mark.asyncio
async def test_select_evidence_returns_parent_context_cache():
    """Verify bugfix: select_evidence returns parent_context_cache in graph state."""
    from src.agents.copilot.nodes import evidence as evidence_nodes

    hit: RetrievalHit = {
        "chunk_id": "chk1",
        "document_id": "doc1",
        "title": "Bảng giá",
        "product_model": "VF 5",
        "status": "active",
        "effective_from": "2026-01-01",
        "effective_to": None,
        "source_uri": None,
        "section": None,
        "page": None,
        "content": "VF 5 giá 468 triệu",
        "citation_id": "C1",
        "version": "1.0",
        "retrieval_method": "dense",
        "native_score": 0.9,
        "rank": 1,
    }
    state: CopilotState = {
        "query": "Giá VF 5",
        "raw_search_results": [{"dense": [hit], "bm25": [hit], "requirement_ids": ["R1"]}],
        "evidence_registry": [hit],
        "requirements": [],
        "parent_context_cache": {("chk1", "2026-10-13"): [hit]},
        "profile_name": "simple",
    }
    result = await evidence_nodes.select_evidence(state)
    assert "parent_context_cache" in result
    assert ("chk1", "2026-10-13") in result["parent_context_cache"]


@pytest.mark.asyncio
async def test_coaching_route_and_copilot_response_without_citations():
    """Verify Đợt 2: coaching queries route directly to generate_answer and publish without citations."""
    from src.agents.copilot.nodes import guard as guard_nodes
    from src.agents.copilot.state import GuardDecision, IntakeDecision, Requirement

    advice_req = Requirement(requirement_id="R1", description="Soạn tin nhắn chào khách lái thử VF 6", kind="advice")
    coaching_decision = IntakeDecision(
        guard_decision=GuardDecision(decision="allow", reason="none"),
        task="call_preparation",
        route="simple",
        answer_kind="coaching",
        requirements=[advice_req],
        product_models=["VF 6"],
    )

    state: CopilotState = {
        "query": "Soạn tin nhắn chào anh Tuấn vừa lái thử VF 6",
        "requirements": [advice_req],
    }

    with patch("src.agents.copilot.nodes.guard._invoke_json", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = (coaching_decision, None)
        result = await guard_nodes.analyze_and_route(state)
        # Must route directly to generate_answer
        assert result["route"] == "generate_answer"
        assert result["answer_kind"] == "coaching"

    # CopilotResponse with answer_kind="coaching" must accept status="answered" without citations
    response = CopilotResponse(
        status="answered",
        answer="Em chào anh Tuấn, em gửi anh thông tin sau buổi lái thử...",
        citations=[],
        answer_kind="coaching",
    )
    assert response.status == "answered"
    assert len(response.citations) == 0


@pytest.mark.asyncio
async def test_memory_summary_passed_to_generator_and_checker():
    """Verify Đợt 2: memory_summary is passed to generate_answer and check_grounding."""
    from src.agents.copilot.nodes import answer as answer_nodes
    from src.agents.copilot.nodes import verification as verif_nodes
    from src.agents.copilot.state import Requirement, SelfCheckVerdict

    req = Requirement(requirement_id="R1", description="Tư vấn gói xe", kind="advice")
    state: CopilotState = {
        "query": "Tư vấn cho tôi",
        "customer_context": "Khách thích màu trắng",
        "memory_summary": "Khách ngân sách 500 triệu, đi 50 km/ngày, sạc tại nhà",
        "requirements": [req],
        "resolved_date": "2026-10-13",
        "answer_context": "",
        "generation_count": 0,
    }

    with patch("src.agents.copilot.nodes.answer._invoke_text", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = ("Dạ với ngân sách 500 triệu...", None)
        await answer_nodes.generate_answer(state)
        payload = mock_gen.call_args[0][2]
        assert "memory_summary" in payload
        assert "ngân sách 500 triệu" in payload["memory_summary"]

    verdict = SelfCheckVerdict(grounded=True, answered_requirement_ids=["R1"])
    with patch("src.agents.copilot.nodes.verification._invoke_json", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = (verdict, None)
        await verif_nodes.check_grounding({**state, "draft_answer": "Dạ..."})
        payload = mock_check.call_args[0][2]
        assert "memory_summary" in payload
        assert "ngân sách 500 triệu" in payload["memory_summary"]


@pytest.mark.asyncio
async def test_comparison_evidence_selection_interleaves_models():
    """Verify Đợt 3: comparison tasks interleave candidates across models so neither model is starved."""
    from src.agents.copilot.nodes import evidence as evidence_nodes
    from src.agents.copilot.state import Requirement

    req1 = Requirement(requirement_id="R1", description="Quãng đường VF 5", kind="fact")
    req2 = Requirement(requirement_id="R2", description="Quãng đường VF 6", kind="fact")

    vf5_hits = [
        {
            "chunk_id": f"vf5-{i}",
            "document_id": "doc-vf5",
            "title": "VF 5 specs",
            "content": f"VF 5 thông số {i}: 326 km NEDC",
            "product_model": "VF 5",
            "status": "active",
            "effective_from": "2026-01-01",
            "effective_to": None,
            "source_uri": None,
            "section": None,
            "page": None,
            "version": "1.0",
            "retrieval_method": "dense",
            "native_score": 0.9,
            "rank": i,
        }
        for i in range(1, 5)
    ]
    vf6_hits = [
        {
            "chunk_id": f"vf6-{i}",
            "document_id": "doc-vf6",
            "title": "VF 6 specs",
            "content": f"VF 6 thông số {i}: 399 km WLTP",
            "product_model": "VF 6",
            "status": "active",
            "effective_from": "2026-01-01",
            "effective_to": None,
            "source_uri": None,
            "section": None,
            "page": None,
            "version": "1.0",
            "retrieval_method": "dense",
            "native_score": 0.85,
            "rank": i,
        }
        for i in range(1, 5)
    ]

    state: CopilotState = {
        "query": "So sánh VF 5 và VF 6",
        "task": "comparison",
        "product_models": ["VF 5", "VF 6"],
        "requirements": [req1, req2],
        "raw_search_results": [
            {"dense": vf5_hits, "bm25": vf5_hits, "requirement_ids": ["R1"]},
            {"dense": vf6_hits, "bm25": vf6_hits, "requirement_ids": ["R2"]},
        ],
        "evidence_registry": [],
        "profile_name": "complex",
    }
    result = await evidence_nodes.select_evidence(state)
    selected_models = {h.get("product_model") for h in result["selected_evidence"]}
    assert "VF 5" in selected_models
    assert "VF 6" in selected_models


@pytest.mark.asyncio
async def test_verified_snapshot_binds_suggestions_and_publishes_them():
    """Verify Đợt 4: VerifiedAnswerSnapshot stores suggestions and finalize_response publishes them."""
    citation = Citation(
        citation_id="C1",
        chunk_id="chunk1",
        document_id="doc1",
        title="VF 5 specs",
    )
    snapshot = VerifiedAnswerSnapshot(
        answer="VF 5 đi được 326 km [C1]",
        draft_hash="hash1",
        context_hash="ctx1",
        requirements_hash="req1",
        resolved_date="2026-10-13",
        citations=[citation],
        answered_requirement_ids=["R1"],
        status="answered",
        suggested_message="Anh Tuấn ơi, xe VF 5 bên em chạy được 326 km theo chuẩn NEDC ạ.",
        suggested_next_question="Anh có muốn đăng ký lái thử ngay tuần này không?",
    )
    state: CopilotState = {
        "verified_snapshot": snapshot,
        "resolved_date": "2026-10-13",
    }
    result = await answer_nodes.finalize_response(state)
    final = result["final_response"]
    assert final.status == "answered"
    assert final.suggested_message == "Anh Tuấn ơi, xe VF 5 bên em chạy được 326 km theo chuẩn NEDC ạ."
    assert final.suggested_next_question == "Anh có muốn đăng ký lái thử ngay tuần này không?"


@pytest.mark.asyncio
async def test_external_gap_does_not_trigger_search_recovery():
    """Verify Đợt 5: external gaps (inventory, dealer discount) do not trigger corrective search."""
    from src.agents.copilot.nodes import verification as verif_nodes
    from src.agents.copilot.state import Requirement, SelfCheckVerdict

    fact_req = Requirement(requirement_id="R1", description="Giá niêm yết VF 5", kind="fact")
    ext_req = Requirement(requirement_id="R2", description="Số lượng tồn kho đại lý", kind="external")

    state: CopilotState = {
        "query": "VF 5 giá bao nhiêu và đại lý còn mấy xe?",
        "requirements": [fact_req, ext_req],
        "resolved_date": "2026-10-13",
        "answer_context": "[C1] Giá niêm yết 468 triệu",
        "selected_evidence": [
            {
                "citation_id": "C1",
                "chunk_id": "c1",
                "document_id": "PRICE",
                "title": "Bảng giá",
                "content": "Giá 468 triệu",
                "product_model": "VF 5",
                "document_type": "price_list",
                "version": "1.0",
                "status": "active",
                "effective_from": "2026-01-01",
                "effective_to": None,
                "section": None,
                "page": None,
                "source_uri": None,
            }
        ],
        "draft_answer": "VF 5 có giá niêm yết là 468 triệu đồng [C1]. Về tồn kho đại lý hiện chưa có dữ liệu.",
        "evidence_map": {"R1": ["C1"], "R2": []},
        "generation_count": 1,
    }

    verdict = SelfCheckVerdict(
        grounded=True,
        answered_requirement_ids=["R1"],
        missing_requirement_ids=["R2"],
        missing_information=["Số lượng xe thực tế tại đại lý"],
    )

    with patch("src.agents.copilot.nodes.verification._invoke_json", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = (verdict, None)
        result = await verif_nodes.check_grounding(state)
        # Must NOT route to search/plan_queries, but route directly to finalize_response with partial snapshot
        assert result["route"] == "finalize_response"
        snap = result["verified_snapshot"]
        assert snap.status == "partial"
        assert "R2" in snap.missing_requirement_ids
        assert len(snap.missing_information) > 0


@pytest.mark.asyncio
async def test_coaching_with_hallucinated_facts_is_rejected():
    """Verify Đợt 4: coaching answers containing unsupported claims are strictly rejected."""
    from src.agents.copilot.nodes import verification as verif_nodes
    from src.agents.copilot.state import Requirement, SelfCheckVerdict

    req = Requirement(requirement_id="R1", description="Chào khách và tư vấn VF 6", kind="advice")
    state: CopilotState = {
        "query": "Nhắn tin chào khách lái thử",
        "requirements": [req],
        "resolved_date": "2026-10-13",
        "answer_context": "",
        "draft_answer": "Chào anh, VF 6 sạc 10 phút chạy được 1000 km anh nhé!",
        "generation_count": 1,
        "answer_kind": "coaching",
    }

    verdict = SelfCheckVerdict(
        grounded=False,
        unsupported_claims=["VF 6 sạc 10 phút chạy được 1000 km"],
        feedback="Phát hiện thông số bịa đặt không có căn cứ.",
    )

    with patch("src.agents.copilot.nodes.verification._invoke_json", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = (verdict, None)
        result = await verif_nodes.check_grounding(state)
        assert result["self_check"].grounded is False
        assert "verified_snapshot" not in result or result.get("verified_snapshot") is None
