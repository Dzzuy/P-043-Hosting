"""Regression coverage for the bounded nine-node production graph."""

import json
import time
from types import SimpleNamespace

import pytest

from src.agents.copilot import model_io, nodes
from src.agents.copilot.graph import NODE_NAMES, copilot_agent
from src.agents.copilot.nodes import evidence, planning, retrieval
from src.agents.copilot.nodes._shared import can_regenerate
from src.agents.copilot.nodes.guard import atomic_requirements, resolve_date
from src.agents.copilot.runtime import CopilotDependencyError, RuntimeBudget
from src.agents.copilot.state import GeneratedAnswer, GroundingVerdict, Requirement, SelfCheckVerdict
from src.agents.copilot.tools import build_evidence_context
from src.config import get_settings


def hit(index=1, model="VF 5", content="VF 5 có quãng đường 326 km NEDC."):
    return {
        "chunk_id": f"c-{index}",
        "document_id": f"doc-{model}",
        "content": content,
        "title": model,
        "section": None,
        "page": None,
        "source_uri": "https://example.com/specs",
        "effective_from": "2026-01-01",
        "effective_to": None,
        "status": "active",
        "version": "1",
        "product_model": model,
        "document_type": "product_specs",
        "policy_type": None,
        "competitor_model": None,
        "retrieval_method": "dense",
        "native_score": 0.9,
        "rank": index,
    }


REQ = {"requirement_id": "R1", "description": "Quãng đường VF 5 theo NEDC"}
REQ2 = {"requirement_id": "R2", "description": "Quãng đường VF 6 theo NEDC"}


def intake(route="simple", requirements=None):
    return {
        "guard_decision": {"decision": "allow", "reason": "none"},
        "task": "knowledge",
        "route": route,
        "requirements": requirements or [REQ],
        "product_models": ["VF 5"],
        "simple_search": {"query": "VF 5 NEDC", "product_model": "VF 5", "document_type": "product_specs"}
        if route == "simple"
        else None,
    }


def generated(text="VF 5 có quãng đường 326 km NEDC", rid="R1", cid="C1"):
    return {"claims": [{"text": text, "requirement_ids": [rid], "citation_ids": [cid]}]}


def checked(status="supported", recovery="none", answered=None):
    return {
        "claim_verdicts": [
            {"claim_index": 0, "status": status, "error_codes": [] if status == "supported" else ["unsupported_claim"]}
        ],
        "answered_requirement_ids": (["R1"] if status == "supported" else []) if answered is None else answered,
        "missing_requirement_ids": [] if status == "supported" else ["R1"],
        "recovery": recovery,
        "suggestions_safe": True,
    }


class ScriptedModel:
    def __init__(self, outputs):
        self.outputs, self.payloads = iter(outputs), []

    async def ainvoke(self, messages):
        self.payloads.append(json.loads(messages[-1].content))
        item = next(self.outputs)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(
            content=json.dumps(item, ensure_ascii=False), usage_metadata={"input_tokens": 10, "output_tokens": 5}
        )


def scripted(monkeypatch, outputs):
    model = ScriptedModel(outputs)
    monkeypatch.setattr(model_io, "get_llm", lambda **kwargs: model)
    return model


@pytest.fixture
def offline(monkeypatch):
    async def snapshot(state):
        return None

    async def search(request, state):
        return {"dense": [hit()], "bm25": [], "errors": [], "requirement_ids": request.requirement_ids}

    monkeypatch.setattr(retrieval, "_ensure_snapshot", snapshot)
    monkeypatch.setattr(retrieval, "_search", search)
    monkeypatch.setattr(
        planning,
        "_catalog",
        lambda state: {
            "product_model": ["VF 5", "VF 6", "ALL"],
            "document_type": ["product_specs", "price_list"],
            "policy_type": [],
        },
    )
    return search


def draft_state():
    source = {**hit(), "citation_id": "C1"}
    context = build_evidence_context([source])[0]
    return {
        "query": "VF 5?",
        "requirements": [Requirement(**REQ)],
        "selected_evidence": [source],
        "evidence_registry": [source],
        "answer_context": context,
        "resolved_date": "2026-10-11",
        "generation_count": 1,
        "runtime": RuntimeBudget(time.monotonic() + 180),
    }


@pytest.mark.asyncio
async def test_simple_graph_has_nine_nodes_and_three_calls(monkeypatch, offline):
    model = scripted(monkeypatch, [intake(), generated(), checked()])
    state = await copilot_agent.ainvoke({"query": "VF 5 NEDC?"})
    assert set(NODE_NAMES) == set(copilot_agent.get_graph().nodes) - {"__start__", "__end__"}
    assert len(NODE_NAMES) == 9 and len(model.payloads) == 3
    assert state["final_response"].status == "answered"
    assert state["final_response"].answer.endswith("[C1]")
    assert state["generation_count"] == 1 and state["corrective_retrieval_count"] == 0
    assert state["runtime"].attempts == 3
    assert "quote_parts" not in json.dumps(model.payloads)


@pytest.mark.asyncio
async def test_complex_graph_adds_only_planner(monkeypatch, offline):
    plan = {"searches": [{"query": "VF 5 NEDC", "product_model": "VF 5", "requirement_ids": ["R1"]}]}
    model = scripted(monkeypatch, [intake("complex"), plan, generated(), checked()])
    result = await copilot_agent.ainvoke({"query": "VF 5 NEDC?"})
    assert result["final_response"].status == "answered" and len(model.payloads) == 4


@pytest.mark.asyncio
async def test_missing_customer_preferences_cannot_hide_known_factual_comparison(monkeypatch, offline):
    decision = intake("clarify")
    decision.update(
        task="comparison", product_models=["VF 5", "VF 6"], clarification_question="Khách có chỗ sạc không?"
    )
    plan = {"searches": [{"query": "VF 5 NEDC", "product_model": "VF 5", "requirement_ids": ["R1"]}]}
    model = scripted(monkeypatch, [decision, plan, generated(), checked()])
    result = await copilot_agent.ainvoke({"query": "So sánh VF 5 và VF 6 về NEDC, khách đi làm?"})
    assert result["final_response"].status == "answered" and len(model.payloads) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["clarify", "blocked", "out_of_scope"])
async def test_nonretrieval_routes_never_check_vector_readiness(monkeypatch, route):
    decision = intake("complex")
    decision["route"] = route
    if route == "blocked":
        decision["guard_decision"] = {"decision": "block", "reason": "instruction_override"}
    if route == "clarify":
        decision["clarification_question"] = "Ngân sách của khách là bao nhiêu?"

    async def forbidden(state):
        pytest.fail("readiness must be lazy")

    monkeypatch.setattr(retrieval, "_ensure_snapshot", forbidden)
    model = scripted(monkeypatch, [decision])
    result = await copilot_agent.ainvoke({"query": "Khách đi làm?"})
    assert result["final_response"].status == ("needs_clarification" if route == "clarify" else "abstained")
    assert len(model.payloads) == 1


@pytest.mark.asyncio
async def test_regenerate_once_and_recheck(monkeypatch, offline):
    model = scripted(
        monkeypatch,
        [intake(), generated("VF 5 chạy 999 km"), checked("unsupported", "regenerate"), generated(), checked()],
    )
    result = await copilot_agent.ainvoke({"query": "VF 5 NEDC?"})
    assert result["final_response"].status == "answered"
    assert result["generation_count"] == 2 and len(model.payloads) == 5
    assert "999" not in result["final_response"].answer


@pytest.mark.asyncio
async def test_followup_uses_history_entity_and_catalog(monkeypatch, offline):
    model = scripted(monkeypatch, [intake(), generated(), checked()])
    result = await copilot_agent.ainvoke(
        {
            "query": "Còn quãng đường thì sao?",
            "history": [{"role": "user", "content": "VF 5 Plus có pin bao nhiêu?"}],
        }
    )
    assert result["final_response"].status == "answered"
    assert model.payloads[0]["catalog"]["product_model"] == ["VF 5", "VF 6", "ALL"]


@pytest.mark.asyncio
async def test_intake_rejects_filter_outside_catalog_without_retrieval(monkeypatch, offline):
    decision = intake()
    decision["simple_search"]["policy_type"] = "warranty"
    model = scripted(monkeypatch, [decision])
    with pytest.raises(CopilotDependencyError):
        await copilot_agent.ainvoke({"query": "VF 5 bảo hành pin?"})
    assert len(model.payloads) == 1


@pytest.mark.asyncio
async def test_missing_fact_with_no_recovery_requests_search(monkeypatch):
    state = draft_state()
    state["draft_answer"] = "VF 5 có thể bay [C1]"
    scripted(monkeypatch, [checked("unsupported")])
    result = await nodes.check_grounding(state)
    assert result["route"] == "plan_queries"
    assert result["recovery_requirement_ids"] == ["R1"]


@pytest.mark.asyncio
async def test_corrective_prioritizes_new_hits_over_unhelpful_old_context():
    old = [{**hit(i, content="Không có giá cần tìm"), "citation_id": f"C{i}"} for i in range(1, 9)]
    new = hit(20, content="VF 5 có quãng đường 326 km NEDC.")
    state = {
        **draft_state(),
        "corrective_retrieval_count": 1,
        "profile_name": "corrective",
        "selected_evidence": old,
        "candidate_evidence": old,
        "evidence_registry": old,
        "raw_search_results": [{"dense": [new], "bm25": [], "errors": [], "requirement_ids": ["R1"]}],
    }
    result = await nodes.select_evidence(state)
    assert result["selected_evidence"][0]["chunk_id"] == new["chunk_id"]


@pytest.mark.asyncio
async def test_no_third_generation_after_second_failure(monkeypatch, offline):
    bad = generated("VF 5 chạy 999 km")
    model = scripted(
        monkeypatch, [intake(), bad, checked("unsupported", "regenerate"), bad, checked("unsupported", "regenerate")]
    )
    result = await copilot_agent.ainvoke({"query": "VF 5 NEDC?"})
    assert result["generation_count"] == 2 and result["final_response"].status == "abstained"
    assert len(model.payloads) == 5


@pytest.mark.skip(reason="Deprecated: claim merging across revisions replaced by single-draft self-check and abstain")
@pytest.mark.asyncio
async def test_valid_claim_survives_second_draft_schema_failure(monkeypatch, offline):
    decision = intake(requirements=[REQ, {"requirement_id": "R2", "description": "Dung lượng pin"}])
    verdict = checked(recovery="regenerate")
    verdict["missing_requirement_ids"] = ["R2"]
    model = scripted(monkeypatch, [decision, generated(), verdict, {"answer": "malformed"}])
    result = await copilot_agent.ainvoke({"query": "VF 5 NEDC và pin?"})
    assert result["final_response"].status == "partial"
    assert "326" in result["final_response"].answer
    assert len(model.payloads) == 4 and result["generation_count"] == 2


@pytest.mark.skip(reason="Deprecated: corrective search loop replaced by single retrieval round in simplification plan")
@pytest.mark.asyncio
async def test_corrective_search_only_once_and_rechecks_new_context(monkeypatch, offline):
    decision = {**intake("complex", [REQ, REQ2]), "task": "comparison", "product_models": ["VF 5", "VF 6"]}
    plan = {"searches": [{"query": "VF 5 NEDC", "product_model": "VF 5", "requirement_ids": ["R1"]}]}
    correction = {"searches": [{"query": "VF 6 NEDC", "product_model": "VF 6", "requirement_ids": ["R2"]}]}
    first = {**checked(recovery="search"), "missing_requirement_ids": ["R2"], "feedback": "Thiếu VF 6"}
    second = {"claims": [*generated()["claims"], *generated("VF 6 có quãng đường 485 km NEDC", "R2", "C2")["claims"]]}
    verdict = {
        "claim_verdicts": [{"claim_index": i, "status": "supported"} for i in range(2)],
        "answered_requirement_ids": ["R1", "R2"],
        "suggestions_safe": True,
    }

    async def search(request, state):
        source = (
            hit(2, "VF 6", "VF 6 có quãng đường 485 km NEDC.") if state.get("corrective_retrieval_count") else hit()
        )
        return {"dense": [source], "bm25": [], "errors": [], "requirement_ids": request.requirement_ids}

    monkeypatch.setattr(retrieval, "_search", search)
    model = scripted(monkeypatch, [decision, plan, generated(), first, correction, second, verdict])
    result = await copilot_agent.ainvoke({"query": "So sánh VF 5 và VF 6 NEDC"})
    assert result["corrective_retrieval_count"] == 1 and result["generation_count"] == 2
    assert result["final_response"].status == "answered" and len(model.payloads) == 7
    assert result["retrieval_rounds"] == 2 and result["profile_name"] == "corrective"


@pytest.mark.asyncio
async def test_global_pool_balances_two_queries_and_caps_context():
    a = [hit(i) for i in range(1, 13)]
    b = [hit(i, "VF 6", "VF 6 chạy 485 km.") for i in range(20, 32)]
    result = await nodes.select_evidence(
        {
            "profile_name": "complex",
            "resolved_date": "2026-10-11",
            "raw_search_results": [
                {"dense": a, "bm25": [], "requirement_ids": ["R1"]},
                {"dense": b, "bm25": [], "requirement_ids": ["R2"]},
            ],
        }
    )
    assert len(result["candidate_evidence"]) == 12
    assert len(result["selected_evidence"]) == 6
    assert {h["product_model"] for h in result["selected_evidence"]} == {"VF 5", "VF 6"}
    assert len(build_evidence_context(result["selected_evidence"])[0]) <= 9000


@pytest.mark.asyncio
async def test_mandatory_context_bundle_is_not_truncated(monkeypatch):
    sources = [{**hit(i), "context_prefix": "Header"} for i in range(1, 6)]
    monkeypatch.setattr(evidence, "get_bm25_search_engine", lambda: SimpleNamespace(read_context=lambda *args: sources))
    state = {"resolved_date": "2026-10-11", "new_hits": sources[:1]}
    simple = await nodes.select_evidence(state)
    assert simple["selected_evidence"] == []
    recovery = await nodes.build_context({**state, **simple, "query": "VF 5 NEDC?"})
    assert recovery["route"] == "retrieve_documents" and recovery["read_anchor_ids"] == ["C1"]
    assert recovery["corrective_retrieval_count"] == 1
    corrective = await nodes.select_evidence({**state, "profile_name": "corrective"})
    assert len(corrective["selected_evidence"]) == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy, expected", [
    ("legacy", {"c-2", "c-4"}), ("rrf_context", {"c-1", "c-3"}),
])
async def test_comparison_selection_respects_configured_strategy(monkeypatch, strategy, expected):
    monkeypatch.setattr(get_settings(), "copilot_evidence_selection_strategy", strategy)
    monkeypatch.setattr(
        evidence,
        "_profile",
        lambda state: SimpleNamespace(candidate_pool=12, evidence_blocks=2, context_characters=9000),
    )
    state = {
        "query": "So sánh VF 5 và VF 6 về quãng đường NEDC",
        "task": "comparison",
        "requirements": [Requirement(**REQ), Requirement(**REQ2)],
        "resolved_date": "2026-10-11",
        "raw_search_results": [
            {"dense": [hit(1, content="VF 5 giới thiệu sản phẩm"), hit(2)], "bm25": [], "requirement_ids": ["R1"]},
            {
                "dense": [
                    hit(3, "VF 6", "VF 6 giới thiệu sản phẩm"),
                    hit(4, "VF 6", "VF 6 có quãng đường 485 km NEDC"),
                ],
                "bm25": [],
                "requirement_ids": ["R2"],
            },
        ],
    }
    result = await nodes.select_evidence(state)
    assert {h["chunk_id"] for h in result["selected_evidence"]} == expected


@pytest.mark.asyncio
async def test_forged_citation_cannot_be_approved_by_checker(monkeypatch):
    state = draft_state()
    state.update(draft_answer="VF 5 có quãng đường 326 km NEDC [C999]", generation_count=2)
    scripted(monkeypatch, [checked()])
    checked_state = {**state, **await nodes.check_grounding(state)}
    assert checked_state.get("verified_snapshot") is None
    assert checked_state["route"] == "fallback_response"


@pytest.mark.asyncio
async def test_provider_retry_is_shared_across_nodes(monkeypatch):
    model = scripted(monkeypatch, [ConnectionError("offline"), generated(), ConnectionError("offline")])
    state = draft_state()
    await model_io._invoke_json(state, "system", {}, GeneratedAnswer)
    with pytest.raises(CopilotDependencyError):
        await model_io._invoke_json(state, "system", {}, GeneratedAnswer)
    assert len(model.payloads) == 3 and state["runtime"].provider_retries == 1


@pytest.mark.asyncio
async def test_schema_failure_has_no_hidden_retry(monkeypatch):
    model = scripted(monkeypatch, [{"bad": "schema"}])
    with pytest.raises(CopilotDependencyError):
        await model_io._invoke_json(draft_state(), "system", {}, GeneratedAnswer)
    assert len(model.payloads) == 1


def test_usage_distinguishes_reasoning_from_visible_output_without_inventing_zero():
    response = SimpleNamespace(
        usage_metadata={"input_tokens": 20, "output_tokens": 10, "output_token_details": {"reasoning": 8}},
        response_metadata={"finish_reason": "length"},
    )
    usage = model_io._model_usage(response)
    assert usage["output_tokens"] == 10 and usage["reasoning_tokens"] == 8 and usage["finish_reason"] == "length"
    assert model_io._model_usage(SimpleNamespace())["reasoning_tokens"] is None


def test_native_schema_preserves_reasoning_override_and_requires_supported_endpoint():
    from langchain_openai import ChatOpenAI

    model = ChatOpenAI(
        api_key="test-key", base_url="https://openrouter.ai/api/v1", extra_body={"reasoning": {"effort": "none"}}
    )
    bound = model_io._bind_schema(model, GroundingVerdict, "openrouter")
    assert bound.kwargs["extra_body"] == {"reasoning": {"effort": "none"}, "provider": {"require_parameters": True}}
    wire = bound.kwargs["response_format"]["json_schema"]
    assert wire["strict"] and set(wire["schema"]["required"]) == set(wire["schema"]["properties"])
    assert wire["schema"]["$defs"]["ClaimVerdict"]["properties"]["status"]["enum"] == [
        "supported",
        "unsupported",
        "uncertain",
    ]


@pytest.mark.asyncio
async def test_valid_json_with_length_finish_cannot_bypass_truncation_check(monkeypatch):
    class TruncatedModel:
        async def ainvoke(self, messages):
            return SimpleNamespace(content=json.dumps(generated()), response_metadata={"finish_reason": "length"})

    monkeypatch.setattr(model_io, "get_llm", lambda **kwargs: TruncatedModel())
    state = draft_state()
    with pytest.raises(CopilotDependencyError):
        await model_io._invoke_json(state, "system", {}, GeneratedAnswer)
    assert state["runtime"].attempts == 1


@pytest.mark.asyncio
async def test_changed_context_invalidates_previous_approval():
    state = draft_state()
    state.update(self_check=SelfCheckVerdict(grounded=True))
    result = await nodes.build_context(state)
    assert result["self_check"] is None


@pytest.mark.parametrize(
    "query,supplied,conflict",
    [
        ("Giá ngày 11/10/2026", None, False),
        ("Giá 2026-10-11", "2026-10-12", True),
        ("Giá 11/10/2026 hoặc 12/10/2026", None, True),
        ("Giá 31/02/2026", None, True),
        ("Mua xe, xuất hóa đơn ngày 01/10/2026, sạc thứ Bảy", "2026-10-13", False),
        ("Mua ngày 01/10/2026, tra cứu chính sách ngày 13/10/2026", "2026-10-13", False),
        ("Mua ngày 01/10/2026, tra cứu chính sách ngày 12/10/2026", "2026-10-13", True),
    ],
)
def test_explicit_dates_are_resolved_or_clarified(query, supplied, conflict):
    _, found = resolve_date(query, supplied)
    assert found == conflict


def test_regeneration_requires_remaining_budget():
    assert not can_regenerate({"generation_count": 1, "runtime": RuntimeBudget(time.monotonic() + 50)})
    assert not can_regenerate({"generation_count": 2, "runtime": RuntimeBudget(time.monotonic() + 180)})


def test_range_candidate_cannot_borrow_warranty_mileage_or_charging_price():
    requirement = Requirement(**REQ)
    source = hit(content="NEDC hoặc WLTP. " + "Điều kiện sử dụng thực tế. " * 8 + "Bảo hành 8 năm/160.000 km.")
    assert evidence.requirement_affinity(requirement, source) == 0
    assert evidence.requirement_affinity(requirement, hit()) > 0
    price = Requirement(requirement_id="R2", description="Giá niêm yết VF 5 Plus kèm pin và VAT")
    tariff = {**hit(content="VF 5: giá sạc 3.858 VNĐ/kWh"), "document_type": "policy"}
    assert evidence.requirement_affinity(price, tariff) == 0


def test_comparison_requirement_cannot_conflate_price_range_and_battery():
    from src.agents.copilot.state import IntakeDecision

    decision = IntakeDecision(
        **intake(
            "complex",
            [
                {"requirement_id": "R1", "description": "VF 5 Plus: giá niêm yết và quãng đường NEDC"},
                {"requirement_id": "R2", "description": "VF 6 Eco: giá niêm yết và quãng đường NEDC"},
                {"requirement_id": "R3", "description": "Tư vấn đi làm 40 km/ngày", "kind": "advice"},
            ],
        )
    )
    result = atomic_requirements(decision)
    assert len(result.requirements) == 5
    assert [r.requirement_id for r in result.requirements] == ["R1", "R2", "R3", "R4", "R5"]
    assert "Eco" in result.requirements[2].description
    assert result.requirements[-1].kind == "advice"
    assert evidence.requirement_affinity(result.requirements[1], hit(content="VF 5: 326 km NEDC")) > 0


def test_policy_context_preserves_current_audience_conditions_without_expanding_other_audiences():
    from src.agents.copilot.tools import BM25SearchEngine
    from src.knowledge.schemas import ChunkMetadata, KnowledgeChunk

    engine = object.__new__(BM25SearchEngine)
    engine._chunks = []
    sections = [
        ("scope", "Phạm vi áp dụng", "Áp dụng tại Việt Nam"),
        ("new", "Nội dung chính sách > Đối tượng áp dụng: mua từ 10/02", "Xe mới: 10 lần sạc"),
        ("new", "Nội dung chính sách > Đối tượng áp dụng: mua từ 10/02", "Biển vàng: thứ Bảy chỉ 14–16h"),
        ("new", "Nội dung chính sách > Đối tượng áp dụng: mua từ 10/02", "Điều kiện bắt buộc của nhóm xe mới"),
        ("old", "Nội dung chính sách > Đối tượng áp dụng: mua trước 10/02", "Ưu đãi nhóm xe cũ"),
    ]
    for i, (section, title, text) in enumerate(sections):
        meta = ChunkMetadata(
            chunk_id=f"policy-{i}",
            document_id="policy",
            title="Chính sách",
            document_type="policy",
            product_model="ALL",
            effective_date="2026-01-01",
            source="official",
            chunk_index=i,
            section_id=section,
            section_title=title,
        )
        engine._chunks.append(KnowledgeChunk(chunk_id=meta.chunk_id, document_id="policy", content=text, metadata=meta))
    result = engine.read_context("policy-2", include_header=True)
    assert {h["chunk_id"] for h in result} == {"policy-0", "policy-1", "policy-2", "policy-3"}


@pytest.mark.skip(reason="Deprecated: coverage verification routing to planner replaced by whole-answer self-check")
@pytest.mark.asyncio
async def test_supported_claims_do_not_hide_missing_factual_coverage(monkeypatch):
    state = draft_state()
    state.update(
        requirements=[Requirement(**REQ), Requirement(**REQ2)], generated_answer=GeneratedAnswer(**generated())
    )
    scripted(monkeypatch, [checked()])
    result = await nodes.check_grounding(state)
    assert result["route"] == "plan_queries"
    assert result["recovery_requirement_ids"] == ["R2"]
    assert result["corrective_retrieval_count"] == 1
    assert len(result["verified_claims"]) == 1


@pytest.mark.skip(reason="Deprecated: evidence_map based regeneration replaced by whole-answer self-check")
@pytest.mark.asyncio
async def test_missing_fact_in_context_regenerates_without_new_search(monkeypatch):
    state = draft_state()
    state.update(
        requirements=[Requirement(**REQ), Requirement(**REQ2)],
        generated_answer=GeneratedAnswer(**generated()),
        evidence_map={"R2": ["C2"]},
    )
    scripted(monkeypatch, [checked()])
    result = await nodes.check_grounding(state)
    assert result["route"] == "generate_answer"
    assert "corrective_retrieval_count" not in result


@pytest.mark.asyncio
async def test_missing_external_quote_preserves_partial_without_corpus_search(monkeypatch):
    state = draft_state()
    state.update(
        requirements=[
            Requirement(**REQ),
            Requirement(requirement_id="R2", description="Báo giá đại lý", kind="external"),
        ],
        draft_answer="VF 5 có quãng đường 326 km NEDC [C1]",
    )
    scripted(monkeypatch, [checked(recovery="search")])
    result = await nodes.check_grounding(state)
    assert result["route"] == "finalize_response"
    assert "corrective_retrieval_count" not in result


@pytest.mark.asyncio
async def test_upstream_error_is_not_schema_repair_and_known_transient_retries_once(monkeypatch):
    from src.services.provider_response import ProviderResponseError

    state = draft_state()
    scripted(monkeypatch, [ProviderResponseError({"code": 503}), generated()])
    await model_io._invoke_json(state, "system", {}, GeneratedAnswer)
    assert state["runtime"].attempts == 2 and state["runtime"].provider_retries == 1
    assert state["runtime"].events[0]["failure_kind"] == "provider"
    assert state["runtime"].events[0].get("input_tokens") is None


@pytest.mark.asyncio
async def test_finish_error_without_transient_code_does_not_retry_or_report_zero_usage(monkeypatch):
    class ErrorModel:
        async def ainvoke(self, messages):
            return SimpleNamespace(
                content="",
                usage_metadata={"input_tokens": 0, "output_tokens": 0},
                response_metadata={"finish_reason": "error"},
            )

    monkeypatch.setattr(model_io, "get_llm", lambda **kwargs: ErrorModel())
    state = draft_state()
    with pytest.raises(CopilotDependencyError):
        await model_io._invoke_json(state, "system", {}, GeneratedAnswer)
    assert state["runtime"].attempts == 1 and state["runtime"].provider_retries == 0
    assert state["runtime"].events[0]["input_tokens"] is None
    assert state["runtime"].events[0]["failure_kind"] == "provider"


def test_current_lookup_does_not_choose_latest_version():
    sources = [hit(), {**hit(2), "version": "future-label"}]
    registry, _ = nodes._merge_evidence({"resolved_date": "2026-10-11"}, sources)
    assert len(registry) == 2
    assert not nodes._valid_evidence_date({**hit(), "status": "expired"}, {"target_date": "2026-07-01"})


@pytest.mark.asyncio
async def test_scope_filter_prevents_other_vehicle_from_spending_candidate_pool():
    state = {
        "resolved_date": "2026-10-11",
        "analysis": SimpleNamespace(product_models=["VF 5"]),
        "new_hits": [hit(1, "VF 8"), hit(2), hit(3, "ALL")],
    }
    result = await nodes.select_evidence(state)
    assert {h["chunk_id"] for h in result["candidate_evidence"]} == {"c-2", "c-3"}
