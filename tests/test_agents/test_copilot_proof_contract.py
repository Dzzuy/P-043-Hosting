"""Proof provenance and safe exact dedup; semantic judgments stay model-owned."""

from types import SimpleNamespace

import pytest

from src.agents.copilot.nodes.evidence import _choose_bundles
from src.agents.copilot.state import EvidenceProof, StructuredGroundingReview
from src.agents.copilot.validation.structured import (
    bind_citation_dependencies,
    render_answer,
    summarize_grounding_review,
    validate_generated_answer,
    validate_grounding_review,
)
from tests.test_agents.test_copilot_agentic import checked, draft_state
from tests.test_agents.test_copilot_evidence_selection import hit


def test_declared_inline_markers_render_once_without_changing_links():
    state = draft_state()
    answer = state["generated_answer"]
    text = answer.claims[0].text
    answer.claims[0].text += " [C1]"
    bind_citation_dependencies(answer, state)
    validate_generated_answer(answer, state)
    assert answer.claims[0].text == text
    assert answer.claims[0].citation_ids == ["C1"]
    assert render_answer(answer).count("[C1]") == 1


def test_undeclared_inline_marker_cannot_be_hidden_by_normalization():
    state = draft_state()
    answer = state["generated_answer"]
    answer.claims[0].text += " [C999]"
    bind_citation_dependencies(answer, state)
    with pytest.raises(ValueError, match="citation markers"):
        validate_generated_answer(answer, state)


def test_marker_only_block_is_rejected():
    state = draft_state()
    answer = state["generated_answer"]
    answer.claims[0].text = "[C1]"
    with pytest.raises(ValueError, match="no text"):
        bind_citation_dependencies(answer, state)


def test_supported_fact_without_checker_proof_is_not_published():
    state = draft_state()
    review = StructuredGroundingReview(**checked())
    review.claim_verdicts[0].evidence_proofs = []
    result = summarize_grounding_review(review, state)
    assert not result.grounded and result.missing_requirement_ids == ["R1"]
    assert review.claim_verdicts[0].status == "supported"


@pytest.mark.parametrize("error", ["unsupported_scope", "wrong_unit", "wrong_number", "policy_condition"])
def test_semantic_failure_cannot_establish_coverage(error):
    state = draft_state()
    value = checked()
    value["claim_verdicts"][0].update(status="unsupported", error_codes=[error])
    review = StructuredGroundingReview(**value)
    result = summarize_grounding_review(review, state)
    assert not result.grounded and not result.answered_requirement_ids


@pytest.mark.parametrize("quote", [
    "Mọi thành viên nhóm doanh nghiệp được hỗ trợ 14 ngày.",
    "| Thời gian (giờ) | 2,5 |", "Orion: năm chỗ.",
    "Tầm hoạt động mỗi lần sạc: 300 km.",
])
def test_proof_binding_does_not_use_entity_or_unit_whitelists(quote):
    state = draft_state()
    state["query"] = "Orion thuộc nhóm doanh nghiệp; tra cứu thông tin phù hợp."
    state["selected_evidence"][0]["content"] = quote
    review = StructuredGroundingReview(**checked())
    review.claim_verdicts[0].evidence_proofs = [EvidenceProof(citation_id="C1", quote=quote)]
    assert summarize_grounding_review(review, state).grounded


def test_cannot_repair_source_unit_inside_a_quote():
    state = draft_state()
    state["selected_evidence"][0]["content"] = "Nguồn ghi: 59,6 kW."
    review = StructuredGroundingReview(**checked())
    review.claim_verdicts[0].evidence_proofs = [EvidenceProof(citation_id="C1", quote="Nguồn ghi: 59,6 kWh.")]
    with pytest.raises(ValueError, match="evidence quote"):
        validate_grounding_review(review, state)


def test_proof_cannot_be_borrowed_from_another_claims_citation():
    state = draft_state()
    state["selected_evidence"].append(dict(state["selected_evidence"][0], citation_id="C2"))
    review = StructuredGroundingReview(**checked())
    review.claim_verdicts[0].evidence_proofs[0].citation_id = "C2"
    with pytest.raises(ValueError, match="outside claim citations"):
        validate_grounding_review(review, state)


def test_sufficient_evidence_without_inventory_is_verification_gap_not_source_gap():
    state = draft_state()
    review = StructuredGroundingReview(**checked())
    diagnostic = review.requirement_verdicts[0]
    diagnostic.evidence_proofs = []
    diagnostic.evidence_status = "sufficient"
    diagnostic.evidence_citation_ids = ["C1"]
    result = summarize_grounding_review(review, state)
    assert result.requirement_diagnostics[0].blocker == "verification_uncertain"
    assert result.requirement_diagnostics[0].evidence_status == "unknown"
    diagnostic.evidence_proofs = [EvidenceProof(citation_id="C1", quote="VF 5")]
    assert summarize_grounding_review(review, state).answered_requirement_ids == ["R1"]


def choose(anchors, assessments=None, bundles=None):
    return _choose_bundles(
        bundles or [(h, [h]) for h in anchors], assessments or {}, set(),
        SimpleNamespace(evidence_blocks=4, context_characters=10000), set(), {}, bool(assessments),
    )


def duplicates(**changes):
    first = hit("first", citation_id="C1", content="Same exact facts", search_requirement_ids=["R1"])
    second = dict(first, chunk_id="second", citation_id="C2", search_requirement_ids=["R2"], **changes)
    return first, second


def test_duplicate_contents_share_budget_but_keep_trace_provenance():
    first, second = duplicates()
    selected, _, diagnostics, rejected = choose([first, second])
    assert len(selected) == 1
    assert selected[0]["search_requirement_ids"] == ["R1", "R2"]
    assert diagnostics[1]["canonical_chunk_id"] == "first"
    assert diagnostics[1]["original_bundle_chunk_ids"] == ["second"]
    assert diagnostics[1]["bundle_chunk_ids"] == ["first"]
    assert not rejected


@pytest.mark.parametrize("changes", [
    {"version": "2"}, {"document_id": "other"}, {"section": "Other variant"},
    {"effective_to": "2026-12-31"}, {"context_prefix": "Only fleet customers"},
    {"product_model": "VF 9"}, {"source_uri": "https://other.example"},
    {"content": "Same  exact facts"},
])
def test_similar_content_with_different_source_scope_or_validity_stays_separate(changes):
    assert len(choose(duplicates(**changes))[0]) == 2


def test_conflict_role_and_dependency_bundles_never_alias():
    first, second = duplicates()
    assessments = {"first": {"route": "include"}, "second": {"route": "conflict"}}
    selected, conflicts, _, _ = choose([first, second], assessments)
    assert len(selected) == 2 and conflicts == {"second"}
    dependency = hit("condition", citation_id="C3")
    selected, _, _, _ = choose([first, second], bundles=[(first, [first, dependency]), (second, [second])])
    assert {h["chunk_id"] for h in selected} == {"first", "second", "condition"}
