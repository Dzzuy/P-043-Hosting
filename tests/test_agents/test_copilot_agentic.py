"""Regression coverage for the bounded nine-node production graph."""

import json
import time
from types import SimpleNamespace

import pytest

from src.agents.copilot import model_io, nodes
from src.agents.copilot.graph import NODE_NAMES, copilot_agent
from src.agents.copilot.nodes import evidence, planning, retrieval
from src.agents.copilot.nodes._shared import can_regenerate
from src.agents.copilot.nodes.guard import resolve_date
from src.agents.copilot.runtime import CopilotDependencyError, RuntimeBudget
from src.agents.copilot.state import GeneratedAnswer, Requirement, StructuredGroundingReview
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


def checked(status="supported", recovery="none", answered=None, missing=(), scope="VF 5"):
    answered = (["R1"] if status == "supported" else []) if answered is None else answered
    missing = list(missing) or ([] if status == "supported" else ["R1"])
    return {
        "claim_verdicts": [
            {"claim_index": 0, "status": status, "error_codes": [] if status == "supported" else ["unsupported_claim"],
             "evidence_proofs": [{"citation_id": "C1", "quote": scope}] if scope else []}
        ],
        "requirement_verdicts": [
            {"requirement_id": rid, "status": "answered", "supporting_claim_indices": [0],
             "evidence_status": "sufficient" if scope else "unknown",
             "evidence_citation_ids": ["C1"] if scope else [],
             "evidence_proofs": [{"citation_id": "C1", "quote": scope}] if scope else []} for rid in answered
        ]
        + [{"requirement_id": rid, "status": "missing"} for rid in missing],
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


@pytest.fixture(autouse=True)
def disable_live_jev(monkeypatch):
    monkeypatch.setattr(get_settings(), "openrouter_api_key", "")


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
        "generated_answer": GeneratedAnswer(**generated()),
        "draft_answer": "VF 5 có quãng đường 326 km NEDC [C1]",
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
    state["generated_answer"] = GeneratedAnswer(**generated("VF 5 có thể bay"))
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
    assert len(result["candidate_evidence"]) == 18
    assert len(result["selected_evidence"]) <= 20
    assert {h["product_model"] for h in result["selected_evidence"]} == {"VF 5", "VF 6"}
    assert len(build_evidence_context(result["selected_evidence"])[0]) <= 16000


@pytest.mark.asyncio
async def test_mandatory_context_bundle_is_not_truncated(monkeypatch):
    sources = [{**hit(i), "requires_context": True} for i in range(1, 6)]
    monkeypatch.setattr(evidence, "get_bm25_search_engine", lambda: SimpleNamespace(read_context=lambda *args: sources))
    state = {
        "resolved_date": "2026-10-11",
        "raw_search_results": [{"dense": sources[:1], "bm25": [], "requirement_ids": ["R1"]}],
    }
    simple = await nodes.select_evidence(state)
    assert simple["selected_evidence"] == []
    recovery = await nodes.build_context({**state, **simple, "query": "VF 5 NEDC?"})
    assert recovery["route"] == "select_evidence"
    assert recovery["corrective_retrieval_count"] == 1
    corrective = await nodes.select_evidence({**state, "profile_name": "corrective"})
    assert len(corrective["selected_evidence"]) == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "strategy, expected",
    [
        ("rrf_context", {"c-1", "c-3"}),
    ],
)
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
    bound = model_io._bind_schema(model, StructuredGroundingReview, "openrouter")
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
    result = engine.read_context("policy-2")
    assert {h["chunk_id"] for h in result} == {"policy-0", "policy-1", "policy-2", "policy-3"}


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
    scripted(monkeypatch, [checked(recovery="search", missing=["R2"])])
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
    registry = nodes._merge_evidence({"resolved_date": "2026-10-11"}, sources)
    assert len(registry) == 2
    assert not nodes._valid_evidence_date({**hit(), "status": "expired"}, {"target_date": "2026-07-01"})


@pytest.mark.asyncio
async def test_scope_filter_prevents_other_vehicle_from_spending_candidate_pool():
    state = {
        "resolved_date": "2026-10-11",
        "analysis": SimpleNamespace(product_models=["VF 5"]),
        "raw_search_results": [
            {"dense": [hit(1, "VF 8"), hit(2), hit(3, "ALL")], "bm25": [], "requirement_ids": ["R1"]}
        ],
    }
    result = await nodes.select_evidence(state)
    assert {h["chunk_id"] for h in result["candidate_evidence"]} == {"c-2", "c-3"}


def test_requirement_canonicalizes_vf_variant_model_names():
    req = Requirement(requirement_id="R1", description="Giá VF 5 Plus", product_model="VF 5 Plus")
    assert req.product_model == "VF 5"
    req_hyphen = Requirement(requirement_id="R2", description="Thông số VF-7", product_model="vf-7")
    assert req_hyphen.product_model == "VF 7"


def test_intake_and_plan_handle_input_grounded_non_catalog_models(monkeypatch):
    from src.agents.copilot.nodes.guard import _validate_intake
    from src.agents.copilot.nodes.planning import validate_plan
    from src.agents.copilot.state import IntakeDecision, PlannedSearch, SearchPlan, SearchRequest

    catalog = {
        "product_model": ["ALL", "VF 3", "VF 5", "VF 6", "VF 7", "VF 8", "VF 9"],
        "document_type": ["product_specs", "price_list", "policy", "faq", "battlecard"],
        "policy_type": ["pricing", "warranty", "charging"],
    }
    monkeypatch.setattr(planning, "_catalog", lambda state: catalog)
    state = {"query": "So sánh giá Minio Green, EC Van và VF 5 Plus giúp mình", "customer_context": "", "history": []}
    decision = IntakeDecision(
        guard_decision={"decision": "allow", "reason": "none"},
        task="comparison",
        route="complex",
        requirements=[
            Requirement(requirement_id="R1", description="Giá bán", product_model="Minio Green"),
            Requirement(requirement_id="R2", description="Giá bán EC Van", product_model="EC Van"),
            Requirement(requirement_id="R3", description="Giá bán VF 5 Plus", product_model="VF 5 Plus"),
        ],
        product_models=["Minio Green", "EC Van", "VF 5 Plus"],
        simple_search=None,
    )
    _validate_intake(decision, state, [])
    assert decision.product_models == ["VF 5"]
    assert decision.requirements[0].product_model is None
    assert "Minio Green" in decision.requirements[0].description
    assert decision.requirements[1].product_model is None
    assert decision.requirements[2].product_model == "VF 5"

    plan = SearchPlan(
        searches=[
            PlannedSearch(
                query="giá xe thương mại",
                product_model="Minio Green",
                document_type="price_list",
                requirement_ids=["R1", "R2"],
            ),
            PlannedSearch(
                query="giá VF 5",
                product_model="VF 5",
                document_type="price_list",
                requirement_ids=["R3"],
            ),
        ]
    )
    validate_plan(plan, {**state, "analysis": decision, "requirements": decision.requirements})
    assert plan.searches[0].product_model is None
    assert "Minio Green" in plan.searches[0].query
    assert plan.searches[1].product_model == "VF 5"

    with pytest.raises(ValueError, match="requirement model outside intake scope"):
        _validate_intake(
            IntakeDecision(
                guard_decision={"decision": "allow", "reason": "none"},
                task="knowledge",
                route="simple",
                requirements=[Requirement(requirement_id="R1", description="Giá Ford Ranger", product_model="Ford Ranger")],
                product_models=["Ford Ranger"],
                simple_search=SearchRequest(query="Giá Ford Ranger", product_model="Ford Ranger"),
            ),
            state,
            [],
        )

