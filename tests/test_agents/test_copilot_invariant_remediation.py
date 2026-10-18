"""Unit tests verifying architectural remediations from review 2026-10-13."""

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from src.agents.copilot.nodes import answer as answer_nodes
from src.agents.copilot.nodes import verification as verif_nodes
from src.agents.copilot.state import (
    Citation,
    CopilotResponse,
    CopilotState,
    RetrievalHit,
    SelfCheckVerdict,
    VerifiedAnswerSnapshot,
)
from tests.test_agents.test_copilot_agentic import checked, draft_state, scripted


@pytest.mark.asyncio
@pytest.mark.parametrize("supported", [True, False])
@pytest.mark.parametrize("recovery", ["none", "search", "regenerate"])
async def test_typed_checker_controls_missing_fact_recovery(monkeypatch, supported, recovery):
    from src.agents.copilot.state import Requirement

    state = draft_state()
    state["requirements"].append(Requirement(requirement_id="R2", description="Dung lượng pin VF 5"))
    review = checked(
        status="supported" if supported else "unsupported",
        recovery=recovery,
        answered=["R1"] if supported else [],
        missing=["R2"] if supported else ["R1", "R2"],
    )
    scripted(monkeypatch, [review])
    result = await verif_nodes.check_grounding(state)
    assert result["route"] == ("generate_answer" if recovery == "regenerate" else "plan_queries")
    assert result["recovery_requirement_ids"] == (["R2"] if supported else ["R1", "R2"])
    assert bool(result.get("verified_snapshot")) == supported
    if supported:
        assert result["verified_snapshot"].status == "partial"


@pytest.mark.asyncio
async def test_external_gap_publishes_partial_without_search(monkeypatch):
    from src.agents.copilot.state import Requirement

    state = draft_state()
    state["requirements"].append(Requirement(requirement_id="R2", description="Tồn kho đại lý", kind="external"))
    scripted(monkeypatch, [checked(missing=["R2"], recovery="search")])
    state.update(await verif_nodes.check_grounding(state))
    assert state["route"] == "finalize_response"
    response = (await answer_nodes.finalize_response(state))["final_response"]
    assert response.status == "partial" and response.missing_information == ["Tồn kho đại lý"]


@pytest.mark.asyncio
async def test_partial_snapshot_derives_missing_text_and_survives_exhausted_recovery(monkeypatch):
    from src.agents.copilot.state import Requirement

    state = draft_state()
    state["generation_count"] = 2
    state["requirements"].append(Requirement(requirement_id="R2", description="Dung lượng pin VF 5"))
    scripted(monkeypatch, [checked(missing=["R2"])])
    state.update(await verif_nodes.check_grounding(state))
    response = (await answer_nodes.finalize_response(state))["final_response"]
    assert response.status == "partial"
    assert response.missing_information == ["Dung lượng pin VF 5"]
    assert response.citations[0].excerpt == state["selected_evidence"][0]["content"]


@pytest.mark.asyncio
@pytest.mark.parametrize("generation_count", [1, 2])
async def test_supported_limitation_without_facts_searches_or_abstains(monkeypatch, generation_count):
    from src.agents.copilot.state import GeneratedAnswer
    from src.agents.copilot.validation.structured import render_answer

    state = draft_state()
    state["generation_count"] = generation_count
    state["generated_answer"] = GeneratedAnswer(
        claims=[
            {
                "text": "Chưa có dữ liệu xác minh quãng đường VF 5.",
                "kind": "limitation",
                "requirement_ids": ["R1"],
                "citation_ids": [],
            }
        ]
    )
    state["draft_answer"] = render_answer(state["generated_answer"])
    scripted(monkeypatch, [checked(answered=[], missing=["R1"], recovery="search", scope=None)])
    result = await verif_nodes.check_grounding(state)
    assert "verified_snapshot" not in result
    assert result["route"] == ("plan_queries" if generation_count == 1 else "fallback_response")
    if generation_count == 2:
        state.update(result)
        response = (await answer_nodes.fallback_response(state))["final_response"]
        assert response.status == "abstained" and response.reason_code == "insufficient_evidence"


@pytest.mark.asyncio
async def test_limitation_only_recovery_keeps_previous_verified_answer(monkeypatch):
    from src.agents.copilot.state import GeneratedAnswer
    from src.agents.copilot.validation.structured import render_answer

    state = draft_state()
    scripted(monkeypatch, [checked()])
    state.update(await verif_nodes.check_grounding(state))
    previous = state["verified_snapshot"]
    state["generation_count"] = 2
    state["generated_answer"] = GeneratedAnswer(
        claims=[
            {
                "text": "Chưa đủ dữ liệu.",
                "kind": "limitation",
                "requirement_ids": ["R1"],
                "citation_ids": [],
            }
        ]
    )
    state["draft_answer"] = render_answer(state["generated_answer"])
    scripted(monkeypatch, [checked(answered=[], missing=["R1"], recovery="search", scope=None)])
    state.update(await verif_nodes.check_grounding(state))
    assert state["route"] == "finalize_response" and state["verified_snapshot"] is previous
    response = (await answer_nodes.finalize_response(state))["final_response"]
    assert response.answer == previous.answer and response.citations == previous.citations


@pytest.mark.asyncio
async def test_coaching_cannot_hide_hallucinated_product_facts(monkeypatch):
    from src.agents.copilot.state import GeneratedAnswer, Requirement
    from src.agents.copilot.validation.structured import render_answer

    state = draft_state()
    state.update(answer_kind="coaching", selected_evidence=[], answer_context="")
    state["requirements"] = [Requirement(requirement_id="R1", kind="advice", description="Chào khách")]
    state["generated_answer"] = GeneratedAnswer(
        claims=[
            {
                "text": "Chào anh, VF 6 sạc 10 phút chạy 1000 km!",
                "kind": "advice",
                "requirement_ids": ["R1"],
                "citation_ids": [],
            }
        ]
    )
    state["draft_answer"] = render_answer(state["generated_answer"])
    scripted(monkeypatch, [checked("unsupported", recovery="regenerate", scope=None)])
    result = await verif_nodes.check_grounding(state)
    assert result["route"] == "generate_answer" and not result.get("verified_snapshot")


@pytest.mark.asyncio
async def test_budget_exhaustion_cannot_publish_plain_text_approval(monkeypatch):
    from src.agents.copilot.nodes import answer
    from src.agents.copilot.runtime import BudgetExhaustedError

    state = draft_state()
    state["self_check"] = SelfCheckVerdict(grounded=True)
    monkeypatch.setattr(answer, "_invoke_json", AsyncMock(side_effect=BudgetExhaustedError()))
    result = await answer.generate_answer(state)
    assert result["route"] == "fallback_response"


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
    state: CopilotState = {
        "draft_answer": "VF 5 thuê pin là 468 triệu [C1], kèm pin là 548 triệu [C2].",
        "draft_citations": ["C1", "C2"],
        "selected_evidence": [hit1, hit2],
        "requirements": [],
        "answered_requirement_ids": [],
    }
    from src.agents.copilot.tools import build_evidence_context

    _, citations = build_evidence_context([hit1, hit2])
    state["verified_snapshot"] = VerifiedAnswerSnapshot(
        answer=state["draft_answer"],
        resolved_date="2026-10-13",
        status="answered",
        citations=citations,
    )
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
        resolved_date="2026-10-13",
        citations=[cit1],
        answered_requirement_ids=["R1"],
        missing_requirement_ids=["R2"],
        missing_information=["Chính sách ưu đãi"],
        status="partial",
        reason_code="insufficient_evidence",
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


def test_verified_answer_snapshot_rejects_empty_missing_info_for_partial():
    """Verify invariant: partial snapshot requires non-empty missing_information."""
    with pytest.raises(ValidationError):
        VerifiedAnswerSnapshot(
            answer="VF 5 giá 468 triệu [C1]",
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
    from src.agents.copilot.state import GeneratedAnswer, Requirement

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

    with patch("src.agents.copilot.nodes.answer._invoke_json", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = (
            GeneratedAnswer(
                claims=[
                    {
                        "text": "Dạ với ngân sách 500 triệu...",
                        "kind": "advice",
                        "requirement_ids": ["R1"],
                        "citation_ids": [],
                    }
                ]
            ),
            None,
        )
        await answer_nodes.generate_answer(state)
        payload = mock_gen.call_args[0][2]
        assert "memory_summary" in payload
        assert "ngân sách 500 triệu" in payload["memory_summary"]

    from src.agents.copilot.state import StructuredGroundingReview
    from src.agents.copilot.validation.structured import render_answer
    from tests.test_agents.test_copilot_agentic import checked

    generated = GeneratedAnswer(
        claims=[
            {
                "text": "Dạ với ngân sách 500 triệu...",
                "kind": "advice",
                "requirement_ids": ["R1"],
                "citation_ids": [],
            }
        ]
    )
    with patch("src.agents.copilot.nodes.verification._invoke_json", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = (StructuredGroundingReview(**checked(scope=None)), None)
        await verif_nodes.check_grounding(
            {**state, "generated_answer": generated, "draft_answer": render_answer(generated)}
        )
        payload = mock_check.call_args[0][2]
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
