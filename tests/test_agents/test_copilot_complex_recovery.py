"""Complex goals, complementary bundles and recovery without redundant retrieval."""

from datetime import date
from types import SimpleNamespace

import pytest

from src.agents.copilot.context import context_fits, format_selected_context
from src.agents.copilot.graph import copilot_agent
from src.agents.copilot.model_io import _request_schema
from src.agents.copilot.nodes import evidence
from src.agents.copilot.nodes._shared import schedule_corrective
from src.agents.copilot.state import GeneratedAnswer, IntakeDecision, Requirement, SearchPlan, StructuredGroundingReview
from src.agents.copilot.tools import _make_hit
from src.agents.copilot.validation.structured import (
    bind_citation_dependencies,
    summarize_grounding_review,
    validate_grounding_review,
)
from src.config import get_settings
from src.knowledge.index_readiness import load_snapshot
from src.knowledge.source_context import source_context_chunks
from tests.test_agents.test_copilot_agentic import checked, generated, intake, offline, scripted  # noqa: F401
from tests.test_agents.test_copilot_jev import hit, mock_provider, response, state
from tests.test_agents.test_copilot_jev_bundles import chunk


@pytest.fixture(autouse=True)
def configure(monkeypatch):
    monkeypatch.setattr(get_settings(), "copilot_evidence_selection_strategy", "jev_context")
    monkeypatch.setattr(get_settings(), "openrouter_api_key", "fake-key")


def test_three_cars_nine_goals_and_derived_dependency_contract():
    requirements = [
        {"requirement_id": f"R{i + 1}", "description": f"{model}: {metric}", "product_model": model, "metric": metric}
        for i, (model, metric) in enumerate(
            (m, metric) for m in ("VF 3", "VF 5", "VF 6") for metric in ("price", "seats", "range")
        )
    ]
    decision = IntakeDecision(
        guard_decision={"decision": "allow", "reason": "none"},
        route="complex",
        requirements=[
            *requirements,
            {
                "requirement_id": "R10",
                "description": "Chênh lệch giá VF 3 và VF 5",
                "operation": "calculate",
                "depends_on": ["R1", "R4"],
            },
        ],
    )
    assert len(decision.requirements) == 10
    assert decision.requirements[-1].depends_on == ["R1", "R4"]
    for dependency in ("R10", "R99"):
        broken = decision.model_dump()
        broken["requirements"][-1]["depends_on"] = [dependency]
        with pytest.raises(ValueError, match="dependenc"):
            IntakeDecision.model_validate(broken)


def test_native_schema_limits_match_remaining_request_budget():
    for available in (1, 2, 3, 5):
        assert (
            _request_schema(SearchPlan, {"max_queries": available})["properties"]["searches"]["maxItems"] == available
        )
    assert _request_schema(IntakeDecision, {"max_requirements": 18})["properties"]["requirements"]["maxItems"] == 18


def test_fallback_planning_keeps_all_goals_inside_remaining_budget():
    from src.agents.copilot.nodes import planning

    requirements = [
        Requirement(requirement_id=f"R{i + 1}", description=f"{model}: {metric}", product_model=model, metric=metric)
        for i, (model, metric) in enumerate(
            (m, metric) for m in ("VF 3", "VF 5", "VF 6") for metric in ("price", "seats", "range")
        )
    ]
    snapshot = SimpleNamespace(
        catalog=lambda: {
            "product_model": ["VF 3", "VF 5", "VF 6"],
            "document_type": [],
            "policy_type": [],
        }
    )
    current = {
        "requirements": requirements,
        "query": "VF 3 VF 5 VF 6",
        "snapshot": snapshot,
        "analysis": SimpleNamespace(product_models=["VF 3", "VF 5", "VF 6"]),
    }
    plan = planning._fallback_plan(current)
    assert len(plan.searches) == 3
    assert {rid for search in plan.searches for rid in search.requirement_ids} == {
        r.requirement_id for r in requirements
    }
    corrective = planning._fallback_plan(
        {**current, "tool_calls": 3, "retrieval_rounds": 1, "recovery_requirement_ids": ["R5", "R6", "R8"]}
    )
    assert len(corrective.searches) == 2
    assert {rid for search in corrective.searches for rid in search.requirement_ids} == {"R5", "R6", "R8"}


def test_derived_answer_cannot_pass_with_missing_input():
    current = {
        "requirements": [
            Requirement(requirement_id="R1", description="Giá xe"),
            Requirement(requirement_id="R2", description="Chênh lệch", operation="calculate", depends_on=["R1"]),
        ],
        "generated_answer": GeneratedAnswer(
            claims=[
                {
                    "text": "Chênh lệch 100 triệu",
                    "requirement_ids": ["R2"],
                    "citation_ids": ["C1"],
                }
            ]
        ),
    }
    review = StructuredGroundingReview(
        claim_verdicts=[{"claim_index": 0, "status": "supported"}],
        requirement_verdicts=[
            {"requirement_id": "R1", "status": "missing"},
            {"requirement_id": "R2", "status": "answered", "supporting_claim_indices": [0]},
        ],
        suggestions_safe=True,
    )
    with pytest.raises(ValueError, match="unverified inputs"):
        validate_grounding_review(review, current)


def test_unreliable_checker_links_downgrade_coverage_and_dependent_goals():
    current = {
        "requirements": [
            Requirement(requirement_id="R1", description="Giá đầu vào"),
            Requirement(requirement_id="R2", description="Chênh lệch", operation="calculate", depends_on=["R1"]),
        ],
        "generated_answer": GeneratedAnswer(
            claims=[
                {
                    "text": "Chênh lệch 100 triệu",
                    "requirement_ids": ["R2"],
                    "citation_ids": ["C1"],
                }
            ]
        ),
    }
    review = StructuredGroundingReview(
        claim_verdicts=[{"claim_index": 0, "status": "supported"}],
        requirement_verdicts=[
            {"requirement_id": rid, "status": "answered", "supporting_claim_indices": [0]} for rid in ("R1", "R2")
        ],
        suggestions_safe=True,
    )
    verdict = summarize_grounding_review(review, current)
    assert verdict.answered_requirement_ids == []
    assert set(verdict.missing_requirement_ids) == {"R1", "R2"}
    assert verdict.recovery == "regenerate"
    assert not verdict.grounded


def test_policy_claim_cites_scope_and_exceptions_with_its_anchor():
    answer = GeneratedAnswer(
        claims=[
            {
                "text": "VF 5 thuộc các dòng xe khác, được 10 lần sạc",
                "requirement_ids": ["R1"],
                "citation_ids": ["C1"],
            }
        ]
    )
    current = {
        "selected_evidence": [
            hit("benefit", citation_id="C1"),
            hit("audience", citation_id="C2"),
            hit("condition", citation_id="C3"),
        ],
        "evidence_selection_diagnostics": [
            {"chunk_id": "benefit", "reason": "selected", "bundle_chunk_ids": ["benefit", "audience"]},
            {"chunk_id": "audience", "reason": "selected", "bundle_chunk_ids": ["audience", "condition"]},
        ],
    }
    bind_citation_dependencies(answer, current)
    assert answer.claims[0].citation_ids == ["C1", "C2", "C3"]
    assert "VF 5 thuộc các dòng xe khác" in answer.claims[0].text


@pytest.mark.asyncio
async def test_weak_partial_support_never_hides_true_range(monkeypatch):
    # One cheap seat passage contributes .63 to range; the explicit range must
    # remain valuable after that passage has been selected.
    import json

    anchors = [hit("seats"), hit("duplicate-seat"), hit("range")]
    monkeypatch.setattr(
        evidence,
        "_profile",
        lambda _: SimpleNamespace(
            candidate_pool=3,
            evidence_blocks=2,
            context_characters=6000,
            context_tokens=4000,
        ),
    )

    def provider(request):
        cid = json.loads(request.content)["state"]["source_bundle"][0]["chunk_id"]
        if cid == "range":
            return response(request, supports_R1=0.1, answers_R1=0.1, supports_R2=0.98, answers_R2=0.98)
        return response(request, supports_R1=0.96, answers_R1=0.96, supports_R2=0.63, answers_R2=0.1)

    mock_provider(monkeypatch, provider)
    result = await evidence.select_evidence(state(anchors))
    assert "range" in {h["chunk_id"] for h in result["selected_evidence"]}
    assert len(result["selected_evidence"]) == 2


def test_swaps_replace_early_bundle_with_better_joint_coverage():
    # Cheap A initially wins on benefit/cost. B+C together cover two goals much
    # better; selection must be able to evict A rather than keep it pinned.
    a = hit("a", citation_id="C1", content="x")
    b = hit("b", citation_id="C2", content="x" * 2000)
    c = hit("c", citation_id="C3", content="y" * 2000)
    bundles = [(a, [a]), (b, [b]), (c, [c])]
    decisions = {
        "a": {"route": "include", "support": {"R1": 0.8, "R2": 0.8}, "scores": {"contains_answer_evidence": 0.9}},
        "b": {
            "route": "include",
            "support": {"R1": 0.99},
            "direct_support": {"R1": 0.99},
            "scores": {"contains_answer_evidence": 0.9},
        },
        "c": {
            "route": "include",
            "support": {"R2": 0.99},
            "direct_support": {"R2": 0.99},
            "scores": {"contains_answer_evidence": 0.9},
        },
    }
    selected, _, _, _ = evidence._choose_bundles(
        bundles,
        decisions,
        set(),
        SimpleNamespace(evidence_blocks=2, context_characters=6000),
        set(),
        {},
        True,
    )
    assert {h["chunk_id"] for h in selected} == {"b", "c"}


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [3, 6, 9, 18])
async def test_many_distinct_goals_keep_all_explicit_facts(monkeypatch, count):
    import json

    anchors = [hit(f"goal-{i}", content=f"Requested fact {i}: {100 + i}") for i in range(1, count + 1)]

    def provider(request):
        body = json.loads(request.content)
        index = body["state"]["source_bundle"][0]["chunk_id"].split("-")[1]
        scores = {key: 0.1 for key in body["questions"] if key.startswith(("supports_", "answers_"))}
        scores.update({f"supports_R{index}": 0.98, f"answers_R{index}": 0.98})
        return response(request, **scores)

    mock_provider(monkeypatch, provider)
    current = {
        **state(anchors),
        "profile_name": "complex",
        "requirements": [Requirement(requirement_id=f"R{i}", description=f"Fact {i}") for i in range(1, count + 1)],
    }
    result = await evidence.select_evidence(current)
    assert {h["chunk_id"] for h in result["selected_evidence"]} == {h["chunk_id"] for h in anchors}
    assert (await evidence.build_context({**current, **result}))["route"] == "generate_answer"


@pytest.mark.asyncio
async def test_actual_vf3_vf5_six_facts_fit_together_with_required_conditions(monkeypatch):
    import json

    snapshot = load_snapshot()
    facts = [
        "PRICE_LIST_VINFAST_20260921_5",
        "PRICE_LIST_VINFAST_20260921_6",
        "PRODUCT_VF3_20260922_7",
        "PRODUCT_VF3_20260922_9",
        "SPECS_VF5_PLUS_2026_0",
        "SPECS_VF5_PLUS_2026_1",
    ]
    anchors = [_make_hit(snapshot.chunks[cid], 1, i + 1, "dense") for i, cid in enumerate(facts)]

    def provider(request):
        body = json.loads(request.content)
        ids = {h["chunk_id"] for h in body["state"]["source_bundle"]}
        scores = {key: 0.1 for key in body["questions"] if key.startswith(("supports_", "answers_"))}
        for i, cid in enumerate(facts, 1):
            if cid in ids:
                scores.update({f"supports_R{i}": 0.98, f"answers_R{i}": 0.98})
        return response(request, **scores)

    mock_provider(monkeypatch, provider)
    current = {
        **state(anchors),
        "profile_name": "complex",
        "snapshot": snapshot,
        "requirements": [
            Requirement(requirement_id=f"R{i}", description=f"Fact {cid}") for i, cid in enumerate(facts, 1)
        ],
    }
    result = await evidence.select_evidence(current)
    ids = {h["chunk_id"] for h in result["selected_evidence"]}
    assert set(facts) <= ids
    assert {"PRICE_LIST_VINFAST_20260921_2", "PRICE_LIST_VINFAST_20260921_21"} <= ids
    assert "PRICE_LIST_VINFAST_20260921_22" in ids
    built = await evidence.build_context({**current, **result})
    assert "215" in built["answer_context"] and "326,4" in built["answer_context"]


def test_token_budget_is_enforced_without_truncating_sources():
    source = hit("a", citation_id="C1", content="Thông số kỹ thuật " * 100)
    text = format_selected_context([source])
    profile = SimpleNamespace(evidence_blocks=10, context_characters=len(text) + 1, context_tokens=100)
    assert not context_fits([source], [], profile)


@pytest.mark.asyncio
async def test_three_partial_sources_can_jointly_support_one_goal(monkeypatch):
    mock_provider(monkeypatch, lambda request: response(request, supports_R1=0.9, answers_R1=0.1))
    current = state([hit("input-a"), hit("input-b"), hit("input-c")])
    result = await evidence.select_evidence(current)
    assert {h["chunk_id"] for h in result["selected_evidence"]} == {"input-a", "input-b", "input-c"}


@pytest.mark.asyncio
async def test_repack_uses_cached_bundle_even_when_search_budget_exhausted(monkeypatch):
    mock_provider(monkeypatch, response)
    current = state([hit("range")])
    current.update(await evidence.select_evidence(current))
    current.update(
        selected_evidence=[],
        generation_count=1,
        tool_calls=get_settings().copilot_max_search_calls,
        recovery_requirement_ids=["R1"],
        evidence_selection_diagnostics=[
            {
                "reason": "context_budget",
                "jev": {"support": {"R1": 0.99}},
            }
        ],
    )
    correction = schedule_corrective(current)
    assert correction["route"] == "select_evidence" and correction["repack_pending"]
    current.update(correction)
    result = await evidence.select_evidence(current)
    assert result["route"] == "build_context" and result["selected_evidence"]
    assert current["tool_calls"] == get_settings().copilot_max_search_calls
    assert schedule_corrective({**current, **result}) is None


@pytest.mark.asyncio
async def test_no_progress_repack_searches_once_instead_of_regenerating(monkeypatch):
    mock_provider(monkeypatch, response)
    current = state([hit("same")])
    current.update(await evidence.select_evidence(current))
    current.update(repack_pending=True, corrective_retrieval_count=1, generation_count=1)
    result = await evidence.select_evidence(current)
    assert result["route"] == "plan_queries"
    assert not result["repack_pending"]


@pytest.mark.asyncio
async def test_corrective_pool_retains_old_price_alongside_many_new_hits(monkeypatch):
    import json

    old = hit("official-price", citation_id="C1", content="MSRP including battery and VAT: 496 million")
    monkeypatch.setattr(
        evidence,
        "_profile",
        lambda _: SimpleNamespace(
            candidate_pool=4,
            evidence_blocks=4,
            context_characters=6000,
            context_tokens=4000,
        ),
    )

    def provider(request):
        cid = json.loads(request.content)["state"]["source_bundle"][0]["chunk_id"]
        return response(
            request,
            supports_R1=0.98 if cid == "official-price" else 0.1,
            answers_R1=0.98 if cid == "official-price" else 0.1,
            supports_R2=0.98 if cid == "new-0" else 0.1,
            answers_R2=0.98 if cid == "new-0" else 0.1,
        )

    mock_provider(monkeypatch, provider)
    current = {
        **state([hit(f"new-{i}") for i in range(8)]),
        "profile_name": "corrective",
        "recovery_requirement_ids": ["R2"],
        "candidate_evidence": [old],
        "selected_evidence": [old],
        "evidence_registry": [old],
        "verified_snapshot": SimpleNamespace(citations=[SimpleNamespace(citation_id="C1")]),
    }
    result = await evidence.select_evidence(current)
    assert {"official-price", "new-0"} <= {h["chunk_id"] for h in result["selected_evidence"]}
    assert next(h for h in result["selected_evidence"] if h["chunk_id"] == "official-price")["citation_id"] == "C1"


def test_real_price_bundle_preserves_all_unclassified_conditions():
    snapshot = load_snapshot()
    anchor = snapshot.chunks["PRICE_LIST_VINFAST_20260921_5"]
    result = source_context_chunks(anchor, snapshot.chunks.values(), date(2026, 10, 17))
    ids = {c.chunk_id for c in result}
    assert "PRICE_LIST_VINFAST_20260921_21" in ids  # Deposit/date exceptions remain mandatory.
    assert "PRICE_LIST_VINFAST_20260921_2" in ids  # Global audience remains mandatory.
    assert "PRICE_LIST_VINFAST_20260921_22" in ids  # No guessed optionality from table shape.


def test_price_exception_table_is_never_mistaken_for_auxiliary_context():
    anchor = chunk("price", 0, "Prices > Model A", "A | 100", context_prefix="Model | Price")
    exception = chunk("condition", 1, "Prices > Lưu ý", "| Đối tượng áp dụng | Giá |\n| --- | --- |\n| Taxi | 90 |")
    result = source_context_chunks(anchor, [anchor, exception], date(2026, 10, 17))
    assert {c.chunk_id for c in result} == {"price", "condition"}


@pytest.mark.asyncio
@pytest.mark.usefixtures("offline")
async def test_full_graph_repacks_without_planner_or_new_search(monkeypatch):
    from src.agents.copilot.nodes import retrieval
    from tests.test_agents.test_copilot_agentic import hit as graph_hit

    monkeypatch.setattr(get_settings(), "copilot_evidence_selection_strategy", "rrf_context")
    monkeypatch.setattr(
        evidence,
        "_profile",
        lambda current: SimpleNamespace(
            candidate_pool=2,
            evidence_blocks=2 if current.get("profile_name") == "corrective" else 1,
            context_characters=6000,
            context_tokens=4000,
        ),
    )

    async def search(request, current):
        return {
            "dense": [graph_hit(1), graph_hit(2, content="VF 5 có pin 37,23 kWh")],
            "bm25": [],
            "errors": [],
            "requirement_ids": request.requirement_ids,
        }

    monkeypatch.setattr(retrieval, "_search", search)
    decision = intake(
        requirements=[
            {"requirement_id": "R1", "description": "Quãng đường VF 5"},
            {"requirement_id": "R2", "description": "Pin VF 5"},
        ]
    )
    first = checked(answered=["R1"], missing=["R2"], recovery="search")
    second_draft = generated()
    second_draft["claims"].extend(generated("VF 5 có pin 37,23 kWh", "R2", "C2")["claims"])
    second_review = checked()
    second_review["claim_verdicts"].append({
        "claim_index": 1, "status": "supported",
        "evidence_proofs": [{ "citation_id": "C2", "quote": "VF 5"}],
    })
    second_review["requirement_verdicts"].append(
        {
            "requirement_id": "R2",
            "status": "answered",
            "supporting_claim_indices": [1],
            "evidence_status": "sufficient",
            "evidence_citation_ids": ["C2"],
            "evidence_proofs": [{"citation_id": "C2", "quote": "VF 5 có pin 37,23 kWh"}],
        }
    )
    model = scripted(monkeypatch, [decision, generated(), first, second_draft, second_review])
    result = await copilot_agent.ainvoke({"query": "VF 5 đi bao xa và pin bao nhiêu?"})
    assert result["final_response"].status == "answered"
    assert result["retrieval_rounds"] == result["tool_calls"] == 1
    assert result["generation_count"] == 2 and len(model.payloads) == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("second_review_valid", [True, False])
@pytest.mark.usefixtures("offline")
async def test_invalid_checker_contract_rechecks_same_draft_once(monkeypatch, second_review_valid):
    monkeypatch.setattr(get_settings(), "copilot_evidence_selection_strategy", "rrf_context")
    model = scripted(monkeypatch, [intake(), generated(), {"invalid": True}, checked() if second_review_valid else {}])
    result = await copilot_agent.ainvoke({"query": "VF 5 NEDC?"})
    assert result["generation_count"] == 1 and len(model.payloads) == 4
    assert model.payloads[-1]["generated_answer"] == model.payloads[-2]["generated_answer"]
    assert result["final_response"].status == ("answered" if second_review_valid else "abstained")
