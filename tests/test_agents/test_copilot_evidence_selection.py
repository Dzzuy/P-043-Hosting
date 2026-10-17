"""Rank-preserving context selection and checker-directed recovery."""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agents.copilot.nodes import evidence, verification
from src.agents.copilot.runtime import RuntimeBudget
from src.agents.copilot.state import Requirement, SelfCheckVerdict
from src.agents.copilot.tools import build_evidence_context
from src.config import get_settings


def budget_plan(count):
    from src.agents.copilot.state import PlannedSearch, SearchPlan

    return SearchPlan(searches=[PlannedSearch(query=f"VF 5 query {i}", requirement_ids=["R1"]) for i in range(count)])


def planning_state(**extra):
    return {
        "query": "VF 5",
        "analysis": SimpleNamespace(product_models=["VF 5"]),
        "requirements": [Requirement(requirement_id="R1", description="Giá VF 5")],
        "snapshot": SimpleNamespace(catalog=lambda: {"product_model": ["VF 5"], "document_type": [], "policy_type": []}),
        **extra,
    }


def test_three_queries_leave_two_calls_for_corrective(monkeypatch):
    from src.agents.copilot.nodes.planning import available_searches, validate_plan

    settings = get_settings()
    monkeypatch.setattr(settings, "copilot_max_queries_per_plan", 3)
    monkeypatch.setattr(settings, "copilot_max_search_calls", 5)
    initial = planning_state()
    assert available_searches(initial) == 3
    validate_plan(budget_plan(3), initial)
    corrective = planning_state(tool_calls=3, retrieval_rounds=1, recovery_requirement_ids=["R1"])
    assert available_searches(corrective) == 2
    validate_plan(budget_plan(2), corrective)
    with pytest.raises(ValueError, match="remaining budget"):
        validate_plan(budget_plan(3), corrective)
    assert available_searches(planning_state(tool_calls=5)) == 0
    assert available_searches(planning_state(retrieval_rounds=2)) == 0


@pytest.mark.asyncio
async def test_retrieval_executes_three_plus_two_hybrid_calls_and_rejects_more(monkeypatch):
    from src.agents.copilot.nodes import retrieval
    from src.agents.copilot.runtime import CopilotDependencyError

    settings = get_settings()
    monkeypatch.setattr(settings, "copilot_max_queries_per_plan", 3)
    monkeypatch.setattr(settings, "copilot_max_search_calls", 5)
    calls = {"dense": [], "bm25": []}

    def engine(branch):
        def search(**kwargs):
            calls[branch].append(kwargs["query"])
            return []

        return SimpleNamespace(search=search)

    monkeypatch.setattr(retrieval, "get_dense_search_engine", lambda: engine("dense"))
    monkeypatch.setattr(retrieval, "get_bm25_search_engine", lambda: engine("bm25"))
    state = planning_state(resolved_date="2026-10-15", search_plan=budget_plan(3))
    state.update(await retrieval.retrieve_documents(state))
    assert state["tool_calls"] == 3
    assert state["retrieval_rounds"] == 1
    corrective = budget_plan(2)
    for search in corrective.searches:
        search.query = "corrective " + search.query
    state.update(search_plan=corrective, recovery_requirement_ids=["R1"])
    state.update(await retrieval.retrieve_documents(state))
    assert state["tool_calls"] == 5
    assert state["retrieval_rounds"] == 2
    assert len(calls["dense"]) == len(calls["bm25"]) == 5
    with pytest.raises(CopilotDependencyError, match="round limit"):
        await retrieval.retrieve_documents(state)
    assert len(calls["dense"]) == 5
    with pytest.raises(CopilotDependencyError, match="plan no longer valid"):
        await retrieval.retrieve_documents({**state, "retrieval_rounds": 1})
    assert len(calls["dense"]) == 5


@pytest.mark.asyncio
async def test_planner_receives_remaining_limit_and_keeps_snapshot_on_invalid_output(monkeypatch):
    from src.agents.copilot.errors import CopilotModelOutputError
    from src.agents.copilot.nodes import planning
    from src.agents.copilot.state import IntakeDecision

    monkeypatch.setattr(get_settings(), "copilot_max_search_calls", 5)
    state = planning_state(tool_calls=3, retrieval_rounds=1, verified_snapshot=object(), resolved_date="2026-10-15")
    state["analysis"] = IntakeDecision.model_construct(product_models=["VF 5"])
    invoke = AsyncMock(side_effect=CopilotModelOutputError())
    monkeypatch.setattr(planning, "_invoke_json", invoke)
    result = await planning.plan_queries(state)
    assert result["route"] == "finalize_response"
    assert invoke.call_args.args[2]["max_queries"] == 2
    assert invoke.call_args.args[2]["remaining_search_calls"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("length", [500, 501, 12000])
@pytest.mark.parametrize("use_snapshot", [False, True])
async def test_long_grounded_answer_does_not_overflow_talking_points(monkeypatch, length, use_snapshot):
    from src.agents.copilot.nodes.answer import finalize_response

    draft = "a" * (length - 5) + " [C1]"
    verdict = SelfCheckVerdict(grounded=True, answered_requirement_ids=["R1"])
    state = {
        "query": "Giá VF 5", "resolved_date": "2026-10-15",
        "requirements": [Requirement(requirement_id="R1", description="Giá VF 5")],
        "selected_evidence": [hit("price", citation_id="C1")],
        "draft_answer": draft, "self_check": verdict, "generation_count": 1,
    }
    monkeypatch.setattr("src.agents.copilot.insights.build_complementary_insights", lambda *args, **kwargs: [])
    if use_snapshot:
        monkeypatch.setattr(verification, "_invoke_json", AsyncMock(return_value=(verdict, None)))
        state.update(await verification.check_grounding(state))
    final = (await finalize_response(state))["final_response"]
    assert final.answer == draft
    assert final.status == "answered"
    assert final.citations[0].chunk_id == "price"
    assert final.talking_points == ([draft] if length <= 500 else [])


def test_atomic_price_keeps_vat_and_pin_without_creating_capacity():
    from src.agents.copilot.nodes.guard import atomic_requirements
    from src.agents.copilot.state import IntakeDecision

    decision = IntakeDecision.model_construct(requirements=[Requirement(
        requirement_id="R1", description="Giá kèm pin bao gồm VAT và quãng đường NEDC của VF 5 Plus",
    )])
    result = atomic_requirements(decision)
    assert len(result.requirements) == 2
    assert "kèm pin" in result.requirements[0].description
    assert "VAT" in result.requirements[0].description
    assert not any("Dung lượng" in r.description for r in result.requirements)


@pytest.mark.asyncio
async def test_corrective_recovers_rejected_candidates_and_round_references(monkeypatch):
    old = hit("overflow", citation_id="C1", search_requirement_ids=["R1"])
    state = {
        "resolved_date": "2026-10-15", "profile_name": "corrective",
        "retrieval_rounds": 2, "corrective_retrieval_count": 1,
        "recovery_requirement_ids": ["R1"], "rejected_evidence_ids": ["overflow"],
        "evidence_registry": [old], "evidence_query_references": {"overflow": ["1:0"]},
        "raw_search_results": [{"dense": [hit("new"), hit("overflow")], "bm25": [], "requirement_ids": ["R1"]}],
    }
    result = await evidence.select_evidence(state)
    assert [h["chunk_id"] for h in result["selected_evidence"]][:2] == ["new", "overflow"]
    assert result["evidence_query_references"]["overflow"] == ["1:0", "2:0"]


def test_recovery_stops_at_search_round_and_generation_caps():
    from src.agents.copilot.nodes._shared import can_regenerate, schedule_corrective

    for state in [{"tool_calls": 5}, {"retrieval_rounds": 2}, {"corrective_retrieval_count": 1}, {"generation_count": 2}]:
        assert schedule_corrective(state) is None
    assert not can_regenerate({"generation_count": 2})


def hit(cid, **extra):
    return {
        "chunk_id": cid,
        "document_id": "doc",
        "content": "VF 5 | Plus | 496.000.000 VNĐ",
        "title": "Giá xe",
        "section": "MSRP kèm pin gồm VAT",
        "page": None,
        "source_uri": "https://example.com",
        "effective_from": "2026-01-01",
        "effective_to": None,
        "status": "active",
        "version": "1",
        "product_model": "ALL",
        "document_type": "product_specs",
        "policy_type": None,
        "competitor_model": None,
        "native_score": 1.0,
        "rank": 1,
        "retrieval_method": "dense",
        **extra,
    }


@pytest.fixture(autouse=True)
def strategy(monkeypatch):
    monkeypatch.setattr(get_settings(), "copilot_evidence_selection_strategy", "rrf_context")


def search(hits, rid):
    return {"dense": hits, "bm25": [], "requirement_ids": [rid]}


@pytest.mark.asyncio
async def test_frozen_price_comparison_retains_vehicle_prices():
    from eval.evidence_selection.run import replay

    rows = (await replay())["results"]
    comparison = [r for r in rows if r["request_id"] == "d6866e4352924697a7801ac5735a3b63"]
    assert len(comparison) == 2
    assert "PRICE_LIST_VINFAST_20260921_4" not in comparison[0]["selected_chunk_ids"]
    assert "PRICE_LIST_VINFAST_20260921_4" in comparison[1]["selected_chunk_ids"]
    assert "296.000.000" in comparison[1]["answer_context"]
    assert "496.000.000" in comparison[1]["answer_context"]


@pytest.mark.asyncio
async def test_query_fairness_and_duplicate_provenance(monkeypatch):
    monkeypatch.setattr(
        evidence, "_profile", lambda _: SimpleNamespace(candidate_pool=2, evidence_blocks=2, context_characters=6000)
    )
    result = await evidence.select_evidence(
        {
            "resolved_date": "2026-10-15",
            "raw_search_results": [search([hit("a"), hit("shared")], "R1"), search([hit("shared"), hit("b")], "R2")],
        }
    )
    assert [h["chunk_id"] for h in result["selected_evidence"]] == ["a", "shared"]
    assert result["candidate_evidence"][1]["search_requirement_ids"] == ["R1", "R2"]
    assert result["evidence_query_provenance"]["shared"] == [0, 1]
    assert len({h["citation_id"] for h in result["selected_evidence"]}) == 2


@pytest.mark.asyncio
async def test_oversized_first_bundle_continues_and_requests_correction(monkeypatch):
    anchors = [hit("large", context_prefix="header"), hit("small")]
    monkeypatch.setattr(
        evidence,
        "get_bm25_search_engine",
        lambda: SimpleNamespace(read_context=lambda *args: [anchors[0], *[hit(str(i)) for i in range(4)]]),
    )
    state = {"query": "Giá VF 5", "resolved_date": "2026-10-15", "new_hits": anchors}
    result = await evidence.select_evidence(state)
    assert [h["chunk_id"] for h in result["selected_evidence"]] == ["small"]
    assert result["overflow_anchor_ids"] == ["C1"]
    correction = await evidence.build_context({**state, **result})
    assert correction["route"] == "retrieve_documents"
    assert correction["profile_name"] == "corrective"
    larger = await evidence.select_evidence({**state, "profile_name": "corrective"})
    assert len(larger["selected_evidence"]) == 6


@pytest.mark.asyncio
async def test_shared_conditions_are_not_duplicated(monkeypatch):
    anchors = [hit("a", context_prefix="header"), hit("b", context_prefix="header")]
    monkeypatch.setattr(
        evidence,
        "get_bm25_search_engine",
        lambda: SimpleNamespace(
            read_context=lambda cid, date: [next(h for h in anchors if h["chunk_id"] == cid), hit("condition")]
        ),
    )
    result = await evidence.select_evidence({"new_hits": anchors, "resolved_date": "2026-10-15"})
    assert [h["chunk_id"] for h in result["selected_evidence"]] == ["a", "condition", "b"]


@pytest.mark.asyncio
async def test_unrepresented_query_overflow_is_recovered(monkeypatch):
    monkeypatch.setattr(
        evidence, "_profile", lambda _: SimpleNamespace(candidate_pool=4, evidence_blocks=1, context_characters=6000)
    )
    result = await evidence.select_evidence(
        {
            "resolved_date": "2026-10-15",
            "raw_search_results": [search([hit("a")], "R1"), search([hit("b")], "R2")],
        }
    )
    assert result["selected_anchor_ids"] == ["C1"]
    assert result["overflow_anchor_ids"] == ["C2"]


@pytest.mark.asyncio
async def test_character_budget_does_not_truncate_source(monkeypatch):
    monkeypatch.setattr(
        evidence, "_profile", lambda _: SimpleNamespace(candidate_pool=4, evidence_blocks=4, context_characters=600)
    )
    result = await evidence.select_evidence(
        {
            "resolved_date": "2026-10-15",
            "new_hits": [hit("large", content="x" * 1000), hit("small")],
        }
    )
    assert [h["chunk_id"] for h in result["selected_evidence"]] == ["small"]
    assert len(build_evidence_context(result["selected_evidence"])[0]) <= 600
    assert result["evidence_selection_diagnostics"][0]["reason"] == "context_budget"


def test_selection_telemetry_keeps_metrics_without_content():
    from src.observability import safe_metadata

    metadata = safe_metadata(
        {
            "selection_strategy": "rrf_context",
            "selection_reason": "context_budget",
            "candidate_rank": 1,
            "bundle_blocks": 2,
            "bundle_characters": 1000,
            "parent_context_reads": 4,
            "content": "private source",
            "query": "private query",
        }
    )
    assert metadata["selection_strategy"] == "rrf_context"
    assert metadata["parent_context_reads"] == 4
    assert "content" not in metadata and "query" not in metadata


@pytest.mark.asyncio
async def test_unavailable_context_is_not_silently_dropped():
    result = await evidence.select_evidence(
        {
            "new_hits": [hit("a", requires_context=True)],
            "resolved_date": "2026-10-15",
            "runtime": RuntimeBudget(time.monotonic() + 5),
        }
    )
    assert not result["selected_evidence"]
    assert result["evidence_selection_diagnostics"][0]["reason"] == "context_unavailable"


@pytest.mark.asyncio
async def test_new_selector_never_uses_affinity(monkeypatch):
    def forbidden(*args):
        raise AssertionError("affinity must not govern RRF selection")

    monkeypatch.setattr(evidence, "requirement_affinity", forbidden)
    result = await evidence.select_evidence(
        {
            "new_hits": [hit("a")],
            "resolved_date": "2026-10-15",
            "task": "comparison",
            "requirements": [Requirement(requirement_id="R1", description="Giá VF 5")],
            "query": "So sánh giá VF 5 và VF 3",
        }
    )
    assert result["selected_evidence"][0]["chunk_id"] == "a"
    assert result["evidence_map"] == {}


@pytest.mark.asyncio
async def test_parent_timeout_preserves_other_complete_sources(monkeypatch):
    async def timeout(*args):
        raise TimeoutError

    monkeypatch.setattr(evidence, "bounded_io", timeout)
    result = await evidence.select_evidence(
        {
            "new_hits": [hit("needs_parent", requires_context=True), hit("complete")],
            "resolved_date": "2026-10-15",
        }
    )
    assert [h["chunk_id"] for h in result["selected_evidence"]] == ["complete"]
    assert result["evidence_selection_diagnostics"][0]["reason"] == "context_unavailable"
    assert result["overflow_anchor_ids"] == ["C1"]


@pytest.mark.asyncio
async def test_context_reads_are_bounded_cached_and_incomplete_bundles_excluded(monkeypatch):
    calls = []
    anchors = [hit(str(i), context_prefix="header") for i in range(6)]

    def read(cid, date):
        calls.append(cid)
        return [anchors[int(cid)]]

    monkeypatch.setattr(evidence, "get_bm25_search_engine", lambda: SimpleNamespace(read_context=read))
    state = {"new_hits": anchors, "resolved_date": "2026-10-15"}
    result = await evidence.select_evidence(state)
    assert len(calls) == 4
    assert len(result["selected_evidence"]) == 4
    assert all(d["reason"] == "context_unavailable" for d in result["evidence_selection_diagnostics"][4:])
    calls.clear()
    await evidence.select_evidence({**state, **result, "new_hits": anchors[:4]})
    # The first four cached parents are never read again.
    assert not set(calls) & {"0", "1", "2", "3"}


@pytest.mark.asyncio
async def test_date_scope_snapshot_and_verified_source_priority():
    good = hit("good", product_model="VF 5", citation_id="C1")
    result = await evidence.select_evidence(
        {
            "resolved_date": "2026-10-15",
            "analysis": SimpleNamespace(product_models=["VF 5"]),
            "new_hits": [
                hit("expired", status="expired"),
                hit("future", effective_from="2027-01-01"),
                hit("other", product_model="VF 6"),
                hit("new"),
                good,
            ],
            "corrective_retrieval_count": 1,
            "selected_evidence": [good],
            "verified_snapshot": SimpleNamespace(citations=[SimpleNamespace(citation_id="C1")]),
            "evidence_registry": [good],
        }
    )
    assert [h["chunk_id"] for h in result["selected_evidence"]] == ["good", "new"]
    assert result["selected_evidence"][0]["citation_id"] == "C1"
    from src.agents.copilot.runtime import CopilotDependencyError

    with pytest.raises(CopilotDependencyError, match="outside verified snapshot"):
        await evidence.select_evidence(
            {"new_hits": [hit("forged")], "snapshot": SimpleNamespace(chunks={}), "resolved_date": "2026-10-15"}
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("grounded", [True, False])
@pytest.mark.parametrize(
    "recovery,route", [("search", "plan_queries"), ("none", "plan_queries"), ("regenerate", "generate_answer")]
)
async def test_checker_directs_recovery_despite_keyword_coverage(monkeypatch, grounded, recovery, route):
    source = hit("a", citation_id="C1")
    verdict = SelfCheckVerdict(
        grounded=grounded,
        answered_requirement_ids=["R1"],
        missing_requirement_ids=["R2"],
        missing_information=["Thiếu giá VF 3"],
        recovery=recovery,
    )
    monkeypatch.setattr(verification, "_invoke_json", AsyncMock(return_value=(verdict, None)))
    result = await verification.check_grounding(
        {
            "query": "So sánh giá",
            "resolved_date": "2026-10-15",
            "generation_count": 1,
            "requirements": [
                Requirement(requirement_id="R1", description="Giá VF 5"),
                Requirement(requirement_id="R2", description="Giá VF 3"),
            ],
            "selected_evidence": [source],
            "answer_context": build_evidence_context([source])[0],
            "draft_answer": "VF 5: 496 triệu [C1]",
            "evidence_map": {"R1": ["C1"], "R2": ["C1"]},
        }
    )
    assert result["route"] == route
    if route == "plan_queries":
        assert result["recovery_requirement_ids"] == ["R2"]
    if grounded:
        assert result["verified_snapshot"].status == "partial"
