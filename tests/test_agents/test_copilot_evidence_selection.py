"""Rank-preserving context selection and checker-directed recovery."""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agents.copilot.nodes import evidence
from src.agents.copilot.runtime import RuntimeBudget
from src.agents.copilot.state import Requirement
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
        "snapshot": SimpleNamespace(
            catalog=lambda: {"product_model": ["VF 5"], "document_type": [], "policy_type": []}
        ),
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
    assert result["route"] == "retrieve_documents"
    assert result["search_plan"].searches[0].requirement_ids == ["R1"]
    assert "verified_snapshot" not in result  # Fallback plan never replaces a verified answer.
    assert invoke.call_args.args[2]["max_queries"] == 2
    assert invoke.call_args.args[2]["remaining_search_calls"] == 2


@pytest.mark.asyncio
async def test_corrective_recovers_rejected_candidates_and_round_references(monkeypatch):
    old = hit("overflow", citation_id="C1", search_requirement_ids=["R1"])
    state = {
        "resolved_date": "2026-10-15",
        "profile_name": "corrective",
        "retrieval_rounds": 2,
        "corrective_retrieval_count": 1,
        "recovery_requirement_ids": ["R1"],
        "rejected_evidence_ids": ["overflow"],
        "evidence_registry": [old],
        "raw_search_results": [{"dense": [hit("new"), hit("overflow")], "bm25": [], "requirement_ids": ["R1"]}],
    }
    result = await evidence.select_evidence(state)
    assert [h["chunk_id"] for h in result["selected_evidence"]][:2] == ["new", "overflow"]
    assert result["candidate_evidence"][1]["search_requirement_ids"] == ["R1"]


def test_recovery_stops_at_search_round_and_generation_caps():
    from src.agents.copilot.nodes._shared import can_regenerate, schedule_corrective

    for state in [
        {"tool_calls": 5},
        {"retrieval_rounds": 2},
        {"corrective_retrieval_count": 1},
        {"generation_count": 2},
    ]:
        assert schedule_corrective(state) is None
    assert not can_regenerate({"generation_count": 2})


def hit(cid, **extra):
    return {
        "chunk_id": cid,
        "document_id": "doc",
        "content": f"VF 5 | Plus | 496.000.000 VNĐ | {cid}",
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
    assert result["evidence_selection_diagnostics"][1]["query_indices"] == [0, 1]
    assert len({h["citation_id"] for h in result["selected_evidence"]}) == 2


@pytest.mark.asyncio
async def test_oversized_first_bundle_continues_and_requests_correction(monkeypatch):
    anchors = [hit("large", requires_context=True), hit("small")]
    monkeypatch.setattr(
        evidence,
        "get_bm25_search_engine",
        lambda: SimpleNamespace(read_context=lambda *args: [anchors[0], *[hit(str(i)) for i in range(4)]]),
    )
    state = {
        "query": "Giá VF 5",
        "resolved_date": "2026-10-15",
        "raw_search_results": [{"dense": anchors, "bm25": [], "requirement_ids": ["R1"]}],
    }
    result = await evidence.select_evidence(state)
    assert [h["chunk_id"] for h in result["selected_evidence"]] == ["small"]
    correction = await evidence.build_context({**state, **result})
    assert correction["route"] == "generate_answer"
    larger = await evidence.select_evidence({**state, "profile_name": "corrective"})
    assert len(larger["selected_evidence"]) == 6


@pytest.mark.asyncio
async def test_shared_conditions_are_not_duplicated(monkeypatch):
    anchors = [hit("a", requires_context=True), hit("b", requires_context=True)]
    monkeypatch.setattr(
        evidence,
        "get_bm25_search_engine",
        lambda: SimpleNamespace(
            read_context=lambda cid, date: [next(h for h in anchors if h["chunk_id"] == cid), hit("condition")]
        ),
    )
    result = await evidence.select_evidence(
        {
            "raw_search_results": [{"dense": anchors, "bm25": [], "requirement_ids": ["R1"]}],
            "resolved_date": "2026-10-15",
        }
    )
    assert [h["chunk_id"] for h in result["selected_evidence"]] == ["a", "condition", "b"]


@pytest.mark.asyncio
async def test_context_budget_keeps_first_query_and_leaves_recovery_to_checker(monkeypatch):
    monkeypatch.setattr(
        evidence, "_profile", lambda _: SimpleNamespace(candidate_pool=4, evidence_blocks=1, context_characters=6000)
    )
    result = await evidence.select_evidence(
        {
            "resolved_date": "2026-10-15",
            "raw_search_results": [search([hit("a")], "R1"), search([hit("b")], "R2")],
        }
    )

    assert [h["chunk_id"] for h in result["selected_evidence"]] == ["a"]
    assert result["evidence_selection_diagnostics"][1]["reason"] == "context_budget"
    built = await evidence.build_context(result)
    assert built["route"] == "generate_answer"


@pytest.mark.asyncio
async def test_character_budget_does_not_truncate_source(monkeypatch):
    monkeypatch.setattr(
        evidence, "_profile", lambda _: SimpleNamespace(candidate_pool=4, evidence_blocks=4, context_characters=600)
    )
    result = await evidence.select_evidence(
        {
            "resolved_date": "2026-10-15",
            "raw_search_results": [
                {"dense": [hit("large", content="x" * 1000), hit("small")], "bm25": [], "requirement_ids": ["R1"]}
            ],
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
            "raw_search_results": [{"dense": [hit("a", requires_context=True)], "bm25": [], "requirement_ids": ["R1"]}],
            "resolved_date": "2026-10-15",
            "runtime": RuntimeBudget(time.monotonic() + 5),
        }
    )
    assert not result["selected_evidence"]
    assert result["evidence_selection_diagnostics"][0]["reason"] == "context_unavailable"


@pytest.mark.asyncio
async def test_parent_timeout_preserves_other_complete_sources(monkeypatch):
    async def timeout(*args):
        raise TimeoutError

    monkeypatch.setattr(evidence, "bounded_io", timeout)
    result = await evidence.select_evidence(
        {
            "raw_search_results": [
                {
                    "dense": [hit("needs_parent", requires_context=True), hit("complete")],
                    "bm25": [],
                    "requirement_ids": ["R1"],
                }
            ],
            "resolved_date": "2026-10-15",
        }
    )
    assert [h["chunk_id"] for h in result["selected_evidence"]] == ["complete"]
    assert result["evidence_selection_diagnostics"][0]["reason"] == "context_unavailable"


@pytest.mark.asyncio
async def test_context_reads_are_bounded_cached_and_incomplete_bundles_excluded(monkeypatch):
    calls = []
    anchors = [hit(str(i), requires_context=True) for i in range(6)]

    def read(cid, date):
        calls.append(cid)
        return [anchors[int(cid)]]

    monkeypatch.setattr(evidence, "get_bm25_search_engine", lambda: SimpleNamespace(read_context=read))
    state = {
        "raw_search_results": [{"dense": anchors, "bm25": [], "requirement_ids": ["R1"]}],
        "resolved_date": "2026-10-15",
    }
    result = await evidence.select_evidence(state)
    assert len(calls) == 6
    assert len(result["selected_evidence"]) == 4
    assert all(d["reason"] != "context_unavailable" for d in result["evidence_selection_diagnostics"])
    calls.clear()
    await evidence.select_evidence(
        {**state, **result, "raw_search_results": [{"dense": anchors[:4], "bm25": [], "requirement_ids": ["R1"]}]}
    )
    # The first four cached parents are never read again.
    assert not set(calls) & {"0", "1", "2", "3"}


@pytest.mark.asyncio
async def test_date_scope_and_stable_citations_without_pinning_sources():
    good = hit("good", product_model="VF 5", citation_id="C1")
    result = await evidence.select_evidence(
        {
            "resolved_date": "2026-10-15",
            "analysis": SimpleNamespace(product_models=["VF 5"]),
            "raw_search_results": [
                {
                    "dense": [
                        hit("expired", status="expired"),
                        hit("future", effective_from="2027-01-01"),
                        hit("other", product_model="VF 6"),
                        hit("new"),
                        good,
                    ],
                    "bm25": [],
                    "requirement_ids": ["R1"],
                }
            ],
            "corrective_retrieval_count": 1,
            "selected_evidence": [good],
            "verified_snapshot": SimpleNamespace(citations=[SimpleNamespace(citation_id="C1")]),
            "evidence_registry": [good],
        }
    )
    assert [h["chunk_id"] for h in result["selected_evidence"]] == ["new", "good"]
    assert next(h for h in result["selected_evidence"] if h["chunk_id"] == "good")["citation_id"] == "C1"
    from src.agents.copilot.runtime import CopilotDependencyError

    with pytest.raises(CopilotDependencyError, match="outside verified snapshot"):
        await evidence.select_evidence(
            {
                "raw_search_results": [{"dense": [hit("forged")], "bm25": [], "requirement_ids": ["R1"]}],
                "snapshot": SimpleNamespace(chunks={}),
                "resolved_date": "2026-10-15",
            }
        )
